# -*- coding: utf-8 -*-
"""Render last frame of baked bandit Death clip. Does not write GLBs."""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(r"C:\Projekte\AssetGenerator\tools")
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

LIVE = Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans\male_bandit_01.glb")
PREVIEW_PNG = Path(r"C:\Users\windo\agent-previews\bandit_death.png")


def log(msg: str) -> None:
    print(f"[bandit-death-preview] {msg}", flush=True)


def apply_last_keys(arm, act) -> int:
    last_f = None
    for fc in act.fcurves:
        if not fc.keyframe_points:
            continue
        kp = fc.keyframe_points[-1]
        last_f = kp.co[0] if last_f is None else max(last_f, kp.co[0])
        val = kp.co[1]
        dp = fc.data_path
        idx = fc.array_index
        try:
            if dp.endswith("location"):
                bone = dp.split('pose.bones["', 1)[1].split('"]', 1)[0]
                arm.pose.bones[bone].location[idx] = val
            elif dp.endswith("rotation_quaternion"):
                bone = dp.split('pose.bones["', 1)[1].split('"]', 1)[0]
                arm.pose.bones[bone].rotation_mode = "QUATERNION"
                arm.pose.bones[bone].rotation_quaternion[idx] = val
            elif dp.endswith("scale"):
                bone = dp.split('pose.bones["', 1)[1].split('"]', 1)[0]
                arm.pose.bones[bone].scale[idx] = val
        except Exception as exc:
            log(f"skip {dp}[{idx}]: {exc}")
    import bpy
    bpy.context.view_layer.update()
    return int(round(last_f or act.frame_range[1]))


def posed_bbox(meshes):
    import bpy
    from mathutils import Vector
    deps = bpy.context.evaluated_depsgraph_get()
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    hit = False
    for o in meshes:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(deps)
        mesh = ev.to_mesh()
        try:
            for v in mesh.vertices:
                w = ev.matrix_world @ v.co
                mins.x, mins.y, mins.z = min(mins.x, w.x), min(mins.y, w.y), min(mins.z, w.z)
                maxs.x, maxs.y, maxs.z = max(maxs.x, w.x), max(maxs.y, w.y), max(maxs.z, w.z)
                hit = True
        finally:
            ev.to_mesh_clear()
    if not hit:
        return Vector((0, 0, 0.2)), Vector((1.2, 1.2, 0.6))
    return (mins + maxs) * 0.5, (maxs - mins)


def main() -> int:
    import bpy
    import bake_human_idle_walk as B

    B.ensure_scratch()
    B.clear_scene()
    B.import_gltf(LIVE)
    dest = B.find_armature(has_bone="pelvis")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    act = bpy.data.actions.get("Death")
    if act is None:
        raise RuntimeError(f"Death missing; have {[a.name for a in bpy.data.actions]}")
    if dest.animation_data:
        dest.animation_data.action = None
        for t in dest.animation_data.nla_tracks:
            t.mute = True
    B.assign_action(dest, act)
    last = apply_last_keys(dest, act)
    bpy.context.scene.frame_set(last)
    bpy.context.view_layer.update()
    pb = dest.pose.bones["pelvis"]
    z = (dest.matrix_world @ pb.matrix).to_translation().z
    log(f"posed Death last={last} pelvis_z={z:.3f} meshes={[m.name for m in meshes]}")
    if z > 0.35:
        raise RuntimeError(f"preview pose still standing pelvis_z={z:.3f}")

    center, extent = posed_bbox(meshes)
    log(f"posed bbox center={tuple(round(c,3) for c in center)} extent={tuple(round(c,3) for c in extent)}")

    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    mat = bpy.data.materials.new("PreviewGround")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.18, 0.175, 0.165, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=12.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "PreviewGround"
    ground.data.materials.append(mat)

    world = bpy.data.worlds.new("PreviewWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.14, 0.145, 0.155, 1.0)
        bg.inputs[1].default_value = 1.0

    from mathutils import Vector
    span = max(float(extent.x), float(extent.y), float(extent.z), 0.6)
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector((
        center.x + 2.25,
        center.y - 2.85,
        1.85,
    ))
    target = Vector((center.x, center.y + 0.12, 0.18))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    def add_light(name, ltype, loc, energy, size=0.6, rot=None):
        data = bpy.data.lights.new(name, ltype)
        data.energy = energy
        if ltype == "AREA":
            data.size = size
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        if rot:
            obj.rotation_euler = rot
        bpy.context.scene.collection.objects.link(obj)

    add_light("Key", "SUN", (3.0, -2.5, 6.0), 3.4, rot=(math.radians(50), math.radians(15), math.radians(35)))
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0, size=1.6)

    scene = bpy.context.scene
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1000
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    log(f"engine={scene.render.engine} cam={tuple(round(c,3) for c in cam.location)}")

    scratch = B.SCRATCH / "bandit_death.png"
    scene.render.filepath = str(scratch)
    bpy.ops.render.render(write_still=True)
    if not scratch.is_file():
        raise RuntimeError("preview not written")
    PREVIEW_PNG.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(scratch, PREVIEW_PNG)
    log(f"preview {PREVIEW_PNG} ({PREVIEW_PNG.stat().st_size} bytes) pelvis_z={z:.3f}")
    return 0


def launch() -> int:
    import blenderctl
    install = blenderctl.require_blender()
    cmd = [
        str(install.executable),
        "--background", "--factory-startup", "-noaudio",
        "--addons", "io_scene_gltf2",
        "--python-exit-code", "1",
        "--python", str(Path(__file__).resolve()),
    ]
    log("exec " + " ".join(cmd))
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        in_blender = True
    except ImportError:
        in_blender = False
    if not in_blender:
        sys.path.insert(0, str(TOOLS))
        sys.exit(launch())
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
