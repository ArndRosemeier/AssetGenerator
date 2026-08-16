"""Stylized palm: gently curved trunk with flat fan fronds at the crown.

Coastal / oasis silhouette — completely unlike temperate conifers or broadleaf domes.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

from blender.generators.nature_tree_common import (
    add_cylinder,
    assign_material,
    faces_of,
    finalize_tree,
)
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
    "trunk_radius",
    "trunk_segments",
    "trunk_curve",
    "frond_count",
    "frond_length",
    "frond_width",
    "frond_thickness",
    "seed",
)


@dataclass(frozen=True)
class PalmParams:
    height: float
    trunk_radius: float
    trunk_segments: int
    trunk_curve: float
    frond_count: int
    frond_length: float
    frond_width: float
    frond_thickness: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> PalmParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = PalmParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        trunk_radius=positive_float(require_key(raw, "trunk_radius", path), f"{path}.trunk_radius"),
        trunk_segments=positive_int(
            require_key(raw, "trunk_segments", path), f"{path}.trunk_segments"
        ),
        trunk_curve=positive_float(require_key(raw, "trunk_curve", path), f"{path}.trunk_curve"),
        frond_count=positive_int(require_key(raw, "frond_count", path), f"{path}.frond_count"),
        frond_length=positive_float(require_key(raw, "frond_length", path), f"{path}.frond_length"),
        frond_width=positive_float(require_key(raw, "frond_width", path), f"{path}.frond_width"),
        frond_thickness=positive_float(
            require_key(raw, "frond_thickness", path), f"{path}.frond_thickness"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.trunk_segments < 3:
        raise SpecError(f"params.trunk_segments must be >= 3, got {params.trunk_segments}.")
    if params.frond_count < 4:
        raise SpecError(f"params.frond_count must be >= 4, got {params.frond_count}.")
    if params.height < 3.0:
        raise SpecError(f"params.height ({params.height}) is too short; use >= 3 m.")
    return params


def _trunk_points(params: PalmParams) -> list[Vector]:
    points: list[Vector] = []
    for index in range(params.trunk_segments + 1):
        t = index / params.trunk_segments
        z = params.height * t
        curve = math.sin(t * math.pi * 0.85) * params.trunk_curve
        points.append(Vector((curve, curve * 0.35, z)))
    return points


def _add_frond(
    bm: bmesh.types.BMesh,
    crown: Vector,
    angle: float,
    params: PalmParams,
    rng: random.Random,
    foliage_index: int,
) -> None:
    length = params.frond_length * rng.uniform(0.88, 1.08)
    width = params.frond_width * rng.uniform(0.9, 1.05)
    thickness = params.frond_thickness
    direction = Vector((math.cos(angle), math.sin(angle), rng.uniform(0.08, 0.22)))
    direction.normalize()
    mid = crown + direction * (length * 0.48)
    size = Vector((width, thickness, length * 0.92))
    rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(direction).to_matrix().to_4x4()
    matrix = Matrix.Translation(mid) @ rotation @ Matrix.Diagonal((size.x, size.y, size.z, 1.0))
    created = bmesh.ops.create_cube(bm, size=1.0, matrix=matrix)
    assign_material(faces_of(created["verts"]), foliage_index)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index, foliage_index = 0, 1

    points = _trunk_points(params)
    for start, end in zip(points, points[1:], strict=False):
        add_cylinder(bm, start, end, params.trunk_radius, segments=6, material_index=bark_index)

    crown = points[-1]
    for index in range(params.frond_count):
        angle = math.tau * (index / params.frond_count) + rng.uniform(-0.08, 0.08)
        _add_frond(bm, crown, angle, params, rng, foliage_index)

    return finalize_tree(spec.asset_id, bm, MATERIAL_SLOTS, spec.materials)
