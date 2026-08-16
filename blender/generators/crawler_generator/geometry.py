"""Build crawler shells and record bone rest chains."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

from blender.generators.crawler_generator.params import CrawlerParams
from blender.lib.scene import activate

SLOT_CHITIN = 0
SLOT_ABDOMEN = 1

_SPHERE_U = 10
_SPHERE_V = 7


@dataclass(frozen=True)
class BoneRest:
    name: str
    head: Vector
    tail: Vector
    parent: str | None


@dataclass(frozen=True)
class CrawlerLayout:
    bones: tuple[BoneRest, ...]
    body_center: Vector
    abdomen_center: Vector


def _link_object(name: str, mesh: bpy.types.Mesh) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    return obj


def _assign_group(obj: bpy.types.Object, group_name: str) -> None:
    group = obj.vertex_groups.new(name=group_name)
    group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")


def _set_slot(mesh: bpy.types.Mesh, slot: int) -> None:
    for polygon in mesh.polygons:
        polygon.material_index = slot
        polygon.use_smooth = True


def _ellipsoid(name: str, center: Vector, radii: Vector, slot: int) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=_SPHERE_U, v_segments=_SPHERE_V, radius=1.0)
    matrix = Matrix.Translation(center) @ Matrix.Diagonal((radii.x, radii.y, radii.z, 1.0))
    bmesh.ops.transform(bm, verts=list(bm.verts), matrix=matrix)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    _set_slot(mesh, slot)
    obj = _link_object(name, mesh)
    _assign_group(obj, name)
    return obj


def _segment(name: str, head: Vector, tail: Vector, radius: float, slot: int) -> bpy.types.Object:
    direction = tail - head
    length = direction.length
    if length <= 1e-6:
        raise RuntimeError(f"Crawler segment '{name}' has zero length ({head} -> {tail})")
    mid = (head + tail) * 0.5
    rotation = direction.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    # Slightly longer than the bone so joints overlap and stay watertight after join.
    half = length * 0.5 + radius * 0.35
    scale = Matrix.Diagonal((radius, radius, half, 1.0))
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=_SPHERE_U, v_segments=_SPHERE_V, radius=1.0)
    bmesh.ops.transform(bm, verts=list(bm.verts), matrix=Matrix.Translation(mid) @ rotation @ scale)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    _set_slot(mesh, slot)
    obj = _link_object(name, mesh)
    _assign_group(obj, name)
    return obj


def _triangulate(obj: bpy.types.Object) -> None:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()


def _join(name: str, parts: list[bpy.types.Object]) -> bpy.types.Object:
    if not parts:
        raise RuntimeError("Crawler join received no parts")
    activate(parts[0])
    for obj in parts:
        obj.select_set(True)
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    if joined is None:
        raise RuntimeError("Crawler join left no active object")
    joined.name = name
    joined.data.name = f"{name}_mesh"
    return joined


def _leg_yaw(pair_index: int, pair_count: int) -> float:
    """Front pair points forward-out; last pair points rear-out. Radians from +Y."""
    if pair_count == 1:
        return math.radians(90.0)
    t = pair_index / (pair_count - 1)
    return math.radians(48.0 + t * 84.0)


def _leg_points(
    attach: Vector,
    outward: Vector,
    lengths: list[float],
    *,
    rng: random.Random,
) -> list[Vector]:
    points = [attach]
    current = attach
    remaining = list(lengths)
    for index, length in enumerate(remaining):
        is_last = index == len(remaining) - 1
        if index == 0:
            lift = Vector((0.0, 0.0, length * 0.28))
            step = outward * length + lift
        elif not is_last:
            step = outward * length + Vector((0.0, 0.0, -length * 0.12))
        else:
            tip_xy = current.xy + outward.xy * length
            tip = Vector((tip_xy.x, tip_xy.y, 0.006 + rng.uniform(0.0, 0.004)))
            points.append(tip)
            continue
        current = current + step
        points.append(current)
    return points


def _segment_lengths(total: float, count: int) -> list[float]:
    if count == 3:
        return [total * 0.32, total * 0.38, total * 0.30]
    return [total * 0.24, total * 0.28, total * 0.26, total * 0.22]


def build_layout(
    params: CrawlerParams, rng: random.Random
) -> tuple[bpy.types.Object, CrawlerLayout]:
    body_center = Vector((0.0, params.body_length * 0.18, params.body_height * 0.62))
    abdomen_center = Vector(
        (
            0.0,
            -params.body_length * 0.42 - params.abdomen_length * 0.42,
            params.abdomen_height * 0.58,
        )
    )
    parts: list[bpy.types.Object] = []
    bones: list[BoneRest] = []

    parts.append(
        _ellipsoid(
            "body",
            body_center,
            Vector((params.body_width * 0.5, params.body_length * 0.5, params.body_height * 0.5)),
            SLOT_CHITIN,
        )
    )
    bones.append(
        BoneRest(
            "body",
            Vector((0.0, body_center.y + params.body_length * 0.15, 0.0)),
            body_center,
            None,
        )
    )
    parts.append(
        _ellipsoid(
            "abdomen",
            abdomen_center,
            Vector(
                (
                    params.abdomen_width * 0.5,
                    params.abdomen_length * 0.5,
                    params.abdomen_height * 0.5,
                )
            ),
            SLOT_ABDOMEN,
        )
    )
    bones.append(BoneRest("abdomen", body_center, abdomen_center, "body"))

    reach = params.leg_span * 0.5
    lengths = _segment_lengths(reach, params.leg_segments)
    for pair_index in range(params.leg_pairs):
        yaw = _leg_yaw(pair_index, params.leg_pairs)
        t = pair_index / max(params.leg_pairs - 1, 1)
        attach_y = body_center.y + (0.5 - t) * params.body_length * 0.62
        attach_z = body_center.z * 0.72
        jitter = rng.uniform(-0.012, 0.012) * params.body_length
        for side, sign in (("L", 1.0), ("R", -1.0)):
            attach = Vector(
                (sign * params.body_width * 0.46, attach_y + jitter * sign, attach_z)
            )
            outward = Vector((sign * math.sin(yaw), math.cos(yaw), 0.0)).normalized()
            points = _leg_points(attach, outward, lengths, rng=rng)
            parent = "body"
            for seg_index in range(len(points) - 1):
                name = f"leg_{side}{pair_index}_{seg_index}"
                head = points[seg_index]
                tail = points[seg_index + 1]
                radius = params.leg_thickness * (1.0 - 0.18 * seg_index)
                parts.append(_segment(name, head, tail, radius, SLOT_CHITIN))
                bones.append(BoneRest(name, head, tail, parent))
                parent = name

    if params.mandibles:
        for side, sign in (("L", 1.0), ("R", -1.0)):
            name = f"mandible_{side}"
            head = body_center + Vector(
                (sign * params.body_width * 0.18, params.body_length * 0.42, -params.body_height * 0.08)
            )
            tail = head + Vector(
                (sign * params.mandible_length * 0.35, params.mandible_length, -params.mandible_length * 0.25)
            )
            parts.append(_segment(name, head, tail, params.mandible_thickness, SLOT_CHITIN))
            bones.append(BoneRest(name, head, tail, "body"))

    if params.antennae:
        for side, sign in (("L", 1.0), ("R", -1.0)):
            name = f"antenna_{side}"
            head = body_center + Vector(
                (sign * params.body_width * 0.12, params.body_length * 0.38, params.body_height * 0.28)
            )
            mid = head + Vector(
                (sign * params.antennae_length * 0.2, params.antennae_length * 0.55, params.antennae_length * 0.35)
            )
            tip = mid + Vector(
                (sign * params.antennae_length * 0.15, params.antennae_length * 0.45, params.antennae_length * 0.15)
            )
            parts.append(_segment(f"{name}_0", head, mid, params.antennae_thickness, SLOT_CHITIN))
            parts.append(
                _segment(f"{name}_1", mid, tip, params.antennae_thickness * 0.7, SLOT_CHITIN)
            )
            bones.append(BoneRest(f"{name}_0", head, mid, "body"))
            bones.append(BoneRest(f"{name}_1", mid, tip, f"{name}_0"))

    if params.stinger:
        rear = abdomen_center + Vector((0.0, -params.abdomen_length * 0.48, params.abdomen_height * 0.1))
        mid = rear + Vector((0.0, -params.stinger_length * 0.35, params.stinger_length * 0.45))
        tip = mid + Vector((0.0, params.stinger_length * 0.15, params.stinger_length * 0.4))
        parts.append(_segment("stinger_0", rear, mid, params.stinger_thickness, SLOT_CHITIN))
        parts.append(_segment("stinger_1", mid, tip, params.stinger_thickness * 0.55, SLOT_CHITIN))
        bones.append(BoneRest("stinger_0", rear, mid, "abdomen"))
        bones.append(BoneRest("stinger_1", mid, tip, "stinger_0"))

    mesh_obj = _join("crawler", parts)
    _triangulate(mesh_obj)
    return mesh_obj, CrawlerLayout(
        bones=tuple(bones),
        body_center=body_center,
        abdomen_center=abdomen_center,
    )
