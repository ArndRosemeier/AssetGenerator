"""Stylized dead snag: weathered trunk with broken stubs, no live foliage.

Forest edge / winter atmosphere — gnarled bark only, optional tiny lichen tuft.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Vector

from blender.generators.nature_tree_common import add_cylinder, add_tuft, finalize_tree
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_float,
    as_int,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

BARK, LICHEN = "bark", "lichen"

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "stub_count",
    "branch_length_scale",
    "lean_x",
    "lean_y",
    "lichen_count",
    "lichen_radius",
    "seed",
)


@dataclass(frozen=True)
class SnagParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    stub_count: int
    branch_length_scale: float
    lean_x: float
    lean_y: float
    lichen_count: int
    lichen_radius: float
    seed: int


def material_slots(params: SnagParams) -> tuple[str, ...]:
    if params.lichen_count > 0:
        return (BARK, LICHEN)
    return (BARK,)


def parse_params(raw: Mapping[str, object]) -> SnagParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = SnagParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        trunk_radius_base=positive_float(
            require_key(raw, "trunk_radius_base", path), f"{path}.trunk_radius_base"
        ),
        trunk_radius_top=positive_float(
            require_key(raw, "trunk_radius_top", path), f"{path}.trunk_radius_top"
        ),
        trunk_segments=positive_int(
            require_key(raw, "trunk_segments", path), f"{path}.trunk_segments"
        ),
        stub_count=as_int(require_key(raw, "stub_count", path), f"{path}.stub_count"),
        branch_length_scale=positive_float(
            require_key(raw, "branch_length_scale", path), f"{path}.branch_length_scale"
        ),
        lean_x=as_float(require_key(raw, "lean_x", path), f"{path}.lean_x"),
        lean_y=as_float(require_key(raw, "lean_y", path), f"{path}.lean_y"),
        lichen_count=as_int(require_key(raw, "lichen_count", path), f"{path}.lichen_count"),
        lichen_radius=positive_float(
            require_key(raw, "lichen_radius", path), f"{path}.lichen_radius"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_radius_top >= params.trunk_radius_base:
        raise SpecError(
            f"params.trunk_radius_top ({params.trunk_radius_top}) must be smaller than "
            f"trunk_radius_base ({params.trunk_radius_base})."
        )
    if params.stub_count < 0:
        raise SpecError(f"params.stub_count must be >= 0, got {params.stub_count}.")
    if params.lichen_count < 0:
        raise SpecError(f"params.lichen_count must be >= 0, got {params.lichen_count}.")
    if params.height < 2.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 2 m.")
    return params


def _trunk_radius_at(params: SnagParams, z: float) -> float:
    t = max(0.0, min(1.0, z / params.height))
    return params.trunk_radius_base * (1.0 - t) + params.trunk_radius_top * t


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    params = parse_params(spec.params)
    slots = material_slots(params)
    require_materials(spec.materials, slots, spec.generator)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index = 0

    tip = Vector((params.lean_x * params.height, params.lean_y * params.height, params.height))
    add_cylinder(
        bm,
        Vector((0.0, 0.0, 0.0)),
        tip,
        radius=params.trunk_radius_base * 0.55 + params.trunk_radius_top * 0.45,
        segments=params.trunk_segments,
        material_index=bark_index,
    )

    for index in range(params.stub_count):
        t = (index + 0.5) / max(params.stub_count, 1)
        z = params.height * (0.12 + 0.78 * t) + rng.uniform(-0.2, 0.2)
        z = max(0.4, min(params.height * 0.95, z))
        angle = rng.uniform(0.0, math.tau) + index * 2.1
        trunk_r = _trunk_radius_at(params, z)
        start = Vector(
            (
                params.lean_x * z / params.height + math.cos(angle) * trunk_r * 0.85,
                params.lean_y * z / params.height + math.sin(angle) * trunk_r * 0.85,
                z,
            )
        )
        direction = Vector((math.cos(angle), math.sin(angle), rng.uniform(-0.35, 0.15)))
        direction.normalize()
        length = rng.uniform(0.12, 0.75) * params.branch_length_scale
        end = start + direction * length
        add_cylinder(
            bm,
            start,
            end,
            radius=rng.uniform(0.015, 0.04),
            segments=5,
            material_index=bark_index,
        )

    if params.lichen_count > 0:
        lichen_index = 1
        for _ in range(params.lichen_count):
            z = rng.uniform(params.height * 0.15, params.height * 0.75)
            angle = rng.uniform(0.0, math.tau)
            trunk_r = _trunk_radius_at(params, z)
            centre = Vector(
                (
                    params.lean_x * z / params.height + math.cos(angle) * trunk_r,
                    params.lean_y * z / params.height + math.sin(angle) * trunk_r,
                    z,
                )
            )
            add_tuft(
                bm,
                centre,
                params.lichen_radius * rng.uniform(0.7, 1.1),
                lichen_index,
                squash=0.35,
                subdivisions=0,
            )

    return finalize_tree(spec.asset_id, bm, slots, spec.materials)
