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
from assetkit.rig import Clip, Skeleton, Skin


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
    #: Skin weights binding the mesh to the asset's skeleton (one entry per vertex), or None.
    skin: Skin | None = None

    def __post_init__(self) -> None:
        missing = [slot for slot in self.mesh.slots if slot not in self.materials]
        if missing:
            raise KeyError(f"Part '{self.name}' has no material for slot(s) {missing}")
        if self.skin is not None and len(self.skin.indices) != len(self.mesh.vertices):
            skinned, meshed = len(self.skin.indices), len(self.mesh.vertices)
            raise ValueError(f"Part '{self.name}': skin has {skinned} vertices, mesh {meshed}")
        for step in self.finish:
            if not isinstance(step, Bevel | ShadeFlat | ShadeSmooth | Unwrap):
                raise TypeError(f"Part '{self.name}': unknown finishing step {step!r}")


@dataclass(frozen=True)
class Asset:
    parts: tuple[Part, ...]
    #: One skeleton for the whole asset (skinned parts follow it), or None for a still asset.
    skeleton: Skeleton | None = None
    #: Animations of the skeleton; each becomes a glTF animation of its name.
    clips: tuple[Clip, ...] = ()

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("An asset needs at least one part")
        skinned = [p for p in self.parts if p.skin is not None]
        if (skinned or self.clips) and self.skeleton is None:
            raise ValueError("Skinned parts and clips need the asset's skeleton")
        for part in skinned:
            unknown = sorted(set(part.skin.bones) - set(self.skeleton.names))  # type: ignore[union-attr]
            if unknown:
                raise ValueError(f"Part '{part.name}': skin names bones {unknown} the skeleton lacks")
        names = [clip.name for clip in self.clips]
        if len(set(names)) != len(names):
            raise ValueError(f"Clip names repeat: {names}")
        if len({clip.fps for clip in self.clips}) > 1:
            raise ValueError("All clips of an asset share one frame rate")
        for clip in self.clips:
            for i, frame in enumerate(clip.frames):
                missing = set(self.skeleton.names) - set(frame)  # type: ignore[union-attr]
                if missing:
                    raise ValueError(f"Clip '{clip.name}' frame {i}: no motion for bones {sorted(missing)}")
