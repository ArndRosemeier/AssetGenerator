"""Parametric swinging door leaf.

Two constructions share one generator:

* ``plank`` — boarded door: vertical planks over a backer, ledges and a
  diagonal brace on the back, strap hinges and a pull handle on the front.
* ``sturdy`` — bound entrance door: stile-and-rail frame, recessed panels,
  iron edge binding, strapped face with studs, long hinges, heavy furniture.

The origin is the hinge axis (X=0, thickness centred on Y, base on Z=0), not
the footprint centre. Engines open the door by rotating the glTF node around
local Y (authoring Z-up becomes glTF Y-up). ``hinge_side`` chooses whether the
leaf occupies +X (left hinge, default) or −X (right hinge).

Kit wall openings already supply a jamb; this mesh is the moving leaf only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import bpy

from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_bool,
    as_str,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("planks", "trim", "hardware")

_STYLES: tuple[str, ...] = ("plank", "sturdy")
_HINGE_SIDES: tuple[str, ...] = ("left", "right")

_SHARED_KEYS = (
    "style",
    "width",
    "height",
    "thickness",
    "hinge_side",
    "hinge_count",
    "hinge_length",
    "handle",
    "bevel_width",
)

_PLANK_KEYS = (
    "plank_count",
    "plank_gap",
    "ledge_count",
    "ledge_width",
    "ledge_proud",
    "brace",
)

_STURDY_KEYS = (
    "stile_width",
    "rail_width",
    "panel_inset",
    "strap_count",
    "strap_width",
    "studs_per_strap",
    "stud_size",
)

_SINK = 0.003
_GROOVE = 0.004
_RAIL_PROUD = 0.0025
_BIND_PROUD = 0.005
_STRAP_PROUD = 0.004
_HANDLE_PLATE = 0.004


@dataclass(frozen=True)
class DoorParams:
    style: str
    width: float
    height: float
    thickness: float
    hinge_side: str
    hinge_count: int
    hinge_length: float
    handle: bool
    bevel_width: float
    plank_count: int
    plank_gap: float
    ledge_count: int
    ledge_width: float
    ledge_proud: float
    brace: bool
    stile_width: float
    rail_width: float
    panel_inset: float
    strap_count: int
    strap_width: float
    studs_per_strap: int
    stud_size: float

    @property
    def half_t(self) -> float:
        return self.thickness * 0.5

    @property
    def hinge_sign(self) -> float:
        return 1.0 if self.hinge_side == "left" else -1.0


def parse_params(raw: Mapping[str, object]) -> DoorParams:
    path = "params"
    style = as_str(require_key(raw, "style", path), f"{path}.style")
    if style not in _STYLES:
        raise SpecError(f"{path}.style: expected one of {_STYLES}, got {style!r}")
    extra = _PLANK_KEYS if style == "plank" else _STURDY_KEYS
    reject_unknown(raw, _SHARED_KEYS + extra, path)

    hinge_side = as_str(require_key(raw, "hinge_side", path), f"{path}.hinge_side")
    if hinge_side not in _HINGE_SIDES:
        raise SpecError(
            f"{path}.hinge_side: expected one of {_HINGE_SIDES}, got {hinge_side!r}"
        )

    shared = dict(
        style=style,
        width=positive_float(require_key(raw, "width", path), f"{path}.width"),
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        thickness=positive_float(require_key(raw, "thickness", path), f"{path}.thickness"),
        hinge_side=hinge_side,
        hinge_count=positive_int(require_key(raw, "hinge_count", path), f"{path}.hinge_count"),
        hinge_length=positive_float(
            require_key(raw, "hinge_length", path), f"{path}.hinge_length"
        ),
        handle=as_bool(require_key(raw, "handle", path), f"{path}.handle"),
        bevel_width=positive_float(
            require_key(raw, "bevel_width", path), f"{path}.bevel_width"
        ),
    )
    if style == "plank":
        params = DoorParams(
            **shared,
            plank_count=positive_int(
                require_key(raw, "plank_count", path), f"{path}.plank_count"
            ),
            plank_gap=positive_float(
                require_key(raw, "plank_gap", path), f"{path}.plank_gap"
            ),
            ledge_count=positive_int(
                require_key(raw, "ledge_count", path), f"{path}.ledge_count"
            ),
            ledge_width=positive_float(
                require_key(raw, "ledge_width", path), f"{path}.ledge_width"
            ),
            ledge_proud=positive_float(
                require_key(raw, "ledge_proud", path), f"{path}.ledge_proud"
            ),
            brace=as_bool(require_key(raw, "brace", path), f"{path}.brace"),
            stile_width=0.1,
            rail_width=0.1,
            panel_inset=0.01,
            strap_count=1,
            strap_width=0.04,
            studs_per_strap=1,
            stud_size=0.012,
        )
    else:
        params = DoorParams(
            **shared,
            plank_count=4,
            plank_gap=0.006,
            ledge_count=3,
            ledge_width=0.1,
            ledge_proud=0.012,
            brace=False,
            stile_width=positive_float(
                require_key(raw, "stile_width", path), f"{path}.stile_width"
            ),
            rail_width=positive_float(
                require_key(raw, "rail_width", path), f"{path}.rail_width"
            ),
            panel_inset=positive_float(
                require_key(raw, "panel_inset", path), f"{path}.panel_inset"
            ),
            strap_count=positive_int(
                require_key(raw, "strap_count", path), f"{path}.strap_count"
            ),
            strap_width=positive_float(
                require_key(raw, "strap_width", path), f"{path}.strap_width"
            ),
            studs_per_strap=positive_int(
                require_key(raw, "studs_per_strap", path), f"{path}.studs_per_strap"
            ),
            stud_size=positive_float(
                require_key(raw, "stud_size", path), f"{path}.stud_size"
            ),
        )
    _validate(params)
    return params


def _validate(params: DoorParams) -> None:
    if params.width < 0.5 or params.width > 1.6:
        raise SpecError(
            f"params.width ({params.width}) must be between 0.5 m and 1.6 m."
        )
    if params.height < 1.4 or params.height > 2.6:
        raise SpecError(
            f"params.height ({params.height}) must be between 1.4 m and 2.6 m."
        )
    if params.thickness >= params.width * 0.2:
        raise SpecError(
            f"params.thickness ({params.thickness}) is too large for width "
            f"{params.width}."
        )
    if params.hinge_count < 2:
        raise SpecError(
            f"params.hinge_count ({params.hinge_count}) must be at least 2."
        )
    if params.hinge_length >= params.width * 0.85:
        raise SpecError(
            f"params.hinge_length ({params.hinge_length}) must stay below 85% of "
            f"width ({params.width})."
        )
    if params.style == "plank":
        _validate_plank(params)
    else:
        _validate_sturdy(params)
    smallest = _smallest_feature(params)
    if params.bevel_width >= smallest * 0.5:
        raise SpecError(
            f"params.bevel_width ({params.bevel_width}) must stay below half the "
            f"smallest feature ({smallest * 0.5:.4f} m)."
        )


def _validate_plank(params: DoorParams) -> None:
    if params.plank_count < 3:
        raise SpecError(
            f"params.plank_count ({params.plank_count}) must be at least 3 so the "
            "boarding reads as planks."
        )
    plank = _band_size(params.width, params.plank_count, params.plank_gap)
    if plank <= params.plank_gap:
        raise SpecError(
            f"params: {params.plank_count} planks with {params.plank_gap} m gaps "
            f"do not fit in a width of {params.width} m (plank would be {plank:.4f} m)."
        )
    if params.ledge_count < 2:
        raise SpecError(
            f"params.ledge_count ({params.ledge_count}) must be at least 2."
        )
    ledge_span = params.ledge_count * params.ledge_width
    if ledge_span >= params.height * 0.7:
        raise SpecError(
            f"params: {params.ledge_count} ledges of {params.ledge_width} m "
            f"({ledge_span:.3f} m) crowd a height of {params.height} m."
        )
    if params.ledge_proud >= params.thickness:
        raise SpecError(
            f"params.ledge_proud ({params.ledge_proud}) must stay below thickness "
            f"({params.thickness})."
        )


def _validate_sturdy(params: DoorParams) -> None:
    if params.stile_width * 2.0 >= params.width * 0.7:
        raise SpecError(
            f"params.stile_width ({params.stile_width}) leaves no panel in a "
            f"width of {params.width} m."
        )
    rails = params.rail_width + params.rail_width * 1.2 + params.rail_width
    if rails >= params.height * 0.65:
        raise SpecError(
            f"params.rail_width ({params.rail_width}) leaves no panel in a "
            f"height of {params.height} m (rails need {rails:.3f} m)."
        )
    if params.panel_inset >= params.thickness * 0.45:
        raise SpecError(
            f"params.panel_inset ({params.panel_inset}) must stay below 45% of "
            f"thickness ({params.thickness})."
        )
    if params.strap_count < 2:
        raise SpecError(
            f"params.strap_count ({params.strap_count}) must be at least 2."
        )
    if params.strap_width * params.strap_count >= params.height * 0.5:
        raise SpecError(
            f"params: {params.strap_count} straps of {params.strap_width} m "
            f"crowd a height of {params.height} m."
        )
    if params.stud_size >= params.strap_width * 0.85:
        raise SpecError(
            f"params.stud_size ({params.stud_size}) must stay below 85% of "
            f"strap_width ({params.strap_width})."
        )


def _smallest_feature(params: DoorParams) -> float:
    if params.style == "plank":
        return min(params.plank_gap, params.ledge_proud, params.thickness * 0.25)
    return min(params.stud_size, params.panel_inset, _BIND_PROUD, params.thickness * 0.2)


def _band_size(total: float, count: int, gap: float) -> float:
    return (total - (count - 1) * gap) / count


def _band_starts(total: float, count: int, gap: float, offset: float) -> list[tuple[float, float]]:
    size = _band_size(total, count, gap)
    return [
        (offset + index * (size + gap), offset + index * (size + gap) + size)
        for index in range(count)
    ]


def _distribute_counts(total: int, buckets: int) -> list[int]:
    if buckets <= 0:
        raise SpecError(f"Cannot distribute {total} items into {buckets} buckets.")
    base, remainder = divmod(total, buckets)
    return [base + (1 if index < remainder else 0) for index in range(buckets)]


def _fixed_bands(low: float, high: float, count: int, width: float) -> list[tuple[float, float]]:
    span = high - low
    if span <= width * count:
        raise SpecError(
            f"params: {count} bands of {width} m do not fit in {span:.3f} m."
        )
    if count == 1:
        mid = (low + high) * 0.5
        return [(mid - width * 0.5, mid + width * 0.5)]
    inner = span - width
    return [
        (low + inner * index / (count - 1), low + inner * index / (count - 1) + width)
        for index in range(count)
    ]


class _Leaf:
    """Places boxes in left-hinged coordinates, then mirrors X for a right hinge."""

    def __init__(self, builder: BoxBuilder, params: DoorParams) -> None:
        self._builder = builder
        self.p = params

    def span(self, x0: float, x1: float) -> tuple[float, float]:
        sign = self.p.hinge_sign
        a = x0 * sign
        b = x1 * sign
        return (min(a, b), max(a, b))

    def box(
        self,
        x0: float,
        y0: float,
        z0: float,
        x1: float,
        y1: float,
        z1: float,
        slot: str,
    ) -> None:
        xa, xb = self.span(x0, x1)
        self._builder.add_box_bounds((xa, y0, z0), (xb, y1, z1), slot)

    def oriented(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        slot: str,
        rotation: tuple[float, float, float],
    ) -> None:
        cx, cy, cz = center
        self._builder.add_box(
            (cx * self.p.hinge_sign, cy, cz),
            size,
            slot,
            rotation=(rotation[0], rotation[1] * self.p.hinge_sign, rotation[2]),
        )


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = BoxBuilder(MATERIAL_SLOTS)
    leaf = _Leaf(builder, params)
    if params.style == "plank":
        _build_plank(leaf)
    else:
        _build_sturdy(leaf)
    _build_hinges(leaf)
    if params.handle:
        _build_handle(leaf)

    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    shade_flat(obj)
    unwrap(obj)
    return [obj]


def _build_plank(leaf: _Leaf) -> None:
    p = leaf.p
    half = p.half_t
    # Backer sits behind the front face so plank gaps read as grooves, not holes.
    leaf.box(0.0, -half + _GROOVE, 0.0, p.width, half, p.height, "planks")
    for x0, x1 in _band_starts(p.width, p.plank_count, p.plank_gap, 0.0):
        leaf.box(x0, -half, 0.0, x1, half - _SINK, p.height, "planks")

    inset, ledges = _plank_ledges(p)
    for z0, z1 in ledges:
        leaf.box(
            inset,
            -half - p.ledge_proud,
            z0,
            p.width - inset,
            -half + _SINK,
            z1,
            "trim",
        )

    if p.brace and len(ledges) >= 2:
        _add_brace(leaf, ledges[0], ledges[-1], inset)


def _add_brace(
    leaf: _Leaf,
    lower: tuple[float, float],
    upper: tuple[float, float],
    inset: float,
) -> None:
    p = leaf.p
    x0 = inset + p.ledge_width * 0.15
    x1 = p.width - inset - p.ledge_width * 0.15
    z0 = lower[1] - _SINK
    z1 = upper[0] + _SINK
    dx = x1 - x0
    dz = z1 - z0
    length = math.hypot(dx, dz)
    if length <= 0.0:
        raise SpecError("params: brace collapsed; ledges are too close together.")
    angle = -math.atan2(dz, dx)
    leaf.oriented(
        ((x0 + x1) * 0.5, -p.half_t - p.ledge_proud * 0.45, (z0 + z1) * 0.5),
        (length + 0.03, p.ledge_proud * 0.85, p.ledge_width * 0.62),
        "trim",
        (0.0, angle, 0.0),
    )


def _build_sturdy(leaf: _Leaf) -> None:
    p = leaf.p
    half = p.half_t
    sw = p.stile_width
    top_rail = p.rail_width
    mid_rail = p.rail_width
    bot_rail = p.rail_width * 1.2
    mid_z0 = (p.height - mid_rail) * 0.5
    mid_z1 = mid_z0 + mid_rail
    rail_y0 = -half - _RAIL_PROUD
    rail_y1 = half + _RAIL_PROUD

    leaf.box(0.0, -half, 0.0, sw, half, p.height, "trim")
    leaf.box(p.width - sw, -half, 0.0, p.width, half, p.height, "trim")
    leaf.box(sw - _SINK, rail_y0, 0.0, p.width - sw + _SINK, rail_y1, bot_rail, "trim")
    leaf.box(
        sw - _SINK,
        rail_y0,
        p.height - top_rail,
        p.width - sw + _SINK,
        rail_y1,
        p.height,
        "trim",
    )
    leaf.box(sw - _SINK, rail_y0, mid_z0, p.width - sw + _SINK, rail_y1, mid_z1, "trim")

    panel_x0 = sw
    panel_x1 = p.width - sw
    panel_y0 = -half + p.panel_inset
    panel_y1 = half - p.panel_inset * 0.35
    panels = (
        (bot_rail, mid_z0),
        (mid_z1, p.height - top_rail),
    )
    molding = min(0.022, sw * 0.22)
    mold_y0 = -half - 0.002
    mold_y1 = -half + p.panel_inset * 0.55
    for z0, z1 in panels:
        leaf.box(panel_x0, panel_y0, z0, panel_x1, panel_y1, z1, "planks")
        # Inner molding sits proud of the stile face and sinks into the panel.
        leaf.box(
            panel_x0 - _SINK,
            mold_y0,
            z0 - _SINK,
            panel_x0 + molding,
            mold_y1,
            z1 + _SINK,
            "trim",
        )
        leaf.box(
            panel_x1 - molding,
            mold_y0,
            z0 - _SINK,
            panel_x1 + _SINK,
            mold_y1,
            z1 + _SINK,
            "trim",
        )
        leaf.box(
            panel_x0 + molding - _SINK,
            mold_y0,
            z0 - _SINK,
            panel_x1 - molding + _SINK,
            mold_y1,
            z0 + molding,
            "trim",
        )
        leaf.box(
            panel_x0 + molding - _SINK,
            mold_y0,
            z1 - molding,
            panel_x1 - molding + _SINK,
            mold_y1,
            z1 + _SINK,
            "trim",
        )

    bind = min(0.02, sw * 0.22)
    front = -half - _BIND_PROUD
    leaf.box(0.0, front, 0.0, bind, -half + _SINK, p.height, "hardware")
    leaf.box(p.width - bind, front, 0.0, p.width, -half + _SINK, p.height, "hardware")
    leaf.box(bind - _SINK, front, 0.0, p.width - bind + _SINK, -half + _SINK, bind, "hardware")
    leaf.box(
        bind - _SINK,
        front,
        p.height - bind,
        p.width - bind + _SINK,
        -half + _SINK,
        p.height,
        "hardware",
    )

    strap_front = -half - _BIND_PROUD - _STRAP_PROUD
    margin = bind + 0.012
    pad = 0.03
    panel_ranges = (
        (bot_rail + pad, mid_z0 - pad),
        (mid_z1 + pad, p.height - top_rail - pad),
    )
    assignments = _distribute_counts(p.strap_count, len(panel_ranges))
    for (pz0, pz1), count in zip(panel_ranges, assignments):
        if count == 0:
            raise SpecError(
                f"params.strap_count ({p.strap_count}) left a panel without a strap."
            )
        span = pz1 - pz0
        if span <= p.strap_width * count:
            raise SpecError(
                f"params: {count} straps of {p.strap_width} m do not fit in a "
                f"panel span of {span:.3f} m."
            )
        for z0, z1 in _fixed_bands(pz0, pz1, count, p.strap_width):
            z_mid = (z0 + z1) * 0.5
            leaf.box(margin, strap_front, z0, p.width - margin, -half + _SINK, z1, "hardware")
            stud_span = p.width - 2.0 * margin - p.stud_size
            for stud_i in range(p.studs_per_strap):
                u = (stud_i + 0.5) / p.studs_per_strap
                sx = margin + p.stud_size * 0.5 + u * stud_span
                half_s = p.stud_size * 0.5
                leaf.box(
                    sx - half_s,
                    strap_front - p.stud_size * 0.45,
                    z_mid - half_s,
                    sx + half_s,
                    strap_front + _SINK,
                    z_mid + half_s,
                    "hardware",
                )


def _plank_ledges(params: DoorParams) -> tuple[float, list[tuple[float, float]]]:
    inset = min(0.045, params.width * 0.06)
    usable = params.height - 2.0 * inset
    ledge_gap = (usable - params.ledge_count * params.ledge_width) / (params.ledge_count - 1)
    ledges: list[tuple[float, float]] = []
    cursor = inset
    for _ in range(params.ledge_count):
        ledges.append((cursor, cursor + params.ledge_width))
        cursor += params.ledge_width + ledge_gap
    return inset, ledges


def _hinge_centers(params: DoorParams) -> list[float]:
    if params.style == "plank":
        _inset, ledges = _plank_ledges(params)
        centers = [(z0 + z1) * 0.5 for z0, z1 in ledges]
        if params.hinge_count > len(centers):
            raise SpecError(
                f"params.hinge_count ({params.hinge_count}) exceeds ledge_count "
                f"({params.ledge_count}); hinges mount on ledges."
            )
        if params.hinge_count == 1:
            return [centers[len(centers) // 2]]
        if params.hinge_count == 2:
            return [centers[0], centers[-1]]
        step = (len(centers) - 1) / (params.hinge_count - 1)
        return [centers[round(index * step)] for index in range(params.hinge_count)]

    top_rail = params.rail_width
    mid_rail = params.rail_width
    bot_rail = params.rail_width * 1.2
    rails = (
        bot_rail * 0.5,
        (params.height - mid_rail) * 0.5 + mid_rail * 0.5,
        params.height - top_rail * 0.5,
    )
    if params.hinge_count > 3:
        raise SpecError(
            f"params.hinge_count ({params.hinge_count}) cannot exceed 3 on a "
            "sturdy door (one hinge per rail)."
        )
    if params.hinge_count == 2:
        return [rails[0], rails[2]]
    return list(rails)


def _build_hinges(leaf: _Leaf) -> None:
    p = leaf.p
    half = p.half_t
    knuckle = min(0.032, p.thickness * 0.9)
    if p.style == "plank":
        strap_h = min(p.ledge_width * 0.7, 0.042)
        leaf_front = -half - p.ledge_proud
    else:
        strap_h = min(0.05, p.rail_width * 0.42)
        leaf_front = -half - _BIND_PROUD - _STRAP_PROUD
    strap_t = 0.008
    for z_mid in _hinge_centers(p):
        z0 = z_mid - strap_h * 0.5
        z1 = z_mid + strap_h * 0.5
        # Barrel: three stacked knuckles so the pivot reads as a hinge, not a block.
        barrel_w = knuckle * 0.55
        for part, y0, y1 in (
            (0, -knuckle * 0.5, -knuckle * 0.12),
            (1, -knuckle * 0.14, knuckle * 0.14),
            (2, knuckle * 0.12, knuckle * 0.5),
        ):
            lift = 0.0015 if part == 1 else 0.0
            leaf.box(
                -barrel_w,
                y0,
                z0 + lift,
                barrel_w,
                y1,
                z1 - lift,
                "hardware",
            )
        strap_end = min(p.hinge_length, p.width * 0.72)
        leaf.box(barrel_w * 0.2, leaf_front - strap_t, z0, strap_end, leaf_front + _SINK, z1, "hardware")
        if p.style == "sturdy":
            # Second, narrower strap step so the hinge tapers across the leaf.
            mid = strap_end * 0.55
            leaf.box(
                mid,
                leaf_front - strap_t * 0.7,
                z0 + strap_h * 0.18,
                strap_end * 1.05,
                leaf_front + _SINK,
                z1 - strap_h * 0.18,
                "hardware",
            )


def _build_handle(leaf: _Leaf) -> None:
    p = leaf.p
    half = p.half_t
    front = -half - (_BIND_PROUD if p.style == "sturdy" else 0.0)
    latch_x = p.width - min(0.13, p.width * 0.14)
    z_mid = p.height * (0.46 if p.style == "plank" else 0.48)
    if p.style == "plank":
        plate_w, plate_h = 0.062, 0.15
        grip_w, grip_d, grip_h = 0.016, 0.038, 0.086
    else:
        plate_w, plate_h = 0.078, 0.18
        grip_w, grip_d, grip_h = 0.02, 0.042, 0.1

    leaf.box(
        latch_x - plate_w * 0.5,
        front - _HANDLE_PLATE,
        z_mid - plate_h * 0.5,
        latch_x + plate_w * 0.5,
        front + _SINK,
        z_mid + plate_h * 0.5,
        "hardware",
    )
    post_z0 = z_mid - grip_h * 0.5
    post_z1 = z_mid + grip_h * 0.5
    post_x0 = latch_x - grip_w * 0.5
    post_x1 = latch_x + grip_w * 0.5
    leaf.box(post_x0, front - grip_d, post_z0, post_x1, front + _SINK, post_z0 + grip_w, "hardware")
    leaf.box(post_x0, front - grip_d, post_z1 - grip_w, post_x1, front + _SINK, post_z1, "hardware")
    leaf.box(
        post_x0,
        front - grip_d,
        post_z0 + grip_w - _SINK,
        post_x1,
        front - grip_d + grip_w,
        post_z1 - grip_w + _SINK,
        "hardware",
    )

    if p.style == "sturdy":
        lock_w, lock_h = 0.055, 0.07
        lock_z = z_mid - plate_h * 0.5 - lock_h * 0.65
        leaf.box(
            latch_x - lock_w * 0.5,
            front - _HANDLE_PLATE,
            lock_z - lock_h * 0.5,
            latch_x + lock_w * 0.5,
            front + _SINK,
            lock_z + lock_h * 0.5,
            "hardware",
        )
        key_r = 0.01
        leaf.box(
            latch_x - key_r,
            front - _HANDLE_PLATE - 0.003,
            lock_z - key_r,
            latch_x + key_r,
            front - _HANDLE_PLATE + _SINK,
            lock_z + key_r,
            "hardware",
        )
