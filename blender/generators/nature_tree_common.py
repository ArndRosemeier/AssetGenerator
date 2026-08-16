"""Shared bmesh helpers for stylized tree generators."""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Matrix, Vector

from blender.lib.scene import activate, make_material, unwrap, world_bounds


def assign_material(faces: set[bmesh.types.BMFace], index: int) -> None:
    for face in faces:
        face.material_index = index


def faces_of(verts: list[bmesh.types.BMVert]) -> set[bmesh.types.BMFace]:
    return {face for vert in verts for face in vert.link_faces}


def cylinder_matrix(start: Vector, end: Vector, radius: float) -> Matrix:
    direction = end - start
    length = direction.length
    if length < 1e-6:
        raise RuntimeError("Degenerate limb with zero length")
    mid = (start + end) * 0.5
    rotation = (
        Vector((0.0, 0.0, 1.0)).rotation_difference(direction.normalized()).to_matrix().to_4x4()
    )
    scale = Matrix.Diagonal((radius * 2.0, radius * 2.0, length, 1.0))
    return Matrix.Translation(mid) @ rotation @ scale


def add_cylinder(
    bm: bmesh.types.BMesh,
    start: Vector,
    end: Vector,
    radius: float,
    segments: int,
    material_index: int,
) -> None:
    matrix = cylinder_matrix(start, end, radius)
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
    assign_material(faces_of(created["verts"]), material_index)


def add_trunk_cone(
    bm: bmesh.types.BMesh,
    height: float,
    radius_base: float,
    radius_top: float,
    segments: int,
    material_index: int,
) -> None:
    matrix = Matrix.Translation((0.0, 0.0, height * 0.5))
    created = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius_base,
        radius2=radius_top,
        depth=height,
        matrix=matrix,
    )
    assign_material(faces_of(created["verts"]), material_index)


def add_tuft(
    bm: bmesh.types.BMesh,
    center: Vector,
    radius: float,
    material_index: int,
    *,
    squash: float = 0.85,
    subdivisions: int = 1,
) -> None:
    matrix = Matrix.Translation(center) @ Matrix.Diagonal((radius, radius, radius * squash, 1.0))
    created = bmesh.ops.create_icosphere(
        bm,
        subdivisions=subdivisions,
        radius=1.0,
        matrix=matrix,
    )
    assign_material(faces_of(created["verts"]), material_index)


def add_box(
    bm: bmesh.types.BMesh,
    center: Vector,
    size: Vector,
    material_index: int,
) -> None:
    matrix = Matrix.Translation(center) @ Matrix.Diagonal((size.x, size.y, size.z, 1.0))
    created = bmesh.ops.create_cube(bm, size=1.0, matrix=matrix)
    assign_material(faces_of(created["verts"]), material_index)


def finalize_tree(
    spec_id: str,
    bm: bmesh.types.BMesh,
    material_slots: tuple[str, ...],
    materials: dict[str, object],
) -> list[bpy.types.Object]:
    if not bm.faces:
        bm.free()
        raise RuntimeError(f"Generator produced no geometry for '{spec_id}'")

    mesh = bpy.data.meshes.new(spec_id)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    for slot in material_slots:
        mesh.materials.append(make_material(slot, materials[slot]))
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
