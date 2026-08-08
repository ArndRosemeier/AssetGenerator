"""Parametric wooden crate.

Built from axis-aligned boxes: four corner posts wrapped in a plank skin, with
a planked floor and an optional planked lid. Boxes are allowed to interpenetrate
the way real timber overlaps; each box stays individually closed, so the result
is manifold without any boolean operations.
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

MATERIAL_SLOTS: tuple[str, ...] = ("frame", "planks")

_PARAM_KEYS = (
    "width",
    "depth",
    "height",
    "post_size",
    "plank_thickness",
    "plank_gap",
    "side_plank_count",
    "floor_plank_count",
    "lid",
    "bevel_width",
)


@dataclass(frozen=True)
class CrateParams:
    width: float
    depth: float
    height: float
    post_size: float
    plank_thickness: float
    plank_gap: float
    side_plank_count: int
    floor_plank_count: int
    lid: bool
    bevel_width: float


def parse_params(raw: Mapping[str, object]) -> CrateParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = CrateParams(
        width=positive_float(require_key(raw, "width", path), f"{path}.width"),
        depth=positive_float(require_key(raw, "depth", path), f"{path}.depth"),
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        post_size=positive_float(require_key(raw, "post_size", path), f"{path}.post_size"),
        plank_thickness=positive_float(
            require_key(raw, "plank_thickness", path), f"{path}.plank_thickness"
        ),
        plank_gap=positive_float(require_key(raw, "plank_gap", path), f"{path}.plank_gap"),
        side_plank_count=positive_int(
            require_key(raw, "side_plank_count", path), f"{path}.side_plank_count"
        ),
        floor_plank_count=positive_int(
            require_key(raw, "floor_plank_count", path), f"{path}.floor_plank_count"
        ),
        lid=as_bool(require_key(raw, "lid", path), f"{path}.lid"),
        bevel_width=positive_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
    )
    _validate(params)
    return params


def _validate(params: CrateParams) -> None:
    inner_width = params.width - 2.0 * params.plank_thickness
    inner_depth = params.depth - 2.0 * params.plank_thickness
    if inner_width <= 2.0 * params.post_size or inner_depth <= 2.0 * params.post_size:
        raise SpecError(
            f"params: corner posts do not fit. Inner footprint is "
            f"{inner_width:.3f} x {inner_depth:.3f} m but two posts need "
            f"{2 * params.post_size:.3f} m per axis."
        )
    if _band_size(params.height, params.side_plank_count, params.plank_gap) <= 0.0:
        raise SpecError(
            f"params: {params.side_plank_count} side planks with {params.plank_gap} m gaps "
            f"do not fit in a height of {params.height} m."
        )
    if _band_size(inner_depth, params.floor_plank_count, params.plank_gap) <= 0.0:
        raise SpecError(
            f"params: {params.floor_plank_count} floor planks with {params.plank_gap} m gaps "
            f"do not fit in an inner depth of {inner_depth:.3f} m."
        )
    if params.height <= params.plank_thickness * 2.0:
        raise SpecError(
            f"params.height ({params.height}) must exceed twice the plank thickness "
            f"({params.plank_thickness * 2}) so the corner posts have somewhere to go."
        )
    if params.bevel_width >= params.plank_thickness * 0.5:
        raise SpecError(
            f"params.bevel_width ({params.bevel_width}) must stay below half the plank "
            f"thickness ({params.plank_thickness / 2})."
        )


def _band_size(total: float, count: int, gap: float) -> float:
    """Size of one element when `count` elements share `total` with `gap` between them."""
    return (total - (count - 1) * gap) / count


def _band_starts(total: float, count: int, gap: float, offset: float) -> list[tuple[float, float]]:
    size = _band_size(total, count, gap)
    return [(offset + index * (size + gap), offset + index * (size + gap) + size) for index in range(count)]


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)

    half_width = params.width * 0.5
    half_depth = params.depth * 0.5
    thickness = params.plank_thickness
    post = params.post_size

    builder = BoxBuilder(MATERIAL_SLOTS)

    # Posts are sunk half a plank into the floor and lid rather than butting against
    # them: coplanar faces would z-fight in every renderer that sees the crate.
    post_bottom = thickness * 0.5
    post_top = params.height - thickness * 0.5 if params.lid else params.height
    post_inner_x = half_width - thickness - post
    post_inner_y = half_depth - thickness - post
    for sign_x in (-1.0, 1.0):
        for sign_y in (-1.0, 1.0):
            x_bounds = sorted((sign_x * (half_width - thickness), sign_x * post_inner_x))
            y_bounds = sorted((sign_y * (half_depth - thickness), sign_y * post_inner_y))
            builder.add_box_bounds(
                (x_bounds[0], y_bounds[0], post_bottom),
                (x_bounds[1], y_bounds[1], post_top),
                "frame",
            )

    bands = _band_starts(params.height, params.side_plank_count, params.plank_gap, 0.0)
    for low_z, high_z in bands:
        for sign_x in (-1.0, 1.0):
            x_bounds = sorted((sign_x * half_width, sign_x * (half_width - thickness)))
            builder.add_box_bounds(
                (x_bounds[0], -half_depth, low_z),
                (x_bounds[1], half_depth, high_z),
                "planks",
            )
        for sign_y in (-1.0, 1.0):
            y_bounds = sorted((sign_y * half_depth, sign_y * (half_depth - thickness)))
            builder.add_box_bounds(
                (-(half_width - thickness), y_bounds[0], low_z),
                (half_width - thickness, y_bounds[1], high_z),
                "planks",
            )

    inner_depth = params.depth - 2.0 * thickness
    floor_bands = _band_starts(
        inner_depth, params.floor_plank_count, params.plank_gap, -inner_depth * 0.5
    )
    inner_half_width = half_width - thickness
    for low_y, high_y in floor_bands:
        builder.add_box_bounds(
            (-inner_half_width, low_y, 0.0),
            (inner_half_width, high_y, thickness),
            "planks",
        )
        if params.lid:
            builder.add_box_bounds(
                (-inner_half_width, low_y, params.height - thickness),
                (inner_half_width, high_y, params.height),
                "planks",
            )

    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    shade_flat(obj)
    unwrap(obj)
    return [obj]
