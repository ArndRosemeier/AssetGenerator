"""Stylized multi-trunk grove tree: several trunks sharing one broad crown.

Mangrove, coppiced elm, or old-growth cluster — breaks the single-trunk convention.
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
    "trunk_count",
    "trunk_radius",
    "trunk_spread",
    "crown_height",
    "lobe_count",
    "lobe_radius",
    "crown_spread",
    "seed",
)

_MAX_TRUNKS = 5
_MAX_LOBES = 8
_SQUASH = 0.74


@dataclass(frozen=True)
class GroveParams:
    height: float
    trunk_count: int
    trunk_radius: float
    trunk_spread: float
    crown_height: float
    lobe_count: int
    lobe_radius: float
    crown_spread: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> GroveParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = GroveParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        trunk_count=positive_int(require_key(raw, "trunk_count", path), f"{path}.trunk_count"),
        trunk_radius=positive_float(require_key(raw, "trunk_radius", path), f"{path}.trunk_radius"),
        trunk_spread=positive_float(require_key(raw, "trunk_spread", path), f"{path}.trunk_spread"),
        crown_height=positive_float(require_key(raw, "crown_height", path), f"{path}.crown_height"),
        lobe_count=positive_int(require_key(raw, "lobe_count", path), f"{path}.lobe_count"),
        lobe_radius=positive_float(require_key(raw, "lobe_radius", path), f"{path}.lobe_radius"),
        crown_spread=positive_float(require_key(raw, "crown_spread", path), f"{path}.crown_spread"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_count > _MAX_TRUNKS:
        raise SpecError(f"params.trunk_count must be <= {_MAX_TRUNKS}.")
    if params.lobe_count > _MAX_LOBES:
        raise SpecError(f"params.lobe_count must be <= {_MAX_LOBES}.")
    if not 0.45 <= params.crown_height <= 0.95:
        raise SpecError(
            f"params.crown_height ({params.crown_height}) must be between 0.45 and 0.95 "
            "(fraction of height where crown sits)."
        )
    if params.height < 3.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 3 m.")
    return params


def _trunk_footprints(params: GroveParams, rng: random.Random) -> list[Vector]:
    if params.trunk_count == 1:
        return [Vector((0.0, 0.0, 0.0))]
    feet: list[Vector] = []
    for index in range(params.trunk_count):
        angle = math.tau * (index / params.trunk_count) + rng.uniform(-0.2, 0.2)
        reach = params.trunk_spread * rng.uniform(0.55, 1.0)
        feet.append(Vector((math.cos(angle) * reach, math.sin(angle) * reach, 0.0)))
    return feet


def _crown_centres(params: GroveParams, rng: random.Random) -> list[Vector]:
    z = params.height * params.crown_height
    top = params.height * 0.97
    mid = (z + top) * 0.5
    centres = [Vector((0.0, 0.0, mid))]
    for index in range(params.lobe_count - 1):
        angle = math.tau * (index / max(params.lobe_count - 1, 1)) + rng.uniform(-0.3, 0.3)
        reach = params.crown_spread * rng.uniform(0.5, 1.0)
        lift = rng.uniform(z, top)
        centres.append(Vector((math.cos(angle) * reach, math.sin(angle) * reach, lift)))
    return centres


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index, foliage_index = 0, 1

    feet = _trunk_footprints(params, rng)
    trunk_top = params.height * params.crown_height * 0.92
    for foot in feet:
        top = foot + Vector((0.0, 0.0, trunk_top + rng.uniform(-0.15, 0.25)))
        add_cylinder(
            bm,
            foot,
            top,
            params.trunk_radius * rng.uniform(0.85, 1.1),
            segments=6,
            material_index=bark_index,
        )

    for centre in _crown_centres(params, rng):
        radius = params.lobe_radius * rng.uniform(0.8, 1.15)
        add_tuft(bm, centre, radius, foliage_index, squash=_SQUASH, subdivisions=1)

    return finalize_tree(spec.asset_id, bm, MATERIAL_SLOTS, spec.materials)
