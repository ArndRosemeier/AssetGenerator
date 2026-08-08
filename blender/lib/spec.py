"""Strict parsing of asset spec JSON.

Specs are the source of truth for every asset. Parsing is deliberately
unforgiving: missing keys, unknown keys and wrong types all raise, so a
malformed spec fails before Blender is ever launched.

Stdlib-only: imported by both `tools/ag.py` and code running inside Blender.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SPEC_VERSION: Final[int] = 1


class SpecError(ValueError):
    """Raised when a spec file is malformed."""


def _as_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SpecError(f"{path}: expected an object, got {type(value).__name__}")
    for key in value:
        if not isinstance(key, str):
            raise SpecError(f"{path}: object keys must be strings, got {key!r}")
    return value


def _require(mapping: Mapping[str, object], key: str, path: str) -> object:
    if key not in mapping:
        raise SpecError(f"{path}: missing required key '{key}'")
    return mapping[key]


def _reject_unknown(mapping: Mapping[str, object], allowed: Sequence[str], path: str) -> None:
    unknown = sorted(set(mapping) - set(allowed))
    if unknown:
        raise SpecError(f"{path}: unknown key(s) {unknown}; allowed keys are {sorted(allowed)}")


def as_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise SpecError(f"{path}: expected a string, got {type(value).__name__}")
    return value


def as_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise SpecError(f"{path}: expected a boolean, got {type(value).__name__}")
    return value


def as_float(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{path}: expected a number, got {type(value).__name__}")
    return float(value)


def as_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpecError(f"{path}: expected an integer, got {type(value).__name__}")
    return value


def positive_float(value: object, path: str) -> float:
    number = as_float(value, path)
    if number <= 0.0:
        raise SpecError(f"{path}: expected a positive number, got {number}")
    return number


def positive_int(value: object, path: str) -> int:
    number = as_int(value, path)
    if number <= 0:
        raise SpecError(f"{path}: expected a positive integer, got {number}")
    return number


@dataclass(frozen=True)
class MaterialSpec:
    base_color: tuple[float, float, float, float]
    roughness: float
    metallic: float

    @staticmethod
    def parse(raw: object, path: str) -> MaterialSpec:
        mapping = _as_mapping(raw, path)
        _reject_unknown(mapping, ("base_color", "roughness", "metallic"), path)
        color_raw = _require(mapping, "base_color", path)
        if not isinstance(color_raw, list) or len(color_raw) != 4:
            raise SpecError(f"{path}.base_color: expected a list of 4 numbers (RGBA)")
        channels = tuple(as_float(component, f"{path}.base_color[{i}]") for i, component in enumerate(color_raw))
        for index, channel in enumerate(channels):
            if not 0.0 <= channel <= 1.0:
                raise SpecError(f"{path}.base_color[{index}]: expected 0..1, got {channel}")
        roughness = as_float(_require(mapping, "roughness", path), f"{path}.roughness")
        metallic = as_float(_require(mapping, "metallic", path), f"{path}.metallic")
        if not 0.0 <= roughness <= 1.0:
            raise SpecError(f"{path}.roughness: expected 0..1, got {roughness}")
        if not 0.0 <= metallic <= 1.0:
            raise SpecError(f"{path}.metallic: expected 0..1, got {metallic}")
        return MaterialSpec(
            base_color=(channels[0], channels[1], channels[2], channels[3]),
            roughness=roughness,
            metallic=metallic,
        )


@dataclass(frozen=True)
class QaSpec:
    max_triangles: int
    require_uvs: bool
    require_manifold: bool
    require_origin_at_base: bool
    max_dimension_m: float

    @staticmethod
    def parse(raw: object, path: str) -> QaSpec:
        mapping = _as_mapping(raw, path)
        allowed = (
            "max_triangles",
            "require_uvs",
            "require_manifold",
            "require_origin_at_base",
            "max_dimension_m",
        )
        _reject_unknown(mapping, allowed, path)
        return QaSpec(
            max_triangles=positive_int(_require(mapping, "max_triangles", path), f"{path}.max_triangles"),
            require_uvs=as_bool(_require(mapping, "require_uvs", path), f"{path}.require_uvs"),
            require_manifold=as_bool(_require(mapping, "require_manifold", path), f"{path}.require_manifold"),
            require_origin_at_base=as_bool(
                _require(mapping, "require_origin_at_base", path), f"{path}.require_origin_at_base"
            ),
            max_dimension_m=positive_float(
                _require(mapping, "max_dimension_m", path), f"{path}.max_dimension_m"
            ),
        )


@dataclass(frozen=True)
class AssetSpec:
    spec_version: int
    asset_id: str
    generator: str
    params: Mapping[str, object]
    materials: Mapping[str, MaterialSpec]
    qa: QaSpec
    source_path: Path

    @property
    def glb_name(self) -> str:
        return f"{self.asset_id}.glb"


def parse_spec(raw: object, source_path: Path) -> AssetSpec:
    path = source_path.name
    mapping = _as_mapping(raw, path)
    _reject_unknown(mapping, ("spec_version", "id", "generator", "params", "materials", "qa"), path)

    spec_version = as_int(_require(mapping, "spec_version", path), f"{path}.spec_version")
    if spec_version != SPEC_VERSION:
        raise SpecError(f"{path}.spec_version: expected {SPEC_VERSION}, got {spec_version}")

    asset_id = as_str(_require(mapping, "id", path), f"{path}.id")
    if not asset_id or not all(char.isalnum() or char in "_-" for char in asset_id):
        raise SpecError(f"{path}.id: must be non-empty and only contain letters, digits, '_' or '-'")

    generator = as_str(_require(mapping, "generator", path), f"{path}.generator")

    params = _as_mapping(_require(mapping, "params", path), f"{path}.params")

    materials_raw = _as_mapping(_require(mapping, "materials", path), f"{path}.materials")
    if not materials_raw:
        raise SpecError(f"{path}.materials: at least one material slot is required")
    materials = {
        name: MaterialSpec.parse(value, f"{path}.materials.{name}")
        for name, value in materials_raw.items()
    }

    qa = QaSpec.parse(_require(mapping, "qa", path), f"{path}.qa")

    return AssetSpec(
        spec_version=spec_version,
        asset_id=asset_id,
        generator=generator,
        params=params,
        materials=materials,
        qa=qa,
        source_path=source_path,
    )


def load_spec(path: Path) -> AssetSpec:
    if not path.is_file():
        raise SpecError(f"Spec file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecError(f"{path.name}: invalid JSON - {exc}") from exc
    return parse_spec(raw, path)


# Public aliases for generator modules, which parse their own `params` block.
as_mapping = _as_mapping
require_key = _require
reject_unknown = _reject_unknown


def require_materials(materials: Mapping[str, MaterialSpec], slots: Sequence[str], generator: str) -> None:
    """Fail loudly when a spec does not supply exactly the slots a generator needs."""
    missing = sorted(set(slots) - set(materials))
    extra = sorted(set(materials) - set(slots))
    problems: list[str] = []
    if missing:
        problems.append(f"missing material slot(s) {missing}")
    if extra:
        problems.append(f"unused material slot(s) {extra}")
    if problems:
        raise SpecError(f"generator '{generator}' requires slots {list(slots)}: " + "; ".join(problems))
