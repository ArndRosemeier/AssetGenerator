"""A sculpted, furred, rigged and animated quadruped: the feral dog.

The body is sculpted as a field of shapes round a skeleton (anatomy.py, sdf.py), meshed with surface
nets and relaxed (sculpt.py); the coat stands off it where a feral dog bristles and is painted in
(coat.py), then baked from the dense sculpt onto a light mesh as a colour and a normal map
(texture.py). The skin weights come from the sculpt's own shapes (skin.py), and every clip the game
needs is keyed from poses with paws planted by IK (pose.py, clips.py).

Materials: `coat` (the baked maps), `eye` and `teeth` (vertex colours: the game draws eyes with a
glow, so they throw the headlamp back).
"""

from __future__ import annotations

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from blender.generators.quadruped_generator.anatomy import Body, feral_dog
from blender.generators.quadruped_generator.clips import bake_clips
from blender.generators.quadruped_generator.coat import Noise, Palette, coat_colours, fur_offsets, hair_coords
from blender.generators.quadruped_generator.params import QuadrupedParams, parse_params
from blender.generators.quadruped_generator.pose import Rig
from blender.generators.quadruped_generator.sculpt import (
    field_of,
    mesh_object,
    points_and_normals,
    push_out,
    relax,
    ribs,
    thin,
)
from blender.generators.quadruped_generator.sdf import surface_nets
from blender.generators.quadruped_generator.skin import armature_for, bind, skin_weights
from blender.generators.quadruped_generator.texture import bake, coat_material, light_material
from blender.lib.scene import activate, unwrap
from blender.lib.spec import AssetSpec, MaterialSpec, require_materials

MATERIAL_SLOTS: tuple[str, ...] = ("coat", "eye", "teeth")
#: Baked maps go into the glb as WebP: a tenth of the PNGs' size.
IMAGE_FORMAT = "WEBP"


def _sculpt(body: Body, params: QuadrupedParams, noise: Noise) -> bpy.types.Object:
    grid = field_of(body, params.voxel)
    ribs(grid, 0.003 * params.lean)
    verts, faces = surface_nets(grid)
    dense = mesh_object("dense", verts, faces)
    relax(dense, 4)
    p, n = points_and_normals(dense)
    push_out(dense, fur_offsets(p, n, noise, params.fur_length))
    relax(dense, 1)
    return dense


def _plain_material(name: str, spec: MaterialSpec) -> bpy.types.Material:
    """Colour from the vertex colours (so the export carries them), roughness from the spec."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    attr = m.node_tree.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    m.node_tree.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = spec.roughness
    bsdf.inputs["Metallic"].default_value = spec.metallic
    return m


def _bits(body: Body) -> tuple[bpy.types.Object, list[tuple[str, str]]]:
    """The eyes and teeth as one mesh, and for each of its vertices: its bone, and which it is ('eye' or 'teeth')."""
    bm = bmesh.new()
    owners: list[tuple[str, str]] = []
    for centre, r in body.eyes:
        made = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=7, radius=r)["verts"]
        for v in made:
            v.co += Vector(centre)
        for f in {f for v in made for f in v.link_faces}:
            f.material_index = 0
        owners += [("head", "eye")] * len(made)
    for root, tip, r, bone in body.teeth:
        d = Vector(tip) - Vector(root)
        made = bmesh.ops.create_cone(
            bm, cap_ends=True, segments=6, radius1=r, radius2=r * 0.15, depth=d.length
        )["verts"]
        rot = Vector((0.0, 0.0, 1.0)).rotation_difference(d.normalized()).to_matrix()
        for v in made:
            v.co = rot @ v.co + (Vector(root) + Vector(tip)) * 0.5
        for f in {f for v in made for f in v.link_faces}:
            f.material_index = 1
        owners += [(bone, "teeth")] * len(made)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    me = bpy.data.meshes.new("bits")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("bits", me)
    bpy.data.scenes[0].collection.objects.link(obj)
    return obj, owners


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    noise = Noise(params.seed)
    body = feral_dog(params.lean)

    dense = _sculpt(body, params, noise)
    p, n = points_and_normals(dense)
    palette = Palette(
        params.coat, params.saddle, params.pale, params.mask, params.nose, params.mange_colour, params.dirt
    )
    coat_material(
        dense,
        coat_colours(p, n, noise, palette, params.mange),
        hair_coords(p, 25.0, 200.0),
        hair_coords(p, 8.0, 60.0),
    )

    light = dense.copy()
    light.data = dense.data.copy()
    light.name = spec.asset_id
    bpy.data.scenes[0].collection.objects.link(light)
    thin(light, params.triangles)
    unwrap(light, 66.0, 0.004)
    colour, normal = bake(dense, light, spec.asset_id, params.texture_resolution, params.bake_samples)
    coat = light_material(light, colour, normal)
    coat.name = "coat"
    coat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = spec.materials[
        "coat"
    ].roughness
    bpy.data.meshes.remove(dense.data)
    for name in ("coat", "hair", "tuft"):
        a = light.data.attributes.get(name)
        if a is not None:
            light.data.attributes.remove(a)

    # Skin weights for the body, before the eyes and teeth join it.
    p, _ = points_and_normals(light)
    names, weights = skin_weights(body, p)
    # Centre the footprint and stand the coat's lowest hair on the ground (millimetres; the skeleton stays put).
    lo, hi = p.min(axis=0), p.max(axis=0)
    light.data.transform(
        Matrix.Translation((-float(lo[0] + hi[0]) / 2, -float(lo[1] + hi[1]) / 2, -float(lo[2])))
    )
    body_count = len(p)

    bits, owners = _bits(body)
    eye = _plain_material("eye", spec.materials["eye"])
    teeth = _plain_material("teeth", spec.materials["teeth"])
    bits.data.materials.append(eye)
    bits.data.materials.append(teeth)
    light.data.materials.append(eye)
    light.data.materials.append(teeth)
    activate(light)
    bits.select_set(True)
    bpy.ops.object.join()

    count = len(light.data.vertices)
    cols = np.ones((count, 4), dtype=np.float32)
    for i, (_, kind) in enumerate(owners):
        cols[body_count + i] = spec.materials[kind].base_color
    attr = light.data.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", cols.ravel())

    weights = np.concatenate([weights, np.zeros((count - body_count, len(names)))], axis=0)
    fixed = {body_count + i: bone for i, (bone, _) in enumerate(owners)}
    armature = armature_for(spec.asset_id, body)
    bind(light, armature, names, weights, fixed)
    activate(armature)
    bake_clips(armature, Rig(armature, body))
    armature.data.pose_position = "REST"
    bpy.context.scene.frame_set(1)
    return [light, armature]
