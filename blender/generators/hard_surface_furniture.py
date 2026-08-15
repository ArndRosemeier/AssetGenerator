"""Parametric indoor furniture and a planked floor cell.

Each kind is built from overlapping closed boxes (crate style) so the mesh
stays manifold without booleans. Origin is footprint centre, base on Z=0.
The back of wall pieces (shelf, cupboard, hearth) is −Y so a 180° yaw puts
them flush on a +Y / engine +Z wall.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import bpy

from blender.lib.bake import apply_baked_principled, bake_maps
from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_int,
    as_str,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)
from blender.generators.hard_surface_kit_cell import build_look_material

MATERIAL_SLOTS: tuple[str, ...] = ("wood", "accent", "cloth", "stone")

_KINDS: tuple[str, ...] = (
    "table",
    "bed",
    "chest",
    "hearth",
    "shelf",
    "cupboard",
    "bench",
    "floor",
)

_SHARED = (
    "kind",
    "width",
    "depth",
    "height",
    "bevel_width",
    "texture_resolution",
    "bake_samples",
    "seed",
)


@dataclass(frozen=True)
class FurnitureParams:
    kind: str
    width: float
    depth: float
    height: float
    bevel_width: float
    texture_resolution: int
    bake_samples: int
    seed: int
    extra: Mapping[str, object]


def parse_params(raw: Mapping[str, object]) -> FurnitureParams:
    path = "params"
    kind = as_str(require_key(raw, "kind", path), f"{path}.kind")
    if kind not in _KINDS:
        raise SpecError(f"{path}.kind: unknown '{kind}'; allowed {list(_KINDS)}")
    extra_keys = _extra_keys(kind)
    reject_unknown(raw, _SHARED + extra_keys, path)
    extra = {key: raw[key] for key in extra_keys}
    params = FurnitureParams(
        kind=kind,
        width=positive_float(require_key(raw, "width", path), f"{path}.width"),
        depth=positive_float(require_key(raw, "depth", path), f"{path}.depth"),
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        bevel_width=positive_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
        texture_resolution=positive_int(
            require_key(raw, "texture_resolution", path), f"{path}.texture_resolution"
        ),
        bake_samples=positive_int(
            require_key(raw, "bake_samples", path), f"{path}.bake_samples"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
        extra=extra,
    )
    if params.bevel_width >= min(params.width, params.depth, params.height) * 0.25:
        raise SpecError(
            f"params.bevel_width ({params.bevel_width}) is too large for "
            f"{params.width} x {params.depth} x {params.height}"
        )
    if params.texture_resolution not in {256, 512, 1024, 2048}:
        raise SpecError(
            f"params.texture_resolution ({params.texture_resolution}) "
            "must be 256, 512, 1024 or 2048"
        )
    if params.bake_samples > 128:
        raise SpecError(f"params.bake_samples ({params.bake_samples}) must be <= 128")
    return params


def _extra_keys(kind: str) -> tuple[str, ...]:
    if kind == "table":
        return ("leg_size", "apron_height", "plank_count", "plank_gap")
    if kind == "bed":
        return ("post_size", "rail_height", "mattress_inset", "plank_count")
    if kind == "chest":
        return ("plank_count", "plank_gap", "lid_height", "band_width")
    if kind == "hearth":
        return ("opening_width", "opening_height", "mantel_depth", "hearth_slab")
    if kind == "shelf":
        return ("shelf_count", "plank_thickness", "upright_size")
    if kind == "cupboard":
        return ("plank_count", "door_gap", "cornice")
    if kind == "bench":
        return ("leg_size", "seat_thickness")
    if kind == "floor":
        return ("plank_count", "plank_gap", "joist_count")
    raise SpecError(f"params.kind: unhandled '{kind}'")


def _pf(extra: Mapping[str, object], key: str) -> float:
    return positive_float(extra[key], f"params.{key}")


def _pi(extra: Mapping[str, object], key: str) -> int:
    return positive_int(extra[key], f"params.{key}")


def _band_size(total: float, count: int, gap: float) -> float:
    return (total - (count - 1) * gap) / count


def _band_starts(total: float, count: int, gap: float, offset: float) -> list[tuple[float, float]]:
    size = _band_size(total, count, gap)
    if size <= 0.0:
        raise SpecError(
            f"params: {count} bands with {gap} m gaps do not fit in {total:.3f} m"
        )
    step = size + gap
    return [(offset + i * step, offset + i * step + size) for i in range(count)]


def _box(
    builder: BoxBuilder,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    slot: str,
) -> None:
    builder.add_box_bounds(
        (min(x0, x1), min(y0, y1), min(z0, z1)),
        (max(x0, x1), max(y0, y1), max(z0, z1)),
        slot,
    )


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = BoxBuilder(MATERIAL_SLOTS)
    if params.kind == "table":
        _table(builder, params)
    elif params.kind == "bed":
        _bed(builder, params)
    elif params.kind == "chest":
        _chest(builder, params)
    elif params.kind == "hearth":
        _hearth(builder, params)
    elif params.kind == "shelf":
        _shelf(builder, params)
    elif params.kind == "cupboard":
        _cupboard(builder, params)
    elif params.kind == "bench":
        _bench(builder, params)
    elif params.kind == "floor":
        _floor(builder, params)
    else:
        raise SpecError(f"params.kind: unhandled '{params.kind}'")
    obj = builder.to_object(spec.asset_id, spec.materials)
    apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    shade_flat(obj)
    unwrap(obj)
    _bake_furniture_textures(obj, spec, params)
    return [obj]


def _slot_look(kind: str, slot: str) -> str:
    if slot == "wood":
        return "timber"
    if slot == "accent":
        return "iron" if kind in {"chest", "hearth", "cupboard"} else "timber"
    if slot == "cloth":
        return "soot" if kind == "hearth" else "linen"
    if slot == "stone":
        return "stone"
    raise SpecError(f"unknown furniture material slot '{slot}'")


def _bake_furniture_textures(
    obj: bpy.types.Object,
    spec: AssetSpec,
    params: FurnitureParams,
) -> None:
    mesh = obj.data
    if len(mesh.materials) != len(MATERIAL_SLOTS):
        raise SpecError(
            f"{spec.asset_id} has {len(mesh.materials)} material slots, "
            f"expected {len(MATERIAL_SLOTS)}."
        )
    for index, slot in enumerate(MATERIAL_SLOTS):
        look = _slot_look(params.kind, slot)
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
    apply_baked_principled(obj, maps, metallic=0.0)


def _table(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    leg = _pf(extra, "leg_size")
    apron_h = _pf(extra, "apron_height")
    planks = _pi(extra, "plank_count")
    gap = _pf(extra, "plank_gap")
    hw, hd = params.width * 0.5, params.depth * 0.5
    top_t = 0.04
    inset = 0.04
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            _box(
                builder,
                sx * (hw - inset - leg),
                sy * (hd - inset - leg),
                0.0,
                sx * (hw - inset),
                sy * (hd - inset),
                params.height - top_t,
                "accent",
            )
    apron_z0 = params.height - top_t - apron_h
    _box(builder, -hw + inset, -hd + inset, apron_z0, hw - inset, -hd + inset + 0.05, params.height - top_t, "wood")
    _box(builder, -hw + inset, hd - inset - 0.05, apron_z0, hw - inset, hd - inset, params.height - top_t, "wood")
    _box(builder, -hw + inset, -hd + inset + 0.05, apron_z0, -hw + inset + 0.05, hd - inset - 0.05, params.height - top_t, "wood")
    _box(builder, hw - inset - 0.05, -hd + inset + 0.05, apron_z0, hw - inset, hd - inset - 0.05, params.height - top_t, "wood")
    for low, high in _band_starts(params.width, planks, gap, -hw):
        _box(builder, low, -hd, params.height - top_t, high, hd, params.height, "wood")
    _box(builder, -0.12, -hd + 0.03, params.height, 0.12, hd - 0.03, params.height + 0.016, "cloth")
    _box(builder, -0.06, -0.06, params.height + 0.016, 0.06, 0.06, params.height + 0.030, "stone")


def _bed(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    post = _pf(extra, "post_size")
    rail_h = _pf(extra, "rail_height")
    inset = _pf(extra, "mattress_inset")
    planks = _pi(extra, "plank_count")
    hw, hd = params.width * 0.5, params.depth * 0.5
    mattress_h = 0.18
    deck_z = rail_h
    head_h = params.height
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            z1 = head_h if sy < 0.0 else rail_h + 0.12
            _box(builder, sx * (hw - post), sy * (hd - post), 0.0, sx * hw, sy * hd, z1, "accent")
    _box(builder, -hw + post, -hd + 0.02, rail_h - 0.07, hw - post, -hd + 0.08, rail_h, "wood")
    _box(builder, -hw + post, hd - 0.08, rail_h - 0.07, hw - post, hd - 0.02, rail_h, "wood")
    _box(builder, -hw + 0.02, -hd + post, rail_h - 0.07, -hw + 0.08, hd - post, rail_h, "wood")
    _box(builder, hw - 0.08, -hd + post, rail_h - 0.07, hw - 0.02, hd - post, rail_h, "wood")
    _box(builder, -hw + post, -hd + 0.04, 0.18, hw - post, -hd + 0.10, head_h - 0.04, "wood")
    _box(builder, -hw + post + 0.04, -hd + 0.06, 0.28, hw - post - 0.04, -hd + 0.12, head_h - 0.14, "accent")
    gap = 0.008
    for low, high in _band_starts(params.width - 2.0 * post, planks, gap, -hw + post):
        _box(builder, low, -hd + post, deck_z - 0.03, high, hd - post, deck_z, "wood")
    _box(
        builder,
        -hw + inset,
        -hd + inset + 0.06,
        deck_z,
        hw - inset,
        hd - inset,
        deck_z + mattress_h,
        "cloth",
    )
    _box(
        builder,
        -hw + inset + 0.08,
        -hd + inset + 0.10,
        deck_z + mattress_h,
        hw - inset - 0.16,
        hd - inset - 0.04,
        deck_z + mattress_h + 0.04,
        "cloth",
    )
    _box(builder, -0.08, hd - 0.10, rail_h + 0.02, 0.08, hd - 0.02, rail_h + 0.08, "stone")


def _chest(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    planks = _pi(extra, "plank_count")
    gap = _pf(extra, "plank_gap")
    lid_h = _pf(extra, "lid_height")
    band = _pf(extra, "band_width")
    hw, hd = params.width * 0.5, params.depth * 0.5
    t = 0.028
    body_h = params.height - lid_h
    _box(builder, -hw, -hd, 0.0, hw, hd, t, "wood")
    for low, high in _band_starts(body_h - t, planks, gap, t):
        _box(builder, -hw, -hd, low, hw, -hd + t, high, "wood")
        _box(builder, -hw, hd - t, low, hw, hd, high, "wood")
        _box(builder, -hw, -hd + t, low, -hw + t, hd - t, high, "wood")
        _box(builder, hw - t, -hd + t, low, hw, hd - t, high, "wood")
    _box(builder, -hw + t, -hd + t, t, hw - t, hd - t, t + 0.012, "cloth")
    for x in (-hw + 0.08, 0.0 - band * 0.5, hw - 0.08 - band):
        _box(builder, x, -hd - 0.004, t, x + band, hd + 0.004, body_h, "accent")
    _box(builder, -hw - 0.01, -hd - 0.01, body_h, hw + 0.01, hd + 0.01, body_h + lid_h * 0.45, "wood")
    _box(builder, -hw + 0.03, -hd + 0.03, body_h + lid_h * 0.35, hw - 0.03, hd - 0.03, params.height, "wood")
    _box(builder, -0.04, -hd - 0.004, body_h + lid_h * 0.2, 0.04, -hd + 0.02, body_h + lid_h * 0.75, "accent")
    _box(builder, -0.03, -hd - 0.002, body_h + lid_h * 0.35, 0.03, -hd + 0.016, body_h + lid_h * 0.55, "stone")


def _hearth(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    open_w = _pf(extra, "opening_width")
    open_h = _pf(extra, "opening_height")
    mantel_d = _pf(extra, "mantel_depth")
    slab = _pf(extra, "hearth_slab")
    hw, hd = params.width * 0.5, params.depth * 0.5
    if open_w >= params.width - 0.16 or open_h >= params.height - 0.28:
        raise SpecError("params: hearth opening does not leave a surround")
    _box(builder, -hw, -hd, 0.0, hw, hd, slab, "stone")
    jamb = (params.width - open_w) * 0.5
    _box(builder, -hw, -hd + 0.04, slab, -hw + jamb, hd, slab + open_h, "stone")
    _box(builder, hw - jamb, -hd + 0.04, slab, hw, hd, slab + open_h, "stone")
    _box(builder, -hw, hd - 0.14, slab, hw, hd, params.height - 0.12, "stone")
    _box(builder, -hw, -hd + 0.04, slab + open_h, hw, hd, params.height - 0.10, "stone")
    _box(builder, -open_w * 0.5, -hd + 0.06, slab, open_w * 0.5, -hd + 0.10, slab + 0.04, "accent")
    _box(builder, -open_w * 0.45, -hd + 0.08, slab + 0.01, open_w * 0.45, hd - 0.16, slab + 0.03, "cloth")
    _box(builder, -hw - 0.04, -hd, params.height - 0.10, hw + 0.04, -hd + mantel_d, params.height, "wood")
    _box(builder, -hw + 0.06, -hd + 0.02, 0.02, -hw + 0.16, -hd + 0.08, 0.12, "accent")
    _box(builder, hw - 0.16, -hd + 0.02, 0.02, hw - 0.06, -hd + 0.08, 0.12, "accent")


def _shelf(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    count = _pi(extra, "shelf_count")
    t = _pf(extra, "plank_thickness")
    upright = _pf(extra, "upright_size")
    hw, hd = params.width * 0.5, params.depth * 0.5
    _box(builder, -hw, hd - 0.02, 0.0, -hw + upright, hd, params.height, "accent")
    _box(builder, hw - upright, hd - 0.02, 0.0, hw, hd, params.height, "accent")
    _box(builder, -hw, hd - 0.018, 0.0, hw, hd, params.height, "wood")
    for i, (low, _high) in enumerate(_band_starts(params.height, count, 0.04, 0.0)):
        z = max(low, 0.0)
        _box(builder, -hw + 0.01, -hd, z, hw - 0.01, hd - 0.01, z + t, "wood")
        if z >= 0.08:
            for sx in (-1.0, 1.0):
                _box(
                    builder,
                    sx * (hw - upright - 0.04),
                    -hd + 0.02,
                    z - 0.05,
                    sx * (hw - upright),
                    hd - 0.02,
                    z,
                    "accent",
                )
        if i == 1:
            _box(builder, -0.18, -hd + 0.02, z + t, -0.04, -hd + 0.14, z + t + 0.11, "cloth")
            _box(builder, 0.06, -hd + 0.03, z + t, 0.16, -hd + 0.13, z + t + 0.08, "stone")


def _cupboard(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    planks = _pi(extra, "plank_count")
    door_gap = _pf(extra, "door_gap")
    cornice = _pf(extra, "cornice")
    hw, hd = params.width * 0.5, params.depth * 0.5
    t = 0.024
    body_h = params.height - cornice
    _box(builder, -hw, -hd, 0.0, hw, hd, 0.06, "wood")
    _box(builder, -hw, hd - t, 0.06, hw, hd, body_h, "wood")
    _box(builder, -hw, -hd, 0.06, -hw + t, hd - t, body_h, "wood")
    _box(builder, hw - t, -hd, 0.06, hw, hd - t, body_h, "wood")
    _box(builder, -hw + t, -hd, body_h - t, hw - t, hd - t, body_h, "wood")
    mid = 0.0
    leaf_w = (params.width - 2.0 * t - door_gap) * 0.5
    for low, high in _band_starts(body_h - 0.16, planks, 0.006, 0.10):
        _box(builder, -hw + t + 0.01, -hd, low, -hw + t + leaf_w, -hd + t, high, "wood")
        _box(builder, hw - t - leaf_w, -hd, low, hw - t - 0.01, -hd + t, high, "wood")
    _box(builder, mid - door_gap * 0.5, -hd - 0.002, 0.10, mid + door_gap * 0.5, -hd + t + 0.002, body_h - 0.06, "accent")
    _box(builder, -0.18, -hd - 0.01, body_h * 0.48, -0.12, -hd + 0.02, body_h * 0.56, "accent")
    _box(builder, 0.12, -hd - 0.01, body_h * 0.48, 0.18, -hd + 0.02, body_h * 0.56, "accent")
    _box(builder, -hw - 0.03, -hd - 0.02, body_h, hw + 0.03, hd + 0.02, params.height, "accent")
    _box(builder, -0.05, -hd - 0.008, 0.08, 0.05, -hd + 0.02, 0.14, "stone")


def _bench(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    leg = _pf(extra, "leg_size")
    seat_t = _pf(extra, "seat_thickness")
    hw, hd = params.width * 0.5, params.depth * 0.5
    for sx in (-1.0, 1.0):
        _box(
            builder,
            sx * (hw - 0.06 - leg),
            -hd + 0.03,
            0.0,
            sx * (hw - 0.06),
            hd - 0.03,
            params.height - seat_t,
            "accent",
        )
    _box(builder, -hw, -hd, params.height - seat_t, hw, hd, params.height, "wood")
    _box(builder, -hw + 0.04, hd - 0.05, params.height - seat_t - 0.08, hw - 0.04, hd, params.height - seat_t, "wood")
    _box(builder, -hw + 0.10, -hd + 0.04, 0.10, hw - 0.10, -hd + 0.08, 0.16, "accent")
    _box(builder, -0.04, -0.04, 0.0, 0.04, 0.04, 0.02, "stone")


def _floor(builder: BoxBuilder, params: FurnitureParams) -> None:
    extra = params.extra
    planks = _pi(extra, "plank_count")
    gap = _pf(extra, "plank_gap")
    joists = _pi(extra, "joist_count")
    hw, hd = params.width * 0.5, params.depth * 0.5
    joist_h = 0.03
    plank_t = params.height - joist_h
    if plank_t <= 0.0:
        raise SpecError("params.height must leave room for joists under the planks")
    for low, high in _band_starts(params.depth, joists, 0.08, -hd):
        _box(builder, -hw + 0.04, low, 0.0, hw - 0.04, high, joist_h, "accent")
    for low, high in _band_starts(params.width, planks, gap, -hw):
        _box(builder, low, -hd, joist_h, high, hd, params.height, "wood")
    _box(builder, -hw, -hd, joist_h, -hw + 0.04, hd, params.height, "stone")
    _box(builder, hw - 0.04, -hd, joist_h, hw, hd, params.height, "stone")
