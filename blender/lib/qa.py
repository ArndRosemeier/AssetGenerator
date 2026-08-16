"""Geometry quality gates.

These are the checks that make LLM-authored geometry trustworthy: budget,
UVs, manifoldness, normal direction, transforms and pivot convention. A failing
check is an error in the report, never a silent fixup.
"""

from __future__ import annotations

from collections.abc import Sequence

import bmesh
import bpy

from blender.lib.report import CheckResult, MeshStats, check
from blender.lib.scene import world_bounds
from blender.lib.spec import QaSpec

_EPSILON = 1e-4


def triangle_count(mesh: bpy.types.Mesh) -> int:
    return sum(len(polygon.vertices) - 2 for polygon in mesh.polygons)


def _mesh_objects(objects: Sequence[bpy.types.Object]) -> list[bpy.types.Object]:
    return [obj for obj in objects if obj.type == "MESH"]


def collect_stats(objects: Sequence[bpy.types.Object]) -> MeshStats:
    mesh_objects = _mesh_objects(objects)
    meshes = [obj.data for obj in mesh_objects]
    if not mesh_objects:
        raise RuntimeError("QA collect_stats received no mesh objects")
    lower, upper = world_bounds(mesh_objects)
    material_names: set[str] = set()
    for mesh in meshes:
        for material in mesh.materials:
            if material is not None:
                material_names.add(material.name)
    return {
        "objects": len(objects),
        "vertices": sum(len(mesh.vertices) for mesh in meshes),
        "triangles": sum(triangle_count(mesh) for mesh in meshes),
        "materials": len(material_names),
        "uv_layers": max((len(mesh.uv_layers) for mesh in meshes), default=0),
        "dimensions_m": [
            round(upper.x - lower.x, 6),
            round(upper.y - lower.y, 6),
            round(upper.z - lower.z, 6),
        ],
    }


def _non_manifold_counts(mesh: bpy.types.Mesh) -> tuple[int, int, float]:
    """Return (non-manifold edge count, loose vertex count, signed volume)."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        bad_edges = sum(1 for edge in bm.edges if len(edge.link_faces) != 2)
        loose_verts = sum(1 for vert in bm.verts if not vert.link_edges)
        volume = bm.calc_volume(signed=True)
    finally:
        bm.free()
    return bad_edges, loose_verts, volume


def _uv_bounds(mesh: bpy.types.Mesh) -> tuple[float, float]:
    layer = mesh.uv_layers.active
    if layer is None:
        raise RuntimeError(f"Mesh '{mesh.name}' has no active UV layer")
    lowest = min(min(datum.uv) for datum in layer.data)
    highest = max(max(datum.uv) for datum in layer.data)
    return lowest, highest


def _degenerate_faces(mesh: bpy.types.Mesh) -> int:
    return sum(1 for polygon in mesh.polygons if polygon.area < 1e-10)


def run_checks(
    objects: Sequence[bpy.types.Object],
    qa: QaSpec,
    stats: MeshStats,
    *,
    topology: bool,
) -> list[CheckResult]:
    """Run the QA gates.

    `topology` must be False when the objects came from a reimported glTF. glTF
    stores one vertex per unique normal/UV combination, so edge connectivity is
    not preserved by the format and manifold checks there would be meaningless.
    Topology is guaranteed at authoring time instead.
    """
    checks: list[CheckResult] = []
    mesh_objects = _mesh_objects(objects)
    meshes = [obj.data for obj in mesh_objects]

    checks.append(
        check(
            "triangle_budget",
            stats["triangles"] <= qa.max_triangles,
            f"{stats['triangles']} tris (budget {qa.max_triangles})",
        )
    )

    largest = max(stats["dimensions_m"])
    checks.append(
        check(
            "size_limit",
            0.0 < largest <= qa.max_dimension_m,
            f"largest dimension {largest:.3f} m (limit {qa.max_dimension_m} m)",
        )
    )

    if qa.require_uvs:
        missing = [mesh.name for mesh in meshes if not mesh.uv_layers]
        checks.append(
            check("uvs_present", not missing, "all meshes unwrapped" if not missing else f"missing on {missing}")
        )
        if not missing:
            lowest = min(_uv_bounds(mesh)[0] for mesh in meshes)
            highest = max(_uv_bounds(mesh)[1] for mesh in meshes)
            inside = lowest >= -_EPSILON and highest <= 1.0 + _EPSILON
            checks.append(
                check("uvs_in_unit_square", inside, f"UV range [{lowest:.4f}, {highest:.4f}]")
            )

    degenerate = sum(_degenerate_faces(mesh) for mesh in meshes)
    checks.append(
        check("no_degenerate_faces", degenerate == 0, f"{degenerate} zero-area face(s)")
    )

    if qa.require_manifold:
        bad_edges = 0
        loose_verts = 0
        inverted: list[str] = []
        for mesh in meshes:
            edges, verts, volume = _non_manifold_counts(mesh)
            bad_edges += edges
            loose_verts += verts
            if volume <= 0.0:
                inverted.append(mesh.name)
        if topology:
            checks.append(
                check("manifold", bad_edges == 0, f"{bad_edges} non-manifold edge(s)")
            )
            checks.append(
                check("no_loose_geometry", loose_verts == 0, f"{loose_verts} loose vertex/vertices")
            )
        checks.append(
            check(
                "normals_outward",
                not inverted,
                "positive signed volume" if not inverted else f"inverted normals on {inverted}",
            )
        )

    unassigned: list[str] = []
    for obj in mesh_objects:
        mesh = obj.data
        if not mesh.materials:
            unassigned.append(mesh.name)
            continue
        slot_count = len(mesh.materials)
        if any(polygon.material_index >= slot_count for polygon in mesh.polygons):
            unassigned.append(mesh.name)
    checks.append(
        check(
            "materials_assigned",
            not unassigned,
            f"{stats['materials']} material(s)" if not unassigned else f"bad material slots on {unassigned}",
        )
    )

    off_transform = [
        obj.name
        for obj in objects
        if any(abs(value - 1.0) > _EPSILON for value in obj.scale)
        or any(abs(value) > _EPSILON for value in obj.rotation_euler)
        or any(abs(value) > _EPSILON for value in obj.location)
    ]
    checks.append(
        check(
            "transforms_identity",
            not off_transform,
            "loc/rot/scale are neutral" if not off_transform else f"non-neutral transform on {off_transform}",
        )
    )

    if qa.require_origin_at_base:
        lower, upper = world_bounds(mesh_objects)
        centred = abs(lower.x + upper.x) < 1e-3 and abs(lower.y + upper.y) < 1e-3
        on_ground = abs(lower.z) < 1e-3
        checks.append(
            check(
                "origin_at_base",
                centred and on_ground,
                f"footprint centre ({(lower.x + upper.x) / 2:.4f}, {(lower.y + upper.y) / 2:.4f}), "
                f"base z {lower.z:.4f}",
            )
        )

    return checks
