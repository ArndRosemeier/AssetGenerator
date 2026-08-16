"""Stylized mushroom cluster for forest-floor clutter.

A tight group of stem + cap mushrooms rooted at Z=0. Caps are squashed icospheres;
optional spot blobs for fly-agaric-style variants. Cheap MultiMesh ground fluff.
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

STEM, CAP, SPOTS = "stem", "cap", "spots"

_PARAM_KEYS = (
    "mushroom_count",
    "cluster_spread",
    "stem_height",
    "stem_radius",
    "cap_radius",
    "cap_squash",
    "spot_count",
    "spot_radius",
    "seed",
)

_MAX_MUSHROOMS = 8


@dataclass(frozen=True)
class MushroomParams:
    mushroom_count: int
    cluster_spread: float
    stem_height: float
    stem_radius: float
    cap_radius: float
    cap_squash: float
    spot_count: int
    spot_radius: float
    seed: int


def material_slots(params: MushroomParams) -> tuple[str, ...]:
    if params.spot_count > 0:
        return (STEM, CAP, SPOTS)
    return (STEM, CAP)


def parse_params(raw: Mapping[str, object]) -> MushroomParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = MushroomParams(
        mushroom_count=positive_int(
            require_key(raw, "mushroom_count", path), f"{path}.mushroom_count"
        ),
        cluster_spread=positive_float(
            require_key(raw, "cluster_spread", path), f"{path}.cluster_spread"
        ),
        stem_height=positive_float(require_key(raw, "stem_height", path), f"{path}.stem_height"),
        stem_radius=positive_float(
            require_key(raw, "stem_radius", path), f"{path}.stem_radius"
        ),
        cap_radius=positive_float(require_key(raw, "cap_radius", path), f"{path}.cap_radius"),
        cap_squash=positive_float(require_key(raw, "cap_squash", path), f"{path}.cap_squash"),
        spot_count=as_int(require_key(raw, "spot_count", path), f"{path}.spot_count"),
        spot_radius=positive_float(require_key(raw, "spot_radius", path), f"{path}.spot_radius"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.mushroom_count > _MAX_MUSHROOMS:
        raise SpecError(f"params.mushroom_count must be <= {_MAX_MUSHROOMS}.")
    if params.spot_count < 0:
        raise SpecError(f"params.spot_count must be >= 0, got {params.spot_count}.")
    if not 0.25 <= params.cap_squash <= 1.0:
        raise SpecError(
            f"params.cap_squash ({params.cap_squash}) must be between 0.25 and 1.0."
        )
    if params.seed < 0:
        raise SpecError("params.seed must be non-negative.")
    return params


def _paint(created: dict, index: int) -> None:
    for vert in created["verts"]:
        for face in vert.link_faces:
            face.material_index = index


def _stem(
    bm: bmesh.types.BMesh,
    base: Vector,
    height: float,
    radius: float,
    index: int,
) -> Vector:
    top = base + Vector((0.0, 0.0, height))
    direction = top - base
    mid = (base + top) * 0.5
    rotation = (
        Vector((0.0, 0.0, 1.0)).rotation_difference(direction.normalized()).to_matrix().to_4x4()
    )
    matrix = (
        Matrix.Translation(mid)
        @ rotation
        @ Matrix.Diagonal((radius * 2.0, radius * 2.0, direction.length, 1.0))
    )
    _paint(
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=5,
            radius1=0.5,
            radius2=0.42,
            depth=1.0,
            matrix=matrix,
        ),
        index,
    )
    return top


def _cap(
    bm: bmesh.types.BMesh,
    centre: Vector,
    radius: float,
    squash: float,
    index: int,
) -> None:
    matrix = Matrix.Translation(centre) @ Matrix.Diagonal((radius, radius, radius * squash, 1.0))
    _paint(bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0, matrix=matrix), index)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    params = parse_params(spec.params)
    slots = material_slots(params)
    require_materials(spec.materials, slots, spec.generator)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    stem_index, cap_index = 0, 1
    spot_index = 2 if params.spot_count > 0 else None

    cap_tops: list[tuple[Vector, float]] = []

    for index in range(params.mushroom_count):
        angle = math.tau * (index / params.mushroom_count) + rng.uniform(-0.35, 0.35)
        reach = params.cluster_spread * rng.uniform(0.15, 1.0)
        base = Vector((math.cos(angle) * reach, math.sin(angle) * reach, 0.0))
        height = params.stem_height * rng.uniform(0.75, 1.15)
        radius = params.stem_radius * rng.uniform(0.85, 1.15)
        top = _stem(bm, base, height, radius, stem_index)
        cap_r = params.cap_radius * rng.uniform(0.85, 1.12)
        cap_z = top.z + cap_r * params.cap_squash * 0.35
        cap_centre = Vector((top.x, top.y, cap_z))
        _cap(bm, cap_centre, cap_r, params.cap_squash, cap_index)
        cap_tops.append((cap_centre, cap_r))

    if spot_index is not None:
        spots_left = params.spot_count
        for cap_centre, cap_r in cap_tops:
            while spots_left > 0 and rng.random() < 0.65:
                direction = Vector(
                    (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(0.2, 1.0))
                ).normalized()
                reach = cap_r * rng.uniform(0.35, 0.88)
                point = cap_centre + direction * reach
                _cap(bm, point, params.spot_radius * rng.uniform(0.8, 1.2), 0.95, spot_index)
                spots_left -= 1
                if spots_left == 0:
                    break

    if not bm.faces:
        bm.free()
        raise RuntimeError(f"Generator produced no geometry for '{spec.asset_id}'")

    mesh = bpy.data.meshes.new(spec.asset_id)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    for slot in slots:
        mesh.materials.append(make_material(slot, spec.materials[slot]))

    lower, upper = world_bounds([obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length > 1e-6:
        mesh.transform(Matrix.Translation(shift))
        mesh.update()

    shade_flat(obj)
    unwrap(obj)
    return [obj]
