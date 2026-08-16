"""Stylized sedge / reedy grass tuft with stiff triangular blades.

Taller and thicker than `nature.grass_tuft` — marsh edges and meadow fringe where
ordinary grass reads too soft. Crossed cards, flat shading, base on Z=0.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

from blender.lib.scene import make_material, shade_flat, unwrap, world_bounds
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_int,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("blades",)

_PARAM_KEYS = (
    "height",
    "blade_count",
    "blade_width",
    "blade_thickness",
    "splay",
    "drooping",
    "seed",
)


@dataclass(frozen=True)
class SedgeParams:
    height: float
    blade_count: int
    blade_width: float
    blade_thickness: float
    splay: float
    drooping: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> SedgeParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = SedgeParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        blade_count=positive_int(require_key(raw, "blade_count", path), f"{path}.blade_count"),
        blade_width=positive_float(
            require_key(raw, "blade_width", path), f"{path}.blade_width"
        ),
        blade_thickness=positive_float(
            require_key(raw, "blade_thickness", path), f"{path}.blade_thickness"
        ),
        splay=positive_float(require_key(raw, "splay", path), f"{path}.splay"),
        drooping=positive_float(require_key(raw, "drooping", path), f"{path}.drooping"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.blade_count > 12:
        raise SpecError("params.blade_count must be <= 12 for clutter budgets.")
    if params.seed < 0:
        raise SpecError("params.seed must be non-negative.")
    return params


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    mesh = bpy.data.meshes.new(spec.asset_id)
    bm = bmesh.new()
    mat_index = 0

    for index in range(params.blade_count):
        angle = math.tau * (index / params.blade_count) + rng.uniform(-0.2, 0.2)
        radius = rng.uniform(0.01, params.splay * 0.55)
        lean = params.splay * rng.uniform(0.35, 0.85)
        droop = params.drooping * rng.uniform(0.4, 1.0)
        h = params.height * rng.uniform(0.82, 1.08)
        w = params.blade_width * rng.uniform(0.85, 1.15)
        t = params.blade_thickness

        cx = math.cos(angle) * radius
        cy = math.sin(angle) * radius
        mid_x = cx + math.cos(angle) * lean * 0.45
        mid_y = cy + math.sin(angle) * lean * 0.45
        mid_z = h * 0.62
        tip_x = cx + math.cos(angle) * lean
        tip_y = cy + math.sin(angle) * lean
        tip_z = h - droop

        spine = [
            Vector((cx, cy, 0.0)),
            Vector((mid_x, mid_y, mid_z)),
            Vector((tip_x, tip_y, tip_z)),
        ]
        widths = [w, w * 0.92, w * 0.55]

        for yaw in (angle, angle + math.pi * 0.5):
            across = Vector((math.cos(yaw), math.sin(yaw), 0.0))
            rungs: list[list[bmesh.types.BMVert]] = []
            for point, width in zip(spine, widths):
                offset = across * (width * 0.5)
                rungs.append([bm.verts.new(point - offset), bm.verts.new(point + offset)])
            bm.verts.ensure_lookup_table()
            for lower, upper in zip(rungs, rungs[1:]):
                face = bm.faces.new((lower[0], lower[1], upper[1], upper[0]))
                face.material_index = mat_index
            if t > 0.006:
                offset_vec = Vector((-math.sin(yaw), math.cos(yaw), 0.0)) * t
                rungs2: list[list[bmesh.types.BMVert]] = []
                for point, width in zip(spine, widths):
                    off = across * (width * 0.5)
                    rungs2.append(
                        [
                            bm.verts.new(point - off + offset_vec),
                            bm.verts.new(point + off + offset_vec),
                        ]
                    )
                bm.verts.ensure_lookup_table()
                for lower, upper in zip(rungs2, rungs2[1:]):
                    face = bm.faces.new((lower[0], lower[1], upper[1], upper[0]))
                    face.material_index = mat_index

    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    mesh.materials.append(make_material("blades", spec.materials["blades"]))

    lower, upper = world_bounds([obj])
    cx = (lower.x + upper.x) * 0.5
    cy = (lower.y + upper.y) * 0.5
    if abs(cx) > 1e-5 or abs(cy) > 1e-5 or abs(lower.z) > 1e-5:
        obj.data.transform(Matrix.Translation(Vector((-cx, -cy, -lower.z))))
        obj.data.update()

    shade_flat(obj)
    unwrap(obj)
    return [obj]
