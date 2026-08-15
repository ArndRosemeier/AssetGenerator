"""One-cell kit pieces: wall, corner, door, gate, window, roof, chimney, plinth,
floor, battlement, turret, plus dungeon tiles (open/wall/passage/end/cap/mouth/shaft/stair).

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

`jagged` switches the dungeon kinds from dressed stone to a cave shell: two
displaced rock masses (floor sweeping up into the walls, vault doming over the
middle) plus dripstone spindles, instead of axis-aligned boxes. See the
`_CAVE_*` constants for the walk corridor those masses must leave clear.

`storey_role` splits a dungeon storey into slices so a chamber can be many
cells high: `cell` is the single-storey default, `floor` omits the vault,
`rise` is banks only, `vault` omits the floor. Vertical seams use a different
catalog profile (`storey_void`); this param only changes the mesh.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
import math
import random

import bpy
from mathutils import Euler, Vector

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
    "stair",
    "ladder",
    "hatch",
    "floor",
    "roof",
    "chimney",
    "plinth",
    "battlement",
    "turret",
    "dungeon_open",
    "dungeon_wall",
    "dungeon_arch",
    "dungeon_corner",
    "dungeon_passage",
    "dungeon_end",
    "dungeon_cap",
    "dungeon_mouth",
    "dungeon_shaft",
    "dungeon_stair",
    "dungeon_plinth",
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
    "stair",
    "ladder",
    "hatch",
    "floor",
    "turret",
    "dungeon_open",
    "dungeon_wall",
    "dungeon_arch",
    "dungeon_corner",
    "dungeon_passage",
    "dungeon_end",
    "dungeon_shaft",
)

_CAP_KINDS = ("roof", "chimney", "battlement", "dungeon_cap", "dungeon_mouth")
_DUNGEON_STOREY = (
    "dungeon_open",
    "dungeon_wall",
    "dungeon_arch",
    "dungeon_corner",
    "dungeon_passage",
    "dungeon_end",
    "dungeon_shaft",
)
_DUNGEON_CAP = ("dungeon_cap", "dungeon_mouth")

# Jambs beside an opening. Thick curtains use this instead of full wall thickness
# so a gate can be 2–3 m wide.
_MIN_JAMB = 0.4

# The stairwell, in the authored frame that a riser and the piece above it share.
#
# One rectangle, used by `stair`, `ladder` and the `hatch` that roofs them, so a
# flight cannot land under a slab. It runs from the inner face of the outward
# wall back past `_HATCH_Y0`: a flight climbing a full storey is already at head
# height well before the top, so a hole sized to the landing alone would have
# the climber walk into the floor above.
_HATCH_HALF_X = 0.6
_HATCH_Y0 = -0.9
# Thirteen treads and the floor above makes fourteen risers over one storey:
# 193 mm up, 286 mm going. Steep for a modern code, ordinary for a townhouse.
_STAIR_TREADS = 13

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
    "jagged",
    "storey_role",
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


def _rotated_aabb(
    center: Vec3, size: Vec3, rotation: tuple[float, float, float]
) -> tuple[Vec3, Vec3]:
    hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    matrix = Euler(rotation).to_matrix()
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for sx in (-hx, hx):
        for sy in (-hy, hy):
            for sz in (-hz, hz):
                corner = matrix @ Vector((sx, sy, sz))
                xs.append(center[0] + corner.x)
                ys.append(center[1] + corner.y)
                zs.append(center[2] + corner.z)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _mesh_aabb(vertices: Sequence[Vec3]) -> tuple[Vec3, Vec3]:
    if not vertices:
        raise SpecError("mesh shell has no vertices")
    xs = [vertex[0] for vertex in vertices]
    ys = [vertex[1] for vertex in vertices]
    zs = [vertex[2] for vertex in vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


class BoundsSink:
    """Records boxes without building a mesh. Used for neighbor z-fight checks."""

    def __init__(self) -> None:
        self.boxes: list[KitBox] = []

    def add_box_bounds(self, lower: Vec3, upper: Vec3, slot: str) -> None:
        lo, hi = _sorted_bounds(lower, upper)
        self.boxes.append(KitBox(lo, hi, slot))

    def add_rotated_box(
        self,
        center: Vec3,
        size: Vec3,
        slot: str,
        rotation: tuple[float, float, float],
    ) -> None:
        lo, hi = _rotated_aabb(center, size, rotation)
        self.add_box_bounds(lo, hi, slot)

    def add_mesh(
        self,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
        slot: str,
    ) -> None:
        lo, hi = _mesh_aabb(vertices)
        self.add_box_bounds(lo, hi, slot)


class KitBoxes:
    """BoxBuilder that records bounds so kit envelope checks can fail loudly."""

    def __init__(self) -> None:
        self._builder = BoxBuilder(MATERIAL_SLOTS)
        self.boxes: list[KitBox] = []

    def add_box_bounds(self, lower: Vec3, upper: Vec3, slot: str) -> None:
        lo, hi = _sorted_bounds(lower, upper)
        self.boxes.append(KitBox(lo, hi, slot))
        self._builder.add_box_bounds(lo, hi, slot)

    def add_rotated_box(
        self,
        center: Vec3,
        size: Vec3,
        slot: str,
        rotation: tuple[float, float, float],
    ) -> None:
        lo, hi = _rotated_aabb(center, size, rotation)
        lo, hi = _sorted_bounds(lo, hi)
        self.boxes.append(KitBox(lo, hi, slot))
        self._builder.add_box(center, size, slot, rotation=rotation)

    def add_mesh(
        self,
        vertices: Sequence[Vec3],
        faces: Sequence[Sequence[int]],
        slot: str,
    ) -> None:
        """Displaced shell. The envelope and coplanar gates see its bounding box.

        A displaced surface has no coplanar outer face except its flat cap, so
        reporting the AABB is conservative: the gate can only over-report, never
        miss a real shared plane.
        """
        lo, hi = _sorted_bounds(*_mesh_aabb(vertices))
        self.boxes.append(KitBox(lo, hi, slot))
        self._builder.add_mesh(vertices, faces, slot)

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
        if params.kind in ("plinth", "dungeon_plinth") and upper[2] > params.cell_y + 1e-4:
            raise SpecError(
                f"plinth overrun: box z {upper[2]:.4f} > cell_y {params.cell_y}. "
                "Plinths must not poke into the storey above."
            )
        if params.kind == "dungeon_stair":
            if upper[2] > params.cell_y * 2.0 + 1e-4:
                raise SpecError(
                    f"stair overrun: box z {upper[2]:.4f} > 2*cell_y {params.cell_y * 2.0}."
                )
            if lower[2] < params.overlap - 1e-4:
                raise SpecError(
                    f"stair underrun: box z {lower[2]:.4f} < overlap {params.overlap}."
                )
        if params.kind == "dungeon_stair":
            if abs(lower[0]) > h + pad + 1e-3 or abs(upper[0]) > h + pad + 1e-3:
                raise SpecError(
                    f"plan overrun X {lower[0]:.4f}..{upper[0]:.4f} (limit {h + pad:.4f})."
                )
            span = params.cell_xz + params.overlap
            if abs(lower[1]) > span + 1e-3 or abs(upper[1]) > span + 1e-3:
                raise SpecError(
                    f"stair plan overrun Y {lower[1]:.4f}..{upper[1]:.4f} (limit {span:.4f})."
                )
        else:
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
    if params.kind in _DUNGEON_STOREY:
        for kind in ("plinth", "dungeon_plinth"):
            below = _collect_layout(replace(params, kind=kind, jagged=False))
            _assert_no_coplanar_faces(
                boxes,
                other=_shift_axis(below, 2, -params.cell_y),
                context=f"{params.kind}/{kind} stack",
            )
        return
    if params.kind in _DUNGEON_CAP:
        for kind in _DUNGEON_STOREY:
            support = _collect_layout(replace(params, kind=kind))
            _assert_no_coplanar_faces(
                boxes,
                other=_shift_axis(support, 2, -params.cell_y),
                context=f"{params.kind}/{kind} stack",
            )
        return
    if params.kind == "dungeon_stair":
        below = _collect_layout(replace(params, kind="dungeon_plinth", jagged=False))
        _assert_no_coplanar_faces(
            boxes,
            other=_shift_axis(below, 2, -params.cell_y),
            context=f"{params.kind}/dungeon_plinth stack",
        )
        return
    if params.kind == "dungeon_plinth":
        return
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
    elif params.kind.startswith("dungeon_"):
        _dungeon_layout(builder, params)
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
        "stair",
        "ladder",
        "hatch",
    ):
        _floor_slab(
            builder,
            params,
            west_wall=west,
            door=params.kind in ("door", "door_b", "gate"),
            hatch=params.kind == "hatch",
        )
        _south_wall(builder, params, shiplap_neg=not west, shiplap_pos=True)
        if west:
            _west_wall(builder, params)
        if params.kind == "gate":
            _portcullis(builder, params)
        elif params.kind == "stair":
            _stair_flight(builder, params)
        elif params.kind == "ladder":
            _loft_ladder(builder, params)
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
    jagged: bool
    storey_role: str
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
        jagged=as_bool(raw["jagged"], f"{path}.jagged") if "jagged" in raw else False,
        storey_role=(
            as_str(raw["storey_role"], f"{path}.storey_role") if "storey_role" in raw else "cell"
        ),
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
    if params.storey_role not in ("cell", "floor", "rise", "vault"):
        raise SpecError(
            f"params.storey_role: expected cell, floor, rise or vault, got {params.storey_role!r}"
        )
    if params.storey_role != "cell" and params.kind not in _DUNGEON_STOREY:
        raise SpecError(
            f"params.storey_role {params.storey_role!r} is only for dungeon storey kinds."
        )


def _storey_floor_z(params: KitParams) -> float:
    if params.jagged and params.storey_role in ("rise", "vault"):
        # A tall slice has rock below it, not a walk floor or plinth. Keep a
        # deliberate non-coplanar clearance, but do not turn that clearance into
        # a visible horizontal slot between two parts of the same cave wall.
        return params.overlap + 0.002
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


def _hatch_rect(params: KitParams) -> tuple[float, float, float, float]:
    """Stairwell footprint: `(x0, x1, y0, y1)` in the authored frame."""
    return (-_HATCH_HALF_X, _HATCH_HALF_X, _HATCH_Y0, params.half - params.wall_thickness)


def _floor_slab(
    builder: BoxBuilder,
    params: KitParams,
    *,
    west_wall: bool,
    door: bool,
    hatch: bool = False,
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
    if hatch:
        # Three boards around the well rather than one slab with a hole. The
        # pieces are disjoint in plan, so sharing the deck planes is not a
        # coplanar miss, and the stair below now has somewhere to arrive.
        hx0, hx1, _hy0, _hy1 = _hatch_rect(params)
        builder.add_box_bounds((x0, y0, z0), (x1, _HATCH_Y0, z0 + thickness), "structure")
        builder.add_box_bounds((x0, _HATCH_Y0, z0), (hx0, y1, z0 + thickness), "structure")
        builder.add_box_bounds((hx1, _HATCH_Y0, z0), (x1, y1, z0 + thickness), "structure")
    else:
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


def _deck_z(params: KitParams) -> float:
    """Top of a storey's own floor slab: what a boot stands on."""
    return _storey_floor_z(params) + 0.08


def _stair_flight(builder: BoxBuilder, params: KitParams) -> None:
    """Straight flight climbing the full storey, from the room to the outward wall.

    Solid blocks, not open risers: this is boxed-in joinery, and a solid mass
    keeps the space under the stair out of the enclosure flood entirely. Oak,
    not plaster — a stair the colour of the wall behind it is unreadable in a
    room this evenly lit.
    """
    h = params.half
    t = params.wall_thickness
    hx0, hx1, _hy0, _hy1 = _hatch_rect(params)
    x0 = hx0 + 0.06
    x1 = hx1 - 0.06
    y0 = -h
    # Bite into the wall so the top tread does not butt its inner face.
    y1 = h - t + 0.04
    run = (y1 - y0) / _STAIR_TREADS
    deck = _deck_z(params)
    # The last riser is the floor above, so divide the storey by treads + 1.
    rise = params.cell_y / (_STAIR_TREADS + 1)
    # Under the slab top and over its underside: the flight interpenetrates the
    # deck instead of sharing a plane with it.
    base = _storey_floor_z(params) + 0.044
    for index in range(_STAIR_TREADS):
        ys = y0 + index * run
        builder.add_box_bounds((x0, ys, base), (x1, ys + run, deck + (index + 1) * rise), "trim")


def _loft_ladder(builder: BoxBuilder, params: KitParams) -> None:
    """Two stiles and rungs, stood against the outward wall under the same well."""
    h = params.half
    t = params.wall_thickness
    stile = 0.07
    half_w = 0.28
    y0 = h - t - 0.17
    y1 = y0 + 0.11
    deck = _deck_z(params)
    top = params.cell_y - 0.02
    builder.add_box_bounds((-half_w, y0, _storey_floor_z(params) + 0.03), (-half_w + stile, y1, top), "trim")
    builder.add_box_bounds((half_w - stile, y0, _storey_floor_z(params) + 0.03), (half_w, y1, top), "trim")
    rungs = 12
    pitch = params.cell_y / (rungs + 1)
    for index in range(rungs):
        z0 = deck + (index + 1) * pitch
        builder.add_box_bounds((-half_w + 0.01, y0 + 0.02, z0), (half_w - 0.01, y1 - 0.02, z0 + 0.045), "trim")


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
    elif params.kind in ("wall_b", "stair", "ladder", "hatch"):
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


def _dungeon_closed(kind: str) -> set[str]:
    return {
        "dungeon_open": set(),
        "dungeon_wall": {"s"},
        "dungeon_arch": {"s"},
        "dungeon_corner": {"s", "w"},
        "dungeon_passage": {"s", "n"},
        "dungeon_end": {"s", "n", "w"},
        "dungeon_shaft": {"s", "n", "w", "e"},
    }.get(kind, set())


def _dungeon_floor(
    builder: BoxBuilder, params: KitParams, closed: set[str], *, hole: bool
) -> None:
    h = params.half
    t = params.wall_thickness
    sink = 0.03
    z0 = _storey_floor_z(params)
    z1 = z0 + (0.11 if params.jagged else 0.08)
    x0 = -h + (t - sink if "w" in closed else 0.0)
    x1 = h - (t - sink if "e" in closed else 0.0)
    y0 = -h + (t - sink if "n" in closed else 0.0)
    y1 = h - (t - sink if "s" in closed else 0.0)
    if hole:
        well = 0.55
        builder.add_box_bounds((x0, y0, z0 + 0.01), (-well, y1, z1 + 0.01), "structure")
        builder.add_box_bounds((well, y0, z0 + 0.014), (x1, y1, z1 + 0.014), "structure")
        builder.add_box_bounds((-well, y0, z0 + 0.018), (well, -well, z1 + 0.018), "structure")
        builder.add_box_bounds((-well, well, z0 + 0.022), (well, y1, z1 + 0.022), "structure")
        return
    builder.add_box_bounds((x0, y0, z0), (x1, y1, z1), "structure")
    if params.jagged:
        _dungeon_lumps(builder, params, x0, x1, y0, y1, z0, z1, 5)


def _dungeon_rise_posts(builder: BoxBuilder, params: KitParams) -> None:
    """Corner posts so an open rise/vault slice is not an empty mesh."""
    h = params.half
    o = params.overlap
    post = 0.16
    inset = 1.05
    for index, (sx, sy) in enumerate(((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))):
        z0 = o + 0.01 + index * 0.004
        z1 = params.cell_y - 0.02 - index * 0.004
        cx = inset * sx
        cy = inset * sy
        builder.add_box_bounds(
            (cx - post * 0.5, cy - post * 0.5, z0),
            (cx + post * 0.5, cy + post * 0.5, z1),
            "trim",
        )


def _dungeon_lumps(
    builder: BoxBuilder,
    params: KitParams,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    count: int,
) -> None:
    rng = random.Random(params.seed + 17)
    limit = params.half - 0.06
    ix0, ix1 = max(x0, -limit), min(x1, limit)
    iy0, iy1 = max(y0, -limit), min(y1, limit)
    if ix1 - ix0 < 0.5 or iy1 - iy0 < 0.5:
        return
    for index in range(count):
        span_x = min(0.45, (ix1 - ix0) * 0.2)
        span_y = min(0.45, (iy1 - iy0) * 0.2)
        cx = rng.uniform(ix0 + span_x * 0.5, ix1 - span_x * 0.5)
        cy = rng.uniform(iy0 + span_y * 0.5, iy1 - span_y * 0.5)
        z_lo = z0 + 0.008 + index * 0.011
        z_hi = z1 + 0.018 + index * 0.009
        builder.add_box_bounds(
            (cx - span_x * 0.5, cy - span_y * 0.5, z_lo),
            (cx + span_x * 0.5, cy + span_y * 0.5, z_hi),
            "trim" if index % 2 else "structure",
        )


def _dungeon_north_wall(builder: BoxBuilder, params: KitParams) -> None:
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    half_t = t * 0.5
    builder.add_box_bounds((-h + o, -h, o + 0.01), (h - o, -h + half_t, params.cell_y - 0.012), "structure")
    builder.add_box_bounds(
        (-h - o, -h + half_t - 0.02, o + 0.028),
        (h + o, -h + t, params.cell_y - 0.034),
        "structure",
    )


def _dungeon_east_wall(builder: BoxBuilder, params: KitParams) -> None:
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    half_t = t * 0.5
    builder.add_box_bounds((h - half_t, -h + o, o + 0.016), (h, h - o, params.cell_y - 0.02), "structure")
    builder.add_box_bounds(
        (h - t, -h - o, o + 0.036),
        (h - half_t + 0.02, h + o, params.cell_y - 0.044),
        "structure",
    )


def _dungeon_cap(builder: BoxBuilder, params: KitParams, *, mouth: bool) -> None:
    if params.jagged:
        _dungeon_cave_cap(builder, params, mouth=mouth)
        return
    h = params.half
    o = params.overlap
    z0 = o
    z1 = o + 0.16
    if mouth:
        well = 0.9
        builder.add_box_bounds((-h, -h, z0), (h, -well, z1), "structure")
        builder.add_box_bounds((-h, well, z0 + 0.012), (h, h, z1 + 0.012), "structure")
        builder.add_box_bounds((-h, -well, z0 + 0.024), (-well, well, z1 + 0.024), "structure")
        builder.add_box_bounds((well, -well, z0 + 0.036), (h, well, z1 + 0.036), "structure")
        # Raised curb: four boxes, never one solid square over the opening.
        # The old full lip hid the entrance even though the seam was a mouth.
        lip = 0.16
        outer = well + lip
        curb_z0 = z1 - 0.025
        curb_z1 = z1 + 0.38
        builder.add_box_bounds(
            (-outer, -outer, curb_z0),
            (outer, -well, curb_z1),
            "trim",
        )
        builder.add_box_bounds((-outer, well, curb_z0), (outer, outer, curb_z1), "trim")
        builder.add_box_bounds((-outer, -well, curb_z0), (-well, well, curb_z1), "trim")
        builder.add_box_bounds((well, -well, curb_z0), (outer, well, curb_z1), "trim")
        return
    builder.add_box_bounds((-h, -h, z0), (h, h, z1), "structure")


def _dungeon_stair(builder: BoxBuilder, params: KitParams) -> None:
    """Lower cell toward +Y, rise toward -Y. Two storeys, enter from authored +Y."""
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    cy = params.cell_y
    # Player step height is 0.45 m. Eighteen risers keep this two-storey
    # connector comfortably below that while preserving the 8 m run.
    steps = 18
    y0 = -params.cell_xz
    y1 = params.cell_xz
    run = (y1 - y0) / steps
    rise = (cy * 2.0 - o - 0.08) / steps
    for index in range(steps):
        ys = y1 - (index + 1) * run
        ye = y1 - index * run
        z0 = o + 0.012 + index * rise
        z1 = z0 + 0.1 + (0.02 if index % 2 else 0.0)
        builder.add_box_bounds((-h + t, ys, z0), (h - t, ye, z1), "structure")
    # Side walls run the full length. Stopping short of a dock leaves a slit at
    # the corner that neither this piece nor its neighbour covers.
    builder.add_box_bounds((-h, y0, o + 0.02), (-h + t, y1, cy * 2.0 - 0.04), "structure")
    builder.add_box_bounds((h - t, y0, o + 0.032), (h, y1, cy * 2.0 - 0.06), "structure")
    # A diagonal run sweeps four cells, not two: the void under the top landing
    # and the void over the bottom one. Both are occupancy this piece claims, so
    # both need stone or the enclosure check finds daylight under the stairs.
    # The two open ends are the docks: lower cell toward +Y, upper cell toward -Y.
    builder.add_box_bounds((-h, y0, o + 0.026), (h, y0 + t, cy - 0.014), "structure")
    builder.add_box_bounds((-h, y1 - t, cy + 0.014), (h, y1, cy * 2.0 - 0.052), "structure")
    # The lower deck is a storey floor and lines up with one, minus a hair on the
    # underside so the bottom tread does not share a plane with it.
    builder.add_box_bounds((-h, y0, o + 0.006), (h, y1, _storey_floor_z(params) + 0.08), "structure")
    builder.add_box_bounds((-h, 0.0, cy * 2.0 - 0.158), (h, y1, cy * 2.0 - 0.068), "structure")


def _dungeon_layout(builder: BoxBuilder, params: KitParams) -> None:
    if params.kind == "dungeon_plinth":
        _plinth(builder, params)
        return
    if params.kind == "dungeon_stair":
        _dungeon_stair(builder, params)
        return
    if params.kind in _DUNGEON_CAP:
        _dungeon_cap(builder, params, mouth=params.kind == "dungeon_mouth")
        return
    closed = _dungeon_closed(params.kind)
    hole = params.kind == "dungeon_shaft"
    if params.jagged:
        _dungeon_cave_cell(builder, params, closed, hole=hole)
        return
    if params.storey_role in ("cell", "floor"):
        _dungeon_floor(builder, params, closed, hole=hole)
    if params.storey_role in ("rise", "vault"):
        _dungeon_rise_posts(builder, params)
    if "s" in closed:
        _south_wall(builder, params, shiplap_neg="w" not in closed, shiplap_pos="e" not in closed)
    if "w" in closed:
        _west_wall(builder, params)
    if "n" in closed:
        _dungeon_north_wall(builder, params)
    if "e" in closed:
        _dungeon_east_wall(builder, params)
    if closed:
        _dungeon_opening_frames(builder, params, closed)


class _CaveSculpt:
    """Many irregular boxes with unique storey-axis planes so the Z detector stays loud."""

    def __init__(self, builder: BoxBuilder, params: KitParams) -> None:
        self.builder = builder
        self.params = params
        self.used: set[float] = set()
        self.n = 0
        self.limit = params.half - 0.012

    def span(self, height: float) -> tuple[float, float]:
        o = self.params.overlap + 0.016
        top = self.params.cell_y - 0.05
        height = min(max(height, 0.05), top - o - 0.04)
        for _ in range(80):
            stride = 0.006 + (self.n % 17) * 0.0004
            z0 = o + (self.n * stride) % (top - o - height - 0.03)
            z1 = z0 + height
            self.n += 1
            if self._free(z0) and self._free(z1):
                self.used.add(round(z0, 5))
                self.used.add(round(z1, 5))
                return z0, z1
        raise SpecError("cave sculpt exhausted unique Z planes.")

    def _free(self, z: float) -> bool:
        return all(abs(z - other) > 0.0014 for other in self.used)

    def box(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        height: float,
        slot: str,
    ) -> None:
        lim = self.limit
        ax0, ax1 = sorted((max(-lim, min(lim, x0)), max(-lim, min(lim, x1))))
        ay0, ay1 = sorted((max(-lim, min(lim, y0)), max(-lim, min(lim, y1))))
        if ax1 - ax0 < 0.06 or ay1 - ay0 < 0.06:
            return
        z0, z1 = self.span(height)
        self.builder.add_box_bounds((ax0, ay0, z0), (ax1, ay1, z1), slot)

    def rock(
        self,
        cx: float,
        cy: float,
        sx: float,
        sy: float,
        height: float,
        slot: str,
        tilt: tuple[float, float, float],
    ) -> None:
        z0, z1 = self.span(height)
        cz = (z0 + z1) * 0.5
        sz = z1 - z0
        lo, hi = _rotated_aabb((cx, cy, cz), (sx, sy, sz), tilt)
        lim = self.limit
        if (
            lo[0] < -lim
            or hi[0] > lim
            or lo[1] < -lim
            or hi[1] > lim
            or lo[2] < self.params.overlap
            or hi[2] > self.params.cell_y
            or not self._free(lo[2])
            or not self._free(hi[2])
        ):
            self.box(cx - sx * 0.4, cy - sy * 0.4, cx + sx * 0.4, cy + sy * 0.4, height, slot)
            return
        self.used.add(round(lo[2], 5))
        self.used.add(round(hi[2], 5))
        self.builder.add_rotated_box((cx, cy, cz), (sx, sy, sz), slot, tilt)


def _cave_tilt(rng: random.Random) -> tuple[float, float, float]:
    return (
        rng.uniform(-0.62, 0.62),
        rng.uniform(-0.45, 0.45),
        rng.uniform(-0.85, 0.85),
    )


# --- Cave shell ------------------------------------------------------------
#
# A cave tile is not a box of rocks. It is two displaced rock masses: a floor
# that sweeps up into the walls and a ceiling that domes over the middle and
# drops into the corners. They interpenetrate in the outer band, so that band
# is solid stone; what is left is a plus-shaped walk corridor with arms only
# through the open (docked) sides.
#
# The corridor numbers are a contract with the collision proxy in
# examples/dungeon_kit/src/physics.rs. Rock must never grow into the clear
# volume, because the proxy has no geometry there:
#   * floor stays at or below _CAVE_WALK_Z inside _CAVE_CORRIDOR
#   * ceiling stays at or above _CAVE_HEAD inside _CAVE_HEAD_CLEAR
#   * nothing at all inside _CAVE_WELL: that is the drop column under a mouth
#     and the shaft, and a falling player passes through it. The vault is built
#     as four rings around that column, so the column is a real hole rather than
#     a thin lid the player would fall through.
_CAVE_CORRIDOR = 1.05
_CAVE_BANK = 1.55
_CAVE_HEAD_CLEAR = 1.25
# Just clear of a 1.8 m player: rock this low reads as a duck-under, and the eye
# still passes under it.
_CAVE_HEAD = 1.95
_CAVE_WELL = 0.95
_CAVE_WALK_Z = 0.185
_CAVE_SHAFT_WELL = 0.55
# Rock left above the vault where it sweeps up into the drop column, and the room
# `_CavePlanes` needs below `cell_y` to nudge four ring caps onto free planes.
_CAVE_RIM = 0.06
# Seam profiles are seed-free functions of |distance along the seam|, so two
# mated tiles agree on the rock height at the shared border in any rotation.
_CAVE_SEAM_CORNER_FLOOR = 2.52
_CAVE_SEAM_CORNER_CEIL = 1.05
_CAVE_SEAM_BLEND = 0.5
# The mass runs `overlap` past the cell and drops a hair on the way out, so two
# neighbours cross in a shallow crease instead of presenting coplanar faces.
_CAVE_LIP = 0.02


def _smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


class _CaveNoise:
    """Deterministic value noise. Same seed, same rock, build after build."""

    def __init__(self, seed: int) -> None:
        self._seed = (seed * 2654435761) & 0xFFFFFFFF

    def _lattice(self, ix: int, iy: int, octave: int) -> float:
        n = (ix * 73856093) ^ (iy * 19349663) ^ (octave * 83492791) ^ self._seed
        n &= 0xFFFFFFFF
        n = ((n ^ (n >> 15)) * 2246822519) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 3266489917) & 0xFFFFFFFF
        return float((n ^ (n >> 16)) & 0xFFFFFF) / float(0xFFFFFF)

    def _octave(self, x: float, y: float, octave: int) -> float:
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = _smoothstep(x - ix), _smoothstep(y - iy)
        c00 = self._lattice(ix, iy, octave)
        c10 = self._lattice(ix + 1, iy, octave)
        c01 = self._lattice(ix, iy + 1, octave)
        c11 = self._lattice(ix + 1, iy + 1, octave)
        return (c00 * (1.0 - fx) + c10 * fx) * (1.0 - fy) + (c01 * (1.0 - fx) + c11 * fx) * fy

    def at(self, x: float, y: float, *, frequency: float, octaves: int = 3) -> float:
        total = 0.0
        weight = 0.0
        amplitude = 1.0
        for octave in range(octaves):
            total += amplitude * self._octave(x * frequency, y * frequency, octave)
            weight += amplitude
            amplitude *= 0.52
            frequency *= 2.13
        return total / weight


class _CavePlanes:
    """Keeps every storey-axis face on its own plane.

    Displaced surfaces present no shared plane, but the coplanar gate sees
    bounding boxes, so two shells whose extents happen to land within
    `_PLANE_EPS` would fail the build. Requested heights are nudged by
    millimetres, never by enough to change the shape.
    """

    def __init__(self) -> None:
        self._used: list[float] = []

    def claim(self, z: float) -> float:
        for step in range(400):
            for direction in (1.0, -1.0):
                candidate = round(z + direction * step * 0.0017, 5)
                if all(abs(candidate - other) > 0.0018 for other in self._used):
                    self._used.append(candidate)
                    return candidate
        raise SpecError("cave shell exhausted unique storey planes.")

    def reserve(self, z: float) -> None:
        self._used.append(round(z, 5))


@dataclass(frozen=True)
class _CaveShape:
    """Floor and ceiling height fields for one cave tile."""

    params: KitParams
    closed: frozenset[str]
    floor_noise: _CaveNoise
    ceiling_noise: _CaveNoise

    def openness(
        self,
        x: float,
        y: float,
        *,
        corridor: float,
        bank: float,
        noise: _CaveNoise,
    ) -> float:
        """1 in the walk corridor, 0 in the solid band, smooth across the slope.

        The boundary wanders in plan so the wall is not an extruded ramp. It only
        ever wanders *outward*: rock must never grow inside `corridor`.
        """
        distance = max(abs(x), abs(y)) - corridor
        for face, (axis, sign) in (
            ("s", (1, 1.0)),
            ("n", (1, -1.0)),
            ("e", (0, 1.0)),
            ("w", (0, -1.0)),
        ):
            if face in self.closed:
                continue
            across = abs(y) if axis == 0 else abs(x)
            along = (x if axis == 0 else y) * sign
            distance = min(distance, max(across - corridor, corridor - along))
        distance -= 0.36 * noise.at(x + 3.0, y - 2.0, frequency=1.45)
        return 1.0 - _smoothstep(distance / (bank - corridor))

    def _seam(self, x: float, y: float) -> tuple[float, float, bool]:
        """Border weight, distance along the owning seam, and whether it is open."""
        h = self.params.half
        if abs(x) >= abs(y):
            reach, along, face = abs(x), y, "e" if x > 0.0 else "w"
        else:
            reach, along, face = abs(y), x, "s" if y > 0.0 else "n"
        weight = _smoothstep((reach - (h - _CAVE_SEAM_BLEND)) / _CAVE_SEAM_BLEND)
        return weight, along, face not in self.closed

    def _lip(self, x: float, y: float) -> float:
        overshoot = max(abs(x), abs(y)) - self.params.half
        return _CAVE_LIP * min(1.0, max(0.0, overshoot / max(self.params.overlap, 1e-6)))

    def floor(self, x: float, y: float) -> float:
        rough = self.floor_noise.at(x - 4.0, y + 6.0, frequency=3.9)
        # Rubble relief on the walk floor. The collision proxy is a flat slab at
        # `_CAVE_WALK_Z`, so this has to stay small enough that a boot sinking
        # into a bump does not read as a bug.
        low = 0.105 + 0.06 * self.floor_noise.at(x, y, frequency=1.7) + 0.032 * rough
        bank = 1.5 + 0.75 * self.floor_noise.at(x + 11.0, y - 7.0, frequency=0.85) + 0.22 * rough
        openness = self.openness(
            x, y, corridor=_CAVE_CORRIDOR, bank=_CAVE_BANK, noise=self.floor_noise
        )
        interior = low + (bank - low) * (1.0 - openness)
        weight, along, open_face = self._seam(x, y)
        seam = _cave_seam_floor(self.params, along, open_face=open_face)
        return interior + (seam - interior) * weight - self._lip(x, y)

    def ceiling(self, x: float, y: float) -> float:
        rough = self.ceiling_noise.at(x + 8.0, y + 2.0, frequency=4.2)
        # Keep the top of the vault clear of `_CAVE_HEAD` on its own: the sag
        # below does the descending, and a base that already dips under head
        # height would flatten onto the contract plane.
        high = 2.66 - 0.44 * self.ceiling_noise.at(x, y, frequency=1.15) - 0.1 * rough
        low = 1.4 - 0.42 * self.ceiling_noise.at(x - 5.0, y + 9.0, frequency=0.95) - 0.12 * rough
        openness = self.openness(
            x,
            y,
            corridor=_CAVE_HEAD_CLEAR,
            bank=self.params.half - 0.15,
            noise=self.ceiling_noise,
        )
        interior = low + (high - low) * openness
        weight, along, open_face = self._seam(x, y)
        seam = _cave_seam_ceiling(self.params, along, open_face=open_face)
        vault = self._sag(x, y, vault=interior + (seam - interior) * weight + self._lip(x, y))
        # Sweep up into the drop column so its rim is a lip a few centimetres
        # thick. Left alone, the four vault rings meet the column in half-metre
        # vertical walls and the hole reads as a hatch cut in a ceiling.
        funnel = 1.0 - _smoothstep((max(abs(x), abs(y)) - _CAVE_WELL) / 0.55)
        chimney = self.params.cell_y - _CAVE_RIM
        return vault + (chimney - vault) * funnel

    def _sag(self, x: float, y: float, *, vault: float) -> float:
        """Pull the vault down in blobs, scaled by the head room available here.

        The sag is a *fraction* of the room down to the lowest legal ceiling, not
        an absolute drop clamped against it: clamping flattens every blob onto the
        same plane and the tile reads as a lid again. Over the walk corridor that
        floor is `_CAVE_HEAD`, a contract with the collision proxy; over the rock
        bank it is the bank itself, so the vault can come down and nearly close.
        """
        # Rare and deep beats constant and shallow: a threshold well above the
        # mean leaves most of the vault high and drops a few pendants far down.
        blob = self.ceiling_noise.at(x + 21.0, y - 13.0, frequency=0.62)
        knuckle = self.ceiling_noise.at(x - 17.0, y + 29.0, frequency=1.85)
        sag = min(1.0, max(0.0, blob - 0.56) * 3.4 + max(0.0, knuckle - 0.63) * 1.2)
        walk = self.openness(
            x, y, corridor=_CAVE_CORRIDOR, bank=_CAVE_BANK, noise=self.floor_noise
        )
        # Over solid rock the vault has to sink *into* the bank, not stop above
        # it. A positive clearance here reads as care and is in fact a slot: at a
        # closed seam the floor tops out around 1.76 m and this floor pinned the
        # vault at 1.88 m, leaving 12 cm of daylight the length of every wall.
        bank_floor = self.floor(x, y) - 0.12
        lowest = bank_floor + (_CAVE_HEAD + 0.06 - bank_floor) * walk
        return max(vault - max(0.0, vault - lowest) * sag, lowest)

    def walkable(self, x: float, y: float) -> bool:
        return (
            self.openness(
                x, y, corridor=_CAVE_CORRIDOR, bank=_CAVE_BANK, noise=self.floor_noise
            )
            > 0.02
        )

    def tall_floor(self, x: float, y: float) -> float:
        """Walk floor in the clear plus; full-height rock everywhere else.

        A normal one-storey cave can stop its bank halfway up because the vault
        descends to meet it. A floor slice has no vault, so that same bank leaves
        daylight between it and the rise slice above. Use the exact same plan
        rectangles as `rise`; a separately-noised boundary would leave a gap
        wherever the two seeds disagreed.
        """
        floor = self.floor(x, y)
        reach = self.params.half + self.params.overlap
        solid = any(
            x0 <= x <= x1 and y0 <= y <= y1
            for x0, x1, y0, y1 in _cave_solid_rects(
                reach, _CAVE_CORRIDOR, self.closed
            )
        )
        return self.rise_top(x, y) if solid else floor

    def rise_top(self, x: float, y: float) -> float:
        """Top of a sliced bank, millimetres under the storey envelope."""
        wobble = self.ceiling_noise.at(x + 4.0, y - 3.0, frequency=2.4)
        return self.params.cell_y - 0.0005 - 0.0005 * wobble


def _cave_wobble(a: float) -> float:
    """Seed-free 0..1 ripple along a seam, so both sides of a join agree."""
    return 0.5 + 0.5 * math.sin(a * 7.7 + 0.6) * math.cos(a * 3.1 - 1.2)


def _cave_seam_floor(params: KitParams, along: float, *, open_face: bool) -> float:
    h = params.half
    reach = min(abs(along), h)
    a = reach / h
    wobble = _cave_wobble(a)
    if open_face:
        rise = _smoothstep((reach - _CAVE_CORRIDOR) / (h - _CAVE_CORRIDOR))
        low = 0.13 + 0.045 * wobble
        return low + (_CAVE_SEAM_CORNER_FLOOR - low) * rise
    return _CAVE_SEAM_CORNER_FLOOR - (0.55 + 0.35 * wobble) * (1.0 - a) ** 1.4


def _cave_seam_ceiling(params: KitParams, along: float, *, open_face: bool) -> float:
    h = params.half
    reach = min(abs(along), h)
    a = reach / h
    wobble = _cave_wobble(a + 0.37)
    if open_face:
        fall = _smoothstep((reach - _CAVE_HEAD_CLEAR) / (h - _CAVE_HEAD_CLEAR))
        high = 2.5 - 0.52 * wobble
        return high + (_CAVE_SEAM_CORNER_CEIL - high) * fall
    return _CAVE_SEAM_CORNER_CEIL - 0.16 + 0.3 * wobble * (1.0 - a)


def _cave_axis(lo: float, hi: float) -> list[float]:
    """Ascending samples, dense where the rock turns up into the wall."""
    step_fine = 0.072
    step_coarse = 0.118
    out = [lo]
    position = lo
    while position < hi - 1e-6:
        near_wall = abs(position) > _CAVE_CORRIDOR - 0.25
        position = min(hi, position + (step_fine if near_wall else step_coarse))
        out.append(position)
    return out


def _cave_ring_rects(reach: float, well: float) -> tuple[tuple[float, float, float, float], ...]:
    """Four rectangles that surround a clear square column of half-width `well`."""
    return (
        (-reach, reach, -reach, -well),
        (-reach, reach, well, reach),
        (-reach, -well - 0.03, -well, well),
        (well + 0.03, reach, -well, well),
    )


def _cave_solid_rects(
    reach: float, corridor: float, closed: frozenset[str]
) -> tuple[tuple[float, float, float, float], ...]:
    """Rock that stays in a rise slice: four corners, plus a bank on each closed face.

    The walk plus is omitted. Open arms stay empty so a mid-storey passage continues
    the chamber; closed faces keep a full-height bank.

    Face names follow `_CaveShape._seam`: `s` is +y, `n` is -y, `e` is +x, `w` is
    -x. Getting `n`/`s` backwards banks the rock across the passage and leaves the
    exterior wall as an open arm, which is a hole with a dock contract that still
    says everything is fine.
    """
    c = corridor
    rects: list[tuple[float, float, float, float]] = [
        (-reach, -c, -reach, -c),
        (-reach, -c, c, reach),
        (c, reach, -reach, -c),
        (c, reach, c, reach),
    ]
    if "s" in closed:
        rects.append((-c, c, c, reach))
    if "n" in closed:
        rects.append((-c, c, -reach, -c))
    if "w" in closed:
        rects.append((-reach, -c, -c, c))
    if "e" in closed:
        rects.append((c, reach, -c, c))
    return tuple(rects)


def _cave_field(
    builder: BoxBuilder,
    shape: _CaveShape,
    planes: _CavePlanes,
    *,
    x_lo: float,
    x_hi: float,
    y_lo: float,
    y_hi: float,
    upward: bool,
    slot: str,
    height_fn: Callable[[float, float], float] | None = None,
    cap_z_override: float | None = None,
) -> None:
    """One displaced rock mass: noisy surface, vertical skirt, flat back cap."""
    params = shape.params
    xs = _cave_axis(x_lo, x_hi)
    ys = _cave_axis(y_lo, y_hi)
    height = height_fn or (shape.floor if upward else shape.ceiling)
    jitter = _CaveNoise(params.seed + (17 if upward else 53))
    nx, ny = len(xs), len(ys)
    vertices: list[Vec3] = []
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            px, py = x, y
            if 0 < ix < nx - 1 and 0 < iy < ny - 1:
                span_x = min(x - xs[ix - 1], xs[ix + 1] - x)
                span_y = min(y - ys[iy - 1], ys[iy + 1] - y)
                px += (jitter.at(x * 3.1, y * 3.1, frequency=1.0, octaves=1) - 0.5) * span_x * 0.8
                py += (jitter.at(x * 2.7 + 31.0, y * 2.7, frequency=1.0, octaves=1) - 0.5) * span_y * 0.8
            vertices.append((px, py, height(px, py)))

    faces: list[list[int]] = []
    for ix in range(nx - 1):
        for iy in range(ny - 1):
            a = ix * ny + iy
            b = (ix + 1) * ny + iy
            quad = [a, b, b + 1, a + 1]
            faces.append(quad if upward else list(reversed(quad)))

    ring: list[int] = []
    ring.extend(ix * ny for ix in range(nx))
    ring.extend((nx - 1) * ny + iy for iy in range(1, ny))
    ring.extend(ix * ny + (ny - 1) for ix in range(nx - 2, -1, -1))
    ring.extend(iy for iy in range(ny - 2, 0, -1))
    surface_extreme = max(vertex[2] for vertex in vertices) if upward else min(
        vertex[2] for vertex in vertices
    )
    planes.reserve(surface_extreme)
    # Leave room under `cell_y` for `_CavePlanes` to nudge: the vault is built
    # from four rings, and a nudge past the cell top is an envelope failure.
    cap_z = (
        cap_z_override
        if cap_z_override is not None
        else planes.claim(_storey_floor_z(params) if upward else params.cell_y - _CAVE_RIM * 0.34)
    )
    cap_start = len(vertices)
    for index in ring:
        x, y, _ = vertices[index]
        vertices.append((x, y, cap_z))
    for step, index in enumerate(ring):
        next_index = ring[(step + 1) % len(ring)]
        a_cap = cap_start + step
        b_cap = cap_start + (step + 1) % len(ring)
        if upward:
            faces.append([index, a_cap, b_cap, next_index])
        else:
            faces.append([index, next_index, b_cap, a_cap])
    cap = [cap_start + step for step in range(len(ring))]
    faces.append(cap if not upward else list(reversed(cap)))
    builder.add_mesh(vertices, faces, slot)


def _cave_rings(
    x: float,
    y: float,
    z0: float,
    z1: float,
    radius: float,
    waist: float,
    sides: int,
    rings: int,
    noise: _CaveNoise,
) -> list[list[Vec3]]:
    """Lumpy rings from z0 to z1. `waist` < 1 is fat low, > 1 is fat high."""
    out: list[list[Vec3]] = []
    span = z1 - z0
    for ring in range(rings):
        t = (ring + 1.0) / (rings + 1.0)
        profile = (t**waist) * (1.0 - t) ** 0.3
        scale = profile / (0.5**waist * 0.5**0.3)
        loop: list[Vec3] = []
        for side in range(sides):
            angle = 2.0 * math.pi * side / sides
            lump = 0.6 + 0.8 * noise.at(
                math.cos(angle) * 2.0 + x * 3.0,
                math.sin(angle) * 2.0 + y * 3.0 + t * 4.0,
                frequency=1.4,
            )
            r = radius * scale * lump
            loop.append((x + math.cos(angle) * r, y + math.sin(angle) * r, z0 + span * t))
        out.append(loop)
    return out


def _cave_hull(
    builder: BoxBuilder,
    loops: Sequence[Sequence[Vec3]],
    *,
    bottom: Vec3 | None,
    top: Vec3 | None,
    slot: str,
) -> None:
    """Close a stack of rings with a tip or a flat cap at each end."""
    sides = len(loops[0])
    vertices: list[Vec3] = []
    faces: list[list[int]] = []
    if bottom is not None:
        vertices.append(bottom)
    first = len(vertices)
    for loop in loops:
        vertices.extend(loop)
    if bottom is None:
        faces.append([first + side for side in range(sides - 1, -1, -1)])
    else:
        for side in range(sides):
            faces.append([0, first + (side + 1) % sides, first + side])
    for ring in range(len(loops) - 1):
        base = first + ring * sides
        above = base + sides
        for side in range(sides):
            nxt = (side + 1) % sides
            faces.append([base + side, base + nxt, above + nxt, above + side])
    last = first + (len(loops) - 1) * sides
    if top is None:
        faces.append([last + side for side in range(sides)])
    else:
        vertices.append(top)
        apex = len(vertices) - 1
        for side in range(sides):
            faces.append([last + side, last + (side + 1) % sides, apex])
    builder.add_mesh(vertices, faces, slot)


def _cave_spindle(
    builder: BoxBuilder,
    planes: _CavePlanes,
    *,
    x: float,
    y: float,
    z0: float,
    z1: float,
    radius: float,
    waist: float,
    sides: int,
    rings: int,
    noise: _CaveNoise,
    slot: str,
) -> None:
    """Boulder or stalagmite: pointed at both ends, base buried in the floor."""
    low = planes.claim(z0)
    high = planes.claim(z1)
    if high - low < 0.12:
        return
    loops = _cave_rings(x, y, low, high, radius, waist, sides, rings, noise)
    _cave_hull(builder, loops, bottom=(x, y, low), top=(x, y, high), slot=slot)


def _cave_stalactite(
    builder: BoxBuilder,
    planes: _CavePlanes,
    *,
    x: float,
    y: float,
    tip_z: float,
    root_z: float,
    radius: float,
    sides: int,
    rings: int,
    noise: _CaveNoise,
    slot: str,
) -> None:
    """Hanging stone: widest at the flat root that sits inside the vault."""
    tip = planes.claim(tip_z)
    root = planes.claim(root_z)
    if root - tip < 0.15:
        return
    loops = _cave_rings(x, y, tip, root, radius, 1.0, sides, rings, noise)
    widest = [
        [(vx, vy, root) for vx, vy, _ in loops[-1]],
    ]
    _cave_hull(builder, loops + widest, bottom=(x, y, tip), top=None, slot=slot)


def _dungeon_cave_cell(
    builder: BoxBuilder, params: KitParams, closed: set[str], *, hole: bool
) -> None:
    """Natural cave volume: rock sweeps up into the walls and domes overhead.

    `storey_role` splits that into slices so a chamber can be many cells high:
    floor is the walk slab and banks, rise is banks only, vault is the dome.
    """
    shape = _CaveShape(
        params=params,
        closed=frozenset(closed),
        floor_noise=_CaveNoise(params.seed + 311),
        ceiling_noise=_CaveNoise(params.seed + 977),
    )
    planes = _CavePlanes()
    planes.reserve(params.overlap)
    planes.reserve(0.0)
    reach = params.half + params.overlap
    role = params.storey_role
    if role == "rise":
        bank_base = planes.claim(_storey_floor_z(params))
        for x_lo, x_hi, y_lo, y_hi in _cave_solid_rects(reach, _CAVE_CORRIDOR, frozenset(closed)):
            _cave_field(
                builder,
                shape,
                planes,
                x_lo=x_lo,
                x_hi=x_hi,
                y_lo=y_lo,
                y_hi=y_hi,
                upward=True,
                slot="structure",
                height_fn=shape.rise_top,
                cap_z_override=bank_base,
            )
        return
    if role in ("cell", "floor"):
        floor_rects = (
            _cave_ring_rects(reach, _CAVE_SHAFT_WELL) if hole else ((-reach, reach, -reach, reach),)
        )
        for x_lo, x_hi, y_lo, y_hi in floor_rects:
            _cave_field(
                builder,
                shape,
                planes,
                x_lo=x_lo,
                x_hi=x_hi,
                y_lo=y_lo,
                y_hi=y_hi,
                upward=True,
                slot="structure",
                height_fn=shape.tall_floor if role == "floor" else None,
            )
    if role in ("cell", "vault"):
        if role == "vault":
            # The dome only occupies the upper part of this slice. Continue the
            # perimeter banks from the void seam to meet it; otherwise the lower
            # half of the vault slice is open to the terrain.
            bank_base = planes.claim(_storey_floor_z(params))
            for x_lo, x_hi, y_lo, y_hi in _cave_solid_rects(
                reach, _CAVE_CORRIDOR, frozenset(closed)
            ):
                _cave_field(
                    builder,
                    shape,
                    planes,
                    x_lo=x_lo,
                    x_hi=x_hi,
                    y_lo=y_lo,
                    y_hi=y_hi,
                    upward=True,
                    slot="structure",
                    height_fn=shape.rise_top,
                    cap_z_override=bank_base,
                )
        # Every vault keeps a hole over its middle. The `up` seam is terminated
        # by a cap or by the mouth, so there is always rock overhead; the hole is
        # what lets the mouth drop through and what frees the vault to dome.
        for x_lo, x_hi, y_lo, y_hi in _cave_ring_rects(reach, _CAVE_WELL):
            _cave_field(
                builder,
                shape,
                planes,
                x_lo=x_lo,
                x_hi=x_hi,
                y_lo=y_lo,
                y_hi=y_hi,
                upward=False,
                slot="structure",
            )
    _cave_dripstone(builder, shape, planes)


def _cave_dripstone(builder: BoxBuilder, shape: _CaveShape, planes: _CavePlanes) -> None:
    """Stalactites overhead, stalagmites and boulders on the banks."""
    params = shape.params
    rng = random.Random(params.seed + 1531)
    noise = _CaveNoise(params.seed + 4409)
    reach = params.half + params.overlap - 0.02
    placed = 0
    for _ in range(640):
        if placed >= 68:
            break
        x = rng.uniform(-reach, reach)
        y = rng.uniform(-reach, reach)
        if max(abs(x), abs(y)) < _CAVE_WELL + 0.1:
            continue
        radius = min(0.055 + rng.random() * 0.135, (reach - max(abs(x), abs(y))) / 2.2)
        if radius < 0.05:
            continue
        floor_z = shape.floor(x, y)
        ceiling_z = shape.ceiling(x, y)
        walkable = shape.walkable(x, y)
        # Calcite is the exception, not the rule: pale dripstone everywhere turns
        # the middle distance into milk.
        slot = "trim" if placed % 5 == 0 else "structure"
        roll = rng.random()
        if roll < 0.46:
            if params.storey_role == "floor":
                continue
            # A stalactite roots *inside* the vault, so there has to be vault
            # above it. Where the rock has already swept up to the cell top —
            # the chimney funnel — there is none, and a root there would either
            # overrun the envelope or hang its flat cap in open air.
            if ceiling_z > params.cell_y - 0.25:
                continue
            tip = ceiling_z - (0.3 + rng.random() * 1.5)
            if walkable:
                tip = max(tip, _CAVE_HEAD + 0.05)
            if ceiling_z - tip < 0.18 or tip < floor_z + 0.2:
                continue
            _cave_stalactite(
                builder,
                planes,
                x=x,
                y=y,
                tip_z=tip,
                root_z=ceiling_z + 0.12,
                radius=radius,
                sides=8,
                rings=4,
                noise=noise,
                slot=slot,
            )
        elif params.storey_role == "vault" or walkable or ceiling_z - floor_z < 0.35:
            continue
        elif roll < 0.82:
            rise = 0.3 + rng.random() * 1.4
            _cave_spindle(
                builder,
                planes,
                x=x,
                y=y,
                z0=max(floor_z - 0.3, params.overlap + 0.05),
                z1=min(floor_z + rise, ceiling_z + 0.1, params.cell_y - 0.015),
                radius=radius,
                waist=0.5,
                sides=8,
                rings=4,
                noise=noise,
                slot=slot,
            )
        else:
            _cave_spindle(
                builder,
                planes,
                x=x,
                y=y,
                z0=max(floor_z - 0.35, params.overlap + 0.05),
                z1=min(floor_z + 0.2 + rng.random() * 0.4, params.cell_y - 0.015),
                radius=min(radius * 1.9, (reach - max(abs(x), abs(y))) / 2.2),
                waist=0.9,
                sides=9,
                rings=3,
                noise=noise,
                slot=slot,
            )
        placed += 1


def _dungeon_cave_cap(builder: BoxBuilder, params: KitParams, *, mouth: bool) -> None:
    """Broken ceiling mass. Underside is uneven so the room below is not a lid."""
    sculpt = _CaveSculpt(builder, params)
    rng = random.Random(params.seed + 709)
    h = params.half
    well = 0.9 if mouth else 0.0
    steps = 6
    span = (2.0 * h) / steps
    for iz in range(steps):
        for ix in range(steps):
            x0 = -h + ix * span
            y0 = -h + iz * span
            x1 = x0 + span + 0.05
            y1 = y0 + span + 0.05
            if mouth and abs((x0 + x1) * 0.5) < well and abs((y0 + y1) * 0.5) < well:
                continue
            sculpt.box(x0, y0, x1, y1, 0.18 + rng.random() * 0.7, "structure")
    for index in range(20):
        r = 0.08 + rng.random() * 0.22
        cx = rng.uniform(-h + 0.25, h - 0.25)
        cy = rng.uniform(-h + 0.25, h - 0.25)
        if mouth and abs(cx) < well + 0.1 and abs(cy) < well + 0.1:
            continue
        sculpt.rock(
            cx,
            cy,
            r * 2.0,
            r * 2.0,
            0.35 + rng.random() * 0.95,
            "trim" if index % 2 else "structure",
            _cave_tilt(rng),
        )
    if mouth:
        lip = 0.18
        outer = well + lip
        for index, (x0, y0, x1, y1) in enumerate(
            (
                (-outer, -outer, outer, -well),
                (-outer, well, outer, outer),
                (-outer, -well, -well, well),
                (well, -well, outer, well),
            )
        ):
            sculpt.box(x0, y0, x1, y1, 0.28 + index * 0.04, "trim")


def _dungeon_opening_frames(
    builder: BoxBuilder, params: KitParams, closed: set[str]
) -> None:
    """Stone lintel and jambs on every open side so a connection reads as an exit.

    Frames sit inside the cell (not on the seam) so two neighbors cannot share a
    storey-axis face.
    """
    h = params.half
    o = params.overlap
    cy = params.cell_y
    inset = 0.42
    half_gap = 0.95
    jamb = 0.14
    lintel_z0 = cy - 0.32
    lintel_z1 = cy - 0.05
    jamb_z0 = o + 0.04
    faces = (
        ("s", 0.0, h - inset, True),
        ("n", 0.0, -h + inset, True),
        ("e", h - inset, 0.0, False),
        ("w", -h + inset, 0.0, False),
    )
    for name, cx, cy_face, along_x in faces:
        if name in closed:
            continue
        if along_x:
            builder.add_box_bounds(
                (-half_gap - jamb, cy_face - 0.05, lintel_z0),
                (half_gap + jamb, cy_face + 0.05, lintel_z1),
                "trim",
            )
            builder.add_box_bounds(
                (-half_gap - jamb, cy_face - 0.04, jamb_z0),
                (-half_gap, cy_face + 0.04, lintel_z0 - 0.02),
                "trim",
            )
            builder.add_box_bounds(
                (half_gap, cy_face - 0.04, jamb_z0 + 0.012),
                (half_gap + jamb, cy_face + 0.04, lintel_z0 - 0.03),
                "trim",
            )
        else:
            builder.add_box_bounds(
                (cx - 0.05, -half_gap - jamb, lintel_z0 + 0.01),
                (cx + 0.05, half_gap + jamb, lintel_z1 - 0.01),
                "trim",
            )
            builder.add_box_bounds(
                (cx - 0.04, -half_gap - jamb, jamb_z0 + 0.008),
                (cx + 0.04, -half_gap, lintel_z0 - 0.018),
                "trim",
            )
            builder.add_box_bounds(
                (cx - 0.04, half_gap, jamb_z0 + 0.02),
                (cx + 0.04, half_gap + jamb, lintel_z0 - 0.028),
                "trim",
            )


def _dungeon_face_lumps(builder: BoxBuilder, params: KitParams, closed: set[str]) -> None:
    """Proud stones on closed faces. Unique Z so they do not share a storey plane."""
    h = params.half
    t = params.wall_thickness
    o = params.overlap
    cy = params.cell_y
    rng = random.Random(params.seed + 91)
    if "s" in closed:
        for index in range(4):
            x = rng.uniform(-h + t + 0.2, h - t - 0.2)
            z0 = o + 0.22 + index * 0.41
            z1 = min(cy - 0.1, z0 + 0.28 + index * 0.02)
            builder.add_box_bounds(
                (x - 0.2, h - t - 0.14, z0),
                (x + 0.2, h - t + 0.05, z1),
                "trim",
            )
    if "n" in closed:
        for index in range(3):
            x = rng.uniform(-h + t + 0.2, h - t - 0.2)
            z0 = o + 0.28 + index * 0.47
            z1 = min(cy - 0.12, z0 + 0.24 + index * 0.025)
            builder.add_box_bounds(
                (x - 0.18, -h + t - 0.05, z0),
                (x + 0.18, -h + t + 0.12, z1),
                "trim",
            )
    if "w" in closed:
        for index in range(3):
            y = rng.uniform(-h + t + 0.2, h - t - 0.2)
            z0 = o + 0.31 + index * 0.44
            z1 = min(cy - 0.11, z0 + 0.26 + index * 0.02)
            builder.add_box_bounds(
                (-h + t - 0.05, y - 0.16, z0),
                (-h + t + 0.12, y + 0.16, z1),
                "trim",
            )


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
    if params.kind.startswith("dungeon_"):
        if params.jagged:
            return "cave_rock" if slot == "structure" else "cave_calcite"
        return "ashlar" if slot == "structure" else "stone_trim"
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


def _voronoi_edges(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    generated: bpy.types.NodeSocket,
    *,
    location: tuple[float, float],
    scale: tuple[float, float, float],
    offset: tuple[float, float, float],
    randomness: float,
) -> bpy.types.NodeSocket:
    """Distance to the nearest cell edge: the crack network in broken rock."""
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.location = location
    mapping.inputs["Scale"].default_value = scale
    mapping.inputs["Location"].default_value = offset
    links.new(generated, mapping.inputs["Vector"])
    voronoi = nodes.new(type="ShaderNodeTexVoronoi")
    voronoi.location = (location[0] + 200.0, location[1])
    voronoi.voronoi_dimensions = "3D"
    voronoi.feature = "DISTANCE_TO_EDGE"
    voronoi.inputs["Scale"].default_value = 1.0
    voronoi.inputs["Randomness"].default_value = randomness
    links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])
    return voronoi.outputs["Distance"]


def _height_mask(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    generated: bpy.types.NodeSocket,
    *,
    location: tuple[float, float],
    from_min: float,
    from_max: float,
) -> bpy.types.NodeSocket:
    """0 low in the object, 1 high. Drives damp floors and dry vaults."""
    separate = nodes.new(type="ShaderNodeSeparateXYZ")
    separate.location = location
    links.new(generated, separate.inputs["Vector"])
    ramp = nodes.new(type="ShaderNodeMapRange")
    ramp.location = (location[0] + 190.0, location[1])
    ramp.inputs["From Min"].default_value = from_min
    ramp.inputs["From Max"].default_value = from_max
    ramp.clamp = True
    links.new(separate.outputs["Z"], ramp.inputs["Value"])
    return ramp.outputs["Result"]


def _remap(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    value: bpy.types.NodeSocket,
    *,
    location: tuple[float, float],
    from_min: float,
    from_max: float,
    to_min: float,
    to_max: float,
) -> bpy.types.NodeSocket:
    ramp = nodes.new(type="ShaderNodeMapRange")
    ramp.location = location
    ramp.inputs["From Min"].default_value = from_min
    ramp.inputs["From Max"].default_value = from_max
    ramp.inputs["To Min"].default_value = to_min
    ramp.inputs["To Max"].default_value = to_max
    ramp.clamp = True
    links.new(value, ramp.inputs["Value"])
    return ramp.outputs["Result"]


def _multiply(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    first: bpy.types.NodeSocket,
    second: bpy.types.NodeSocket,
    *,
    location: tuple[float, float],
) -> bpy.types.NodeSocket:
    node = nodes.new(type="ShaderNodeMath")
    node.location = location
    node.operation = "MULTIPLY"
    links.new(first, node.inputs[0])
    links.new(second, node.inputs[1])
    return node.outputs["Value"]


def _rgb(
    nodes: bpy.types.Nodes,
    color: tuple[float, float, float],
    *,
    location: tuple[float, float],
) -> bpy.types.NodeSocket:
    node = nodes.new(type="ShaderNodeRGB")
    node.location = location
    node.outputs[0].default_value = (color[0], color[1], color[2], 1.0)
    return node.outputs[0]


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


def build_look_material(
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
        max(0.0, spec.base_color[0] * 0.58),
        max(0.0, spec.base_color[1] * 0.54),
        max(0.0, spec.base_color[2] * 0.48),
        1.0,
    )
    lift_rgb = nodes.new(type="ShaderNodeRGB")
    lift_rgb.location = (-200, 280)
    lift_rgb.outputs[0].default_value = (
        min(1.0, spec.base_color[0] * 1.12 + 0.035),
        min(1.0, spec.base_color[1] * 1.09 + 0.025),
        min(1.0, spec.base_color[2] * 1.06 + 0.018),
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
        coarse = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(1.4, 1.4, 2.0),
            offset=(shift, shift * 0.4, 0.0),
            detail=6.0,
            roughness=0.58,
        )
        fibre = _noise(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(7.0, 2.2, 1.3),
            offset=(shift * 0.12, shift * 0.2, shift * 0.05),
            detail=8.0,
            roughness=0.7,
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=coarse,
            color_a=dark_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        fibre_mask = nodes.new(type="ShaderNodeMapRange")
        fibre_mask.location = (80, -40)
        fibre_mask.inputs["From Min"].default_value = 0.35
        fibre_mask.inputs["From Max"].default_value = 0.78
        fibre_mask.inputs["To Min"].default_value = 0.0
        fibre_mask.inputs["To Max"].default_value = 0.32
        fibre_mask.clamp = True
        links.new(fibre, fibre_mask.inputs["Value"])
        color = _mix_rgba(
            nodes,
            links,
            location=(280, 80),
            factor=fibre_mask.outputs["Result"],
            color_a=color,
            color_b=base_rgb.outputs[0],
        )
        bump_height = fibre
        bump_strength = 0.28
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
    elif look == "brick":
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.location = (-700, 180)
        mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
        mapping.inputs["Location"].default_value = (shift * 0.03, shift * 0.02, 0.0)
        links.new(generated, mapping.inputs["Vector"])
        brick = nodes.new(type="ShaderNodeTexBrick")
        brick.location = (-420, 180)
        brick.offset = 0.5
        brick.offset_frequency = 2
        brick.inputs["Scale"].default_value = 8.0
        brick.inputs["Mortar Size"].default_value = 0.028
        brick.inputs["Mortar Smooth"].default_value = 0.06
        brick.inputs["Brick Width"].default_value = 0.58
        brick.inputs["Row Height"].default_value = 0.24
        brick.inputs["Color1"].default_value = spec.base_color
        brick.inputs["Color2"].default_value = (
            spec.base_color[0] * 0.68,
            spec.base_color[1] * 0.62,
            spec.base_color[2] * 0.58,
            1.0,
        )
        brick.inputs["Mortar"].default_value = (0.18, 0.15, 0.12, 1.0)
        links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
        color = brick.outputs["Color"]
        bump_height = brick.outputs["Fac"]
        bump_strength = 0.65
        rough_base = spec.roughness
    elif look in ("cave_rock", "cave_calcite"):
        # The engine samples base colour only, so every bit of rock read has to
        # end up in the albedo: strata, mineral stain, grit, crack shadow and a
        # damp floor. Roughness and bump still drive the preview renders.
        calcite = look == "cave_calcite"
        base = spec.base_color
        # Texture space is Generated (0..1 over the 4 m cell), so a scale of N
        # means features about 4/N metres across.
        # Bedding planes as a vertically squashed noise, not a wave: a wave in Z
        # draws contour rings on every near-horizontal face.
        strata = _noise(
            nodes,
            links,
            generated,
            location=(-1180, 640),
            scale=(2.1, 2.1, 11.0 if calcite else 8.0),
            offset=(shift * 0.05, shift * 0.03, shift * 0.02),
            detail=4.0,
            roughness=0.55,
        )
        blotch = _noise(
            nodes,
            links,
            generated,
            location=(-1180, 520),
            scale=(3.4, 3.4, 2.6),
            offset=(shift * 0.29, shift * 0.07, shift * 0.19),
            detail=4.0,
            roughness=0.55,
        )
        patches = _noise(
            nodes,
            links,
            generated,
            location=(-1180, 420),
            scale=(6.2, 6.2, 4.4),
            offset=(shift * 0.11, shift * 0.17, shift * 0.07),
            detail=6.0,
            roughness=0.62,
        )
        mottle = _noise(
            nodes,
            links,
            generated,
            location=(-1180, 200),
            scale=(19.0, 19.0, 19.0),
            offset=(shift * 0.19, shift * 0.23, shift * 0.13),
            detail=8.0,
            roughness=0.68,
        )
        speckle = _noise(
            nodes,
            links,
            generated,
            location=(-1180, -20),
            scale=(74.0, 74.0, 74.0),
            offset=(shift * 0.31, shift * 0.13, shift * 0.23),
            detail=10.0,
            roughness=0.78,
        )
        # Centimetre grit. Rock reads as rock at arm's length because of this,
        # not because of the crack net.
        grit = _noise(
            nodes,
            links,
            generated,
            location=(-1180, 100),
            scale=(210.0, 210.0, 210.0),
            offset=(shift * 0.43, shift * 0.37, shift * 0.41),
            detail=12.0,
            roughness=0.82,
        )
        cracks = _voronoi_edges(
            nodes,
            links,
            generated,
            location=(-1180, -240),
            scale=(46.0, 46.0, 46.0),
            offset=(shift * 0.07, shift * 0.19, shift * 0.05),
            randomness=1.0,
        )
        seams = _voronoi_edges(
            nodes,
            links,
            generated,
            location=(-1180, -460),
            scale=(62.0, 62.0, 62.0),
            offset=(shift * 0.23, shift * 0.09, shift * 0.29),
            randomness=0.95,
        )
        # Rock is fractured in patches, not everywhere at one strength. Without
        # this gate the crack net reads as reptile skin. It bottoms out at zero
        # on purpose: most of a wall shows no crack at all.
        fracture = _noise(
            nodes,
            links,
            generated,
            location=(-1180, -900),
            scale=(2.4, 2.4, 1.8),
            offset=(shift * 0.37, shift * 0.29, shift * 0.11),
            detail=3.0,
            roughness=0.5,
        )
        fracture_gate = _remap(
            nodes,
            links,
            fracture,
            location=(-820, -900),
            from_min=0.5,
            from_max=0.63,
            to_min=0.0,
            to_max=1.0,
        )
        streaks = (
            _wave(
                nodes,
                links,
                generated,
                location=(-1180, -1120),
                scale=(1.0, 1.0, 0.22),
                rotation=(0.0, 0.0, 0.4),
                offset=(shift * 0.13, shift * 0.07, 0.0),
                wave_scale=3.5,
                distortion=18.0,
                bands="X",
            )
            if calcite
            else None
        )
        high = _height_mask(
            nodes,
            links,
            generated,
            location=(-1180, -680),
            from_min=0.03,
            from_max=0.4,
        )

        color = _mix_rgba(
            nodes,
            links,
            location=(-620, 640),
            # Noise Fac clusters hard around 0.5, so every window below is narrow
            # on purpose. Widen one and that layer stops showing up in the bake.
            factor=_remap(
                nodes,
                links,
                strata,
                location=(-820, 640),
                from_min=0.42,
                from_max=0.58,
                to_min=0.0,
                to_max=1.0,
            ),
            color_a=_rgb(
                nodes,
                (base[0] * 0.72, base[1] * 0.7, base[2] * 0.68),
                location=(-820, 820),
            ),
            color_b=_rgb(
                nodes,
                (
                    min(1.0, base[0] * 1.2 + 0.014),
                    min(1.0, base[1] * 1.17 + 0.012),
                    min(1.0, base[2] * 1.12 + 0.01),
                ),
                location=(-820, 960),
            ),
        )
        # Metre-scale value blotches. Without these the wall is one flat tone no
        # matter how much fine detail sits on top of it.
        color = _mix_rgba(
            nodes,
            links,
            location=(-500, 600),
            factor=_remap(
                nodes,
                links,
                blotch,
                location=(-620, 520),
                from_min=0.43,
                from_max=0.6,
                to_min=0.0,
                to_max=0.62,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (base[0] * 0.5, base[1] * 0.5, base[2] * 0.52),
                location=(-620, 660),
            ),
        )
        # Iron stain on rock, cream flowstone on calcite: the hue break that
        # stops grey rock reading as concrete.
        color = _mix_rgba(
            nodes,
            links,
            location=(-380, 520),
            factor=_remap(
                nodes,
                links,
                patches,
                location=(-620, 420),
                from_min=0.53,
                from_max=0.64,
                to_min=0.0,
                to_max=0.55,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (min(1.0, base[0] * 1.15 + 0.02), base[1] * 0.72, base[2] * 0.42)
                if not calcite
                else (base[0] * 1.28 + 0.03, base[1] * 1.24 + 0.03, base[2] * 1.16 + 0.02),
                location=(-620, 300),
            ),
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(-140, 400),
            factor=_remap(
                nodes,
                links,
                patches,
                location=(-380, 300),
                from_min=0.36,
                from_max=0.47,
                to_min=0.38,
                to_max=0.0,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (
                    min(1.0, base[0] * 1.3 + 0.05),
                    min(1.0, base[1] * 1.27 + 0.05),
                    min(1.0, base[2] * 1.2 + 0.04),
                ),
                location=(-380, 180),
            ),
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(100, 340),
            factor=_remap(
                nodes,
                links,
                mottle,
                location=(-140, 200),
                from_min=0.42,
                from_max=0.6,
                to_min=0.0,
                to_max=0.55,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (base[0] * 0.38, base[1] * 0.38, base[2] * 0.39),
                location=(-140, 80),
            ),
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(340, 300),
            factor=_remap(
                nodes,
                links,
                speckle,
                location=(100, -20),
                from_min=0.48,
                from_max=0.62,
                to_min=0.0,
                to_max=0.24,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (
                    min(1.0, base[0] * 1.6 + 0.04),
                    min(1.0, base[1] * 1.54 + 0.04),
                    min(1.0, base[2] * 1.45 + 0.03),
                ),
                location=(100, -140),
            ),
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(440, 340),
            factor=_remap(
                nodes,
                links,
                grit,
                location=(100, 100),
                from_min=0.44,
                from_max=0.58,
                to_min=0.0,
                to_max=0.34,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (base[0] * 0.45, base[1] * 0.44, base[2] * 0.44),
                location=(100, 220),
            ),
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(580, 260),
            factor=_multiply(
                nodes,
                links,
                _remap(
                    nodes,
                    links,
                    cracks,
                    location=(100, -240),
                    from_min=0.0,
                    from_max=0.055,
                    to_min=0.3,
                    to_max=0.0,
                ),
                fracture_gate,
                location=(340, -180),
            ),
            color_a=color,
            color_b=_rgb(nodes, (0.05, 0.043, 0.038), location=(340, -300)),
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(580, 80),
            factor=_multiply(
                nodes,
                links,
                _remap(
                    nodes,
                    links,
                    seams,
                    location=(100, -460),
                    from_min=0.0,
                    from_max=0.06,
                    to_min=0.28,
                    to_max=0.0,
                ),
                fracture_gate,
                location=(340, -400),
            ),
            color_a=color,
            color_b=_rgb(nodes, (0.09, 0.08, 0.07), location=(340, -520)),
        )
        if streaks is not None:
            color = _mix_rgba(
                nodes,
                links,
                location=(580, -100),
                factor=_multiply(
                    nodes,
                    links,
                    _remap(
                        nodes,
                        links,
                        streaks,
                        location=(100, -1120),
                        from_min=0.58,
                        from_max=0.97,
                        to_min=0.0,
                        to_max=0.4,
                    ),
                    high,
                    location=(340, -1060),
                ),
                color_a=color,
                color_b=_rgb(
                    nodes,
                    (
                        min(1.0, base[0] * 1.9 + 0.1),
                        min(1.0, base[1] * 1.85 + 0.1),
                        min(1.0, base[2] * 1.75 + 0.09),
                    ),
                    location=(340, -1180),
                ),
            )
        color = _mix_rgba(
            nodes,
            links,
            location=(700, 200),
            factor=_remap(
                nodes,
                links,
                high,
                location=(-820, -680),
                from_min=0.0,
                from_max=1.0,
                to_min=0.4,
                to_max=0.0,
            ),
            color_a=color,
            color_b=_rgb(
                nodes,
                (0.11, 0.115, 0.105) if not calcite else (0.22, 0.24, 0.23),
                location=(340, -680),
            ),
        )
        bump_mix = nodes.new(type="ShaderNodeMath")
        bump_mix.location = (340, -580)
        bump_mix.operation = "MULTIPLY"
        links.new(cracks, bump_mix.inputs[0])
        links.new(grit, bump_mix.inputs[1])
        bump_height = bump_mix.outputs["Value"]
        bump_strength = 0.95 if not calcite else 0.55
        rough_base = spec.roughness
    elif look in ("stone", "stone_trim"):
        coarse = _noise(
            nodes,
            links,
            generated,
            location=(-700, 260),
            scale=(2.0, 2.0, 2.0),
            offset=(shift * 0.15, shift * 0.21, shift * 0.08),
            detail=5.0,
            roughness=0.62,
        )
        grain = _noise(
            nodes,
            links,
            generated,
            location=(-700, -40),
            scale=(11.0, 11.0, 11.0),
            offset=(shift * 0.4, shift * 0.2, shift * 0.1),
            detail=8.0,
            roughness=0.72,
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 240),
            factor=coarse,
            color_a=dark_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        grain_mask = nodes.new(type="ShaderNodeMapRange")
        grain_mask.location = (70, 0)
        grain_mask.inputs["From Min"].default_value = 0.38
        grain_mask.inputs["From Max"].default_value = 0.76
        grain_mask.inputs["To Min"].default_value = 0.0
        grain_mask.inputs["To Max"].default_value = 0.28
        grain_mask.clamp = True
        links.new(grain, grain_mask.inputs["Value"])
        color = _mix_rgba(
            nodes,
            links,
            location=(300, 90),
            factor=grain_mask.outputs["Result"],
            color_a=color,
            color_b=base_rgb.outputs[0],
        )
        bump_height = grain
        bump_strength = 0.52 if look == "stone" else 0.32
        rough_base = spec.roughness
    elif look == "linen":
        weave_x = _wave(
            nodes,
            links,
            generated,
            location=(-700, 220),
            scale=(22.0, 1.0, 1.0),
            rotation=(0.0, 0.0, 0.0),
            offset=(shift * 0.02, 0.0, 0.0),
            wave_scale=4.0,
            distortion=0.15,
            bands="X",
        )
        weave_z = _wave(
            nodes,
            links,
            generated,
            location=(-700, -60),
            scale=(1.0, 1.0, 22.0),
            rotation=(0.0, 0.0, 0.0),
            offset=(0.0, 0.0, shift * 0.02),
            wave_scale=4.0,
            distortion=0.15,
            bands="Z",
        )
        weave = nodes.new(type="ShaderNodeMath")
        weave.location = (-250, 100)
        weave.operation = "MULTIPLY"
        links.new(weave_x, weave.inputs[0])
        links.new(weave_z, weave.inputs[1])
        mottling = _noise(
            nodes,
            links,
            generated,
            location=(-700, 430),
            scale=(2.0, 2.0, 2.0),
            offset=(shift, shift * 0.4, shift * 0.2),
            detail=4.0,
            roughness=0.55,
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 220),
            factor=mottling,
            color_a=base_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(300, 80),
            factor=weave.outputs["Value"],
            color_a=color,
            color_b=dark_rgb.outputs[0],
        )
        bump_height = weave.outputs["Value"]
        bump_strength = 0.22
        rough_base = max(spec.roughness, 0.82)
    elif look == "iron":
        pitting = _noise(
            nodes,
            links,
            generated,
            location=(-700, 220),
            scale=(8.0, 8.0, 8.0),
            offset=(shift, shift * 0.7, shift * 0.3),
            detail=7.0,
            roughness=0.68,
        )
        rust = _noise(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(2.2, 2.2, 2.2),
            offset=(shift * 0.1, shift * 0.4, shift * 0.2),
            detail=5.0,
            roughness=0.58,
        )
        rust_rgb = nodes.new(type="ShaderNodeRGB")
        rust_rgb.location = (-80, -120)
        rust_rgb.outputs[0].default_value = (0.19, 0.065, 0.025, 1.0)
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 220),
            factor=pitting,
            color_a=dark_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        rust_mask = nodes.new(type="ShaderNodeMapRange")
        rust_mask.location = (60, -60)
        rust_mask.inputs["From Min"].default_value = 0.62
        rust_mask.inputs["From Max"].default_value = 0.84
        rust_mask.inputs["To Min"].default_value = 0.0
        rust_mask.inputs["To Max"].default_value = 0.72
        rust_mask.clamp = True
        links.new(rust, rust_mask.inputs["Value"])
        color = _mix_rgba(
            nodes,
            links,
            location=(300, 80),
            factor=rust_mask.outputs["Result"],
            color_a=color,
            color_b=rust_rgb.outputs[0],
        )
        bump_height = pitting
        bump_strength = 0.3
        rough_base = max(spec.roughness, 0.58)
        principled.inputs["Metallic"].default_value = max(spec.metallic, 0.55)
    elif look == "soot":
        soot = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(3.0, 3.0, 5.0),
            offset=(shift, shift * 0.6, shift * 0.2),
            detail=8.0,
            roughness=0.72,
        )
        ember_rgb = nodes.new(type="ShaderNodeRGB")
        ember_rgb.location = (-180, 300)
        ember_rgb.outputs[0].default_value = (0.24, 0.045, 0.012, 1.0)
        color = _mix_rgba(
            nodes,
            links,
            location=(100, 160),
            factor=soot,
            color_a=dark_rgb.outputs[0],
            color_b=ember_rgb.outputs[0],
        )
        bump_height = soot
        bump_strength = 0.18
        rough_base = 0.96
    elif look == "plaster":
        coarse = _noise(
            nodes,
            links,
            generated,
            location=(-700, 200),
            scale=(1.1, 1.1, 1.1),
            offset=(shift, shift * 0.6, shift * 0.3),
            detail=5.0,
            roughness=0.58,
        )
        pores = _noise(
            nodes,
            links,
            generated,
            location=(-700, -80),
            scale=(14.0, 14.0, 14.0),
            offset=(shift * 0.2, shift * 0.4, shift * 0.1),
            detail=7.0,
            roughness=0.7,
        )
        warm_rgb = nodes.new(type="ShaderNodeRGB")
        warm_rgb.location = (-120, 360)
        warm_rgb.outputs[0].default_value = (
            spec.base_color[0] * 0.72,
            spec.base_color[1] * 0.67,
            spec.base_color[2] * 0.58,
            1.0,
        )
        color = _mix_rgba(
            nodes,
            links,
            location=(80, 200),
            factor=coarse,
            color_a=warm_rgb.outputs[0],
            color_b=lift_rgb.outputs[0],
        )
        pore_mask = nodes.new(type="ShaderNodeMapRange")
        pore_mask.location = (80, -50)
        pore_mask.inputs["From Min"].default_value = 0.42
        pore_mask.inputs["From Max"].default_value = 0.78
        pore_mask.inputs["To Min"].default_value = 0.0
        pore_mask.inputs["To Max"].default_value = 0.18
        pore_mask.clamp = True
        links.new(pores, pore_mask.inputs["Value"])
        color = _mix_rgba(
            nodes,
            links,
            location=(300, 70),
            factor=pore_mask.outputs["Result"],
            color_a=color,
            color_b=base_rgb.outputs[0],
        )
        bump_height = pores
        bump_strength = 0.18
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

    weather_colors = {
        "timber": (0.075, 0.043, 0.022, 1.0),
        "shingle": (0.12, 0.15, 0.105, 1.0),
        "thatch": (0.19, 0.145, 0.07, 1.0),
        "ashlar": (0.18, 0.16, 0.125, 1.0),
        "stone": (0.17, 0.15, 0.12, 1.0),
        "stone_trim": (0.16, 0.14, 0.115, 1.0),
        "brick": (0.17, 0.075, 0.04, 1.0),
        "plaster": (0.34, 0.27, 0.17, 1.0),
    }
    weather_color = weather_colors.get(look)
    if weather_color is not None:
        age = _noise(
            nodes,
            links,
            generated,
            location=(-720, 650),
            scale=(0.65, 0.65, 0.9),
            offset=(shift * 0.08, shift * 0.11, shift * 0.05),
            detail=5.0,
            roughness=0.64,
        )
        age_mask = nodes.new(type="ShaderNodeMapRange")
        age_mask.location = (60, 500)
        age_mask.inputs["From Min"].default_value = 0.48
        age_mask.inputs["From Max"].default_value = 0.82
        age_mask.inputs["To Min"].default_value = 0.0
        age_mask.inputs["To Max"].default_value = 0.24 if look == "plaster" else 0.17
        age_mask.clamp = True
        links.new(age, age_mask.inputs["Value"])
        age_rgb = nodes.new(type="ShaderNodeRGB")
        age_rgb.location = (260, 500)
        age_rgb.outputs[0].default_value = weather_color
        color = _mix_rgba(
            nodes,
            links,
            location=(490, 330),
            factor=age_mask.outputs["Result"],
            color_a=color,
            color_b=age_rgb.outputs[0],
        )

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
        mesh.materials[index] = build_look_material(
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
    if params.jagged:
        # A displaced rock shell has a sharp angle at nearly every quad, so the
        # default 66 degree limit shreds it into thousands of islands whose
        # margins eat the atlas. One island per shell keeps the texel density
        # that the baked rock detail needs.
        unwrap(obj, angle_limit_deg=87.0, island_margin=0.0015)
    else:
        unwrap(obj)
    _bake_kit_textures(obj, spec, params)
    return [obj]
