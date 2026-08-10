"""Parametric modular bridge mid-span.

One segment of a longer crossing. Authored along +X with flush cut faces at
x = ±segment_length/2 so two (or more) instances butt cleanly. Deck width is
along Y; Z is up with the base on Z=0 and the walking surface at deck_top.

Orrun tiles this mesh along a BridgeSite span; abutments / piers are separate
pieces or still procedural.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import bpy

from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_bool,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("structure", "deck")

_PARAM_KEYS = (
    "segment_length",
    "deck_width",
    "deck_thickness",
    "beam_depth",
    "beam_width",
    "beam_count",
    "joist_spacing",
    "joist_width",
    "joist_depth",
    "plank_count",
    "plank_gap",
    "parapet_height",
    "parapet_thickness",
    "rail_inset",
    "post_size",
    "brace",
    "bevel_width",
)


@dataclass(frozen=True)
class BridgeSpanParams:
    segment_length: float
    deck_width: float
    deck_thickness: float
    beam_depth: float
    beam_width: float
    beam_count: int
    joist_spacing: float
    joist_width: float
    joist_depth: float
    plank_count: int
    plank_gap: float
    parapet_height: float
    parapet_thickness: float
    rail_inset: float
    post_size: float
    brace: bool
    bevel_width: float

    @property
    def deck_top(self) -> float:
        return self.beam_depth + self.joist_depth + self.deck_thickness

    @property
    def half_length(self) -> float:
        return self.segment_length * 0.5

    @property
    def half_width(self) -> float:
        return self.deck_width * 0.5


def parse_params(raw: Mapping[str, object]) -> BridgeSpanParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = BridgeSpanParams(
        segment_length=positive_float(
            require_key(raw, "segment_length", path), f"{path}.segment_length"
        ),
        deck_width=positive_float(require_key(raw, "deck_width", path), f"{path}.deck_width"),
        deck_thickness=positive_float(
            require_key(raw, "deck_thickness", path), f"{path}.deck_thickness"
        ),
        beam_depth=positive_float(require_key(raw, "beam_depth", path), f"{path}.beam_depth"),
        beam_width=positive_float(require_key(raw, "beam_width", path), f"{path}.beam_width"),
        beam_count=positive_int(require_key(raw, "beam_count", path), f"{path}.beam_count"),
        joist_spacing=positive_float(
            require_key(raw, "joist_spacing", path), f"{path}.joist_spacing"
        ),
        joist_width=positive_float(require_key(raw, "joist_width", path), f"{path}.joist_width"),
        joist_depth=positive_float(require_key(raw, "joist_depth", path), f"{path}.joist_depth"),
        plank_count=positive_int(require_key(raw, "plank_count", path), f"{path}.plank_count"),
        plank_gap=positive_float(require_key(raw, "plank_gap", path), f"{path}.plank_gap"),
        parapet_height=positive_float(
            require_key(raw, "parapet_height", path), f"{path}.parapet_height"
        ),
        parapet_thickness=positive_float(
            require_key(raw, "parapet_thickness", path), f"{path}.parapet_thickness"
        ),
        rail_inset=positive_float(require_key(raw, "rail_inset", path), f"{path}.rail_inset"),
        post_size=positive_float(require_key(raw, "post_size", path), f"{path}.post_size"),
        brace=as_bool(require_key(raw, "brace", path), f"{path}.brace"),
        bevel_width=positive_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
    )
    _validate(params)
    return params


def _validate(params: BridgeSpanParams) -> None:
    if params.beam_count < 2:
        raise SpecError("params.beam_count must be at least 2 (outer beams carry the rails).")
    if params.beam_width * params.beam_count >= params.deck_width:
        raise SpecError(
            f"params: {params.beam_count} beams of width {params.beam_width} m do not fit "
            f"in deck_width {params.deck_width} m."
        )
    if params.parapet_thickness + params.rail_inset * 2.0 >= params.deck_width:
        raise SpecError("params: parapet_thickness and rail_inset leave no walking surface.")
    if params.plank_count * params.plank_gap >= params.segment_length:
        raise SpecError("params: plank_count / plank_gap do not fit in segment_length.")
    if params.joist_spacing >= params.segment_length:
        raise SpecError("params.joist_spacing must be shorter than segment_length.")
    if params.bevel_width >= min(params.deck_thickness, params.beam_width) * 0.45:
        raise SpecError("params.bevel_width is too large for the thinnest members.")


def _beam_ys(params: BridgeSpanParams) -> list[float]:
    if params.beam_count == 2:
        inset = params.half_width - params.beam_width * 0.5 - 0.05
        return [-inset, inset]
    span = params.deck_width - params.beam_width
    step = span / float(params.beam_count - 1)
    return [-params.half_width + params.beam_width * 0.5 + i * step for i in range(params.beam_count)]


def _joist_xs(params: BridgeSpanParams) -> list[float]:
    # Keep joists strictly inside the segment so cut faces stay flush for tiling.
    margin = params.joist_width * 0.5 + 0.02
    usable = params.segment_length - 2.0 * margin
    count = max(int(usable / params.joist_spacing) + 1, 2)
    step = usable / float(count - 1)
    start = -params.half_length + margin
    return [start + i * step for i in range(count)]


def _plank_bands(params: BridgeSpanParams) -> list[tuple[float, float]]:
    usable = params.segment_length - params.plank_gap * (params.plank_count - 1)
    plank = usable / float(params.plank_count)
    x = -params.half_length
    bands: list[tuple[float, float]] = []
    for _ in range(params.plank_count):
        bands.append((x, x + plank))
        x += plank + params.plank_gap
    return bands


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)

    half_l = params.half_length
    half_w = params.half_width
    beam_top = params.beam_depth
    joist_top = beam_top + params.joist_depth
    deck_top = params.deck_top

    builder = BoxBuilder(MATERIAL_SLOTS)

    # Longitudinal beams — full length, flush with the tile cuts.
    for y in _beam_ys(params):
        builder.add_box(
            (0.0, y, beam_top * 0.5),
            (params.segment_length, params.beam_width, params.beam_depth),
            "structure",
        )

    # Cross joists sitting on the beams.
    inner_half_w = half_w - 0.04
    for x in _joist_xs(params):
        builder.add_box(
            (x, 0.0, beam_top + params.joist_depth * 0.5),
            (params.joist_width, inner_half_w * 2.0, params.joist_depth),
            "structure",
        )

    # Deck planks (or solid deck courses) on top of the joists.
    walk_half = half_w - params.rail_inset
    for low_x, high_x in _plank_bands(params):
        builder.add_box_bounds(
            (low_x, -walk_half, joist_top),
            (high_x, walk_half, deck_top),
            "deck",
        )

    # Side parapets / handrails — also flush at the tile ends.
    rail_y = half_w - params.parapet_thickness * 0.5
    for sign in (-1.0, 1.0):
        builder.add_box(
            (0.0, sign * rail_y, deck_top + params.parapet_height * 0.5),
            (params.segment_length, params.parapet_thickness, params.parapet_height),
            "structure",
        )
        # Corner posts at each end of the rail (still inside the tile).
        post_x = half_l - params.post_size * 0.5 - 0.02
        for x_sign in (-1.0, 1.0):
            builder.add_box(
                (x_sign * post_x, sign * rail_y, deck_top + params.parapet_height * 0.55),
                (params.post_size, params.post_size, params.parapet_height * 1.1),
                "structure",
            )

    if params.brace:
        # Shallow X-braces under the deck, kept inside ±half_length.
        brace_len = params.segment_length * 0.42
        brace_z = params.beam_depth * 0.45
        for x_sign in (-1.0, 1.0):
            for y_sign in (-1.0, 1.0):
                builder.add_box(
                    (x_sign * brace_len * 0.25, y_sign * (half_w * 0.35), brace_z),
                    (brace_len * 0.5, params.joist_width * 0.7, params.joist_depth * 0.7),
                    "structure",
                )

    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    shade_flat(obj)
    unwrap(obj)

    # Stamp authored deck-top into custom property so runtime kits stay in sync
    # without guessing from mesh bounds.
    obj["orrun_deck_top"] = params.deck_top
    obj["orrun_segment_length"] = params.segment_length
    obj["orrun_deck_width"] = params.deck_width
    return [obj]
