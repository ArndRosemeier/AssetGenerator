"""Stylized weeping tree: short trunk with drooping branches and curtain foliage.

Willow-like silhouette — branches sweep downward and foliage hangs below the limb.
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

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "branch_count",
    "branch_length",
    "droop_depth",
    "tuft_radius",
    "tufts_per_branch",
    "seed",
)


@dataclass(frozen=True)
class WillowParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    branch_count: int
    branch_length: float
    droop_depth: float
    tuft_radius: float
    tufts_per_branch: int
    seed: int


def parse_params(raw: Mapping[str, object]) -> WillowParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = WillowParams(
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
        branch_count=positive_int(require_key(raw, "branch_count", path), f"{path}.branch_count"),
        branch_length=positive_float(require_key(raw, "branch_length", path), f"{path}.branch_length"),
        droop_depth=positive_float(require_key(raw, "droop_depth", path), f"{path}.droop_depth"),
        tuft_radius=positive_float(require_key(raw, "tuft_radius", path), f"{path}.tuft_radius"),
        tufts_per_branch=positive_int(
            require_key(raw, "tufts_per_branch", path), f"{path}.tufts_per_branch"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_radius_top >= params.trunk_radius_base:
        raise SpecError(
            f"params.trunk_radius_top ({params.trunk_radius_top}) must be smaller than "
            f"trunk_radius_base ({params.trunk_radius_base})."
        )
    if params.tufts_per_branch < 1 or params.tufts_per_branch > 8:
        raise SpecError(
            f"params.tufts_per_branch ({params.tufts_per_branch}) must be between 1 and 8."
        )
    if params.height < 3.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 3 m.")
    return params


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index, foliage_index = 0, 1

    trunk_height = params.height * 0.55
    add_trunk_cone(
        bm,
        trunk_height,
        params.trunk_radius_base,
        params.trunk_radius_top,
        params.trunk_segments,
        bark_index,
    )

    for index in range(params.branch_count):
        t = index / max(params.branch_count - 1, 1)
        z = trunk_height * (0.55 + 0.4 * t) + rng.uniform(-0.08, 0.08)
        angle = index * 2.399963 + rng.uniform(-0.3, 0.3)
        start = Vector(
            (
                math.cos(angle) * params.trunk_radius_top * 0.9,
                math.sin(angle) * params.trunk_radius_top * 0.9,
                z,
            )
        )
        outward = Vector((math.cos(angle), math.sin(angle), rng.uniform(-0.05, 0.08)))
        outward.normalize()
        end = start + outward * params.branch_length * rng.uniform(0.85, 1.15)
        droop = Vector((0.0, 0.0, -params.droop_depth * rng.uniform(0.85, 1.15)))
        bend = end + droop
        add_cylinder(bm, start, bend, radius=0.035, segments=5, material_index=bark_index)

        for tuft_index in range(params.tufts_per_branch):
            along = (tuft_index + 1) / (params.tufts_per_branch + 1)
            point = start.lerp(bend, along)
            point.z -= params.tuft_radius * 0.35 * along
            add_tuft(
                bm,
                point,
                params.tuft_radius * rng.uniform(0.75, 1.05) * (1.0 - 0.15 * along),
                foliage_index,
                squash=0.9,
            )

    return finalize_tree(spec.asset_id, bm, MATERIAL_SLOTS, spec.materials)
