"""Scene conventions: metric units, empty start state, one place to build meshes.

Every asset is authored in meters, Z-up, with the origin at the centre of the
footprint and the base sitting on Z=0. The glTF exporter converts to Y-up.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from blender.lib.spec import MaterialSpec


def reset_scene() -> bpy.types.Scene:
    """Remove all datablocks so a build always starts from the same state."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.node_groups,
        bpy.data.armatures,
        bpy.data.actions,
    ):
        for datablock in list(collection):
            collection.remove(datablock)

    scene = bpy.data.scenes[0]
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    return scene


def make_material(name: str, spec: MaterialSpec) -> bpy.types.Material:
    """A plain Principled BSDF, which is exactly what survives a glTF export."""
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    principled = next(
        (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )
    if principled is None:
        raise RuntimeError(f"Material '{name}' has no Principled BSDF node")
    principled.inputs["Base Color"].default_value = spec.base_color
    principled.inputs["Roughness"].default_value = spec.roughness
    principled.inputs["Metallic"].default_value = spec.metallic
    return material


class BoxBuilder:
    """Accumulates axis-aligned boxes into a single mesh with material slots.

    Hard-surface props are overwhelmingly boxes, so this keeps generators short
    and guarantees clean quad topology and consistent outward normals.
    """

    def __init__(self, material_slots: Sequence[str]) -> None:
        if not material_slots:
            raise ValueError("At least one material slot is required")
        self._slots: tuple[str, ...] = tuple(material_slots)
        self._bmesh: bmesh.types.BMesh = bmesh.new()

    def slot_index(self, slot: str) -> int:
        if slot not in self._slots:
            raise KeyError(f"Unknown material slot '{slot}'; have {list(self._slots)}")
        return self._slots.index(slot)

    def add_box(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        slot: str,
        *,
        rotation: tuple[float, float, float] | None = None,
    ) -> None:
        if any(component <= 0.0 for component in size):
            raise ValueError(f"Box size must be positive in every axis, got {size}")
        matrix = Matrix.Translation(Vector(center))
        if rotation is not None:
            matrix = matrix @ Euler(rotation).to_matrix().to_4x4()
        matrix = matrix @ Matrix.Diagonal(Vector((size[0], size[1], size[2], 1.0)))
        created = bmesh.ops.create_cube(self._bmesh, size=1.0, matrix=matrix)
        index = self.slot_index(slot)
        for face in {face for vert in created["verts"] for face in vert.link_faces}:
            face.material_index = index

    def add_box_bounds(
        self,
        lower: tuple[float, float, float],
        upper: tuple[float, float, float],
        slot: str,
    ) -> None:
        center = tuple((low + high) * 0.5 for low, high in zip(lower, upper))
        size = tuple(high - low for low, high in zip(lower, upper))
        self.add_box((center[0], center[1], center[2]), (size[0], size[1], size[2]), slot)

    def add_mesh(
        self,
        vertices: Sequence[tuple[float, float, float]],
        faces: Sequence[Sequence[int]],
        slot: str,
    ) -> None:
        """Add one closed hand-built shell (displaced rock, spindles).

        Faces must wind counter-clockwise seen from outside and the shell must be
        watertight: QA gates manifoldness and signed volume, so a hole or an
        inverted face fails the build instead of shipping.
        """
        if len(vertices) < 4 or len(faces) < 4:
            raise ValueError(f"A closed shell needs 4+ verts and 4+ faces, got {len(vertices)}/{len(faces)}")
        index = self.slot_index(slot)
        created = [self._bmesh.verts.new(Vector(vertex)) for vertex in vertices]
        for corners in faces:
            if len(corners) < 3:
                raise ValueError(f"Face needs 3+ corners, got {list(corners)}")
            face = self._bmesh.faces.new([created[corner] for corner in corners])
            face.material_index = index

    def to_object(self, name: str, materials: Mapping[str, MaterialSpec]) -> bpy.types.Object:
        if not self._bmesh.faces:
            raise RuntimeError(f"Generator produced no geometry for '{name}'")
        mesh = bpy.data.meshes.new(name)
        self._bmesh.to_mesh(mesh)
        self._bmesh.free()

        obj = bpy.data.objects.new(name, mesh)
        bpy.data.scenes[0].collection.objects.link(obj)
        for slot in self._slots:
            if slot not in materials:
                raise KeyError(f"Spec has no material for slot '{slot}'")
            mesh.materials.append(make_material(slot, materials[slot]))
        return obj


def activate(obj: bpy.types.Object) -> None:
    """Make `obj` the sole selected and active object (required by many operators)."""
    view_layer = bpy.context.view_layer
    for other in bpy.data.objects:
        other.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj


def apply_bevel(obj: bpy.types.Object, width: float, segments: int, angle_deg: float) -> None:
    """Bevel and immediately apply, so QA measures the geometry that ships."""
    modifier = obj.modifiers.new(name="Bevel", type="BEVEL")
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = "ANGLE"
    modifier.angle_limit = angle_deg * 3.141592653589793 / 180.0
    modifier.harden_normals = False
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def unwrap(obj: bpy.types.Object, angle_limit_deg: float = 66.0, island_margin: float = 0.02) -> None:
    """Smart-project UVs into 0..1. Runs fine headless with an active mesh object."""
    activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=angle_limit_deg * 3.141592653589793 / 180.0,
        island_margin=island_margin,
        correct_aspect=True,
        scale_to_bounds=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")


def shade_flat(obj: bpy.types.Object) -> None:
    for polygon in obj.data.polygons:
        polygon.use_smooth = False


def world_bounds(objects: Iterable[bpy.types.Object]) -> tuple[Vector, Vector]:
    corners: list[Vector] = []
    for obj in objects:
        matrix = obj.matrix_world
        corners.extend(matrix @ Vector(corner) for corner in obj.bound_box)
    if not corners:
        raise RuntimeError("Cannot compute bounds of an empty object set")
    lower = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    upper = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lower, upper
