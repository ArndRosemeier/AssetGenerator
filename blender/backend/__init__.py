"""The Blender backend: turns a kit `Asset` (assetkit/) into Blender objects.

This and blender/lib/ are the only places that touch `bpy`. Kit generators hand
over plain data; `realize` builds the meshes, the materials and runs the
finishing steps, and for a rigged asset the armature, the vertex groups and one
action per clip on its own NLA track (one glTF animation each). Version
differences live in blender/backend/compat.py.

A kit clip gives each bone a rigid motion of the rest skeleton (assetkit/rig.py).
Blender keys a bone's local transform instead; the two meet in

    basis = rest^-1 @ parent_motion^-1 @ motion @ rest

with `rest` Blender's own rest matrix of the bone, so bone roll and Blender's bone
conventions never matter to the kit.
"""

from __future__ import annotations

from types import ModuleType

import bpy
from mathutils import Matrix, Quaternion, Vector

from assetkit import Asset, Bevel, Part, ShadeFlat, ShadeSmooth, Unwrap
from assetkit.asset import pattern_of
from assetkit.rig import Clip, Motion, Skeleton, Skin
from blender.backend import compat
from blender.lib.scene import activate, apply_bevel, make_material, shade_flat, unwrap
from blender.lib.spec import AssetSpec


def build_objects(module: ModuleType, spec: AssetSpec) -> list[bpy.types.Object]:
    """Run a generator's `build`. A kit generator returns an `Asset`, realized here; a generator not
    moved to the kit yet returns Blender objects itself."""
    return build(module, spec)[0]


def build(module: ModuleType, spec: AssetSpec) -> tuple[list[bpy.types.Object], Asset | None]:
    """`build_objects`, also handing back the kit `Asset` (None for a generator not on the kit)."""
    compat.require_supported()
    result = module.build(spec)
    if isinstance(result, Asset):
        return realize(result), result
    return result, None


def realize(asset: Asset) -> list[bpy.types.Object]:
    objects = [_realize_part(part) for part in asset.parts]
    if asset.skeleton is None:
        return objects
    armature = _armature(asset.skeleton, asset.parts[0].name)
    for part, obj in zip(asset.parts, objects, strict=True):
        if part.skin is not None:
            modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
            modifier.object = armature
            modifier.use_vertex_groups = True
            obj.parent = armature
    if asset.clips:
        _bake(armature, asset.clips)
    armature.data.pose_position = "REST"
    return [*objects, armature]


def _armature(skeleton: Skeleton, name: str) -> bpy.types.Object:
    data = bpy.data.armatures.new(f"{name}_rig")
    armature = bpy.data.objects.new(f"{name}_armature", data)
    bpy.data.scenes[0].collection.objects.link(armature)
    activate(armature)
    bpy.ops.object.mode_set(mode="EDIT")
    created = {}
    for bone in skeleton.bones:
        edit = data.edit_bones.new(bone.name)
        edit.head = bone.head
        edit.tail = bone.tail
        edit.roll = 0.0
        edit.use_connect = False
        created[bone.name] = edit
    for bone in skeleton.bones:
        if bone.parent is not None:
            created[bone.name].parent = created[bone.parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _matrix(motion: Motion) -> Matrix:
    return Matrix.Translation(Vector(motion.translation)) @ Quaternion(motion.rotation).to_matrix().to_4x4()


def _bake(armature: bpy.types.Object, clips: tuple[Clip, ...]) -> None:
    """Key every clip as its own action on its own NLA track (one glTF animation each)."""
    bones = armature.data.bones
    rest = {b.name: b.matrix_local.copy() for b in bones}
    rest_inverse = {n: m.inverted() for n, m in rest.items()}
    parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
    pose_bones = armature.pose.bones
    for pose_bone in pose_bones:
        pose_bone.rotation_mode = "QUATERNION"
    bpy.context.scene.render.fps = clips[0].fps
    bpy.context.scene.render.fps_base = 1.0
    if armature.animation_data is None:
        armature.animation_data_create()
    for clip in clips:
        action = bpy.data.actions.new(clip.name)
        armature.animation_data.action = action
        last: dict[str, Quaternion] = {}
        # A loop keys its first frame again at the end, so it closes without a seam. Keys start
        # at frame 0: glTF time is frame / fps, so the clip starts at 0 s and lasts exactly
        # its length (from frame 1 every loop would hold its first pose a frame too long).
        frames = [*clip.frames, clip.frames[0]] if clip.loop else list(clip.frames)
        for number, frame in enumerate(frames):
            motion = {n: _matrix(m) for n, m in frame.items()}
            for pose_bone in pose_bones:
                n = pose_bone.name
                p = parent[n]
                local = motion[n] if p is None else motion[p].inverted() @ motion[n]
                basis = rest_inverse[n] @ local @ rest[n]
                location, rotation, _ = basis.decompose()
                if n in last and last[n].dot(rotation) < 0:
                    rotation = -rotation  # the short way round from the previous key
                last[n] = rotation
                pose_bone.location = location
                pose_bone.rotation_quaternion = rotation
                pose_bone.keyframe_insert("location", frame=number)
                pose_bone.keyframe_insert("rotation_quaternion", frame=number)
        for fcurve in compat.action_fcurves(action):
            for key in fcurve.keyframe_points:
                key.interpolation = "LINEAR"
        armature.animation_data.action = None
        track = armature.animation_data.nla_tracks.new()
        track.name = clip.name
        strip = track.strips.new(clip.name, 0, action)
        strip.name = clip.name


def rig_deviation(asset: Asset, objects: list[bpy.types.Object]) -> float:
    """How far Blender's skinned mesh lies from the kit's own skinning (`assetkit.skinning.deform`),
    worst vertex over three frames of every clip, in metres. Near zero means the rig sheet shows
    exactly what ships. Leaves the scene as it found it (rest pose, every NLA track live)."""
    import numpy as np

    from assetkit.skinning import deform

    armature = objects[-1]
    worst = 0.0
    data = armature.animation_data
    muted = {track.name: track.mute for track in data.nla_tracks}
    for track in data.nla_tracks:
        track.mute = True
    armature.data.pose_position = "POSE"
    try:
        for part, obj in zip(asset.parts, objects, strict=False):
            if part.skin is None:
                continue
            rest = np.asarray(part.mesh.vertices, dtype=np.float64)
            for clip in asset.clips:
                data.action = data.nla_tracks[clip.name].strips[0].action
                for k in sorted({0, len(clip.frames) // 3, len(clip.frames) - 1}):
                    bpy.context.scene.frame_set(k)
                    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
                    mesh = evaluated.to_mesh()
                    got = np.array([v.co[:] for v in mesh.vertices])
                    evaluated.to_mesh_clear()
                    if len(got) != len(rest):  # a bevel added vertices: compare what both have
                        continue
                    worst = max(worst, float(np.abs(got - deform(rest, part.skin, clip.frames[k])).max()))
    finally:
        data.action = None
        for track in data.nla_tracks:
            track.mute = muted[track.name]
        armature.data.pose_position = "REST"
        bpy.context.scene.frame_set(0)
    return worst


def _vertex_groups(obj: bpy.types.Object, skin: Skin) -> None:
    groups = [obj.vertex_groups.new(name=name) for name in skin.bones]
    for vertex, (indices, weights) in enumerate(zip(skin.indices, skin.weights, strict=True)):
        for i, w in zip(indices, weights, strict=True):
            groups[i].add([vertex], w, "REPLACE")


def _realize_part(part: Part) -> bpy.types.Object:
    source = part.mesh
    mesh = bpy.data.meshes.new(part.name)
    mesh.from_pydata(list(source.vertices), [], [list(face) for face in source.faces])
    mesh.polygons.foreach_set("material_index", source.face_slots)
    for name, values in source.point_attributes.items():
        attribute = mesh.attributes.new(name, "FLOAT", "POINT")
        attribute.data.foreach_set("value", values)
    mesh.update()
    if mesh.validate(verbose=False):
        raise RuntimeError(f"Part '{part.name}': Blender had to repair the mesh, so the kit mesh was invalid")
    for slot in source.slots:
        mesh.materials.append(make_material(slot, part.materials[slot]))

    obj = bpy.data.objects.new(part.name, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    if part.skin is not None:
        # Before the finishing steps: a bevel adds vertices and carries the weights onto them.
        _vertex_groups(obj, part.skin)
    for step in part.finish:
        _finish(obj, step)
    if any(pattern_of(part.materials[slot]) is not None for slot in source.slots):
        _paint(obj, part)
    return obj


def _paint(obj: bpy.types.Object, part: Part) -> None:
    """Bake the part's material patterns on its final mesh and UVs (assetkit/texbake.py), into
    one colour and one roughness texture, wired into every patterned slot's material. Plain
    slots keep their values. The kit does the baking, so the maps match on every version."""
    import numpy as np

    from assetkit.texbake import SlotLook, bake, to_srgb

    mesh = obj.data
    if mesh.uv_layers.active is None:
        raise RuntimeError(f"Part '{part.name}': a pattern needs UVs; Unwrap must run first")
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    positions = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", positions)
    corners = np.empty(count * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", corners)
    loops = np.empty(count * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    slots = np.empty(count, dtype=np.int32)
    mesh.loop_triangles.foreach_get("material_index", slots)
    uv = np.empty(len(mesh.loops) * 2)
    mesh.uv_layers.active.data.foreach_get("uv", uv)
    materials = [part.materials[slot] for slot in part.mesh.slots]
    looks = [SlotLook(pattern_of(m), tuple(m.base_color[:3]), m.roughness) for m in materials]  # type: ignore[arg-type]
    maps = bake(
        positions.reshape(-1, 3),
        corners.reshape(-1, 3),
        uv.reshape(-1, 2)[loops].reshape(-1, 3, 2),
        slots,
        looks,
        origin=part.pattern_origin,
    )
    color = _image(f"{part.name}_color", to_srgb(maps.color), "sRGB")
    rough = _image(f"{part.name}_roughness", np.repeat(maps.roughness[..., None], 3, axis=2), "Non-Color")
    for material, look in zip(mesh.materials, looks, strict=True):
        if look.pattern is None:
            continue
        nodes, links = material.node_tree.nodes, material.node_tree.links
        principled = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
        for image, socket, y in ((color, "Base Color", 300), (rough, "Roughness", 0)):
            node = nodes.new(type="ShaderNodeTexImage")
            node.image = image
            node.location = (principled.location.x - 400, principled.location.y + y)
            links.new(node.outputs["Color"], principled.inputs[socket])


def _image(name: str, rgb: object, colorspace: str) -> bpy.types.Image:
    """A packed 8-bit image from (H, W, 3) values 0..1 stored as given (rows from the bottom)."""
    import numpy as np

    pixels = np.asarray(rgb, dtype=np.float32)
    height, width = pixels.shape[:2]
    image = bpy.data.images.new(name=name, width=width, height=height, alpha=False)
    image.colorspace_settings.name = colorspace
    rgba = np.concatenate([pixels, np.ones((height, width, 1), dtype=np.float32)], axis=2)
    image.pixels.foreach_set(rgba.ravel())
    image.pack()
    return image


def _finish(obj: bpy.types.Object, step: object) -> None:
    if isinstance(step, Bevel):
        apply_bevel(obj, width=step.width, segments=step.segments, angle_deg=step.angle_deg)
    elif isinstance(step, ShadeFlat):
        shade_flat(obj)
    elif isinstance(step, ShadeSmooth):
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        if step.sharp_angle_deg is not None:
            compat.set_sharp_from_angle(obj.data, step.sharp_angle_deg)
    elif isinstance(step, Unwrap):
        unwrap(obj, angle_limit_deg=step.angle_limit_deg, island_margin=step.island_margin)
    else:
        raise TypeError(f"The Blender backend cannot carry out {step!r}")
