"""Spec params for the quadruped generator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from blender.lib.spec import SpecError, as_float, as_int, positive_float, positive_int

Rgb = tuple[float, float, float]


def _rgb(raw: object, path: str) -> Rgb:
    if not isinstance(raw, list) or len(raw) != 3:
        raise SpecError(f"{path}: expected a list of 3 numbers (linear RGB)")
    return (as_float(raw[0], path), as_float(raw[1], path), as_float(raw[2], path))


@dataclass(frozen=True)
class QuadrupedParams:
    seed: int
    lean: float
    voxel: float
    fur_length: float
    mange: float
    triangles: int
    texture_resolution: int
    bake_samples: int
    coat: Rgb
    saddle: Rgb
    pale: Rgb
    mask: Rgb
    nose: Rgb
    mange_colour: Rgb
    dirt: Rgb


_FLOATS = ("lean", "voxel", "fur_length", "mange")
_INTS = ("seed", "triangles", "texture_resolution", "bake_samples")
_COLOURS = ("coat", "saddle", "pale", "mask", "nose", "mange_colour", "dirt")


def parse_params(raw: Mapping[str, object]) -> QuadrupedParams:
    allowed = set(_FLOATS) | set(_INTS) | set(_COLOURS)
    unknown = sorted(set(raw) - allowed)
    missing = sorted(allowed - set(raw))
    if unknown:
        raise SpecError(f"params: unknown key(s) {unknown}")
    if missing:
        raise SpecError(f"params: missing key(s) {missing}")
    values: dict[str, object] = {}
    for k in _FLOATS:
        values[k] = (
            positive_float(raw[k], f"params.{k}")
            if k in ("voxel", "fur_length")
            else as_float(raw[k], f"params.{k}")
        )
    for k in _INTS:
        values[k] = as_int(raw[k], f"params.{k}") if k == "seed" else positive_int(raw[k], f"params.{k}")
    for k in _COLOURS:
        values[k] = _rgb(raw[k], f"params.{k}")
    return QuadrupedParams(**values)  # type: ignore[arg-type]
