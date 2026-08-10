"""Parametric stylized cabin / house.

Axis-aligned box kit: foundation plinth, walls with door and window frames,
a stepped gable roof, optional chimney and porch. Origin at footprint centre,
base of the plinth on Z=0 so game seating can bury most of the foundation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import bpy

from mathutils import Matrix, Vector

from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap, world_bounds
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

MATERIAL_SLOTS: tuple[str, ...] = ("walls", "roof", "trim")

_PARAM_KEYS = (
    "width",
    "depth",
    "wall_height",
    "wall_thickness",
    "roof_height",
    "roof_overhang",
    "roof_layers",
    "door_width",
    "door_height",
    "window_width",
    "window_height",
    "window_count",
    "chimney",
    "porch",
    "porch_depth",
    "bevel_width",
    "foundation_height",
    "foundation_overhang",
)


@dataclass(frozen=True)
class CabinParams:
    width: float
    depth: float
    wall_height: float
    wall_thickness: float
    roof_height: float
    roof_overhang: float
    roof_layers: int
    door_width: float
    door_height: float
    window_width: float
    window_height: float
    window_count: int
    chimney: bool
    porch: bool
    porch_depth: float
    bevel_width: float
    ## Plinth under the walls. Origin stays at its bottom so game sinks can bury
    ## most of it without the wall bottoms reading as floating in mid-air.
    foundation_height: float
    foundation_overhang: float

    @property
    def half_w(self) -> float:
        return self.width * 0.5

    @property
    def half_d(self) -> float:
        return self.depth * 0.5

    @property
    def floor_z(self) -> float:
        return self.foundation_height


def parse_params(raw: Mapping[str, object]) -> CabinParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = CabinParams(
        width=positive_float(require_key(raw, "width", path), f"{path}.width"),
        depth=positive_float(require_key(raw, "depth", path), f"{path}.depth"),
        wall_height=positive_float(
            require_key(raw, "wall_height", path), f"{path}.wall_height"
        ),
        wall_thickness=positive_float(
            require_key(raw, "wall_thickness", path), f"{path}.wall_thickness"
        ),
        roof_height=positive_float(
            require_key(raw, "roof_height", path), f"{path}.roof_height"
        ),
        roof_overhang=positive_float(
            require_key(raw, "roof_overhang", path), f"{path}.roof_overhang"
        ),
        roof_layers=positive_int(require_key(raw, "roof_layers", path), f"{path}.roof_layers"),
        door_width=positive_float(require_key(raw, "door_width", path), f"{path}.door_width"),
        door_height=positive_float(
            require_key(raw, "door_height", path), f"{path}.door_height"
        ),
        window_width=positive_float(
            require_key(raw, "window_width", path), f"{path}.window_width"
        ),
        window_height=positive_float(
            require_key(raw, "window_height", path), f"{path}.window_height"
        ),
        window_count=positive_int(
            require_key(raw, "window_count", path), f"{path}.window_count"
        ),
        chimney=as_bool(require_key(raw, "chimney", path), f"{path}.chimney"),
        porch=as_bool(require_key(raw, "porch", path), f"{path}.porch"),
        porch_depth=positive_float(
            require_key(raw, "porch_depth", path), f"{path}.porch_depth"
        ),
        bevel_width=positive_float(
            require_key(raw, "bevel_width", path), f"{path}.bevel_width"
        ),
        foundation_height=positive_float(
            require_key(raw, "foundation_height", path), f"{path}.foundation_height"
        ),
        foundation_overhang=positive_float(
            require_key(raw, "foundation_overhang", path), f"{path}.foundation_overhang"
        ),
    )
    _validate(params)
    return params


def _validate(params: CabinParams) -> None:
    if params.door_width >= params.width - params.wall_thickness * 2.0:
        raise SpecError("params.door_width leaves no wall beside the door.")
    if params.door_height >= params.wall_height:
        raise SpecError("params.door_height must be below wall_height.")
    if params.roof_layers > 8:
        raise SpecError("params.roof_layers must be <= 8.")
    if params.window_count > 6:
        raise SpecError("params.window_count must be <= 6.")
    if params.bevel_width >= params.wall_thickness * 0.45:
        raise SpecError("params.bevel_width is too large for wall_thickness.")
    if params.foundation_height > 1.8:
        raise SpecError("params.foundation_height must be <= 1.8.")
    if params.foundation_overhang > 0.6:
        raise SpecError("params.foundation_overhang must be <= 0.6.")


def _add_foundation(builder: BoxBuilder, params: CabinParams) -> None:
    """Stone/wood plinth from Z=0 up to floor_z — burial clearance for game seating."""
    if params.foundation_height <= 0.001:
        return
    over = params.foundation_overhang
    builder.add_box_bounds(
        (-params.half_w - over, -params.half_d - over, 0.0),
        (params.half_w + over, params.half_d + over, params.foundation_height),
        "trim",
    )


def _add_wall_front(builder: BoxBuilder, params: CabinParams) -> None:
    """+Y face: door opening in the middle, wall slabs on either side and lintel."""
    t = params.wall_thickness
    z0 = params.floor_z
    z1 = z0 + params.wall_height
    y0 = params.half_d - t
    y1 = params.half_d
    door_half = params.door_width * 0.5
    door_top = z0 + params.door_height
    # Left / right of door
    if -params.half_w < -door_half:
        builder.add_box_bounds(
            (-params.half_w, y0, z0),
            (-door_half, y1, z1),
            "walls",
        )
    if door_half < params.half_w:
        builder.add_box_bounds(
            (door_half, y0, z0),
            (params.half_w, y1, z1),
            "walls",
        )
    # Lintel above door
    if params.door_height < params.wall_height:
        builder.add_box_bounds(
            (-door_half, y0, door_top),
            (door_half, y1, z1),
            "walls",
        )
    # Door frame trim
    frame = min(0.08, t * 0.55)
    builder.add_box_bounds(
        (-door_half - frame, y0 - 0.01, z0),
        (-door_half, y1 + 0.01, door_top),
        "trim",
    )
    builder.add_box_bounds(
        (door_half, y0 - 0.01, z0),
        (door_half + frame, y1 + 0.01, door_top),
        "trim",
    )
    builder.add_box_bounds(
        (-door_half - frame, y0 - 0.01, door_top),
        (door_half + frame, y1 + 0.01, door_top + frame),
        "trim",
    )


def _add_wall_back(builder: BoxBuilder, params: CabinParams) -> None:
    t = params.wall_thickness
    z0 = params.floor_z
    builder.add_box_bounds(
        (-params.half_w, -params.half_d, z0),
        (params.half_w, -params.half_d + t, z0 + params.wall_height),
        "walls",
    )


def _add_side_walls(builder: BoxBuilder, params: CabinParams) -> None:
    """Solid ±X walls with shallow window frames (no cutouts — keeps topology simple)."""
    t = params.wall_thickness
    z0 = params.floor_z
    z1 = z0 + params.wall_height
    inner_d0 = -params.half_d + t
    inner_d1 = params.half_d - t
    win_h0 = z0 + params.wall_height * 0.38
    win_h1 = win_h0 + params.window_height

    for sign in (-1.0, 1.0):
        x0 = sign * params.half_w - (t if sign > 0.0 else 0.0)
        x1 = sign * params.half_w + (0.0 if sign > 0.0 else t)
        builder.add_box_bounds((x0, inner_d0, z0), (x1, inner_d1, z1), "walls")

    if params.window_count <= 0:
        return

    # Distribute frames along both long sides.
    per_side = max((params.window_count + 1) // 2, 1)
    for sign in (-1.0, 1.0):
        slots = per_side if sign > 0.0 else max(params.window_count - per_side, 0)
        if slots <= 0:
            continue
        usable = params.depth - 2.0 * t
        for i in range(slots):
            y = inner_d0 + usable * (float(i) + 0.5) / float(slots)
            if sign > 0.0:
                x0, x1 = params.half_w - 0.02, params.half_w + 0.04
            else:
                x0, x1 = -params.half_w - 0.04, -params.half_w + 0.02
            builder.add_box_bounds(
                (x0, y - params.window_width * 0.5, win_h0),
                (x1, y + params.window_width * 0.5, win_h1),
                "trim",
            )


def _add_roof(builder: BoxBuilder, params: CabinParams) -> None:
    layers = params.roof_layers
    layer_h = params.roof_height / float(layers)
    overhang = params.roof_overhang
    eaves = params.floor_z + params.wall_height
    for i in range(layers):
        t = float(i) / float(max(layers - 1, 1))
        # Shrink across width for a blocky gable; keep depth with overhang.
        half_w = params.half_w + overhang - t * (params.half_w * 0.92)
        half_d = params.half_d + overhang
        z0 = eaves + i * layer_h
        z1 = z0 + layer_h * 1.05
        builder.add_box_bounds((-half_w, -half_d, z0), (half_w, half_d, z1), "roof")


def _add_chimney(builder: BoxBuilder, params: CabinParams) -> None:
    size = min(0.55, params.width * 0.12)
    x = params.half_w * 0.35
    y = -params.half_d * 0.15
    z0 = params.floor_z + params.wall_height * 0.55
    z1 = params.floor_z + params.wall_height + params.roof_height + 0.55
    builder.add_box_bounds(
        (x - size * 0.5, y - size * 0.5, z0),
        (x + size * 0.5, y + size * 0.5, z1),
        "trim",
    )


def _add_porch(builder: BoxBuilder, params: CabinParams) -> None:
    depth = params.porch_depth
    y0 = params.half_d
    y1 = params.half_d + depth
    deck_h = 0.18
    z0 = params.floor_z
    builder.add_box_bounds(
        (-params.half_w * 0.7, y0, z0),
        (params.half_w * 0.7, y1, z0 + deck_h),
        "trim",
    )
    post = 0.14
    roof_z = z0 + params.wall_height * 0.72
    for x_sign in (-1.0, 1.0):
        x = x_sign * params.half_w * 0.55
        builder.add_box_bounds(
            (x - post * 0.5, y1 - post, z0),
            (x + post * 0.5, y1, roof_z),
            "trim",
        )
    builder.add_box_bounds(
        (-params.half_w * 0.72, y0, roof_z),
        (params.half_w * 0.72, y1 + 0.05, roof_z + 0.12),
        "roof",
    )


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = BoxBuilder(MATERIAL_SLOTS)

    _add_foundation(builder, params)
    _add_wall_front(builder, params)
    _add_wall_back(builder, params)
    _add_side_walls(builder, params)

    # Floor slab on top of the plinth so the interior reads solid.
    z_floor = params.floor_z
    builder.add_box_bounds(
        (
            -params.half_w + params.wall_thickness,
            -params.half_d + params.wall_thickness,
            z_floor,
        ),
        (
            params.half_w - params.wall_thickness,
            params.half_d - params.wall_thickness,
            z_floor + 0.08,
        ),
        "trim",
    )

    _add_roof(builder, params)
    if params.chimney:
        _add_chimney(builder, params)
    if params.porch:
        _add_porch(builder, params)

    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    # Porch / overhang can bias the AABB; snap footprint centre back to origin
    # while keeping the base on Z=0.
    lower, upper = world_bounds([obj])
    centre_x = (lower.x + upper.x) * 0.5
    centre_y = (lower.y + upper.y) * 0.5
    if abs(centre_x) > 1e-4 or abs(centre_y) > 1e-4:
        obj.data.transform(Matrix.Translation(Vector((-centre_x, -centre_y, 0.0))))
        obj.data.update()
    shade_flat(obj)
    unwrap(obj)
    return [obj]
