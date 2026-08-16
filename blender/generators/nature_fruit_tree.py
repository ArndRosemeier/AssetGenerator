"""Stylized fruit / blossom tree: broadleaf crown with coloured blossom or fruit clusters.

Orchard and village landmarks — same round crown as broadleaf, plus accent blobs.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Vector

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

BARK, FOLIAGE, ACCENT = "bark", "foliage", "accent"

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "crown_start",
    "lobe_count",
    "lobe_radius",
    "crown_spread",
    "accent_count",
    "accent_radius",
    "seed",
)

_SQUASH = 0.72
_MAX_LOBES = 8


@dataclass(frozen=True)
class FruitTreeParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    crown_start: float
    lobe_count: int
    lobe_radius: float
    crown_spread: float
    accent_count: int
    accent_radius: float
    seed: int


def material_slots(params: FruitTreeParams) -> tuple[str, ...]:
    if params.accent_count > 0:
        return (BARK, FOLIAGE, ACCENT)
    return (BARK, FOLIAGE)


def parse_params(raw: Mapping[str, object]) -> FruitTreeParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = FruitTreeParams(
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
        crown_start=positive_float(require_key(raw, "crown_start", path), f"{path}.crown_start"),
        lobe_count=positive_int(require_key(raw, "lobe_count", path), f"{path}.lobe_count"),
        lobe_radius=positive_float(require_key(raw, "lobe_radius", path), f"{path}.lobe_radius"),
        crown_spread=positive_float(require_key(raw, "crown_spread", path), f"{path}.crown_spread"),
        accent_count=as_int(require_key(raw, "accent_count", path), f"{path}.accent_count"),
        accent_radius=positive_float(
            require_key(raw, "accent_radius", path), f"{path}.accent_radius"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_radius_top >= params.trunk_radius_base:
        raise SpecError(
            f"params.trunk_radius_top ({params.trunk_radius_top}) must be smaller than "
            f"trunk_radius_base ({params.trunk_radius_base})."
        )
    if not 0.35 <= params.crown_start <= 0.9:
        raise SpecError(
            f"params.crown_start ({params.crown_start}) must be between 0.35 and 0.9."
        )
    if params.lobe_count > _MAX_LOBES:
        raise SpecError(f"params.lobe_count must be <= {_MAX_LOBES}.")
    if params.accent_count < 0:
        raise SpecError(f"params.accent_count must be >= 0, got {params.accent_count}.")
    if params.height < 3.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 3 m.")
    return params


def _crown_centres(params: FruitTreeParams, rng: random.Random) -> list[Vector]:
    base_z = params.height * params.crown_start
    crown_top = params.height * 0.96
    mid_z = (base_z + crown_top) * 0.5
    centres = [Vector((0.0, 0.0, mid_z + params.lobe_radius * 0.15))]
    for index in range(params.lobe_count - 1):
        angle = math.tau * (index / max(params.lobe_count - 1, 1)) + rng.uniform(-0.25, 0.25)
        reach = params.crown_spread * rng.uniform(0.45, 0.95)
        lift = rng.uniform(base_z, crown_top)
        centres.append(Vector((math.cos(angle) * reach, math.sin(angle) * reach, lift)))
    return centres


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    params = parse_params(spec.params)
    slots = material_slots(params)
    require_materials(spec.materials, slots, spec.generator)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index, foliage_index = 0, 1

    add_trunk_cone(
        bm,
        params.height * params.crown_start,
        params.trunk_radius_base,
        params.trunk_radius_top,
        params.trunk_segments,
        bark_index,
    )

    lobes: list[tuple[Vector, float]] = []
    for centre in _crown_centres(params, rng):
        radius = params.lobe_radius * rng.uniform(0.82, 1.12)
        lobes.append((centre, radius))
        add_tuft(bm, centre, radius, foliage_index, squash=_SQUASH, subdivisions=1)

    if params.accent_count > 0:
        accent_index = 2
        for _ in range(params.accent_count):
            centre, radius = lobes[rng.randrange(len(lobes))]
            direction = Vector(
                (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-0.15, 0.85))
            ).normalized()
            reach = Vector(
                (direction.x * radius, direction.y * radius, direction.z * radius * _SQUASH)
            )
            add_tuft(
                bm,
                centre + reach * 0.92,
                params.accent_radius * rng.uniform(0.75, 1.15),
                accent_index,
                squash=0.95,
                subdivisions=0,
            )

    return finalize_tree(spec.asset_id, bm, slots, spec.materials)
