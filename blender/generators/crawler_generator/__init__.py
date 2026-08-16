"""Parametric arthropod crawler: body plan + extras + gait clips.

Variation is JSON (`leg_pairs`, stinger / antennae / mandibles, sizes, seed).
The mesh is skinned to a generated armature and ships Idle / Walk / Run.
"""

from __future__ import annotations

import random

import bpy
from mathutils import Matrix, Vector

from blender.generators.crawler_generator.gait import bake_gaits
from blender.generators.crawler_generator.geometry import BoneRest, CrawlerLayout, build_layout
from blender.generators.crawler_generator.materials import apply_crawler_materials
from blender.generators.crawler_generator.params import CrawlerParams, parse_params
from blender.generators.crawler_generator.rig import bind_mesh, build_armature
from blender.lib.scene import world_bounds
from blender.lib.spec import AssetSpec, require_materials

MATERIAL_SLOTS: tuple[str, ...] = ("chitin", "abdomen")


def _shifted_layout(layout: CrawlerLayout, shift: Vector) -> CrawlerLayout:
    bones = tuple(
        BoneRest(bone.name, bone.head + shift, bone.tail + shift, bone.parent)
        for bone in layout.bones
    )
    return CrawlerLayout(
        bones=bones,
        body_center=layout.body_center + shift,
        abdomen_center=layout.abdomen_center + shift,
    )


def _sit_on_ground(mesh_obj: bpy.types.Object, layout: CrawlerLayout) -> CrawlerLayout:
    lower, upper = world_bounds([mesh_obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length <= 1e-8:
        return layout
    mesh_obj.data.transform(Matrix.Translation(shift))
    mesh_obj.data.update()
    return _shifted_layout(layout, shift)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params: CrawlerParams = parse_params(spec.params)
    rng = random.Random(params.seed)

    mesh_obj, layout = build_layout(params, rng)
    mesh_obj.name = spec.asset_id
    layout = _sit_on_ground(mesh_obj, layout)
    apply_crawler_materials(mesh_obj, spec, params)

    armature = build_armature(spec.asset_id, layout)
    bind_mesh(mesh_obj, armature)
    bake_gaits(armature, params)

    mesh_obj.location = (0.0, 0.0, 0.0)
    mesh_obj.rotation_euler = (0.0, 0.0, 0.0)
    mesh_obj.scale = (1.0, 1.0, 1.0)
    armature.location = (0.0, 0.0, 0.0)
    armature.rotation_euler = (0.0, 0.0, 0.0)
    armature.scale = (1.0, 1.0, 1.0)
    return [mesh_obj, armature]
