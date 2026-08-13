"""Stylized shrub: a few woody stems under a cluster of foliage lobes.

Scrub for bank fringes, forest edges and open ground. Low-poly and readable
rather than botanical, base on Z=0, footprint centred, deterministic by seed.

The `berries` slot is required only when a variant actually carries fruit, so a
dry bush cannot quietly declare a colour that never reaches the mesh.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

from blender.lib.scene import activate, make_material, unwrap, world_bounds
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

WOOD, FOLIAGE, BERRIES = "wood", "foliage", "berries"

_PARAM_KEYS = (
    "height",
    "spread",
    "stem_count",
    "stem_radius",
    "lobe_count",
    "lobe_radius",
    "berry_count",
    "berry_radius",
    "seed",
)

_MAX_LOBES = 10

# Foliage lobes are wider than they are tall, the way a shrub grows.
_SQUASH = 0.82


@dataclass(frozen=True)
class BushParams:
    height: float
    spread: float
    stem_count: int
    stem_radius: float
    lobe_count: int
    lobe_radius: float
    berry_count: int
    berry_radius: float
    seed: int


def material_slots(params: BushParams) -> tuple[str, ...]:
    """The slots this variant needs: fruit only where there is fruit."""
    if params.berry_count > 0:
        return (WOOD, FOLIAGE, BERRIES)
    return (WOOD, FOLIAGE)


def parse_params(raw: Mapping[str, object]) -> BushParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = BushParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        spread=positive_float(require_key(raw, "spread", path), f"{path}.spread"),
        stem_count=positive_int(require_key(raw, "stem_count", path), f"{path}.stem_count"),
        stem_radius=positive_float(
            require_key(raw, "stem_radius", path), f"{path}.stem_radius"
        ),
        lobe_count=positive_int(require_key(raw, "lobe_count", path), f"{path}.lobe_count"),
        lobe_radius=positive_float(
            require_key(raw, "lobe_radius", path), f"{path}.lobe_radius"
        ),
        berry_count=as_int(require_key(raw, "berry_count", path), f"{path}.berry_count"),
        berry_radius=positive_float(
            require_key(raw, "berry_radius", path), f"{path}.berry_radius"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.lobe_count > _MAX_LOBES:
        raise SpecError(f"params.lobe_count must be <= {_MAX_LOBES} for clutter budgets.")
    if params.berry_count < 0:
        raise SpecError(f"params.berry_count must be >= 0, got {params.berry_count}")
    if params.lobe_radius > params.height:
        raise SpecError(
            f"params.lobe_radius ({params.lobe_radius}) is larger than the whole bush "
            f"({params.height}); the lobes would swallow it."
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
    start: Vector,
    end: Vector,
    radius: float,
    index: int,
) -> None:
    direction = end - start
    rotation = (
        Vector((0.0, 0.0, 1.0)).rotation_difference(direction.normalized()).to_matrix().to_4x4()
    )
    matrix = (
        Matrix.Translation((start + end) * 0.5)
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
            radius2=0.35,
            depth=1.0,
            matrix=matrix,
        ),
        index,
    )


def _blob(
    bm: bmesh.types.BMesh,
    centre: Vector,
    radius: float,
    squash: float,
    subdivisions: int,
    index: int,
) -> None:
    matrix = Matrix.Translation(centre) @ Matrix.Diagonal(
        (radius, radius, radius * squash, 1.0)
    )
    _paint(
        bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1.0, matrix=matrix),
        index,
    )


def _crown(params: BushParams, rng: random.Random) -> list[Vector]:
    """Where the foliage sits: a squat dome the stems can reach into."""
    centres = [Vector((0.0, 0.0, params.height * 0.62))]
    for index in range(params.lobe_count - 1):
        angle = math.tau * (index / max(params.lobe_count - 1, 1)) + rng.uniform(-0.3, 0.3)
        reach = params.spread * rng.uniform(0.35, 0.62)
        lift = params.height * rng.uniform(0.38, 0.78)
        centres.append(Vector((math.cos(angle) * reach, math.sin(angle) * reach, lift)))
    return centres


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    params = parse_params(spec.params)
    slots = material_slots(params)
    require_materials(spec.materials, slots, spec.generator)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    wood_index, foliage_index = 0, 1

    centres = _crown(params, rng)
    for index in range(params.stem_count):
        target = centres[(index + 1) % len(centres)]
        angle = math.atan2(target.y, target.x)
        foot = Vector((math.cos(angle), math.sin(angle), 0.0)) * (
            params.stem_radius * rng.uniform(0.5, 2.5)
        )
        _stem(bm, foot, target, params.stem_radius * rng.uniform(0.8, 1.2), wood_index)

    lobes = [(centre, params.lobe_radius * rng.uniform(0.75, 1.15)) for centre in centres]
    for centre, radius in lobes:
        _blob(bm, centre, radius, _SQUASH, 1, foliage_index)

    if params.berry_count > 0:
        berry_index = 2
        for _ in range(params.berry_count):
            centre, radius = lobes[rng.randrange(len(lobes))]
            direction = Vector(
                (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-0.2, 1.0))
            ).normalized()
            # Sit on the lobe it hangs from, squash and all, and just inside it,
            # or the fruit floats in mid air.
            reach = Vector(
                (
                    direction.x * radius,
                    direction.y * radius,
                    direction.z * radius * _SQUASH,
                )
            )
            _blob(bm, centre + reach * 0.94, params.berry_radius, 1.0, 0, berry_index)

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
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    lower, upper = world_bounds([obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length > 1e-6:
        mesh.transform(Matrix.Translation(shift))
        mesh.update()

    unwrap(obj)
    activate(obj)
    return [obj]
