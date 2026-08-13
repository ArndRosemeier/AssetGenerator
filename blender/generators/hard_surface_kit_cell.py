"""One-cell kit pieces: wall, corner, door, gate, window, roof, chimney, plinth,
floor, battlement, turret.

Authored Z-up, footprint centre at the origin. The exterior wall sits on +Y so
glTF Y-up export maps it to engine -Z, matching Modular's local wall-on-minus-Z
convention.

Storey pieces occupy z in [overlap, cell_y], not [0, cell_y + overlap]. Sitting
on z=0 shares the storey plane with the plinth below; extending past cell_y
occupies the next cell and z-fights its floor, jetty soffit, or roof. Horizontal
joins are a shiplap (outer wythe past +X, inner past -X). Boxes in one mesh may
interpenetrate; they must not present coplanar outer faces to a neighbor.
`build` fails (`SpecError`) if two boxes share a storey-axis face, including a
phantom stacked neighbor (plinth, ground under jetty, wall under roof).

`jetty` pushes the exterior wythe outward (upper-storey overhang). `timber`
bakes posts, plates, X-braces, and short overhang corbels into the mesh —
that is not an attach socket. Corbels may drop a little below `overlap`,
but only in the overhang strip.

`wall_b` is close-studded timber (verticals, no X-braces). `window_c` is three
lights. `door_b` is a door with a transom. Same seams as the base kinds.

`floor` is a full-cell interior slab at the same plane as wall floors, for the
hollow of a ring (a 3×4 hall). No walls; storey seams only.

`battlement` is a cap (down seam only in the catalog): merlons on +Y, walk slab
starting at `overlap`. `gate` is a door through a thick curtain. `turret` is a
four-sided extra storey with no horizontal seams (tower tops).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import bpy

from pathlib import Path

from blender.lib.bake import apply_baked_principled, bake_maps
from blender.lib.scene import BoxBuilder, apply_bevel, shade_flat, unwrap
from blender.lib.spec import (
    AssetSpec,
    MaterialSpec,
    SpecError,
    as_bool,
    as_float,
    as_int,
    as_str,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("structure", "trim")

_KINDS = (
    "wall",
    "wall_b",
    "corner",
    "door",
    "door_b",
    "gate",
    "window",
    "window_b",
    "window_c",
    "floor",
    "roof",
    "chimney",
    "plinth",
    "battlement",
    "turret",
)

_STOREY_KINDS = (
    "wall",
    "wall_b",
    "corner",
    "door",
    "door_b",
    "gate",
    "window",
    "window_b",
    "window_c",
    "floor",
    "turret",
)

_CAP_KINDS = ("roof", "chimney", "battlement")

# Jambs beside an opening. Thick curtains use this instead of full wall thickness
# so a gate can be 2–3 m wide.
_MIN_JAMB = 0.4

_PARAM_KEYS = (
    "kind",
    "cell_xz",
    "cell_y",
    "wall_thickness",
    "overlap",
    "door_width",
    "door_height",
    "window_width",
    "window_height",
    "window_sill",
    "roof_height",
    "overhang",
    "jetty",
    "timber",
    "bevel_width",
    "texture_resolution",
    "bake_samples",
    "seed",
)

# (x0, x1, z0, z1) in the wall plane.
Opening = tuple[float, float, float, float]
Vec3 = tuple[float, float, float]
BoxBounds = tuple[Vec3, Vec3]

_TIMBER_PROUD = 0.055
_CORNER_POST = 0.18
_PLANE_EPS = 5e-4
_SPAN_EPS = 1e-3
_AXIS_NAME = ("X", "Y", "Z")
# Typical upper-storey overhang. Roof specs have jetty=0; the house still stacks
# a roof on jetty walls, so the phantom neighbor must include that case.
_STACK_JETTY = 0.3


@dataclass(frozen=True)
class KitBox:
    lower: Vec3
    upper: Vec3
    slot: str


def _sorted_bounds(lower: Vec3, upper: Vec3) -> tuple[Vec3, Vec3]:
    lo = (min(lower[0], upper[0]), min(lower[1], upper[1]), min(lower[2], upper[2]))
    hi = (max(lower[0], upper[0]), max(lower[1], upper[1]), max(lower[2], upper[2]))
    if hi[0] <= lo[0] or hi[1] <= lo[1] or hi[2] <= lo[2]:
        raise SpecError(f"empty box {lo} -> {hi}")
    return lo, hi


class BoundsSink:
    """Records boxes without building a mesh. Used for neighbor z-fight checks."""

    def __init__(self) -> None:
        self.boxes: list[KitBox] = []

    def add_box_bounds(self, lower: Vec3, upper: Vec3, slot: str) -> None:
        lo, hi = _sorted_bounds(lower, upper)
        self.boxes.append(KitBox(lo, hi, slot))


class KitBoxes:
    """BoxBuilder that records bounds so kit envelope checks can fail loudly."""

    def __init__(self) -> None:
        self._builder = BoxBuilder(MATERIAL_SLOTS)
        self.boxes: list[KitBox] = []

    def add_box_bounds(self, lower: Vec3, upper: Vec3, slot: str) -> None:
        lo, hi = _sorted_bounds(lower, upper)
        self.boxes.append(KitBox(lo, hi, slot))
        self._builder.add_box_bounds(lo, hi, slot)

    def to_object(self, name: str, materials: Mapping[str, MaterialSpec]) -> bpy.types.Object:
        return self._builder.to_object(name, materials)


def _assert_kit_envelope(params: KitParams, boxes: Sequence[KitBox]) -> None:
    """Walls must not share a storey plane with the piece above or below.

    Shiplap/jetty/timber may leave the cell in X/Y. On a wall/door/window/corner,
    z below `overlap` or past `cell_y` is a kit bug, not a closed joint.
    """
    h = params.half
    pad = params.overlap + params.jetty + (_TIMBER_PROUD if params.timber else 0.0)
    storey = params.kind in _STOREY_KINDS
    for box in boxes:
        lower, upper = box.lower, box.upper
        if storey and upper[2] > params.cell_y + 1e-4:
            raise SpecError(
                f"storey overrun: box z {upper[2]:.4f} > cell_y {params.cell_y}. "
                "Walls must stay in z=[overlap, cell_y]; extending into the next "
                "cell z-fights the floor/wall/roof above."
            )
        if storey and lower[2] < params.overlap - 1e-4:
            drop = params.overlap - 0.42
            if not (_overhang_only(params, lower, upper) and lower[2] >= drop - 1e-4):
                raise SpecError(
                    f"storey underrun: box z {lower[2]:.4f} < overlap {params.overlap}. "
                    "Walls start at overlap so they do not share the storey plane "
                    "with the plinth or floor below."
                )
        if params.kind == "plinth" and upper[2] > params.cell_y + 1e-4:
            raise SpecError(
                f"plinth overrun: box z {upper[2]:.4f} > cell_y {params.cell_y}. "
                "Plinths must not poke into the storey above."
            )
        if abs(lower[0]) > h + pad + 1e-3 or abs(upper[0]) > h + pad + 1e-3:
            raise SpecError(
                f"plan overrun X {lower[0]:.4f}..{upper[0]:.4f} (limit {h + pad:.4f})."
            )
        if abs(lower[1]) > h + pad + 1e-3 or abs(upper[1]) > h + pad + 1e-3:
            raise SpecError(
                f"plan overrun Y {lower[1]:.4f}..{upper[1]:.4f} (limit {h + pad:.4f})."
            )


def _overhang_only(
    params: KitParams, lower: tuple[float, float, float], upper: tuple[float, float, float]
) -> bool:
    """Jetty corbels may drop a little below overlap, but only in the overhang."""
    if params.jetty <= 0.0:
        return False
    h = params.half
    if min(lower[1], upper[1]) >= h - 1e-3:
        return True
    if max(lower[0], upper[0]) <= -h + 1e-3:
        return True
    return False


def _span_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _coplanar_face(
    first: KitBox,
    second: KitBox,
    *,
    axes: Sequence[int],
) -> str | None:
    """If two boxes share an outer plane with overlapping area, return that face."""
    for axis in axes:
        u, v = (axis + 1) % 3, (axis + 2) % 3
        ou = _span_overlap(first.lower[u], first.upper[u], second.lower[u], second.upper[u])
        ov = _span_overlap(first.lower[v], first.upper[v], second.lower[v], second.upper[v])
        if ou < _SPAN_EPS or ov < _SPAN_EPS:
            continue
        name = _AXIS_NAME[axis]
        if abs(first.upper[axis] - second.upper[axis]) < _PLANE_EPS:
            return f"+{name}"
        if abs(first.lower[axis] - second.lower[axis]) < _PLANE_EPS:
            return f"-{name}"
        if abs(first.upper[axis] - second.lower[axis]) < _PLANE_EPS:
            return f"{name}-butt"
        if abs(first.lower[axis] - second.upper[axis]) < _PLANE_EPS:
            return f"{name}-butt"
    return None


def _axes_for_pair(first: KitBox, second: KitBox, *, cross_piece: bool) -> tuple[int, ...]:
    """Only the storey axis. Looking up/down is the recurring flicker; XY is shiplap."""
    del first, second, cross_piece
    return (2,)


def _assert_no_coplanar_faces(
    boxes: Sequence[KitBox],
    *,
    other: Sequence[KitBox] | None = None,
    context: str,
) -> None:
    """Fail loud when two boxes would z-fight. Interpenetration is allowed; butting is not."""
    if other is None:
        pairs = (
            (boxes[i], boxes[j])
            for i in range(len(boxes))
            for j in range(i + 1, len(boxes))
        )
        cross = False
    else:
        pairs = ((left, right) for left in boxes for right in other)
        cross = True
    for first, second in pairs:
        hit = _coplanar_face(
            first,
            second,
            axes=_axes_for_pair(first, second, cross_piece=cross),
        )
        if hit is None:
            continue
        raise SpecError(
            f"coplanar {hit} faces ({context}): "
            f"{first.slot} {first.lower}..{first.upper} vs "
            f"{second.slot} {second.lower}..{second.upper}. "
            "Sink or stand proud; do not butt on a shared plane."
        )


def _shift_axis(boxes: Sequence[KitBox], axis: int, delta: float) -> list[KitBox]:
    out: list[KitBox] = []
    for box in boxes:
        lo = list(box.lower)
        hi = list(box.upper)
        lo[axis] += delta
        hi[axis] += delta
        out.append(KitBox((lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2]), box.slot))
    return out


def _collect_layout(params: KitParams) -> list[KitBox]:
    sink = BoundsSink()
    _layout(sink, params)
    return sink.boxes


def _assert_neighbor_planes(params: KitParams, boxes: Sequence[KitBox]) -> None:
    """Fail if this mesh, or a stacked neighbor, shares a storey-axis face.

    XY is shiplap (checked by envelope + authoring). Looking up at a jetty
    soffit or through a window at the roof is always a Z-plane problem, so the
    detector only watches Z. Do not drop these stack phantoms to silence a fail.
    """
    _assert_no_coplanar_faces(boxes, context=params.kind)
    storey = params.kind in _STOREY_KINDS
    if storey:
        below = _collect_layout(replace(params, kind="plinth"))
        _assert_no_coplanar_faces(
            boxes,
            other=_shift_axis(below, 2, -params.cell_y),
            context=f"{params.kind}/plinth stack",
        )
        if params.jetty > 0.0:
            ground = _collect_layout(replace(params, jetty=0.0))
            _assert_no_coplanar_faces(
                boxes,
                other=_shift_axis(ground, 2, -params.cell_y),
                context=f"{params.kind}/ground stack",
            )
        if params.kind == "turret":
            for kind in ("corner", "wall", "turret"):
                support = _collect_layout(replace(params, kind=kind))
                _assert_no_coplanar_faces(
                    boxes,
                    other=_shift_axis(support, 2, -params.cell_y),
                    context=f"{params.kind}/{kind} stack",
                )
    if params.kind in _CAP_KINDS:
        for kind in (
            "wall",
            "wall_b",
            "window",
            "window_b",
            "window_c",
            "corner",
            "door",
            "door_b",
            "gate",
            "floor",
            "turret",
        ):
            for jetty in (0.0, _STACK_JETTY):
                if kind in ("turret", "floor") and jetty > 0.0:
                    continue
                support = _collect_layout(replace(params, kind=kind, jetty=jetty))
                _assert_no_coplanar_faces(
                    boxes,
                    other=_shift_axis(support, 2, -params.cell_y),
                    context=f"{params.kind}/{kind} jetty={jetty} stack",
                )


def _layout(builder: KitBoxes | BoundsSink, params: KitParams) -> None:
    west = params.kind == "corner"
    if params.kind == "plinth":
        _plinth(builder, params)
    elif params.kind in ("roof", "chimney"):
        _roof(builder, params, chimney=params.kind == "chimney")
    elif params.kind == "battlement":
        _battlement(builder, params)
    elif params.kind == "turret":
        _turret(builder, params)
    elif params.kind == "floor":
        _room_floor(builder, params)
    elif params.kind in (
        "wall",
        "wall_b",
        "door",
        "door_b",
        "gate",
        "window",
        "window_b",
        "window_c",
        "corner",
    ):
        _floor_slab(
            builder,
            params,
            west_wall=west,
            door=params.kind in ("door", "door_b", "gate"),
        )
        _south_wall(builder, params, shiplap_neg=not west, shiplap_pos=True)
        if west:
            _west_wall(builder, params)
        if params.kind == "gate":
            _portcullis(builder, params)
    else:
        raise SpecError(f"params.kind: unhandled {params.kind!r}")


@dataclass(frozen=True)
class KitParams:
    kind: str
    cell_xz: float
    cell_y: float
    wall_thickness: float
    overlap: float
    door_width: float
    door_height: float
    window_width: float
    window_height: float
    window_sill: float
    roof_height: float
    overhang: float
    jetty: float
    timber: bool
    bevel_width: float
    texture_resolution: int | None
    bake_samples: int
    seed: int

    @property
    def half(self) -> float:
        return self.cell_xz * 0.5


def parse_params(raw: Mapping[str, object]) -> KitParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    kind = as_str(require_key(raw, "kind", path), f"{path}.kind")
    if kind not in _KINDS:
        raise SpecError(f"{path}.kind: expected one of {_KINDS}, got {kind!r}")
    bake_keys = ("texture_resolution", "bake_samples", "seed")
    present = [key in raw for key in bake_keys]
    if any(present) and not all(present):
        raise SpecError(
            f"{path}: texture_resolution, bake_samples, and seed must be set together."
        )
    if all(present):
        texture_resolution = positive_int(
            require_key(raw, "texture_resolution", path), f"{path}.texture_resolution"
        )
        bake_samples = positive_int(
            require_key(raw, "bake_samples", path), f"{path}.bake_samples"
        )
        seed = as_int(require_key(raw, "seed", path), f"{path}.seed")
    else:
        texture_resolution = None
        bake_samples = 1
        seed = 0
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
        window_width=positive_float(
            require_key(raw, "window_width", path), f"{path}.window_width"
        ),
        window_height=positive_float(
            require_key(raw, "window_height", path), f"{path}.window_height"
        ),
        window_sill=positive_float(
            require_key(raw, "window_sill", path), f"{path}.window_sill"
        ),
        roof_height=positive_float(
            require_key(raw, "roof_height", path), f"{path}.roof_height"
        ),
        overhang=positive_float(require_key(raw, "overhang", path), f"{path}.overhang"),
        jetty=as_float(require_key(raw, "jetty", path), f"{path}.jetty"),
        timber=as_bool(require_key(raw, "timber", path), f"{path}.timber"),
        bevel_width=as_float(require_key(raw, "bevel_width", path), f"{path}.bevel_width"),
        texture_resolution=texture_resolution,
        bake_samples=bake_samples,
        seed=seed,
    )
    _validate(params)
    return params


def _face_jamb(params: KitParams) -> float:
    """Stone beside an opening. Thick curtains keep a minimum jamb, not full thickness."""
    return min(params.wall_thickness, _MIN_JAMB)


def _validate(params: KitParams) -> None:
    if params.wall_thickness >= params.cell_xz * 0.45:
        raise SpecError("params.wall_thickness leaves no interior in the cell.")
    jamb = _face_jamb(params)
    if params.door_width >= params.cell_xz - jamb * 2.0:
        raise SpecError("params.door_width leaves no wall beside the door.")
    if params.door_height >= params.cell_y:
        raise SpecError("params.door_height must be below cell_y.")
    if params.window_width >= params.cell_xz - jamb * 2.0:
        raise SpecError("params.window_width leaves no wall beside the window.")
    if params.window_sill + params.window_height >= params.cell_y:
        raise SpecError("params.window_sill + window_height must be below cell_y.")
    if params.overlap >= params.wall_thickness * 0.4:
        raise SpecError("params.overlap must be smaller than 0.4 * wall_thickness.")
    if params.jetty < 0.0:
        raise SpecError("params.jetty must be >= 0.")
    if params.jetty > params.cell_xz * 0.2:
        raise SpecError("params.jetty must be <= 20% of cell_xz.")
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
    if params.texture_resolution is not None:
        if params.texture_resolution not in {256, 512, 1024, 2048}:
            raise SpecError(
                f"params.texture_resolution ({params.texture_resolution}) "
                "must be 256, 512, 1024 or 2048"
            )
        if params.bake_samples > 128:
            raise SpecError(f"params.bake_samples ({params.bake_samples}) must be <= 128")
        if params.seed < 0:
            raise SpecError(f"params.seed ({params.seed}) must be >= 0")


def _storey_floor_z(params: KitParams) -> float:
    return params.overlap + 0.012


def _jetty_soffit_z(params: KitParams) -> float:
    """Overhang underside. Offset from the interior slab so they do not share a plane."""
    return params.overlap + 0.024


def _room_floor(builder: BoxBuilder, params: KitParams) -> None:
    """Full-cell slab at the wall-floor plane, for cells a ring does not occupy."""
    h = params.half
    thickness = 0.08
    z0 = _storey_floor_z(params)
    builder.add_box_bounds((-h, -h, z0), (h, h, z0 + thickness), "structure")


def _floor_slab(
    builder: BoxBuilder,
    params: KitParams,
    *,
    west_wall: bool,
    door: bool,
) -> None:
    """Interior slab. Stops inside the walls so it does not share an exterior face."""
    h = params.half
    t = params.wall_thickness
    sink = 0.03
    thickness = 0.08
    z0 = _storey_floor_z(params)
    x0 = -h + t - sink if west_wall else -h
    x1 = h
    y0 = -h
    y1 = h - t + sink
    builder.add_box_bounds((x0, y0, z0), (x1, y1, z0 + thickness), "structure")
    if door:
        door_half = params.door_width * 0.5
        builder.add_box_bounds(
            (-door_half - 0.03, h - t, z0 + 0.015),
            (door_half + 0.03, h + params.jetty, z0 + thickness + 0.015),
            "structure",
        )
    if params.jetty > 0.0:
        soffit = _jetty_soffit_z(params)
        builder.add_box_bounds(
            (x0, h - t + 0.01, soffit),
            (x1, h + params.jetty, soffit + thickness),
            "structure",
        )
        if west_wall:
            west_soffit = soffit + 0.012
            builder.add_box_bounds(
                (-h - params.jetty, y0, west_soffit),
                (-h + t - 0.01, y1, west_soffit + thickness),
                "structure",
            )


def _west_join_y(params: KitParams) -> float:
    """West wall +Y end sits inside the south outer wythe, not on the south plane."""
    return params.half + params.jetty - 0.04


def _wrap_post_y0(params: KitParams) -> float:
    """South-west wrap post starts here so it does not share the west timber plane."""
    return params.half + params.jetty - _CORNER_POST


def _south_span(
    params: KitParams, *, shiplap_neg: bool, shiplap_pos: bool, wythe: str
) -> tuple[float, float]:
    h = params.half
    o = params.overlap
    t = params.wall_thickness
    x0 = -h
    x1 = h
    if wythe == "outer":
        if shiplap_pos:
            x1 = h + o
        if shiplap_neg:
            x0 = -h + o
        else:
            # Corner: no -X cap on the west facade (that plane belongs to the west wythe).
            x0 = -h + t * 0.5 - 0.03
    else:
        if shiplap_pos:
            x1 = h - o
        if shiplap_neg:
            x0 = -h - o
        else:
            x0 = -h + t - 0.03
    return x0, x1


def _south_wythe_y(params: KitParams, wythe: str) -> tuple[float, float]:
    h = params.half
    t = params.wall_thickness
    half_t = t * 0.5
    if wythe == "outer":
        return (h - half_t, h + params.jetty)
    return (h - t, h - half_t + 0.02)


def _openings(params: KitParams) -> list[Opening]:
    if params.kind in ("door", "gate"):
        half = params.door_width * 0.5
        return [(-half, half, 0.0, params.door_height)]
    if params.kind == "door_b":
        half = params.door_width * 0.5
        # Door lintel and transom sill each grow by `frame` (0.08); keep them apart.
        gap = 0.20
        transom_h = 0.30
        transom_z0 = params.door_height + gap
        transom_z1 = transom_z0 + transom_h
        if transom_z1 >= params.cell_y - 0.04:
            raise SpecError("door_b transom does not fit under cell_y.")
        return [
            (-half, half, 0.0, params.door_height),
            (-half * 0.7, half * 0.7, transom_z0, transom_z1),
        ]
    if params.kind == "window":
        half = params.window_width * 0.5
        z0 = params.window_sill
        z1 = z0 + params.window_height
        return [(-half, half, z0, z1)]
    if params.kind == "window_b":
        half = params.window_width * 0.28
        gap = 0.18
        z0 = params.window_sill
        z1 = z0 + params.window_height
        left_c = -gap * 0.5 - half
        right_c = gap * 0.5 + half
        return [
            (left_c - half, left_c + half, z0, z1),
            (right_c - half, right_c + half, z0, z1),
        ]
    if params.kind == "window_c":
        light_half = params.window_width * 0.15
        # Opening trim reaches `frame` (0.08) into the gap from each side.
        gap = 0.22
        z0 = params.window_sill
        z1 = z0 + params.window_height
        pitch = light_half * 2.0 + gap
        outer = pitch + light_half
        if outer >= params.half - params.wall_thickness:
            raise SpecError("window_c lights do not fit beside the jambs.")
        return [
            (center - light_half, center + light_half, z0, z1)
            for center in (-pitch, 0.0, pitch)
        ]
    return []


def _wythe_openings(params: KitParams) -> list[Opening]:
    """Cuts in the plaster. Stacked door_b lights become one hole so lintels do not share Z."""
    if params.kind != "door_b":
        return _openings(params)
    door, transom = _openings(params)
    return [(door[0], door[1], door[2], transom[3])]


def _wythe_with_openings(
    builder: BoxBuilder,
    *,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    openings: Sequence[Opening],
    slot: str,
    z_nudge: float,
) -> None:
    """`z_nudge` offsets this wythe's sill/lintel so inner and outer do not share Z."""
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise SpecError("wythe has empty bounds.")
    if not openings:
        builder.add_box_bounds((x0, y0, z0), (x1, y1, z1), slot)
        return
    join = 0.04
    clipped: list[Opening] = []
    for ox0, ox1, oz0, oz1 in openings:
        cx0 = max(ox0, x0)
        cx1 = min(ox1, x1)
        if cx1 - cx0 < 0.02:
            continue
        clipped.append((cx0, cx1, max(oz0, z0), oz1))
    if not clipped:
        builder.add_box_bounds((x0, y0, z0), (x1, y1, z1), slot)
        return
    clipped.sort(key=lambda item: item[0])
    cursor = x0
    for ox0, ox1, oz0, oz1 in clipped:
        if ox0 > cursor + 0.01:
            builder.add_box_bounds((cursor, y0, z0), (ox0, y1, z1), slot)
        if oz0 > z0 + 0.02:
            builder.add_box_bounds(
                (ox0 - join, y0, z0 + 0.028 + z_nudge),
                (ox1 + join, y1, oz0 + 0.02 - z_nudge),
                slot,
            )
        if oz1 < z1 - 0.02:
            builder.add_box_bounds(
                (ox0 - join, y0, oz1 - 0.025 + z_nudge),
                (ox1 + join, y1, z1 - 0.04 - z_nudge),
                slot,
            )
        cursor = ox1
    if x1 > cursor + 0.01:
        builder.add_box_bounds((cursor, y0, z0), (x1, y1, z1), slot)


def _south_wall(
    builder: BoxBuilder,
    params: KitParams,
    *,
    shiplap_neg: bool,
    shiplap_pos: bool,
) -> None:
    """Exterior slab on +Y. `shiplap_pos` covers the +X join; `shiplap_neg` the -X join."""
    t = params.wall_thickness
    o = params.overlap
    z_outer = params.cell_y
    z_inner = params.cell_y - 0.015
    z0_outer = o
    z0_inner = o + 0.015
    inner_y = _south_wythe_y(params, "inner")[0]
    openings = _wythe_openings(params)
    for wythe, z0, z1, z_nudge in (
        ("outer", z0_outer, z_outer, 0.0),
        ("inner", z0_inner, z_inner, 0.016),
    ):
        x0, x1 = _south_span(
            params, shiplap_neg=shiplap_neg, shiplap_pos=shiplap_pos, wythe=wythe
        )
        y0, y1 = _south_wythe_y(params, wythe)
        _wythe_with_openings(
            builder,
            x0=x0,
            x1=x1,
            y0=y0,
            y1=y1,
            z0=z0,
            z1=z1,
            openings=openings,
            slot="structure",
            z_nudge=z_nudge,
        )
    x0, x1 = _south_span(
        params, shiplap_neg=shiplap_neg, shiplap_pos=shiplap_pos, wythe="inner"
    )
    _south_cornice(builder, params, x0, x1, inner_y, z_inner - 0.015)
    _opening_trim(builder, params, _openings(params))
    if params.timber:
        y0, y1 = _south_wythe_y(params, "outer")
        _timber_south(builder, params, x0, x1, y1)


def _opening_trim(builder: BoxBuilder, params: KitParams, openings: Sequence[Opening]) -> None:
    if not openings:
        return
    t = params.wall_thickness
    inner_y = _south_wythe_y(params, "inner")[0]
    y0 = inner_y + 0.02
    y1 = params.half + params.jetty - 0.02
    frame = min(0.08, t * 0.5)
    proud = 0.02
    o = params.overlap
    for ox0, ox1, oz0, oz1 in openings:
        jamb_z0 = max(oz0 - 0.03, o + 0.018)
        jamb_z1 = oz1 + 0.05
        builder.add_box_bounds((ox0 - frame, y0, jamb_z0), (ox0 + proud, y1, jamb_z1), "trim")
        builder.add_box_bounds((ox1 - proud, y0, jamb_z0), (ox1 + frame, y1, jamb_z1), "trim")
        oz1_hi = min(oz1 + frame, params.cell_y - 0.02)
        builder.add_box_bounds((ox0 - frame, y0, oz1 - 0.03), (ox1 + frame, y1, oz1_hi), "trim")
        if oz0 > 0.05:
            builder.add_box_bounds(
                (ox0 - frame, y0, oz0 - frame),
                (ox1 + frame, y1, oz0 + 0.03),
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
    builder.add_box_bounds(
        (x0 + 0.08, inner_y - depth, z1 - height),
        (x1 - 0.03, inner_y + sink, z1),
        "trim",
    )


def _brace_steps(
    a0: float,
    a1: float,
    z0: float,
    z1: float,
    *,
    rising: bool,
) -> list[tuple[float, float, float, float]]:
    """Overlapping (axis, Z) boxes for one diagonal. Empty when the bay is too small."""
    if a1 - a0 < 0.42 or z1 - z0 < 0.42:
        return []
    steps = 6
    thick = 0.09
    span_a = a1 - a0
    span_z = z1 - z0
    boxes: list[tuple[float, float, float, float]] = []
    for index in range(steps):
        t0 = index / steps
        t1 = (index + 1) / steps
        ba0 = a0 + span_a * t0
        ba1 = a0 + span_a * t1 + 0.03
        if rising:
            bz0 = z0 + span_z * t0
            bz1 = z0 + span_z * t1 + thick
        else:
            bz0 = z1 - span_z * t1 - thick
            bz1 = z1 - span_z * t0 + 0.02
            if bz0 < z0:
                bz0 = z0 + 0.015
        boxes.append((ba0, ba1, bz0, bz1))
    return boxes


def _x_brace(
    builder: BoxBuilder,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
) -> None:
    """X-brace spanning X, sitting on a south (+Y) facade."""
    for rising in (True, False):
        for bx0, bx1, bz0, bz1 in _brace_steps(x0, x1, z0, z1, rising=rising):
            builder.add_box_bounds((bx0, y0, bz0), (bx1, y1, bz1), "trim")


def _x_brace_y(
    builder: BoxBuilder,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
) -> None:
    """X-brace spanning Y, sitting on a west (−X) facade."""
    for rising in (True, False):
        for by0, by1, bz0, bz1 in _brace_steps(y0, y1, z0, z1, rising=rising):
            builder.add_box_bounds((x0, by0, bz0), (x1, by1, bz1), "trim")


def _horizontal_rail(
    builder: BoxBuilder,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    openings: Sequence[Opening],
) -> None:
    """Wall-plate / mid-rail, cut where an opening occupies the same Z."""
    gaps = [(ox0, ox1) for ox0, ox1, oz0, oz1 in openings if oz0 < z1 and oz1 > z0]
    cursor = x0
    for gx0, gx1 in gaps:
        if gx0 > cursor:
            builder.add_box_bounds((cursor, y0, z0), (gx0, y1, z1), "trim")
        cursor = max(cursor, gx1)
    if cursor < x1:
        builder.add_box_bounds((cursor, y0, z0), (x1, y1, z1), "trim")


def _bay_x_braces(
    builder: BoxBuilder,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z_lo: float,
    z_mid0: float,
    z_mid1: float,
    z_hi: float,
) -> None:
    _x_brace(builder, x0, x1, y0, y1, z_lo - 0.02, z_mid0 + 0.02)
    _x_brace(builder, x0, x1, y0, y1, z_mid1 - 0.02, z_hi + 0.02)


def _timber_south(
    builder: BoxBuilder, params: KitParams, x0: float, x1: float, y_outer: float
) -> None:
    """Half-timber frame: posts, plates, mid-rail, X-braces. Proud of the plaster."""
    post = 0.15
    rail = 0.12
    proud = _TIMBER_PROUD
    y0 = y_outer - 0.08
    y1 = y_outer + proud
    plate_z0 = params.overlap + 0.02
    plate_z1 = params.cell_y - 0.02
    post_z0 = plate_z0 + 0.01
    post_z1 = plate_z1 - 0.01
    wrap = params.kind == "corner"
    left = x0 + 0.02
    right = x1 - 0.02
    if wrap:
        plate_x0 = -params.half - params.jetty + _CORNER_POST
        inner_l = plate_x0
    else:
        plate_x0 = x0
        inner_l = left + post
        builder.add_box_bounds((left, y0, post_z0), (left + post, y1, post_z1), "trim")
    builder.add_box_bounds((right - post, y0, post_z0), (right, y1, post_z1), "trim")
    builder.add_box_bounds((plate_x0, y0, plate_z1 - rail), (x1, y1, plate_z1), "trim")
    if params.kind not in ("door", "door_b"):
        builder.add_box_bounds((plate_x0, y0, plate_z0), (x1, y1, plate_z0 + rail), "trim")
    inner_r = right - post
    mid_z0 = plate_z0 + (plate_z1 - plate_z0) * 0.46
    mid_z1 = mid_z0 + rail
    z_lo = plate_z0 + rail + 0.012
    z_hi = plate_z1 - rail - 0.012
    openings = _openings(params)
    timber_gaps = [o for o in openings if o[2] < 0.5] if params.kind == "door_b" else openings
    _horizontal_rail(builder, inner_l, inner_r, y0, y1, mid_z0, mid_z1, timber_gaps)
    if params.kind == "wall":
        mid = (x0 + x1) * 0.5
        builder.add_box_bounds(
            (mid - post * 0.5, y0, post_z0),
            (mid + post * 0.5, y1, post_z1),
            "trim",
        )
        _bay_x_braces(builder, inner_l, mid - post * 0.5, y0, y1, z_lo, mid_z0, mid_z1, z_hi)
        _bay_x_braces(builder, mid + post * 0.5, inner_r, y0, y1, z_lo, mid_z0, mid_z1, z_hi)
    elif params.kind == "wall_b":
        _close_studs(builder, inner_l, inner_r, y0, y1, post_z0, post_z1, timber_gaps)
    elif timber_gaps:
        cursor = inner_l
        for ox0, ox1, _oz0, _oz1 in timber_gaps:
            _bay_x_braces(builder, cursor, ox0 - 0.04, y0, y1, z_lo, mid_z0, mid_z1, z_hi)
            cursor = ox1 + 0.04
        _bay_x_braces(builder, cursor, inner_r, y0, y1, z_lo, mid_z0, mid_z1, z_hi)
    _jetty_supports(builder, params, x0, x1, y_outer)


def _close_studs(
    builder: BoxBuilder,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    openings: Sequence[Opening],
) -> None:
    """Close-studded bay: many verticals, no X-braces. Skip opening spans."""
    stud = 0.075
    spacing = 0.30
    cursor = x0
    while cursor + stud <= x1 + 0.001:
        sx1 = cursor + stud
        blocked = any(ox0 < sx1 and ox1 > cursor for ox0, ox1, _oz0, _oz1 in openings)
        if not blocked:
            builder.add_box_bounds((cursor, y0, z0), (sx1, y1, z1), "trim")
        cursor += spacing


def _jetty_supports(
    builder: BoxBuilder, params: KitParams, x0: float, x1: float, y_outer: float
) -> None:
    """Joists in the overhang plus short corbels dropping into the air below.

    Joists bite into the soffit from below so they do not share its underside.
    Corbels stay past the ground-storey timber proud plane (neighbor stack).
    """
    if params.jetty <= 0.0:
        return
    y_out = params.half + params.jetty
    y_over = params.half + _TIMBER_PROUD + 0.012
    soffit = _jetty_soffit_z(params)
    joist = 0.08
    for index in range(4):
        u = (index + 0.5) / 4.0
        cx = x0 + (x1 - x0) * u
        builder.add_box_bounds(
            (cx - joist * 0.5, y_over, soffit - 0.07),
            (cx + joist * 0.5, y_out, soffit + 0.03),
            "trim",
        )
        drop = soffit - 0.38
        builder.add_box_bounds(
            (cx - 0.06, y_over, drop),
            (cx + 0.06, y_out, soffit - 0.02),
            "trim",
        )
        builder.add_box_bounds(
            (cx - 0.05, params.half + params.jetty * 0.35, drop + 0.12),
            (cx + 0.05, y_out, soffit - 0.04),
            "trim",
        )


def _corner_wrap_post(builder: BoxBuilder, params: KitParams) -> None:
    """One post proud on south (+Y) and west (−X). Hides the L; no second cap on either plane."""
    post = _CORNER_POST
    proud = _TIMBER_PROUD
    h = params.half
    j = params.jetty
    y0 = _wrap_post_y0(params)
    builder.add_box_bounds(
        (-h - j - proud, y0, params.overlap + 0.038),
        (-h - j + post, h + j + proud, params.cell_y - 0.038),
        "trim",
    )


def _west_wall(builder: BoxBuilder, params: KitParams) -> None:
    """Exterior slab on -X. -Y end shiplaps the pos_z join; +Y end sinks into the south wall."""
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    j = params.jetty
    half_t = t * 0.5
    z_inner = params.cell_y - 0.048
    z_outer = params.cell_y - 0.015
    z0_outer = o + 0.015
    z0_inner = o + 0.042
    y_join = _west_join_y(params)
    builder.add_box_bounds((-h - j, -h + o, z0_outer), (-h + half_t, y_join, z_outer), "structure")
    builder.add_box_bounds(
        (-h + half_t - 0.02, -h - o, z0_inner),
        (-h + t, y_join, z_inner),
        "structure",
    )
    inner_x = -h + t
    builder.add_box_bounds(
        (inner_x + 0.01, -h - o, z_inner - 0.125),
        (inner_x + 0.06, y_join, z_inner - 0.035),
        "trim",
    )
    if params.timber:
        post = 0.15
        rail = 0.12
        x0 = -h - j - _TIMBER_PROUD
        x1 = -h - j + 0.09
        timber_y1 = _wrap_post_y0(params)
        plate_z0 = o + 0.02
        plate_z1 = params.cell_y - 0.02
        post_z0 = plate_z0 + 0.03
        post_z1 = plate_z1 - 0.018
        builder.add_box_bounds((x0, -h + o, post_z0), (x1 + post, -h + o + post, post_z1), "trim")
        builder.add_box_bounds((x0, -h + o, plate_z1 - rail), (x1 + post, timber_y1, plate_z1), "trim")
        builder.add_box_bounds((x0, -h + o, plate_z0), (x1 + post, timber_y1, plate_z0 + rail), "trim")
        _corner_wrap_post(builder, params)
        mid_y = (-h + o + timber_y1) * 0.5
        z_lo = plate_z0 + rail + 0.012
        z_hi = plate_z1 - rail - 0.012
        mid_z0 = plate_z0 + (plate_z1 - plate_z0) * 0.46
        mid_z1 = mid_z0 + rail
        builder.add_box_bounds((x0, mid_y - rail * 0.5, post_z0), (x1 + post, mid_y + rail * 0.5, post_z1), "trim")
        builder.add_box_bounds((x0, -h + o, mid_z0), (x1 + post, timber_y1, mid_z1), "trim")
        y_inner0 = -h + o + post
        y_inner1 = timber_y1 - post
        _x_brace_y(builder, x0, x1 + post, y_inner0, mid_y - rail * 0.5, z_lo - 0.02, mid_z0 + 0.02)
        _x_brace_y(builder, x0, x1 + post, y_inner0, mid_y - rail * 0.5, mid_z1 - 0.02, z_hi + 0.02)
        _x_brace_y(builder, x0, x1 + post, mid_y + rail * 0.5, y_inner1, z_lo - 0.02, mid_z0 + 0.02)
        _x_brace_y(builder, x0, x1 + post, mid_y + rail * 0.5, y_inner1, mid_z1 - 0.02, z_hi + 0.02)
        if j > 0.0:
            soffit = _jetty_soffit_z(params)
            for index in range(3):
                u = (index + 0.5) / 3.0
                cy = (-h + o) + (y_join - (-h + o)) * u
                drop = soffit - 0.38
                builder.add_box_bounds(
                    (-h - j, cy - 0.06, drop),
                    (-h - _TIMBER_PROUD - 0.012, cy + 0.06, soffit - 0.02),
                    "trim",
                )


def _battlement(builder: BoxBuilder, params: KitParams) -> None:
    """Crenellated cap. Walk and merlons start at `overlap`, never on the storey plane."""
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    walk_z0 = o
    walk_z1 = o + 0.12
    builder.add_box_bounds(
        (-h + o, -h + 0.05, walk_z0),
        (h - o, h - 0.03, walk_z1),
        "structure",
    )
    rail_z0 = walk_z1 - 0.04
    rail_z1 = o + 0.58
    builder.add_box_bounds(
        (-h + 0.1, -h + 0.05, rail_z0),
        (h - 0.1, -h + 0.16, rail_z1),
        "trim",
    )
    sill_z0 = o + 0.03
    sill_z1 = o + 0.46
    y0_outer = h - min(t * 0.4, 0.55)
    y1_outer = h
    builder.add_box_bounds(
        (-h + o, y0_outer + 0.03, sill_z0),
        (h - o, y1_outer - 0.03, sill_z1),
        "structure",
    )
    merlon_w = 0.56
    crenel_w = 0.42
    merlon_z0 = walk_z1 - 0.05
    merlon_z1 = o + 1.16
    x = -h + 0.18
    while x + merlon_w <= h - 0.18:
        builder.add_box_bounds(
            (x, y0_outer, merlon_z0),
            (x + merlon_w, y1_outer, merlon_z1),
            "structure",
        )
        x += merlon_w + crenel_w


def _turret(builder: BoxBuilder, params: KitParams) -> None:
    """Four-sided extra storey. No horizontal catalog docks; walls stay in-cell."""
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    cy = params.cell_y
    builder.add_box_bounds(
        (-h + t - 0.04, -h + t - 0.04, o + 0.04),
        (h - t + 0.04, h - t + 0.04, o + 0.13),
        "structure",
    )
    slit_half = params.window_width * 0.5
    slit_z0 = params.window_sill
    slit_z1 = params.window_sill + params.window_height
    openings = [(-slit_half, slit_half, slit_z0, slit_z1)]
    _wythe_with_openings(
        builder,
        x0=-h + o,
        x1=h - o,
        y0=h - t,
        y1=h,
        z0=o,
        z1=cy,
        openings=openings,
        slot="structure",
        z_nudge=0.0,
    )
    builder.add_box_bounds((-h + o, -h, o + 0.02), (h - o, -h + t, cy - 0.02), "structure")
    builder.add_box_bounds((-h, -h + o, o + 0.014), (-h + t, h - o, cy - 0.018), "structure")
    builder.add_box_bounds((h - t, -h + o, o + 0.028), (h, h - o, cy - 0.032), "structure")
    builder.add_box_bounds(
        (-h + t - 0.1, h - t - 0.05, cy - 0.16),
        (h - t + 0.1, h - t + 0.04, cy - 0.055),
        "trim",
    )


def _portcullis(builder: BoxBuilder, params: KitParams) -> None:
    """Raised grate baked into the gate mesh so the doorway stays an entrance.

    Not an attach socket. Bars sit in the lintel zone; the walk-through is open.
    """
    half = params.door_width * 0.5
    t = params.wall_thickness
    h = params.half
    y0 = h - t + 0.28
    y1 = h - 0.28
    if y1 <= y0:
        return
    # Stay below the opening-trim lintel (door_height-0.03 .. cell_y) so Z does not butt.
    bar_z1 = params.door_height - 0.22
    bar_z0 = bar_z1 - 0.3
    rail_lo0 = bar_z0 - 0.04
    rail_lo1 = bar_z0 + 0.05
    rail_hi0 = bar_z1 - 0.05
    rail_hi1 = bar_z1 + 0.04
    builder.add_box_bounds((-half + 0.07, y0, rail_lo0), (half - 0.07, y1, rail_lo1), "trim")
    builder.add_box_bounds((-half + 0.07, y0, rail_hi0), (half - 0.07, y1, rail_hi1), "trim")
    bar = 0.055
    gap = 0.2
    x = -half + 0.1
    while x + bar < half - 0.1:
        builder.add_box_bounds((x, y0, bar_z0), (x + bar, y1, bar_z1), "trim")
        x += gap


def _roof(builder: BoxBuilder, params: KitParams, *, chimney: bool) -> None:
    """Stepped shingle cap. Layers interpenetrate in Z. Chimney stack uses trim.

    Underside starts at `overlap`, never on the storey plane (that is the wall-top
    of the piece below). Eaves sit above that soffit so they do not share it.
    """
    h = params.half
    lift = params.overlap
    layers = 8 if params.timber else 4
    step = params.roof_height / layers
    sink = 0.018
    for index in range(layers):
        shrink = params.overhang * index / max(layers - 1, 1)
        z0 = lift + index * step
        z1 = z0 + step + sink
        builder.add_box_bounds(
            (-h + shrink, -h + shrink, z0),
            (h - shrink, h - shrink, z1),
            "structure",
        )
    cap = h - params.overhang - 0.08
    z_top = lift + layers * step
    builder.add_box_bounds((-cap, -cap, z_top - 0.04), (cap, cap, z_top + 0.08), "trim")
    if params.timber:
        eave = 0.05
        eave_z0 = lift + 0.03
        builder.add_box_bounds((-h - eave, -h - eave, eave_z0), (h + eave, -h + 0.06, eave_z0 + 0.1), "trim")
        builder.add_box_bounds((-h - eave, h - 0.06, eave_z0), (h + eave, h + eave, eave_z0 + 0.1), "trim")
        builder.add_box_bounds((-h - eave, -h + 0.06, eave_z0), (-h + 0.06, h - 0.06, eave_z0 + 0.1), "trim")
        builder.add_box_bounds((h - 0.06, -h + 0.06, eave_z0), (h + eave, h - 0.06, eave_z0 + 0.1), "trim")
        ridge = 0.07
        builder.add_box_bounds((-ridge, -cap, z_top - 0.02), (ridge, cap, z_top + 0.12), "trim")
        builder.add_box_bounds((-cap, -ridge, z_top - 0.008), (cap, ridge, z_top + 0.132), "trim")
    if chimney:
        stack = 0.42
        base = z_top - 0.08
        course = 0.22
        for index in range(6):
            inset = 0.0 if index % 2 == 0 else 0.03
            z0 = base + index * course + (0.008 if index % 2 else 0.0)
            builder.add_box_bounds(
                (-stack + inset, -stack + inset, z0),
                (stack - inset, stack - inset, z0 + course + 0.02),
                "trim",
            )
        top = base + 6 * course
        lip = 0.08
        builder.add_box_bounds(
            (-stack - lip, -stack - lip, top - 0.1),
            (stack + lip, stack + lip, top + 0.08),
            "trim",
        )


def _plinth(builder: BoxBuilder, params: KitParams) -> None:
    h = params.half
    top = params.cell_y
    builder.add_box_bounds((-h, -h, 0.0), (h, h, top), "structure")
    recess = 0.04
    builder.add_box_bounds(
        (-h + recess, -h + recess, top - 0.08),
        (h - recess, h - recess, top - 0.01),
        "trim",
    )
    if params.timber:
        proud = 0.05
        courses = 5
        course_h = top / courses
        corners = ((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))
        for corner_i, (sx, sy) in enumerate(corners):
            z_pad = 0.012 + corner_i * 0.006
            for index in range(courses):
                block = 0.34 + (0.05 if index % 2 == 0 else 0.0)
                z0 = index * course_h + z_pad
                z1 = top - z_pad if index == courses - 1 else (index + 1) * course_h + 0.02
                if sx < 0.0:
                    x0, x1 = -h - proud, -h + block
                else:
                    x0, x1 = h - block, h + proud
                if sy < 0.0:
                    y0, y1 = -h - proud, -h + block
                else:
                    y0, y1 = h - block, h + proud
                builder.add_box_bounds((x0, y0, z0), (x1, y1, z1), "trim")


def _mix_rgba(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    *,
    location: tuple[float, float],
    factor: bpy.types.NodeSocket,
    color_a: bpy.types.NodeSocket,
    color_b: bpy.types.NodeSocket,
) -> bpy.types.NodeSocket:
    mix = nodes.new(type="ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.location = location
    links.new(factor, mix.inputs[0])
    links.new(color_a, mix.inputs[6])
    links.new(color_b, mix.inputs[7])
    return mix.outputs[2]


def _slot_look(params: KitParams, slot: str) -> str:
    if params.kind == "plinth":
        if params.wall_thickness >= 1.0:
            return "ashlar" if slot == "structure" else "stone_trim"
        return "stone" if slot == "structure" else "stone_trim"
    if params.kind in ("roof", "chimney"):
        if slot == "structure":
            return "shingle"
        return "brick" if params.kind == "chimney" else "timber"
    if params.kind in ("battlement", "turret", "gate") or params.wall_thickness >= 1.0:
        return "ashlar" if slot == "structure" else "stone_trim"
    if slot == "structure":
        return "plaster"
    return "timber"


def _noise(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    generated: bpy.types.NodeSocket,
    *,
    location: tuple[float, float],
    scale: tuple[float, float, float],
    offset: tuple[float, float, float],
    detail: float,
    roughness: float,
) -> bpy.types.NodeSocket:
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.location = location
    mapping.inputs["Scale"].default_value = scale
    mapping.inputs["Location"].default_value = offset
    links.new(generated, mapping.inputs["Vector"])
    noise = nodes.new(type="ShaderNodeTexNoise")
    noise.location = (location[0] + 200.0, location[1])
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = roughness
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    return noise.outputs["Fac"]


def _wave(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    generated: bpy.types.NodeSocket,
    *,
    location: tuple[float, float],
    scale: tuple[float, float, float],
    rotation: tuple[float, float, float],
    offset: tuple[float, float, float],
    wave_scale: float,
    distortion: float,
    bands: str,
) -> bpy.types.NodeSocket:
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.location = location
    mapping.inputs["Scale"].default_value = scale
    mapping.inputs["Rotation"].default_value = rotation
    mapping.inputs["Location"].default_value = offset
    links.new(generated, mapping.inputs["Vector"])
    wave = nodes.new(type="ShaderNodeTexWave")
    wave.location = (location[0] + 200.0, location[1])
    wave.wave_type = "BANDS"
    wave.bands_direction = bands
    wave.wave_profile = "SIN"
    wave.inputs["Scale"].default_value = wave_scale
    wave.inputs["Distortion"].default_value = distortion
    wave.inputs["Detail"].default_value = 2.0
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    return wave.outputs["Fac"]


def _build_look_material(
    name: str,
    spec: MaterialSpec,
    look: str,
    seed: int,
) -> bpy.types.Material:
    """Procedural look for one kit slot. Baked to images before export."""
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (1100, 0)
    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (850, 0)
    principled.inputs["Metallic"].default_value = spec.metallic
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    tex_coord.location = (-900, 80)
    generated = tex_coord.outputs["Generated"]
    shift = float(seed % 1000) * 0.17

    base_rgb = nodes.new(type="ShaderNodeRGB")
    base_rgb.location = (-200, 420)
    base_rgb.outputs[0].default_value = spec.base_color
    dark_rgb = nodes.new(type="ShaderNodeRGB")
    dark_rgb.location = (-200, 560)
    dark_rgb.outputs[0].default_value = (
        max(0.0, spec.base_color[0] * 0.28),
        max(0.0, spec.base_color[1] * 0.28),
        max(0.0, spec.base_color[2] * 0.24),
        1.0,
    )
    lift_rgb = nodes.new(type="ShaderNodeRGB")
    lift_rgb.location = (-200, 280)
    lift_rgb.outputs[0].default_value = (
        min(1.0, spec.base_color[0] * 1.18 + 0.04),
        min(1.0, spec.base_color[1] * 1.12 + 0.03),
        min(1.0, spec.base_color[2] * 1.05 + 0.02),
        1.0,
    )

    if look == "timber":
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(1.6, 1.6, 14.0),
            offset=(shift, shift * 0.4, shift * 0.2),
            detail=8.0,
            roughness=0.55,
        )
        grain = _wave(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(0.35, 0.35, 4.5),
            rotation=(0.0, 0.0, 0.08),
            offset=(shift * 0.3, 0.0, shift * 0.1),
            wave_scale=18.0,
            distortion=2.4,
            bands="Z",
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=grit,
            color_a=dark_rgb.outputs[0],
            color_b=base_rgb.outputs[0],
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(280, 80),
            factor=grain,
            color_a=color,
            color_b=lift_rgb.outputs[0],
        )
        bump_height = grit
        bump_strength = 0.55
        rough_base = spec.roughness
    elif look == "shingle":
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(3.2, 3.2, 1.4),
            offset=(shift, shift * 0.4, 0.0),
            detail=4.0,
            roughness=0.45,
        )
        rows = _wave(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(1.0, 1.0, 5.5),
            rotation=(0.0, 0.0, 0.04),
            offset=(0.0, 0.0, shift * 0.08),
            wave_scale=2.4,
            distortion=0.35,
            bands="Z",
        )
        cols = _wave(
            nodes,
            links,
            generated,
            location=(-700, -280),
            scale=(4.2, 1.0, 1.0),
            rotation=(0.0, 0.0, 0.0),
            offset=(shift * 0.12, 0.0, 0.0),
            wave_scale=1.6,
            distortion=0.2,
            bands="X",
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=rows,
            color_a=dark_rgb.outputs[0],
            color_b=base_rgb.outputs[0],
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(280, 80),
            factor=cols,
            color_a=color,
            color_b=lift_rgb.outputs[0],
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(460, 40),
            factor=grit,
            color_a=color,
            color_b=base_rgb.outputs[0],
        )
        bump_height = rows
        bump_strength = 0.4
        rough_base = spec.roughness
    elif look == "thatch":
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(6.0, 6.0, 2.0),
            offset=(shift, shift * 0.5, 0.0),
            detail=6.0,
            roughness=0.7,
        )
        straw = _wave(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(3.5, 0.4, 0.4),
            rotation=(0.0, 0.0, 0.15 + shift * 0.01),
            offset=(shift * 0.2, shift * 0.1, 0.0),
            wave_scale=8.0,
            distortion=2.2,
            bands="X",
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=straw,
            color_a=dark_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(280, 80),
            factor=grit,
            color_a=color,
            color_b=base_rgb.outputs[0],
        )
        bump_height = straw
        bump_strength = 0.85
        rough_base = spec.roughness
    elif look == "ashlar":
        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        tex_coord.location = (-920, 200)
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.location = (-700, 200)
        mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, 1.5708)
        mapping.inputs["Location"].default_value = (shift * 0.04, shift * 0.02, 0.0)
        links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
        brick = nodes.new(type="ShaderNodeTexBrick")
        brick.location = (-420, 200)
        brick.offset = 0.5
        brick.offset_frequency = 2
        brick.squash = 1.0
        brick.inputs["Scale"].default_value = 7.0
        brick.inputs["Mortar Size"].default_value = 0.018
        brick.inputs["Mortar Smooth"].default_value = 0.04
        brick.inputs["Bias"].default_value = -0.15
        brick.inputs["Brick Width"].default_value = 0.55
        brick.inputs["Row Height"].default_value = 0.28
        brick.inputs["Color1"].default_value = spec.base_color
        brick.inputs["Color2"].default_value = (
            max(0.0, spec.base_color[0] * 0.82),
            max(0.0, spec.base_color[1] * 0.8),
            max(0.0, spec.base_color[2] * 0.75),
            1.0,
        )
        brick.inputs["Mortar"].default_value = (0.14, 0.12, 0.1, 1.0)
        links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
        color = brick.outputs["Color"]
        bump_height = brick.outputs["Fac"]
        bump_strength = 1.1
        rough_base = spec.roughness
    elif look in ("stone", "stone_trim", "brick"):
        if look == "brick":
            brick_scale, row_scale = 4.5, 7.0
            mortar_lo, mortar_hi = 0.12, 0.28
        else:
            brick_scale, row_scale = 3.2, 4.0
            mortar_lo, mortar_hi = 0.12, 0.28
        mortar_x = _wave(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(brick_scale, 1.0, 1.0),
            rotation=(0.0, 0.0, 0.0),
            offset=(shift * 0.1, 0.0, 0.0),
            wave_scale=1.0,
            distortion=0.85 if look != "ashlar" else 0.35,
            bands="X",
        )
        mortar_z = _wave(
            nodes,
            links,
            generated,
            location=(-700, -40),
            scale=(1.0, 1.0, row_scale),
            rotation=(0.0, 0.0, 0.0),
            offset=(0.0, 0.0, shift * 0.08),
            wave_scale=1.0,
            distortion=0.7 if look != "ashlar" else 0.25,
            bands="Z",
        )
        mortar = nodes.new(type="ShaderNodeMath")
        mortar.location = (-280, 80)
        mortar.operation = "MULTIPLY"
        links.new(mortar_x, mortar.inputs[0])
        links.new(mortar_z, mortar.inputs[1])
        mortar_mask = nodes.new(type="ShaderNodeMapRange")
        mortar_mask.location = (-80, 80)
        mortar_mask.inputs["From Min"].default_value = mortar_lo
        mortar_mask.inputs["From Max"].default_value = mortar_hi
        mortar_mask.clamp = True
        links.new(mortar.outputs["Value"], mortar_mask.inputs["Value"])
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-700, 420),
            scale=(4.5, 4.5, 4.5),
            offset=(shift * 0.4, shift * 0.2, shift * 0.1),
            detail=7.0,
            roughness=0.62,
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 280),
            factor=grit,
            color_a=dark_rgb.outputs[0],
            color_b=base_rgb.outputs[0],
        )
        mortar_rgb = nodes.new(type="ShaderNodeRGB")
        mortar_rgb.location = (80, 40)
        mortar_rgb.outputs[0].default_value = (
            (0.14, 0.12, 0.1, 1.0) if look == "ashlar" else (0.22, 0.20, 0.17, 1.0)
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(300, 80),
            factor=mortar_mask.outputs["Result"],
            color_a=color,
            color_b=mortar_rgb.outputs[0],
        )
        bump_height = grit
        bump_strength = 0.7 if look != "stone_trim" else 0.45
        rough_base = spec.roughness
    elif look == "plaster":
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(1.4, 1.4, 1.4),
            offset=(shift, shift * 0.6, shift * 0.3),
            detail=3.0,
            roughness=0.35,
        )
        grit_mask = nodes.new(type="ShaderNodeMapRange")
        grit_mask.location = (-280, 200)
        grit_mask.inputs["From Min"].default_value = 0.35
        grit_mask.inputs["From Max"].default_value = 0.72
        grit_mask.inputs["To Min"].default_value = 0.0
        grit_mask.inputs["To Max"].default_value = 0.18
        grit_mask.clamp = True
        links.new(grit, grit_mask.inputs["Value"])
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=grit_mask.outputs["Result"],
            color_a=base_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        bump_height = grit
        bump_strength = 0.12
        rough_base = spec.roughness
    else:
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(3.2, 3.2, 3.2),
            offset=(shift, shift * 0.6, shift * 0.3),
            detail=8.0,
            roughness=0.58,
        )
        stain = _noise(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(1.1, 1.1, 2.8),
            offset=(shift * 0.15, shift * 0.4, shift * 0.05),
            detail=4.0,
            roughness=0.45,
        )
        stain_mask = nodes.new(type="ShaderNodeMapRange")
        stain_mask.location = (-280, -80)
        stain_mask.inputs["From Min"].default_value = 0.62
        stain_mask.inputs["From Max"].default_value = 0.88
        stain_mask.clamp = True
        links.new(stain, stain_mask.inputs["Value"])
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=grit,
            color_a=dark_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(280, 40),
            factor=stain_mask.outputs["Result"],
            color_a=color,
            color_b=base_rgb.outputs[0],
        )
        bump_height = grit
        bump_strength = 0.35
        rough_base = spec.roughness

    links.new(color, principled.inputs["Base Color"])
    rough_math = nodes.new(type="ShaderNodeMath")
    rough_math.location = (520, -160)
    rough_math.operation = "MULTIPLY_ADD"
    rough_math.inputs[1].default_value = 0.22
    rough_math.inputs[2].default_value = rough_base * 0.82
    links.new(bump_height, rough_math.inputs[0])
    clamp_rough = nodes.new(type="ShaderNodeClamp")
    clamp_rough.location = (700, -160)
    clamp_rough.inputs["Min"].default_value = 0.3
    clamp_rough.inputs["Max"].default_value = 1.0
    links.new(rough_math.outputs["Value"], clamp_rough.inputs["Value"])
    links.new(clamp_rough.outputs["Result"], principled.inputs["Roughness"])
    bump = nodes.new(type="ShaderNodeBump")
    bump.location = (700, -320)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.04
    links.new(bump_height, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return material


def _apply_procedural_slots(obj: bpy.types.Object, spec: AssetSpec, params: KitParams) -> None:
    mesh = obj.data
    if len(mesh.materials) != len(MATERIAL_SLOTS):
        raise SpecError(
            f"{spec.asset_id} has {len(mesh.materials)} material slots, "
            f"expected {len(MATERIAL_SLOTS)}."
        )
    for index, slot in enumerate(MATERIAL_SLOTS):
        look = _slot_look(params, slot)
        mesh.materials[index] = _build_look_material(
            f"{spec.asset_id}_{slot}_{look}",
            spec.materials[slot],
            look,
            params.seed,
        )


def _bake_kit_textures(obj: bpy.types.Object, spec: AssetSpec, params: KitParams) -> None:
    if params.texture_resolution is None:
        return
    _apply_procedural_slots(obj, spec, params)
    texture_dump = Path(__file__).resolve().parents[2] / "assets" / "out" / "textures"
    maps = bake_maps(
        obj,
        asset_id=spec.asset_id,
        resolution=params.texture_resolution,
        samples=params.bake_samples,
        dump_dir=texture_dump,
    )
    apply_baked_principled(obj, maps, metallic=spec.materials["structure"].metallic)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    builder = KitBoxes()
    _layout(builder, params)
    _assert_kit_envelope(params, builder.boxes)
    _assert_neighbor_planes(params, builder.boxes)
    obj = builder.to_object(spec.asset_id, spec.materials)
    if params.bevel_width > 0.0:
        apply_bevel(obj, width=params.bevel_width, segments=1, angle_deg=30.0)
    shade_flat(obj)
    unwrap(obj)
    _bake_kit_textures(obj, spec, params)
    return [obj]
