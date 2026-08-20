"""Parametric ground-sit outdoor fire ring.

Fieldstone ring, charcoal pit, charred logs and an ember pile built from
overlapping closed boxes (crate style). Not an indoor hearth: no mantel,
chimney or wall surround. Origin is footprint centre, base on Z=0.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import bpy
from mathutils import Euler

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

MATERIAL_SLOTS: tuple[str, ...] = ("stone", "wood", "ember", "iron")

_PARAM_KEYS = (
    "ring_diameter",
    "ring_height",
    "stone_count",
    "log_count",
    "log_length",
    "log_thickness",
    "ember_count",
    "cook_sticks",
    "bevel_width",
    "texture_resolution",
    "bake_samples",
    "seed",
)

_SLOT_LOOK = {
    "stone": "stone",
    "wood": "timber",
    "ember": "stone",
    "iron": "iron",
}


@dataclass(frozen=True)
class CampfireParams:
    ring_diameter: float
    ring_height: float
    stone_count: int
    log_count: int
    log_length: float
    log_thickness: float
    ember_count: int
    cook_sticks: bool
    bevel_width: float
    texture_resolution: int
    bake_samples: int
    seed: int


def parse_params(raw: Mapping[str, object]) -> CampfireParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    cook_raw = require_key(raw, "cook_sticks", path)
    if not isinstance(cook_raw, bool):
        raise SpecError(f"{path}.cook_sticks: expected a boolean, got {type(cook_raw).__name__}")
    params = CampfireParams(
        ring_diameter=positive_float(require_key(raw, "ring_diameter", path), f"{path}.ring_diameter"),
        ring_height=positive_float(require_key(raw, "ring_height", path), f"{path}.ring_height"),
        stone_count=positive_int(require_key(raw, "stone_count", path), f"{path}.stone_count"),
        log_count=positive_int(require_key(raw, "log_count", path), f"{path}.log_count"),
        log_length=positive_float(require_key(raw, "log_length", path), f"{path}.log_length"),
        log_thickness=positive_float(require_key(raw, "log_thickness", path), f"{path}.log_thickness"),
        ember_count=positive_int(require_key(raw, "ember_count", path), f"{path}.ember_count"),
        cook_sticks=cook_raw,
        bevel_width=positive_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
        texture_resolution=positive_int(
            require_key(raw, "texture_resolution", path), f"{path}.texture_resolution"
        ),
        bake_samples=positive_int(require_key(raw, "bake_samples", path), f"{path}.bake_samples"),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    _validate(params)
    return params


def _validate(params: CampfireParams) -> None:
    if not 1.2 <= params.ring_diameter <= 1.8:
        raise SpecError(
            f"params.ring_diameter ({params.ring_diameter}) should be a hamlet-readable "
            "fire ring, about 1.3-1.6 m."
        )
    if params.stone_count < 10 or params.stone_count > 22:
        raise SpecError(f"params.stone_count ({params.stone_count}) must be 10-22")
    if params.log_count < 3 or params.log_count > 5:
        raise SpecError(f"params.log_count ({params.log_count}) must be 3-5")
    if params.log_length >= params.ring_diameter:
        raise SpecError("params.log_length must stay inside the ring diameter")
    if params.texture_resolution not in {256, 512, 1024, 2048}:
        raise SpecError(
            f"params.texture_resolution ({params.texture_resolution}) "
            "must be 256, 512, 1024 or 2048"
        )
    if params.bake_samples > 128:
        raise SpecError(f"params.bake_samples ({params.bake_samples}) must be <= 128")
    if params.bevel_width >= params.ring_height * 0.25:
        raise SpecError(
            f"params.bevel_width ({params.bevel_width}) is too large for ring_height "
            f"{params.ring_height}"
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


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = BoxBuilder(MATERIAL_SLOTS)
    rng = random.Random(params.seed)
    _ring(builder, params, rng)
    _pit(builder, params, rng)
    _logs(builder, params, rng)
    _embers(builder, params, rng)
    if params.cook_sticks:
        _cook_sticks(builder, params)
    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    _center_on_origin(obj)
    shade_flat(obj)
    unwrap(obj)
    _bake(obj, spec, params)
    return [obj]


def _ring(builder: BoxBuilder, params: CampfireParams, rng: random.Random) -> None:
    count = params.stone_count
    outer = params.ring_diameter * 0.5
    # Sit the stones on a circle just inside the outer diameter.
    radius = outer - 0.14
    for index in range(count):
        yaw = (index / count) * math.tau + rng.uniform(-0.07, 0.07)
        radial = radius + rng.uniform(-0.04, 0.035)
        cx = math.cos(yaw) * radial
        cy = math.sin(yaw) * radial
        sx = rng.uniform(0.16, 0.26)
        sy = rng.uniform(0.12, 0.20)
        sz = rng.uniform(params.ring_height * 0.70, params.ring_height * 1.15)
        twist = yaw + rng.uniform(-0.35, 0.35)
        _box_on_ground(builder, (cx, cy), (sx, sy, sz), "stone", (0.0, 0.0, twist))
        # Second overlapping chunk so each stone reads as fieldstone, not a brick.
        ox = cx + math.cos(yaw + 0.4) * 0.04
        oy = cy + math.sin(yaw + 0.4) * 0.04
        _box_on_ground(
            builder,
            (ox, oy),
            (sx * 0.72, sy * 0.78, sz * 0.62),
            "stone",
            (0.0, 0.0, twist + 0.5),
        )


def _pit(builder: BoxBuilder, params: CampfireParams, rng: random.Random) -> None:
    # Charcoal pad: overlapping dark-wood boxes filling the inner circle.
    inner = params.ring_diameter * 0.28
    _box_on_ground(builder, (0.0, 0.0), (inner * 1.35, inner * 1.35, 0.035), "wood")
    for index in range(6):
        yaw = index * (math.tau / 6.0) + 0.11
        r = inner * 0.55
        _box_on_ground(
            builder,
            (math.cos(yaw) * r, math.sin(yaw) * r),
            (inner * 0.85, inner * 0.62, 0.04),
            "wood",
            (0.0, 0.0, yaw),
        )
    # Ash crumbs around the pit, still wood (char) not ember.
    for _ in range(5):
        yaw = rng.uniform(0.0, math.tau)
        r = rng.uniform(inner * 0.15, inner * 0.85)
        s = rng.uniform(0.05, 0.09)
        _box_on_ground(
            builder,
            (math.cos(yaw) * r, math.sin(yaw) * r),
            (s, s * 0.8, 0.03),
            "wood",
            (0.0, 0.0, yaw),
        )


def _logs(builder: BoxBuilder, params: CampfireParams, rng: random.Random) -> None:
    # Mix of ground-star and leaning teepee so the pile reads at hamlet distance.
    count = params.log_count
    length = params.log_length
    thick = params.log_thickness
    for index in range(count):
        yaw = (index / count) * math.tau + rng.uniform(-0.12, 0.12)
        lean = 0.22 if index < 3 else 0.62
        if index >= 3:
            lean += rng.uniform(-0.08, 0.08)
        size = (thick * rng.uniform(0.88, 1.08), length, thick * rng.uniform(0.82, 1.02))
        rotation = (lean, rng.uniform(-0.06, 0.06), yaw)
        # Push the log so the inner end sits over the ember pile.
        radial = 0.16 + (0.10 if index < 3 else 0.04)
        cx = math.cos(yaw) * radial
        cy = math.sin(yaw) * radial
        _box_on_ground(builder, (cx, cy), size, "wood", rotation)
        # Charred knuckle / broken end, overlapping.
        end_r = radial + length * 0.28
        end_size = (thick * 0.7, thick * 0.85, thick * 0.7)
        _box_on_ground(
            builder,
            (math.cos(yaw) * end_r, math.sin(yaw) * end_r),
            end_size,
            "wood",
            (0.15, 0.0, yaw + 0.4),
        )


def _embers(builder: BoxBuilder, params: CampfireParams, rng: random.Random) -> None:
    # Warm mesh coals, not a particle. Heap sits on the charcoal pad.
    for index in range(params.ember_count):
        yaw = rng.uniform(0.0, math.tau)
        r = rng.uniform(0.0, 0.20)
        sx = rng.uniform(0.045, 0.095)
        sy = rng.uniform(0.040, 0.085)
        sz = rng.uniform(0.035, 0.080)
        # Stack a few toward the centre so the pile has height.
        lift = 0.02 + (0.07 if r < 0.07 else 0.0) + rng.uniform(0.0, 0.03)
        cz = lift + sz * 0.5
        _box(
            builder,
            (math.cos(yaw) * r, math.sin(yaw) * r, cz),
            (sx, sy, sz),
            "ember",
            (rng.uniform(-0.25, 0.25), rng.uniform(-0.2, 0.2), yaw),
        )
        if index < 4:
            # Hotter core nugget.
            _box(
                builder,
                (math.cos(yaw + 0.3) * r * 0.4, math.sin(yaw + 0.3) * r * 0.4, 0.06),
                (0.05, 0.045, 0.04),
                "ember",
                (0.2, 0.1, yaw),
            )


def _cook_sticks(builder: BoxBuilder, params: CampfireParams) -> None:
    # Two forked iron sticks planted in the ring, with a spit between them.
    reach = params.ring_diameter * 0.32
    shaft_h = 0.86
    shaft = 0.032
    for sign in (-1.0, 1.0):
        x = sign * reach
        _box_on_ground(builder, (x, 0.0), (shaft, shaft, shaft_h), "iron")
        # Fork tines.
        tine = (0.022, 0.022, 0.16)
        for side in (-1.0, 1.0):
            rot = (side * 0.42, 0.0, 0.0)
            _box(
                builder,
                (x, side * 0.035, shaft_h - 0.04),
                tine,
                "iron",
                rot,
            )
    spit_len = reach * 2.0 + 0.08
    _box(builder, (0.0, 0.0, shaft_h - 0.06), (spit_len, 0.018, 0.018), "iron")



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


def _bake(obj: bpy.types.Object, spec: AssetSpec, params: CampfireParams) -> None:
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
