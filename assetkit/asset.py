"""What a kit generator returns: parts made of a mesh, materials and finishing steps.

The steps are requests, not code: "bevel these edges", "unwrap", "shade smooth
but keep edges sharper than 40 degrees hard". The backend carries them out in
the order given, in whatever way its Blender version needs. A generator never
learns how.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from assetkit.mesh import Mesh


class Material(Protocol):
    """A plain PBR value: what survives a glTF export. `blender.lib.spec.MaterialSpec` is one."""

    @property
    def base_color(self) -> tuple[float, float, float, float]: ...

    @property
    def roughness(self) -> float: ...

    @property
    def metallic(self) -> float: ...


@dataclass(frozen=True)
class Bevel:
    """Bevel edges sharper than `angle_deg`, applied to the mesh (QA measures the result)."""

    width: float
    segments: int = 1
    angle_deg: float = 30.0


@dataclass(frozen=True)
class ShadeFlat:
    """Every face flat."""


@dataclass(frozen=True)
class ShadeSmooth:
    """Every face smooth; with `sharp_angle_deg`, edges whose faces turn by more stay hard."""

    sharp_angle_deg: float | None = None


@dataclass(frozen=True)
class Unwrap:
    """Smart-project UVs into the unit square."""

    angle_limit_deg: float = 66.0
    island_margin: float = 0.02


Step = Bevel | ShadeFlat | ShadeSmooth | Unwrap


@dataclass(frozen=True)
class Part:
    name: str
    mesh: Mesh
    materials: Mapping[str, Material]
    finish: tuple[Step, ...] = ()

    def __post_init__(self) -> None:
        missing = [slot for slot in self.mesh.slots if slot not in self.materials]
        if missing:
            raise KeyError(f"Part '{self.name}' has no material for slot(s) {missing}")
        for step in self.finish:
            if not isinstance(step, Bevel | ShadeFlat | ShadeSmooth | Unwrap):
                raise TypeError(f"Part '{self.name}': unknown finishing step {step!r}")


@dataclass(frozen=True)
class Asset:
    parts: tuple[Part, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("An asset needs at least one part")
