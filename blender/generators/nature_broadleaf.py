"""Stylized broadleaf tree: tapered trunk with a round crown of foliage lobes.

Readable oak / maple / poplar silhouettes — ball-on-a-stick rather than conical
needle clusters. No visible branch sticks; the crown is a few squashed icospheres.
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

MATERIAL_SLOTS: tuple[str, ...] = ("bark", "foliage")

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "crown_start",
    "lobe_count",
    "lobe_radius",
    "crown_spread",
    "seed",
)

_MAX_LOBES = 8
_SQUASH = 0.72


@dataclass(frozen=True)
class BroadleafParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    crown_start: float
    lobe_count: int
    lobe_radius: float
    crown_spread: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> BroadleafParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = BroadleafParams(
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
    if params.height < 3.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 3 m.")
    return params


def _crown_centres(params: BroadleafParams, rng: random.Random) -> list[Vector]:
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
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
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

    for centre in _crown_centres(params, rng):
        radius = params.lobe_radius * rng.uniform(0.82, 1.12)
        add_tuft(bm, centre, radius, foliage_index, squash=_SQUASH, subdivisions=1)

    return finalize_tree(spec.asset_id, bm, MATERIAL_SLOTS, spec.materials)
