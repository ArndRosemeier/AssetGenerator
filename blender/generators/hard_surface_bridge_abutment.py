"""Parametric bridge abutment / end-cap.

Flush +X face butts a mid span. The -X side flares into wing walls and a short
approach apron that reads as the bank landing. Same deck_top / width convention
as hard_surface.bridge_span so kits stay interchangeable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mathutils import Matrix, Vector

import bpy

from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap, world_bounds
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    positive_float,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("structure", "deck")

_PARAM_KEYS = (
    "length",
    "deck_width",
    "deck_thickness",
    "beam_depth",
    "parapet_height",
    "parapet_thickness",
    "wing_flare",
    "apron_drop",
    "bevel_width",
)


@dataclass(frozen=True)
class AbutmentParams:
    length: float
    deck_width: float
    deck_thickness: float
    beam_depth: float
    parapet_height: float
    parapet_thickness: float
    wing_flare: float
    apron_drop: float
    bevel_width: float

    @property
    def deck_top(self) -> float:
        return self.beam_depth + self.deck_thickness

    @property
    def half_l(self) -> float:
        return self.length * 0.5

    @property
    def half_w(self) -> float:
        return self.deck_width * 0.5


def parse_params(raw: Mapping[str, object]) -> AbutmentParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = AbutmentParams(
        length=positive_float(require_key(raw, "length", path), f"{path}.length"),
        deck_width=positive_float(require_key(raw, "deck_width", path), f"{path}.deck_width"),
        deck_thickness=positive_float(
            require_key(raw, "deck_thickness", path), f"{path}.deck_thickness"
        ),
        beam_depth=positive_float(require_key(raw, "beam_depth", path), f"{path}.beam_depth"),
        parapet_height=positive_float(
            require_key(raw, "parapet_height", path), f"{path}.parapet_height"
        ),
        parapet_thickness=positive_float(
            require_key(raw, "parapet_thickness", path), f"{path}.parapet_thickness"
        ),
        wing_flare=positive_float(require_key(raw, "wing_flare", path), f"{path}.wing_flare"),
        apron_drop=positive_float(require_key(raw, "apron_drop", path), f"{path}.apron_drop"),
        bevel_width=positive_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
    )
    if params.wing_flare > params.deck_width:
        raise SpecError("params.wing_flare must stay below deck_width.")
    if params.apron_drop >= params.deck_top:
        raise SpecError("params.apron_drop must stay below deck_top.")
    return params


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    half_l = params.half_l
    half_w = params.half_w
    deck_top = params.deck_top
    builder = BoxBuilder(MATERIAL_SLOTS)

    # Main beams + deck — flush at +X (mid join), slightly proud apron at -X.
    builder.add_box(
        (0.0, 0.0, params.beam_depth * 0.5),
        (params.length, params.deck_width * 0.85, params.beam_depth),
        "structure",
    )
    builder.add_box_bounds(
        (-half_l, -half_w + 0.05, params.beam_depth),
        (half_l, half_w - 0.05, deck_top),
        "deck",
    )

    # Parapets flush on the mid face (+X), flared on the bank face (-X).
    for sign in (-1.0, 1.0):
        y0 = sign * (half_w - params.parapet_thickness * 0.5)
        builder.add_box(
            (0.05, y0, deck_top + params.parapet_height * 0.5),
            (params.length - 0.1, params.parapet_thickness, params.parapet_height),
            "structure",
        )
        # Wing wall steps outward toward the bank (-X).
        wing_y = sign * (half_w + params.wing_flare * 0.5)
        builder.add_box_bounds(
            (-half_l - 0.15, wing_y - params.parapet_thickness * 0.5, 0.0),
            (-half_l + params.length * 0.4, wing_y + params.parapet_thickness * 0.5, deck_top + params.parapet_height),
            "structure",
        )

    # Bank apron: thicker support under the -X half, dropping toward ground.
    apron_z1 = max(params.deck_top - params.apron_drop, 0.08)
    builder.add_box_bounds(
        (-half_l - 0.35, -half_w - params.wing_flare * 0.3, 0.0),
        (-half_l + params.length * 0.35, half_w + params.wing_flare * 0.3, apron_z1),
        "structure",
    )

    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    lower, upper = world_bounds([obj])
    cx = (lower.x + upper.x) * 0.5
    cy = (lower.y + upper.y) * 0.5
    if abs(cx) > 1e-4 or abs(cy) > 1e-4:
        obj.data.transform(Matrix.Translation(Vector((-cx, -cy, 0.0))))
        obj.data.update()
    # Keep the mid-join face at +length/2 after recentre: shift so max X is +half_l.
    lower, upper = world_bounds([obj])
    shift_x = params.half_l - upper.x
    if abs(shift_x) > 1e-4:
        obj.data.transform(Matrix.Translation(Vector((shift_x, 0.0, 0.0))))
        obj.data.update()
    shade_flat(obj)
    unwrap(obj)
    obj["orrun_deck_top"] = params.deck_top
    obj["orrun_segment_length"] = params.length
    obj["orrun_deck_width"] = params.deck_width
    return [obj]
