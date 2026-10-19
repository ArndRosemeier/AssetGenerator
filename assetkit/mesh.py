"""Meshes as plain data: vertices, faces, a material slot per face, values per vertex.

`MeshBuilder` is the one way a kit generator makes geometry. It takes boxes and
closed shells (assetkit/shells.py), and checks what it can without Blender:
slot names, face corners, closed shells. The result is a frozen `Mesh` that a
backend turns into its own mesh type.

Frame (as every asset here): metres, Z up, origin at the footprint centre on Z=0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from assetkit.shells import Shell, Vec, box


@dataclass(frozen=True)
class Mesh:
    """Faces wind counter-clockwise seen from outside. `face_slots[i]` indexes `slots`."""

    vertices: tuple[Vec, ...]
    faces: tuple[tuple[int, ...], ...]
    face_slots: tuple[int, ...]
    slots: tuple[str, ...]
    point_attributes: Mapping[str, tuple[float, ...]] = field(default_factory=dict)

    def bounds(self) -> tuple[Vec, Vec]:
        xs, ys, zs = zip(*self.vertices, strict=True)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def settled(self) -> Mesh:
        """The same mesh moved so its footprint is centred on the origin and it rests on Z=0."""
        (x0, y0, z0), (x1, y1, _) = self.bounds()
        dx, dy = (x0 + x1) / 2, (y0 + y1) / 2
        moved = tuple((x - dx, y - dy, z - z0) for x, y, z in self.vertices)
        return Mesh(moved, self.faces, self.face_slots, self.slots, self.point_attributes)

    def triangle_count(self) -> int:
        return sum(len(face) - 2 for face in self.faces)


class MeshBuilder:
    """Collects boxes and closed shells into one mesh with named material slots."""

    def __init__(self, slots: Sequence[str]) -> None:
        if not slots:
            raise ValueError("At least one material slot is required")
        self._slots: tuple[str, ...] = tuple(slots)
        self._vertices: list[Vec] = []
        self._faces: list[tuple[int, ...]] = []
        self._face_slots: list[int] = []
        self._attributes: dict[str, tuple[float, ...]] = {}

    @property
    def slots(self) -> tuple[str, ...]:
        return self._slots

    def slot_index(self, slot: str) -> int:
        if slot not in self._slots:
            raise KeyError(f"Unknown material slot '{slot}'; have {list(self._slots)}")
        return self._slots.index(slot)

    def add_shell(self, vertices: Sequence[Vec], faces: Sequence[Sequence[int]], slot: str) -> None:
        """Add one closed shell. Faces wind counter-clockwise seen from outside; QA gates
        manifoldness and signed volume, so a hole or an inverted face fails the build."""
        self.add_painted(vertices, faces, [slot] * len(faces))

    def add_painted(
        self, vertices: Sequence[Vec], faces: Sequence[Sequence[int]], slots: Sequence[str]
    ) -> None:
        """Add one closed shell whose faces carry their own material slots (`sdf.paint`)."""
        if len(vertices) < 4 or len(faces) < 4:
            raise ValueError(f"A closed shell needs 4+ verts and 4+ faces, got {len(vertices)}/{len(faces)}")
        if len(slots) != len(faces):
            raise ValueError(f"{len(slots)} slots for {len(faces)} faces")
        indices = {slot: self.slot_index(slot) for slot in set(slots)}
        start = len(self._vertices)
        for corners, slot in zip(faces, slots, strict=True):
            index = indices[slot]
            if len(corners) < 3:
                raise ValueError(f"Face needs 3+ corners, got {list(corners)}")
            if len(set(corners)) != len(corners):
                raise ValueError(f"Face repeats a corner: {list(corners)}")
            if min(corners) < 0 or max(corners) >= len(vertices):
                raise ValueError(f"Face {list(corners)} points past the shell's {len(vertices)} vertices")
            self._faces.append(tuple(start + corner for corner in corners))
            self._face_slots.append(index)
        self._vertices.extend((float(x), float(y), float(z)) for x, y, z in vertices)

    def add(self, shell: Shell, slot: str) -> None:
        self.add_shell(shell[0], shell[1], slot)

    def add_box(
        self,
        center: Vec,
        size: Vec,
        slot: str,
        *,
        rotation: Vec | None = None,
    ) -> None:
        """An axis-aligned box of `size` round `center`, turned by `rotation` (XYZ Euler, radians)."""
        if any(component <= 0.0 for component in size):
            raise ValueError(f"Box size must be positive in every axis, got {size}")
        half = [component * 0.5 for component in size]
        verts, faces = box((-half[0], -half[1], -half[2]), (half[0], half[1], half[2]))
        if rotation is not None:
            verts = [_rotate_xyz(v, rotation) for v in verts]
        verts = [(x + center[0], y + center[1], z + center[2]) for x, y, z in verts]
        self.add_shell(verts, faces, slot)

    def add_box_bounds(self, lower: Vec, upper: Vec, slot: str) -> None:
        center = tuple((low + high) * 0.5 for low, high in zip(lower, upper, strict=True))
        size = tuple(high - low for low, high in zip(lower, upper, strict=True))
        self.add_box((center[0], center[1], center[2]), (size[0], size[1], size[2]), slot)

    def set_point_attribute(self, name: str, values: Sequence[float]) -> None:
        """One float per vertex, in the order the vertices were added (a shade, a mask)."""
        if len(values) != len(self._vertices):
            raise ValueError(
                f"Attribute '{name}' has {len(values)} values for {len(self._vertices)} vertices"
            )
        self._attributes[name] = tuple(float(v) for v in values)

    def build(self) -> Mesh:
        if not self._faces:
            raise RuntimeError("The builder holds no geometry")
        return Mesh(
            vertices=tuple(self._vertices),
            faces=tuple(self._faces),
            face_slots=tuple(self._face_slots),
            slots=self._slots,
            point_attributes=dict(self._attributes),
        )


def _rotate_xyz(v: Vec, rotation: Vec) -> Vec:
    """Rotate about X, then Y, then Z (Blender's XYZ Euler order)."""
    x, y, z = v
    rx, ry, rz = rotation
    c, s = math.cos(rx), math.sin(rx)
    y, z = y * c - z * s, y * s + z * c
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    return (x, y, z)
