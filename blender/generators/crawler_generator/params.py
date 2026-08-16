"""Strict params for the crawler body-plan generator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from blender.lib.spec import (
    SpecError,
    as_bool,
    as_float,
    as_int,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
)

PARAM_KEYS: tuple[str, ...] = (
    "body_length",
    "body_width",
    "body_height",
    "abdomen_length",
    "abdomen_width",
    "abdomen_height",
    "leg_pairs",
    "leg_segments",
    "leg_span",
    "leg_thickness",
    "stinger",
    "stinger_length",
    "stinger_thickness",
    "antennae",
    "antennae_length",
    "antennae_thickness",
    "mandibles",
    "mandible_length",
    "mandible_thickness",
    "idle_amp",
    "walk_hz",
    "run_hz",
    "texture_resolution",
    "bake_samples",
    "seed",
)

_LEG_PAIRS_MIN = 3
_LEG_PAIRS_MAX = 5
_LEG_SEGMENTS_MIN = 3
_LEG_SEGMENTS_MAX = 4
_TEXTURE_RESOLUTIONS = frozenset({256, 512, 1024, 2048})


@dataclass(frozen=True)
class CrawlerParams:
    body_length: float
    body_width: float
    body_height: float
    abdomen_length: float
    abdomen_width: float
    abdomen_height: float
    leg_pairs: int
    leg_segments: int
    leg_span: float
    leg_thickness: float
    stinger: bool
    stinger_length: float
    stinger_thickness: float
    antennae: bool
    antennae_length: float
    antennae_thickness: float
    mandibles: bool
    mandible_length: float
    mandible_thickness: float
    idle_amp: float
    walk_hz: float
    run_hz: float
    texture_resolution: int
    bake_samples: int
    seed: int


def _unit_interval(value: object, path: str) -> float:
    number = as_float(value, path)
    if not 0.0 <= number <= 1.0:
        raise SpecError(f"{path}: expected 0..1, got {number}")
    return number


def parse_params(raw: Mapping[str, object]) -> CrawlerParams:
    path = "params"
    reject_unknown(raw, PARAM_KEYS, path)
    params = CrawlerParams(
        body_length=positive_float(require_key(raw, "body_length", path), f"{path}.body_length"),
        body_width=positive_float(require_key(raw, "body_width", path), f"{path}.body_width"),
        body_height=positive_float(require_key(raw, "body_height", path), f"{path}.body_height"),
        abdomen_length=positive_float(
            require_key(raw, "abdomen_length", path), f"{path}.abdomen_length"
        ),
        abdomen_width=positive_float(
            require_key(raw, "abdomen_width", path), f"{path}.abdomen_width"
        ),
        abdomen_height=positive_float(
            require_key(raw, "abdomen_height", path), f"{path}.abdomen_height"
        ),
        leg_pairs=positive_int(require_key(raw, "leg_pairs", path), f"{path}.leg_pairs"),
        leg_segments=positive_int(require_key(raw, "leg_segments", path), f"{path}.leg_segments"),
        leg_span=positive_float(require_key(raw, "leg_span", path), f"{path}.leg_span"),
        leg_thickness=positive_float(
            require_key(raw, "leg_thickness", path), f"{path}.leg_thickness"
        ),
        stinger=as_bool(require_key(raw, "stinger", path), f"{path}.stinger"),
        stinger_length=positive_float(
            require_key(raw, "stinger_length", path), f"{path}.stinger_length"
        ),
        stinger_thickness=positive_float(
            require_key(raw, "stinger_thickness", path), f"{path}.stinger_thickness"
        ),
        antennae=as_bool(require_key(raw, "antennae", path), f"{path}.antennae"),
        antennae_length=positive_float(
            require_key(raw, "antennae_length", path), f"{path}.antennae_length"
        ),
        antennae_thickness=positive_float(
            require_key(raw, "antennae_thickness", path), f"{path}.antennae_thickness"
        ),
        mandibles=as_bool(require_key(raw, "mandibles", path), f"{path}.mandibles"),
        mandible_length=positive_float(
            require_key(raw, "mandible_length", path), f"{path}.mandible_length"
        ),
        mandible_thickness=positive_float(
            require_key(raw, "mandible_thickness", path), f"{path}.mandible_thickness"
        ),
        idle_amp=_unit_interval(require_key(raw, "idle_amp", path), f"{path}.idle_amp"),
        walk_hz=positive_float(require_key(raw, "walk_hz", path), f"{path}.walk_hz"),
        run_hz=positive_float(require_key(raw, "run_hz", path), f"{path}.run_hz"),
        texture_resolution=positive_int(
            require_key(raw, "texture_resolution", path), f"{path}.texture_resolution"
        ),
        bake_samples=positive_int(require_key(raw, "bake_samples", path), f"{path}.bake_samples"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    _validate(params)
    return params


def _validate(params: CrawlerParams) -> None:
    if not _LEG_PAIRS_MIN <= params.leg_pairs <= _LEG_PAIRS_MAX:
        raise SpecError(
            f"params.leg_pairs ({params.leg_pairs}) must be "
            f"{_LEG_PAIRS_MIN}..{_LEG_PAIRS_MAX} (pairs, not individual legs)"
        )
    if not _LEG_SEGMENTS_MIN <= params.leg_segments <= _LEG_SEGMENTS_MAX:
        raise SpecError(
            f"params.leg_segments ({params.leg_segments}) must be "
            f"{_LEG_SEGMENTS_MIN}..{_LEG_SEGMENTS_MAX}"
        )
    if params.leg_thickness * 2.0 >= params.leg_span:
        raise SpecError(
            f"params.leg_thickness ({params.leg_thickness}) is too fat for "
            f"leg_span {params.leg_span}"
        )
    if params.texture_resolution not in _TEXTURE_RESOLUTIONS:
        raise SpecError(
            f"params.texture_resolution ({params.texture_resolution}) must be one of "
            f"{sorted(_TEXTURE_RESOLUTIONS)}"
        )
    if params.bake_samples > 128:
        raise SpecError(f"params.bake_samples ({params.bake_samples}) must be <= 128")
    if params.run_hz <= params.walk_hz:
        raise SpecError(
            f"params.run_hz ({params.run_hz}) must be greater than walk_hz ({params.walk_hz})"
        )
    if params.body_height >= params.leg_span:
        raise SpecError(
            f"params.body_height ({params.body_height}) must be smaller than "
            f"leg_span {params.leg_span}"
        )
