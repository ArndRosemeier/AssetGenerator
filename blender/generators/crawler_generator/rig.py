"""Armature whose rest bones match the constructed crawler segments."""

from __future__ import annotations

import bpy
from mathutils import Vector

from blender.generators.crawler_generator.geometry import CrawlerLayout
from blender.lib.scene import activate


def build_armature(name: str, layout: CrawlerLayout) -> bpy.types.Armature:
    armature_data = bpy.data.armatures.new(f"{name}_rig")
    armature = bpy.data.objects.new(f"{name}_armature", armature_data)
    bpy.data.scenes[0].collection.objects.link(armature)
    activate(armature)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_data.edit_bones
    created: dict[str, bpy.types.EditBone] = {}
    for rest in layout.bones:
        bone = edit_bones.new(rest.name)
        bone.head = rest.head
        bone.tail = rest.tail
        if (bone.tail - bone.head).length < 1e-4:
            bone.tail = rest.head + Vector((0.0, 0.0, 0.02))
        bone.use_connect = False
        created[rest.name] = bone
    for rest in layout.bones:
        if rest.parent is None:
            continue
        parent = created.get(rest.parent)
        if parent is None:
            raise RuntimeError(f"Crawler bone '{rest.name}' parent '{rest.parent}' is missing")
        created[rest.name].parent = parent
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def bind_mesh(mesh_obj: bpy.types.Object, armature: bpy.types.Object) -> None:
    missing = [
        group.name
        for group in mesh_obj.vertex_groups
        if group.name not in armature.data.bones
    ]
    if missing:
        raise RuntimeError(f"Crawler vertex groups have no bones: {missing}")
    modifier = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature
    modifier.use_vertex_groups = True
    mesh_obj.parent = armature
