"""The Blender backend: turns a kit `Asset` (assetkit/) into Blender objects.

This and blender/lib/ are the only places that touch `bpy`. Kit generators hand
over plain data; `realize` builds the meshes, the materials and runs the
finishing steps. Version differences live in blender/backend/compat.py.
"""

from __future__ import annotations

from types import ModuleType

import bpy

from assetkit import Asset, Bevel, Part, ShadeFlat, ShadeSmooth, Unwrap
from blender.backend import compat
from blender.lib.scene import apply_bevel, make_material, shade_flat, unwrap
from blender.lib.spec import AssetSpec


def build_objects(module: ModuleType, spec: AssetSpec) -> list[bpy.types.Object]:
    """Run a generator's `build`. A kit generator returns an `Asset`, realized here; a generator not
    moved to the kit yet returns Blender objects itself."""
    compat.require_supported()
    result = module.build(spec)
    if isinstance(result, Asset):
        return realize(result)
    return result


def realize(asset: Asset) -> list[bpy.types.Object]:
    return [_realize_part(part) for part in asset.parts]


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
    for step in part.finish:
        _finish(obj, step)
    return obj


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
