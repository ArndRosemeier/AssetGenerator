"""Stylized grass / ground-cover tuft.

A cluster of thin vertical blades around the origin. Cheap MultiMesh clutter:
readable from a few metres, not a lawn simulation. Base on Z=0, footprint
centred. Blade count / height / splay vary per spec (dry / lush / sparse).
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
    "seed",
)


@dataclass(frozen=True)
class TuftParams:
    height: float
    blade_count: int
    blade_width: float
    blade_thickness: float
    splay: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> TuftParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = TuftParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        blade_count=positive_int(require_key(raw, "blade_count", path), f"{path}.blade_count"),
        blade_width=positive_float(
            require_key(raw, "blade_width", path), f"{path}.blade_width"
        ),
        blade_thickness=positive_float(
            require_key(raw, "blade_thickness", path), f"{path}.blade_thickness"
        ),
        splay=positive_float(require_key(raw, "splay", path), f"{path}.splay"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.blade_count > 24:
        raise SpecError("params.blade_count must be <= 24 for clutter budgets.")
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

    for i in range(params.blade_count):
        angle = math.tau * (i / params.blade_count) + rng.uniform(-0.25, 0.25)
        radius = rng.uniform(0.02, params.splay)
        lean = rng.uniform(0.05, 0.35) * params.splay
        h = params.height * rng.uniform(0.65, 1.05)
        w = params.blade_width * rng.uniform(0.75, 1.15)
        t = params.blade_thickness

        cx = math.cos(angle) * radius
        cy = math.sin(angle) * radius
        # Tip drifts outward so blades fan.
        tip_x = cx + math.cos(angle) * lean
        tip_y = cy + math.sin(angle) * lean

        # Two crossed quads (card-like) for a readable silhouette without alpha.
        for yaw in (0.0, math.pi * 0.5):
            c, s = math.cos(yaw), math.sin(yaw)
            hx, hy = c * w * 0.5, s * w * 0.5
            verts = [
                bm.verts.new((cx - hx, cy - hy, 0.0)),
                bm.verts.new((cx + hx, cy + hy, 0.0)),
                bm.verts.new((tip_x + hx * 0.35, tip_y + hy * 0.35, h)),
                bm.verts.new((tip_x - hx * 0.35, tip_y - hy * 0.35, h)),
            ]
            bm.verts.ensure_lookup_table()
            face = bm.faces.new(verts)
            face.material_index = mat_index
            # Slight thickness via a second offset card when thickness is large.
            if t > 0.004:
                ox, oy = -s * t, c * t
                verts2 = [
                    bm.verts.new((cx - hx + ox, cy - hy + oy, 0.0)),
                    bm.verts.new((cx + hx + ox, cy + hy + oy, 0.0)),
                    bm.verts.new((tip_x + hx * 0.35 + ox, tip_y + hy * 0.35 + oy, h)),
                    bm.verts.new((tip_x - hx * 0.35 + ox, tip_y - hy * 0.35 + oy, h)),
                ]
                face2 = bm.faces.new(verts2)
                face2.material_index = mat_index

    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    mesh.materials.append(make_material("blades", spec.materials["blades"]))
    lower, upper = world_bounds([obj])
    cx = (lower.x + upper.x) * 0.5
    cy = (lower.y + upper.y) * 0.5
    if abs(cx) > 1e-5 or abs(cy) > 1e-5:
        obj.data.transform(Matrix.Translation(Vector((-cx, -cy, 0.0))))
        obj.data.update()
    shade_flat(obj)
    unwrap(obj)
    return [obj]
