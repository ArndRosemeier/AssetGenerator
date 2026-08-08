"""Stylized conifer / ponderosa-like pine.

Low-poly cold-test generator: tapered trunk, sparse lower stubs, live branches
in the upper canopy, and soft icosphere needle tufts. Deterministic via seed.
Not photoreal — readable silhouette and material split (bark / foliage).
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
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
    as_float,
    as_int,
)

MATERIAL_SLOTS: tuple[str, ...] = ("bark", "foliage")

_PARAM_KEYS = (
    "height",
    "trunk_radius_base",
    "trunk_radius_top",
    "trunk_segments",
    "canopy_start",
    "branch_count",
    "stub_count",
    "branch_length_scale",
    "tuft_radius",
    "seed",
)


@dataclass(frozen=True)
class PineParams:
    height: float
    trunk_radius_base: float
    trunk_radius_top: float
    trunk_segments: int
    canopy_start: float
    branch_count: int
    stub_count: int
    branch_length_scale: float
    tuft_radius: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> PineParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = PineParams(
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
        canopy_start=as_float(require_key(raw, "canopy_start", path), f"{path}.canopy_start"),
        branch_count=positive_int(require_key(raw, "branch_count", path), f"{path}.branch_count"),
        stub_count=as_int(require_key(raw, "stub_count", path), f"{path}.stub_count"),
        branch_length_scale=positive_float(
            require_key(raw, "branch_length_scale", path), f"{path}.branch_length_scale"
        ),
        tuft_radius=positive_float(require_key(raw, "tuft_radius", path), f"{path}.tuft_radius"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    _validate(params)
    return params


def _validate(params: PineParams) -> None:
    if params.trunk_radius_top >= params.trunk_radius_base:
        raise SpecError(
            f"params: trunk_radius_top ({params.trunk_radius_top}) must be smaller than "
            f"trunk_radius_base ({params.trunk_radius_base})."
        )
    if not 0.2 <= params.canopy_start <= 0.85:
        raise SpecError(
            f"params.canopy_start ({params.canopy_start}) must be between 0.2 and 0.85 "
            "(fraction of height where live canopy begins)."
        )
    if params.stub_count < 0:
        raise SpecError(f"params.stub_count must be >= 0, got {params.stub_count}")
    if params.trunk_segments < 6 or params.trunk_segments > 24:
        raise SpecError(
            f"params.trunk_segments ({params.trunk_segments}) must be between 6 and 24."
        )
    if params.height < 2.0:
        raise SpecError(f"params.height ({params.height}) is too short for a pine; use >= 2 m.")


def _assign_material(faces: set[bmesh.types.BMFace], index: int) -> None:
    for face in faces:
        face.material_index = index


def _faces_of(verts: list[bmesh.types.BMVert]) -> set[bmesh.types.BMFace]:
    return {face for vert in verts for face in vert.link_faces}


def _add_trunk(bm: bmesh.types.BMesh, params: PineParams, bark_index: int) -> None:
    # Cone along Z, centred at origin — shift up so the base sits on Z=0.
    matrix = Matrix.Translation((0.0, 0.0, params.height * 0.5))
    created = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=params.trunk_segments,
        radius1=params.trunk_radius_base,
        radius2=params.trunk_radius_top,
        depth=params.height,
        matrix=matrix,
    )
    _assign_material(_faces_of(created["verts"]), bark_index)


def _cylinder_matrix(
    start: Vector,
    end: Vector,
    radius: float,
) -> tuple[Matrix, float]:
    direction = end - start
    length = direction.length
    if length < 1e-6:
        raise RuntimeError("Degenerate branch with zero length")
    mid = (start + end) * 0.5
    # Default cone/cylinder axis is +Z; rotate that onto `direction`.
    rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(direction.normalized()).to_matrix().to_4x4()
    scale = Matrix.Diagonal((radius * 2.0, radius * 2.0, length, 1.0))
    return Matrix.Translation(mid) @ rotation @ scale, length


def _add_limb(
    bm: bmesh.types.BMesh,
    start: Vector,
    end: Vector,
    radius: float,
    segments: int,
    material_index: int,
) -> None:
    matrix, _length = _cylinder_matrix(start, end, radius)
    # Unit cone depth=1, radius1=radius2=0.5, then scaled by matrix.
    created = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=0.5,
        radius2=0.5,
        depth=1.0,
        matrix=matrix,
    )
    _assign_material(_faces_of(created["verts"]), material_index)


def _add_tuft(
    bm: bmesh.types.BMesh,
    center: Vector,
    radius: float,
    material_index: int,
) -> None:
    matrix = Matrix.Translation(center) @ Matrix.Diagonal((radius, radius, radius * 0.85, 1.0))
    created = bmesh.ops.create_icosphere(
        bm,
        subdivisions=1,
        radius=1.0,
        matrix=matrix,
    )
    _assign_material(_faces_of(created["verts"]), material_index)


def _trunk_radius_at(params: PineParams, z: float) -> float:
    t = max(0.0, min(1.0, z / params.height))
    return params.trunk_radius_base * (1.0 - t) + params.trunk_radius_top * t


def _add_stubs(
    bm: bmesh.types.BMesh,
    params: PineParams,
    rng: random.Random,
    bark_index: int,
) -> None:
    canopy_z = params.height * params.canopy_start
    for index in range(params.stub_count):
        z = 0.08 * params.height + (canopy_z - 0.12 * params.height) * (
            (index + 0.5) / max(params.stub_count, 1)
        )
        z += rng.uniform(-0.15, 0.15)
        z = max(0.3, min(canopy_z - 0.2, z))
        angle = rng.uniform(0.0, math.tau) + index * 2.3
        trunk_r = _trunk_radius_at(params, z)
        length = rng.uniform(0.15, 0.55) * params.branch_length_scale
        direction = Vector((math.cos(angle), math.sin(angle), rng.uniform(-0.25, 0.05)))
        direction.normalize()
        start = Vector((math.cos(angle) * trunk_r * 0.85, math.sin(angle) * trunk_r * 0.85, z))
        end = start + direction * length
        _add_limb(bm, start, end, radius=rng.uniform(0.02, 0.045), segments=5, material_index=bark_index)


def _add_canopy(
    bm: bmesh.types.BMesh,
    params: PineParams,
    rng: random.Random,
    bark_index: int,
    foliage_index: int,
) -> None:
    canopy_z = params.height * params.canopy_start
    crown_z = params.height * 0.96
    for index in range(params.branch_count):
        t = index / max(params.branch_count - 1, 1)
        # Bias density upward (ponderosa: fuller near the top).
        height_t = t ** 0.65
        z = canopy_z + (crown_z - canopy_z) * height_t
        z += rng.uniform(-0.12, 0.12)
        angle = (index * 2.399963) + rng.uniform(-0.35, 0.35)

        # Lower live branches longer and more horizontal; upper ones shorter / upswept.
        length = params.branch_length_scale * (1.85 - 1.25 * height_t) * rng.uniform(0.8, 1.2)
        lift = -0.12 + 0.7 * height_t + rng.uniform(-0.1, 0.12)
        trunk_r = _trunk_radius_at(params, z)
        direction = Vector((math.cos(angle), math.sin(angle), lift))
        direction.normalize()
        start = Vector((math.cos(angle) * trunk_r * 0.7, math.sin(angle) * trunk_r * 0.7, z))
        end = start + direction * length
        radius = max(0.02, 0.07 * (1.0 - 0.55 * height_t))
        _add_limb(bm, start, end, radius=radius, segments=6, material_index=bark_index)

        # Needle tufts: tip + mid-branch bulk. Slightly larger lower in the canopy.
        tuft = params.tuft_radius * rng.uniform(0.9, 1.3) * (1.15 - 0.35 * height_t)
        _add_tuft(bm, end, tuft, foliage_index)
        if length > 1.1:
            mid = start.lerp(end, rng.uniform(0.5, 0.72))
            _add_tuft(bm, mid, tuft * 0.78, foliage_index)
        if length > 2.0 and height_t < 0.55:
            near = start.lerp(end, rng.uniform(0.28, 0.4))
            _add_tuft(bm, near, tuft * 0.55, foliage_index)

    # Crown cap so the top doesn't look bald.
    tip = Vector((0.0, 0.0, params.height * 0.98))
    _add_tuft(bm, tip, params.tuft_radius * 1.35, foliage_index)
    for index in range(4):
        angle = index * (math.tau / 4.0) + 0.4
        offset = Vector((math.cos(angle), math.sin(angle), 0.35)).normalized() * (
            params.tuft_radius * 0.9
        )
        _add_tuft(bm, tip + offset, params.tuft_radius * 0.9, foliage_index)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    bark_index = 0
    foliage_index = 1

    _add_trunk(bm, params, bark_index)
    _add_stubs(bm, params, rng, bark_index)
    _add_canopy(bm, params, rng, bark_index, foliage_index)

    if not bm.faces:
        bm.free()
        raise RuntimeError(f"Generator produced no geometry for '{spec.asset_id}'")

    mesh = bpy.data.meshes.new(spec.asset_id)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    for slot in MATERIAL_SLOTS:
        mesh.materials.append(make_material(slot, spec.materials[slot]))

    # Smooth bark/foliage reads better for organic forms in the preview.
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    # Branches are intentionally irregular, so recenter the footprint on X/Y while
    # keeping the base on Z=0 (origin_at_base convention).
    lower, upper = world_bounds([obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length > 1e-6:
        mesh.transform(Matrix.Translation(shift))
        mesh.update()

    unwrap(obj)
    activate(obj)
    return [obj]
