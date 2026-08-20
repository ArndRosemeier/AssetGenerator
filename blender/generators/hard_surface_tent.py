"""Parametric one-occupancy A-frame canvas tent.

Wedge canvas on wooden poles with guy-line pegs, all overlapping closed boxes.
Open / half-open front so it reads as a tent, not a house. No thatch, timber
frame, chimney or windows. Origin is footprint centre, base on Z=0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import bpy
from mathutils import Euler, Vector

from blender.generators.hard_surface_kit_cell import build_look_material
from blender.lib.bake import apply_baked_principled, bake_maps
from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_int,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("canvas", "wood", "peg")

_PARAM_KEYS = (
    "length",
    "width",
    "height",
    "pole_size",
    "canvas_thickness",
    "peg_size",
    "bevel_width",
    "texture_resolution",
    "bake_samples",
    "seed",
)

_SLOT_LOOK = {
    "canvas": "linen",
    "wood": "timber",
    "peg": "iron",
}


@dataclass(frozen=True)
class TentParams:
    length: float
    width: float
    height: float
    pole_size: float
    canvas_thickness: float
    peg_size: float
    bevel_width: float
    texture_resolution: int
    bake_samples: int
    seed: int


def parse_params(raw: Mapping[str, object]) -> TentParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = TentParams(
        length=positive_float(require_key(raw, "length", path), f"{path}.length"),
        width=positive_float(require_key(raw, "width", path), f"{path}.width"),
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        pole_size=positive_float(require_key(raw, "pole_size", path), f"{path}.pole_size"),
        canvas_thickness=positive_float(
            require_key(raw, "canvas_thickness", path), f"{path}.canvas_thickness"
        ),
        peg_size=positive_float(require_key(raw, "peg_size", path), f"{path}.peg_size"),
        bevel_width=positive_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
        texture_resolution=positive_int(
            require_key(raw, "texture_resolution", path), f"{path}.texture_resolution"
        ),
        bake_samples=positive_int(
            require_key(raw, "bake_samples", path), f"{path}.bake_samples"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    _validate(params)
    return params


def _validate(params: TentParams) -> None:
    if not 1.8 <= params.length <= 2.6:
        raise SpecError(f"params.length ({params.length}) should be ~2.2 m for one occupancy")
    if not 1.3 <= params.width <= 1.9:
        raise SpecError(f"params.width ({params.width}) should be ~1.6 m")
    if not 1.2 <= params.height <= 1.6:
        raise SpecError(f"params.height ({params.height}) should be 1.3-1.5 m")
    if params.pole_size >= min(params.width, params.length) * 0.12:
        raise SpecError("params.pole_size is too thick for the tent frame")
    if params.texture_resolution not in {256, 512, 1024, 2048}:
        raise SpecError(
            f"params.texture_resolution ({params.texture_resolution}) "
            "must be 256, 512, 1024 or 2048"
        )
    if params.bake_samples > 128:
        raise SpecError(f"params.bake_samples ({params.bake_samples}) must be <= 128")
    if params.bevel_width >= params.pole_size * 0.45:
        raise SpecError(
            f"params.bevel_width ({params.bevel_width}) must stay below half pole_size"
        )


def _half_z(size: tuple[float, float, float], rotation: tuple[float, float, float]) -> float:
    rot = Euler(rotation).to_matrix()
    return (
        abs(rot[2][0]) * size[0] * 0.5
        + abs(rot[2][1]) * size[1] * 0.5
        + abs(rot[2][2]) * size[2] * 0.5
    )


def _box(
    builder: BoxBuilder,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    slot: str,
    rotation: tuple[float, float, float] | None = None,
) -> None:
    kwargs = {} if rotation is None else {"rotation": rotation}
    builder.add_box(center, size, slot, **kwargs)


def _box_on_ground(
    builder: BoxBuilder,
    xy: tuple[float, float],
    size: tuple[float, float, float],
    slot: str,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    _box(builder, (xy[0], xy[1], _half_z(size, rotation)), size, slot, rotation)


def _box_between(
    builder: BoxBuilder,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    thickness: float,
    slot: str,
) -> None:
    direction = Vector(end) - Vector(start)
    length = direction.length
    if length <= 1e-5:
        raise SpecError("zero-length box_between")
    center = (Vector(start) + Vector(end)) * 0.5
    euler = direction.normalized().to_track_quat("Z", "Y").to_euler()
    _box(
        builder,
        (center.x, center.y, center.z),
        (thickness, thickness, length),
        slot,
        (euler.x, euler.y, euler.z),
    )


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = BoxBuilder(MATERIAL_SLOTS)
    _frame(builder, params)
    _canvas(builder, params)
    _back_wall(builder, params)
    _front_flaps(builder, params)
    _pegs_and_guys(builder, params)
    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    _center_on_origin(obj)
    shade_flat(obj)
    unwrap(obj)
    _bake(obj, spec, params)
    return [obj]


def _frame(builder: BoxBuilder, params: TentParams) -> None:
    hw = params.width * 0.5
    hl = params.length * 0.5
    height = params.height
    pole = params.pole_size
    slope = math.hypot(hw, height)
    theta_left = math.atan2(hw, height)
    theta_right = math.atan2(-hw, height)
    size = (pole, pole, slope)
    for y in (-hl, hl):
        _box_on_ground(builder, (-hw * 0.5, y), size, "wood", (0.0, theta_left, 0.0))
        _box_on_ground(builder, (hw * 0.5, y), size, "wood", (0.0, theta_right, 0.0))
    # Ridge pole sits on the A-frame peaks.
    _box(
        builder,
        (0.0, 0.0, height),
        (pole * 0.85, params.length + pole, pole * 0.85),
        "wood",
    )
    # Short ground sills at each A-frame so the feet read as planted.
    for y in (-hl, hl):
        _box_on_ground(builder, (0.0, y), (params.width * 0.22, pole, pole * 0.7), "wood")


def _canvas(builder: BoxBuilder, params: TentParams) -> None:
    hw = params.width * 0.5
    hl = params.length * 0.5
    height = params.height
    slope = math.hypot(hw, height)
    thick = params.canvas_thickness
    # Leave the -Y end open (preview front camera). Canvas biased to the +Y back.
    canvas_len = params.length * 0.76
    y_center = hl - 0.07 - canvas_len * 0.5
    theta_left = math.atan2(hw, height)
    theta_right = math.atan2(-hw, height)
    size = (thick, canvas_len, slope)
    _box_on_ground(builder, (-hw * 0.5, y_center), size, "canvas", (0.0, theta_left, 0.0))
    _box_on_ground(builder, (hw * 0.5, y_center), size, "canvas", (0.0, theta_right, 0.0))
    # Second overlapping skin so the canvas reads thicker and a bit wrinkled.
    skin = (thick * 0.7, canvas_len * 0.92, slope * 0.96)
    _box_on_ground(
        builder,
        (-hw * 0.5 + 0.012, y_center - 0.02),
        skin,
        "canvas",
        (0.0, theta_left + 0.03, 0.0),
    )
    _box_on_ground(
        builder,
        (hw * 0.5 - 0.012, y_center - 0.02),
        skin,
        "canvas",
        (0.0, theta_right - 0.03, 0.0),
    )
    # Ground hems along the eaves.
    _box_on_ground(builder, (-hw, y_center), (0.045, canvas_len, 0.04), "canvas")
    _box_on_ground(builder, (hw, y_center), (0.045, canvas_len, 0.04), "canvas")
    # Rolled lintel at the open front edge of the canvas.
    front_y = y_center - canvas_len * 0.5
    roll = (0.52, 0.085, 0.085)
    _box(builder, (0.0, front_y, height * 0.70), roll, "canvas", (0.15, 0.0, 0.0))


def _back_wall(builder: BoxBuilder, params: TentParams) -> None:
    # Stepped gable of canvas boxes: closed back, still a tent not a house wall.
    hw = params.width * 0.5
    hl = params.length * 0.5
    height = params.height
    y = hl - 0.012
    thick = params.canvas_thickness * 1.1
    bands = (
        (0.26, params.width * 0.74),
        (0.66, params.width * 0.48),
        (0.98, params.width * 0.26),
    )
    for center_z, width in bands:
        band_h = 0.34 if center_z < 0.8 else 0.28
        # Keep each band inside the A-frame silhouette.
        max_w = params.width * max(0.12, 1.0 - center_z / height) - 0.04
        w = min(width, max_w)
        _box(builder, (0.0, y, center_z), (w, thick, band_h), "canvas")


def _front_flaps(builder: BoxBuilder, params: TentParams) -> None:
    # Parted door flaps, symmetric, hanging short of the ground so the opening reads.
    hw = params.width * 0.5
    hl = params.length * 0.5
    canvas_len = params.length * 0.76
    y_center = hl - 0.07 - canvas_len * 0.5
    front_y = y_center - canvas_len * 0.5
    flap = (0.40, 0.022, 0.82)
    for sign, yaw in ((-1.0, 0.28), (1.0, -0.28)):
        rot = (0.08, sign * 0.22, yaw)
        _box(
            builder,
            (sign * 0.26, front_y - 0.07, _half_z(flap, rot) + 0.10),
            flap,
            "canvas",
            rot,
        )
    # Wooden toggles on the parted edges, still symmetric.
    toggle = (0.04, 0.03, 0.06)
    for sign in (-1.0, 1.0):
        _box(builder, (sign * 0.10, front_y - 0.09, 0.62), toggle, "wood")


def _pegs_and_guys(builder: BoxBuilder, params: TentParams) -> None:
    hw = params.width * 0.5
    hl = params.length * 0.5
    peg = params.peg_size
    peg_h = peg * 2.2
    outset = 0.20
    height = params.height
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            px = sx * (hw + outset)
            py = sy * (hl + outset)
            _box_on_ground(builder, (px, py), (peg, peg, peg_h), "peg")
            # Guy as a thin peg-material box from the stake to the eave.
            eave = (
                sx * hw * 0.92,
                sy * hl * 0.55,
                height * 0.28,
            )
            _box_between(builder, (px, py, peg_h * 0.7), eave, peg * 0.28, "peg")



def _center_on_origin(obj: bpy.types.Object) -> None:
    from blender.lib.scene import world_bounds

    mesh = obj.data
    lower, upper = world_bounds([obj])
    shift_x = (lower.x + upper.x) * 0.5
    shift_y = (lower.y + upper.y) * 0.5
    shift_z = lower.z
    if abs(shift_x) < 1e-6 and abs(shift_y) < 1e-6 and abs(shift_z) < 1e-6:
        return
    for vert in mesh.vertices:
        vert.co.x -= shift_x
        vert.co.y -= shift_y
        vert.co.z -= shift_z
    mesh.update()

def _mark_opaque(material: bpy.types.Material) -> None:
    if hasattr(material, "blend_method"):
        material.blend_method = "OPAQUE"
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"


def _bake(obj: bpy.types.Object, spec: AssetSpec, params: TentParams) -> None:
    mesh = obj.data
    if len(mesh.materials) != len(MATERIAL_SLOTS):
        raise SpecError(
            f"{spec.asset_id} has {len(mesh.materials)} material slots, "
            f"expected {len(MATERIAL_SLOTS)}."
        )
    for index, slot in enumerate(MATERIAL_SLOTS):
        look = _SLOT_LOOK[slot]
        mesh.materials[index] = build_look_material(
            f"{spec.asset_id}_{slot}_{look}",
            spec.materials[slot],
            look,
            params.seed + index * 97,
        )
    texture_dump = Path(__file__).resolve().parents[2] / "assets" / "out" / "textures"
    maps = bake_maps(
        obj,
        asset_id=spec.asset_id,
        resolution=params.texture_resolution,
        samples=params.bake_samples,
        dump_dir=texture_dump,
    )
    material = apply_baked_principled(obj, maps, metallic=0.0)
    _mark_opaque(material)
