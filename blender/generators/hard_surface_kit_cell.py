"""One-cell kit pieces: wall, corner, door, roof, plinth.

Authored Z-up, footprint centre at the origin, base on Z=0. The exterior wall
sits on +Y so glTF Y-up export maps it to engine -Z, matching Modular's local
wall-on-minus-Z convention.

Horizontal joins are a shiplap, not a gap and not a coplanar overlap. The outer
wythe extends past +X, the inner wythe past -X, so mated instances cover the
seam at different depths. Boxes in one mesh may interpenetrate; they must not
present coplanar outer faces to a neighbor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import bpy

from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_float,
    as_str,
    positive_float,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("structure", "trim")

_KINDS = ("wall", "corner", "door", "roof", "plinth")

_PARAM_KEYS = (
    "kind",
    "cell_xz",
    "cell_y",
    "wall_thickness",
    "overlap",
    "door_width",
    "door_height",
    "roof_height",
    "overhang",
    "bevel_width",
)


@dataclass(frozen=True)
class KitParams:
    kind: str
    cell_xz: float
    cell_y: float
    wall_thickness: float
    overlap: float
    door_width: float
    door_height: float
    roof_height: float
    overhang: float
    bevel_width: float

    @property
    def half(self) -> float:
        return self.cell_xz * 0.5


def parse_params(raw: Mapping[str, object]) -> KitParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    kind = as_str(require_key(raw, "kind", path), f"{path}.kind")
    if kind not in _KINDS:
        raise SpecError(f"{path}.kind: expected one of {_KINDS}, got {kind!r}")
    params = KitParams(
        kind=kind,
        cell_xz=positive_float(require_key(raw, "cell_xz", path), f"{path}.cell_xz"),
        cell_y=positive_float(require_key(raw, "cell_y", path), f"{path}.cell_y"),
        wall_thickness=positive_float(
            require_key(raw, "wall_thickness", path), f"{path}.wall_thickness"
        ),
        overlap=positive_float(require_key(raw, "overlap", path), f"{path}.overlap"),
        door_width=positive_float(require_key(raw, "door_width", path), f"{path}.door_width"),
        door_height=positive_float(
            require_key(raw, "door_height", path), f"{path}.door_height"
        ),
        roof_height=positive_float(
            require_key(raw, "roof_height", path), f"{path}.roof_height"
        ),
        overhang=positive_float(require_key(raw, "overhang", path), f"{path}.overhang"),
        bevel_width=as_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
    )
    _validate(params)
    return params


def _validate(params: KitParams) -> None:
    if params.wall_thickness >= params.cell_xz * 0.45:
        raise SpecError("params.wall_thickness leaves no interior in the cell.")
    if params.door_width >= params.cell_xz - params.wall_thickness * 2.0:
        raise SpecError("params.door_width leaves no wall beside the door.")
    if params.door_height >= params.cell_y:
        raise SpecError("params.door_height must be below cell_y.")
    if params.overlap >= params.wall_thickness * 0.4:
        raise SpecError("params.overlap must be smaller than 0.4 * wall_thickness.")
    if params.bevel_width < 0.0:
        raise SpecError("params.bevel_width must be >= 0.")
    if params.bevel_width >= params.overlap:
        raise SpecError("params.bevel_width must be smaller than overlap or seams will open.")
    if params.roof_height > params.cell_y:
        raise SpecError("params.roof_height must be <= cell_y.")
    if params.overhang > params.cell_xz * 0.2:
        raise SpecError("params.overhang must be <= 20% of cell_xz.")
    if params.half - params.overhang - 0.08 <= 0.0:
        raise SpecError("params.overhang leaves no roof cap.")


def _floor_slab(builder: BoxBuilder, params: KitParams, *, west_wall: bool, door: bool) -> None:
    """Interior slab. Stops inside the walls so it does not share an exterior face."""
    h = params.half
    t = params.wall_thickness
    sink = 0.03
    thickness = 0.08
    x0 = -h + t - sink if west_wall else -h
    x1 = h
    y0 = -h
    y1 = h - t + sink
    builder.add_box_bounds((x0, y0, 0.0), (x1, y1, thickness), "structure")
    if door:
        door_half = params.door_width * 0.5
        builder.add_box_bounds(
            (-door_half - 0.03, h - t, 0.0),
            (door_half + 0.03, h, thickness),
            "structure",
        )


def _south_span(params: KitParams, *, shiplap_neg: bool, shiplap_pos: bool, wythe: str) -> tuple[float, float]:
    h = params.half
    o = params.overlap
    x0 = -h
    x1 = h
    if wythe == "outer":
        if shiplap_pos:
            x1 = h + o
        if shiplap_neg:
            x0 = -h + o
    else:
        if shiplap_pos:
            x1 = h - o
        if shiplap_neg:
            x0 = -h - o
    return x0, x1


def _south_wythe_y(params: KitParams, wythe: str) -> tuple[float, float]:
    h = params.half
    t = params.wall_thickness
    half_t = t * 0.5
    if wythe == "outer":
        return (h - half_t, h)
    return (h - t, h - half_t + 0.02)


def _south_wall(
    builder: BoxBuilder,
    params: KitParams,
    *,
    shiplap_neg: bool,
    shiplap_pos: bool,
    door: bool,
) -> None:
    """Exterior slab on +Y. `shiplap_pos` covers the +X join; `shiplap_neg` the -X join."""
    t = params.wall_thickness
    o = params.overlap
    z_inner = params.cell_y
    z_outer = params.cell_y + o
    inner_y = _south_wythe_y(params, "inner")[0]
    if not door:
        for wythe, z1 in (("outer", z_outer), ("inner", z_inner)):
            x0, x1 = _south_span(
                params, shiplap_neg=shiplap_neg, shiplap_pos=shiplap_pos, wythe=wythe
            )
            y0, y1 = _south_wythe_y(params, wythe)
            builder.add_box_bounds((x0, y0, 0.0), (x1, y1, z1), "structure")
        x0, x1 = _south_span(
            params, shiplap_neg=shiplap_neg, shiplap_pos=shiplap_pos, wythe="inner"
        )
        _south_cornice(builder, params, x0, x1, inner_y, z_inner)
        return

    door_half = params.door_width * 0.5
    door_top = params.door_height
    join = 0.04
    left = {
        "outer": (_south_span(params, shiplap_neg=True, shiplap_pos=False, wythe="outer")[0], -door_half),
        "inner": (_south_span(params, shiplap_neg=True, shiplap_pos=False, wythe="inner")[0], -door_half),
    }
    right = {
        "outer": (door_half, _south_span(params, shiplap_neg=False, shiplap_pos=True, wythe="outer")[1]),
        "inner": (door_half, _south_span(params, shiplap_neg=False, shiplap_pos=True, wythe="inner")[1]),
    }
    for wythe, z1 in (("outer", z_outer), ("inner", z_inner)):
        y0, y1 = _south_wythe_y(params, wythe)
        lx0, lx1 = left[wythe]
        rx0, rx1 = right[wythe]
        builder.add_box_bounds((lx0, y0, 0.0), (lx1, y1, z1), "structure")
        builder.add_box_bounds((rx0, y0, 0.0), (rx1, y1, z1), "structure")
        builder.add_box_bounds(
            (-door_half - join, y0, door_top),
            (door_half + join, y1, z1),
            "structure",
        )
    _south_cornice(builder, params, left["inner"][0], -door_half, inner_y, z_inner)
    _south_cornice(builder, params, door_half, right["inner"][1], inner_y, z_inner)
    _south_cornice(builder, params, -door_half, door_half, inner_y, z_inner)

    frame = min(0.08, t * 0.5)
    proud = 0.02
    y0 = inner_y + 0.02
    y1 = params.half - 0.02
    builder.add_box_bounds(
        (-door_half - frame, y0, o),
        (-door_half + proud, y1, door_top),
        "trim",
    )
    builder.add_box_bounds(
        (door_half - proud, y0, o),
        (door_half + frame, y1, door_top),
        "trim",
    )
    builder.add_box_bounds(
        (-door_half - frame, y0, door_top - proud),
        (door_half + frame, y1, door_top + frame),
        "trim",
    )


def _south_cornice(
    builder: BoxBuilder,
    params: KitParams,
    x0: float,
    x1: float,
    inner_y: float,
    z1: float,
) -> None:
    """Interior top band, proud of the inner face so it does not z-fight the wall."""
    if x1 <= x0:
        raise SpecError("south cornice has empty span.")
    depth = 0.05
    height = 0.08
    sink = 0.03
    builder.add_box_bounds((x0, inner_y - depth, z1 - height), (x1, inner_y + sink, z1), "trim")


def _west_wall(builder: BoxBuilder, params: KitParams) -> None:
    """Exterior slab on -X. -Y end shiplaps the pos_z join; +Y end sinks into the south wall."""
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    half_t = t * 0.5
    sink = 0.04
    z_inner = params.cell_y
    z_outer = params.cell_y + o
    y_join = h - t + sink
    # Outer wythe short at -Y, inner extends — matches a neighbor whose outer extends +X
    # after the 90° yaw that mates pos_z to a +X join.
    builder.add_box_bounds((-h, -h + o, 0.0), (-h + half_t, y_join, z_outer), "structure")
    builder.add_box_bounds(
        (-h + half_t - 0.02, -h - o, 0.0),
        (-h + t, y_join, z_inner),
        "structure",
    )
    inner_x = -h + t
    builder.add_box_bounds(
        (inner_x - 0.03, -h - o, z_inner - 0.08),
        (inner_x + 0.05, y_join, z_inner),
        "trim",
    )


def _roof(builder: BoxBuilder, params: KitParams) -> None:
    """Stepped cap filling the cell. Layers interpenetrate in Z."""
    h = params.half
    layers = 3
    step = params.roof_height / layers
    sink = 0.02
    for index in range(layers):
        shrink = params.overhang * index / max(layers - 1, 1)
        z0 = index * step
        z1 = z0 + step + sink
        builder.add_box_bounds(
            (-h + shrink, -h + shrink, z0),
            (h - shrink, h - shrink, z1),
            "structure",
        )
    cap = h - params.overhang - 0.08
    z_top = layers * step
    builder.add_box_bounds((-cap, -cap, z_top - 0.04), (cap, cap, z_top + 0.06), "trim")


def _plinth(builder: BoxBuilder, params: KitParams) -> None:
    h = params.half
    top = params.cell_y + params.overlap
    builder.add_box_bounds((-h, -h, 0.0), (h, h, top), "structure")
    recess = 0.04
    builder.add_box_bounds(
        (-h + recess, -h + recess, top - 0.08),
        (h - recess, h - recess, top - 0.01),
        "trim",
    )


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = BoxBuilder(MATERIAL_SLOTS)
    if params.kind == "plinth":
        _plinth(builder, params)
    elif params.kind == "roof":
        _roof(builder, params)
    elif params.kind == "corner":
        _floor_slab(builder, params, west_wall=True, door=False)
        _south_wall(builder, params, shiplap_neg=False, shiplap_pos=True, door=False)
        _west_wall(builder, params)
    elif params.kind == "wall":
        _floor_slab(builder, params, west_wall=False, door=False)
        _south_wall(builder, params, shiplap_neg=True, shiplap_pos=True, door=False)
    elif params.kind == "door":
        _floor_slab(builder, params, west_wall=False, door=True)
        _south_wall(builder, params, shiplap_neg=True, shiplap_pos=True, door=True)
    else:
        raise SpecError(f"params.kind: unhandled {params.kind!r}")

    obj = builder.to_object(spec.asset_id, spec.materials)
    if params.bevel_width > 0.0:
        apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    shade_flat(obj)
    unwrap(obj)
    return [obj]
