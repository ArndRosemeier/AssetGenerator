"""Stylized birch: slender white trunk with sparse horizontal twigs and light foliage.

Distinct at distance from pine by bark colour and airy, horizontal branching.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Vector

from blender.generators.nature_tree_common import add_cylinder, add_trunk_cone, add_tuft, finalize_tree
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

MATERIAL_SLOTS: tuple[str, ...] = ("bark", "foliage")

BARK, FOLIAGE = "bark", "foliage"

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "canopy_start",
    "branch_count",
    "branch_length",
    "tuft_radius",
    "tuft_count",
    "seed",
)


@dataclass(frozen=True)
class BirchParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    canopy_start: float
    branch_count: int
    branch_length: float
    tuft_radius: float
    tuft_count: int
    seed: int


def material_slots(params: BirchParams) -> tuple[str, ...]:
    if params.tuft_count > 0:
        return (BARK, FOLIAGE)
    return (BARK,)


def parse_params(raw: Mapping[str, object]) -> BirchParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = BirchParams(
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
        canopy_start=positive_float(require_key(raw, "canopy_start", path), f"{path}.canopy_start"),
        branch_count=positive_int(require_key(raw, "branch_count", path), f"{path}.branch_count"),
        branch_length=positive_float(require_key(raw, "branch_length", path), f"{path}.branch_length"),
        tuft_radius=positive_float(require_key(raw, "tuft_radius", path), f"{path}.tuft_radius"),
        tuft_count=as_int(require_key(raw, "tuft_count", path), f"{path}.tuft_count"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_radius_top >= params.trunk_radius_base:
        raise SpecError(
            f"params.trunk_radius_top ({params.trunk_radius_top}) must be smaller than "
            f"trunk_radius_base ({params.trunk_radius_base})."
        )
    if not 0.25 <= params.canopy_start <= 0.85:
        raise SpecError(
            f"params.canopy_start ({params.canopy_start}) must be between 0.25 and 0.85."
        )
    if params.tuft_count < 0:
        raise SpecError(f"params.tuft_count must be >= 0, got {params.tuft_count}.")
    if params.height < 3.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 3 m.")
    return params


def _trunk_radius_at(params: BirchParams, z: float) -> float:
    t = max(0.0, min(1.0, z / params.height))
    return params.trunk_radius_base * (1.0 - t) + params.trunk_radius_top * t


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    params = parse_params(spec.params)
    slots = material_slots(params)
    require_materials(spec.materials, slots, spec.generator)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index = 0
    foliage_index = 1 if params.tuft_count > 0 else None

    add_trunk_cone(
        bm,
        params.height,
        params.trunk_radius_base,
        params.trunk_radius_top,
        params.trunk_segments,
        bark_index,
    )

    canopy_z = params.height * params.canopy_start
    crown_z = params.height * 0.96
    tufts_placed = 0

    for index in range(params.branch_count):
        t = index / max(params.branch_count - 1, 1)
        z = canopy_z + (crown_z - canopy_z) * t + rng.uniform(-0.1, 0.1)
        angle = index * 2.513 + rng.uniform(-0.25, 0.25)
        trunk_r = _trunk_radius_at(params, z)
        start = Vector((math.cos(angle) * trunk_r * 0.85, math.sin(angle) * trunk_r * 0.85, z))
        direction = Vector((math.cos(angle), math.sin(angle), rng.uniform(-0.05, 0.12)))
        direction.normalize()
        end = start + direction * params.branch_length * rng.uniform(0.75, 1.15)
        add_cylinder(bm, start, end, radius=0.022, segments=5, material_index=bark_index)

        if tufts_placed < params.tuft_count and foliage_index is not None:
            add_tuft(
                bm,
                end,
                params.tuft_radius * rng.uniform(0.65, 0.95),
                foliage_index,
                squash=0.75,
                subdivisions=0,
            )
            tufts_placed += 1

    if params.tuft_count > tufts_placed and foliage_index is not None:
        for _ in range(params.tuft_count - tufts_placed):
            z = rng.uniform(canopy_z, crown_z)
            angle = rng.uniform(0.0, math.tau)
            reach = params.branch_length * rng.uniform(0.35, 0.85)
            centre = Vector((math.cos(angle) * reach, math.sin(angle) * reach, z))
            add_tuft(
                bm,
                centre,
                params.tuft_radius * rng.uniform(0.55, 0.85),
                foliage_index,
                squash=0.75,
                subdivisions=0,
            )

    return finalize_tree(spec.asset_id, bm, slots, spec.materials)
