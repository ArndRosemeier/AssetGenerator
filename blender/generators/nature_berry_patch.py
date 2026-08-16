"""Stylized low berry patch for ground-level forage clutter.

Flat leaf mounds with scattered berry spheres — reads as cranberry, blueberry or
wild strawberry at ankle height, not a full shrub. Base on Z=0, footprint centred.
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

LEAVES, BERRIES = "leaves", "berries"

_PARAM_KEYS = (
    "patch_radius",
    "leaf_count",
    "leaf_radius",
    "leaf_height",
    "berry_count",
    "berry_radius",
    "seed",
)


@dataclass(frozen=True)
class BerryPatchParams:
    patch_radius: float
    leaf_count: int
    leaf_radius: float
    leaf_height: float
    berry_count: int
    berry_radius: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> BerryPatchParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = BerryPatchParams(
        patch_radius=positive_float(
            require_key(raw, "patch_radius", path), f"{path}.patch_radius"
        ),
        leaf_count=positive_int(require_key(raw, "leaf_count", path), f"{path}.leaf_count"),
        leaf_radius=positive_float(require_key(raw, "leaf_radius", path), f"{path}.leaf_radius"),
        leaf_height=positive_float(require_key(raw, "leaf_height", path), f"{path}.leaf_height"),
        berry_count=positive_int(
            require_key(raw, "berry_count", path), f"{path}.berry_count"
        ),
        berry_radius=positive_float(
            require_key(raw, "berry_radius", path), f"{path}.berry_radius"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.leaf_count > 8:
        raise SpecError("params.leaf_count must be <= 8 for clutter budgets.")
    if params.berry_count > 24:
        raise SpecError("params.berry_count must be <= 24 for clutter budgets.")
    if params.leaf_height > 0.45:
        raise SpecError(
            f"params.leaf_height ({params.leaf_height}) is too tall for a ground patch; "
            "use <= 0.45 m."
        )
    if params.seed < 0:
        raise SpecError("params.seed must be non-negative.")
    return params


def _paint(created: dict, index: int) -> None:
    for vert in created["verts"]:
        for face in vert.link_faces:
            face.material_index = index


def _leaf_blob(
    bm: bmesh.types.BMesh,
    centre: Vector,
    radius: float,
    height: float,
    index: int,
) -> None:
    matrix = Matrix.Translation(centre) @ Matrix.Diagonal(
        (radius, radius, max(radius * 0.35, height), 1.0)
    )
    _paint(bmesh.ops.create_icosphere(bm, subdivisions=0, radius=1.0, matrix=matrix), index)


def _berry(
    bm: bmesh.types.BMesh,
    centre: Vector,
    radius: float,
    index: int,
) -> None:
    matrix = Matrix.Translation(centre) @ Matrix.Diagonal((radius, radius, radius * 0.92, 1.0))
    _paint(bmesh.ops.create_icosphere(bm, subdivisions=0, radius=1.0, matrix=matrix), index)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, (LEAVES, BERRIES), spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    leaf_index, berry_index = 0, 1

    leaf_centres: list[tuple[Vector, float]] = []
    for index in range(params.leaf_count):
        angle = math.tau * (index / params.leaf_count) + rng.uniform(-0.4, 0.4)
        reach = params.patch_radius * rng.uniform(0.2, 0.95)
        centre = Vector(
            (
                math.cos(angle) * reach,
                math.sin(angle) * reach,
                params.leaf_height * rng.uniform(0.35, 0.85),
            )
        )
        radius = params.leaf_radius * rng.uniform(0.8, 1.15)
        _leaf_blob(bm, centre, radius, params.leaf_height, leaf_index)
        leaf_centres.append((centre, radius))

    for _ in range(params.berry_count):
        centre, radius = leaf_centres[rng.randrange(len(leaf_centres))]
        direction = Vector(
            (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-0.1, 0.6))
        ).normalized()
        reach = Vector((direction.x * radius, direction.y * radius, direction.z * radius * 0.35))
        berry_centre = centre + reach * rng.uniform(0.55, 0.95)
        berry_centre.z = max(params.leaf_height * 0.25, berry_centre.z)
        _berry(
            bm,
            berry_centre,
            params.berry_radius * rng.uniform(0.85, 1.15),
            berry_index,
        )

    if not bm.faces:
        bm.free()
        raise RuntimeError(f"Generator produced no geometry for '{spec.asset_id}'")

    mesh = bpy.data.meshes.new(spec.asset_id)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    for slot in (LEAVES, BERRIES):
        mesh.materials.append(make_material(slot, spec.materials[slot]))

    lower, upper = world_bounds([obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length > 1e-6:
        mesh.transform(Matrix.Translation(shift))
        mesh.update()

    shade_flat(obj)
    unwrap(obj)
    return [obj]
