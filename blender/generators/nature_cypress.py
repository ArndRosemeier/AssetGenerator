"""Stylized columnar cypress: tall narrow trunk with stacked horizontal foliage rings.

Italian cypress / poplar alley silhouette — vertical punctuation, not a pine cone.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy

from blender.generators.nature_tree_common import add_trunk_cone, add_tuft, finalize_tree
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
from mathutils import Vector

MATERIAL_SLOTS: tuple[str, ...] = ("bark", "foliage")

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "ring_count",
    "ring_radius",
    "tuft_radius",
    "tufts_per_ring",
    "seed",
)


@dataclass(frozen=True)
class CypressParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    ring_count: int
    ring_radius: float
    tuft_radius: float
    tufts_per_ring: int
    seed: int


def parse_params(raw: Mapping[str, object]) -> CypressParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = CypressParams(
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
        ring_count=positive_int(require_key(raw, "ring_count", path), f"{path}.ring_count"),
        ring_radius=positive_float(require_key(raw, "ring_radius", path), f"{path}.ring_radius"),
        tuft_radius=positive_float(require_key(raw, "tuft_radius", path), f"{path}.tuft_radius"),
        tufts_per_ring=positive_int(
            require_key(raw, "tufts_per_ring", path), f"{path}.tufts_per_ring"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_radius_top >= params.trunk_radius_base:
        raise SpecError(
            f"params.trunk_radius_top ({params.trunk_radius_top}) must be smaller than "
            f"trunk_radius_base ({params.trunk_radius_base})."
        )
    if params.tufts_per_ring < 3:
        raise SpecError(f"params.tufts_per_ring must be >= 3, got {params.tufts_per_ring}.")
    if params.height < 4.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 4 m.")
    return params


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index, foliage_index = 0, 1

    add_trunk_cone(
        bm,
        params.height,
        params.trunk_radius_base,
        params.trunk_radius_top,
        params.trunk_segments,
        bark_index,
    )

    ring_base = params.height * 0.18
    ring_top = params.height * 0.94
    for ring_index in range(params.ring_count):
        t = ring_index / max(params.ring_count - 1, 1)
        z = ring_base + (ring_top - ring_base) * t
        z += rng.uniform(-0.06, 0.06)
        # Rings taper inward toward the tip.
        reach = params.ring_radius * (1.0 - 0.55 * t) * rng.uniform(0.92, 1.08)
        tuft = params.tuft_radius * (1.0 - 0.35 * t) * rng.uniform(0.88, 1.1)
        for tuft_index in range(params.tufts_per_ring):
            angle = math.tau * (tuft_index / params.tufts_per_ring) + rng.uniform(-0.12, 0.12)
            offset = Vector((math.cos(angle) * reach, math.sin(angle) * reach, z))
            add_tuft(bm, offset, tuft, foliage_index, squash=0.55, subdivisions=1)

    add_tuft(
        bm,
        Vector((0.0, 0.0, params.height * 0.97)),
        params.tuft_radius * 0.65,
        foliage_index,
        squash=0.7,
    )

    return finalize_tree(spec.asset_id, bm, MATERIAL_SLOTS, spec.materials)
