"""Kits: several assets placed together and looked at as one, with their joints measured.

A kit is `assets/kits/<name>.json`:

    {"place": [
       {"asset": "wall_brick_straight", "at": [0, 0, 0]},
       {"asset": "wall_brick_straight", "at": [2, 0, 0]},
       {"asset": "wall_brick_corner", "at": [4, 0, 0], "turn": 90}
     ]}

Each placement puts an asset (a spec id) at `at` (metres), turned `turn` degrees about Z.
`ag.py look kit:<name>` draws them as one sheet, every asset painted in its own frame (as
the game will show them: each file's textures baked for that file), and measures each joint
between neighbours: the gap or overlap between them, and how far the surface pattern steps
where one asset meets the next (a wall whose bricks do not line up across the join).
"""

from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from assetkit.material import evaluate_points
from assetkit.texbake import to_srgb
from assetview.model import ViewModel, from_asset, from_glb
from assetview.paint import PatternPaint, _even_samples
from blender.lib.registry import KIT_GENERATORS, resolve_generator_module
from blender.lib.spec import SpecError, load_spec

JOINT = 0.05  # metres: boxes this close along one axis, overlapping on the others, meet there
VISIBLE = 0.08  # sRGB (0..1) difference between the two sides that the eye picks up
STEP_FLAG = 0.05  # share of a joint where the sides differ visibly before it reads as a seam
GAP_FLAG = 0.0005  # metres of gap or overlap at a joint worth reporting


@dataclass
class Placed:
    asset_id: str
    model: ViewModel
    rotation: np.ndarray  # (3, 3): local to world, v_world = rotation @ v_local
    at: np.ndarray  # (3,)

    def world(self, local: np.ndarray) -> np.ndarray:
        return local @ self.rotation.T + self.at

    def local(self, world: np.ndarray) -> np.ndarray:
        return (world - self.at) @ self.rotation


def load_kit(path: Path, spec_dir: Path, out_dir: Path, from_shipped: bool = False) -> list[Placed]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) - {"place", "description"}:
        raise SpecError(f"{path}: a kit is an object with `place` (and `description`)")
    place = raw.get("place")
    if not isinstance(place, list) or not place:
        raise SpecError(f"{path}.place: expected a non-empty list of placements")
    models: dict[str, ViewModel] = {}
    out = []
    for i, item in enumerate(place):
        here = f"{path.name}.place[{i}]"
        if not isinstance(item, dict) or "asset" not in item or set(item) - {"asset", "at", "turn"}:
            raise SpecError(f"{here}: expected {{'asset': <spec id>, 'at': [x, y, z], 'turn': degrees}}")
        at = item.get("at", [0, 0, 0])
        if not (isinstance(at, list) and len(at) == 3 and all(isinstance(v, int | float) for v in at)):
            raise SpecError(f"{here}.at: expected [x, y, z] in metres")
        turn = item.get("turn", 0)
        if not isinstance(turn, int | float) or isinstance(turn, bool):
            raise SpecError(f"{here}.turn: expected degrees about Z")
        asset_id = str(item["asset"])
        if asset_id not in models:
            models[asset_id] = _model(asset_id, spec_dir, out_dir, from_shipped)
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        rotation = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        out.append(Placed(asset_id, models[asset_id], rotation, np.asarray(at, dtype=np.float64)))
    return out


def _model(asset_id: str, spec_dir: Path, out_dir: Path, from_shipped: bool) -> ViewModel:
    spec = load_spec(spec_dir / f"{asset_id}.json")
    if spec.generator in KIT_GENERATORS and not from_shipped:
        module = importlib.import_module(resolve_generator_module(spec.generator))
        return from_asset(module.build(spec))
    glb = out_dir / spec.glb_name
    if not glb.is_file():
        raise SpecError(f"{glb} does not exist yet: run `python tools/ag.py generate {asset_id}` first")
    return from_glb(glb)


class KitPaint:
    """Each placed asset's own paint, looked up through the kit's triangle numbering."""

    def __init__(self, placed: list[Placed], starts: np.ndarray) -> None:
        self.placed, self.starts = placed, starts

    def _split(self, tri: np.ndarray) -> list[tuple[int, np.ndarray, np.ndarray]]:
        which = np.searchsorted(self.starts, tri, side="right") - 1
        return [
            (k, pick, tri[pick] - self.starts[k])
            for k in range(len(self.placed))
            if len(pick := np.nonzero(which == k)[0])
        ]

    def colors(self, tri: np.ndarray, bary: np.ndarray) -> np.ndarray:
        out = np.zeros((len(tri), 3))
        for k, pick, local in self._split(tri):
            model = self.placed[k].model
            if model.paint is None:
                out[pick] = model.slot_colors[model.tri_slot[local]]
            else:
                out[pick] = model.paint.colors(local, bary[pick])
        return out

    def detailed(self) -> bool:
        return any(getattr(p.model.paint, "detailed", lambda: False)() for p in self.placed)

    def normals(self, tri: np.ndarray, bary: np.ndarray, base: np.ndarray) -> np.ndarray:
        out = base.copy()
        for k, pick, local in self._split(tri):
            p = self.placed[k]
            if getattr(p.model.paint, "detailed", lambda: False)():
                n = p.model.paint.normals(local, bary[pick], base[pick] @ p.rotation)  # type: ignore[union-attr]
                out[pick] = n @ p.rotation.T
        return out

    def report(self, slots: list[str]) -> list[dict[str, object]]:
        """Each asset's pattern report once (the first placement of it)."""
        out: list[dict[str, object]] = []
        seen: set[str] = set()
        for p in self.placed:
            if p.asset_id in seen or not hasattr(p.model.paint, "report"):
                continue
            seen.add(p.asset_id)
            for entry in p.model.paint.report([f"{p.asset_id}.{s}" for s in p.model.slots]):  # type: ignore[union-attr]
                out.append(entry)
        return out


def compose(placed: list[Placed], name: str) -> ViewModel:
    """One view model of every placed asset (kept apart: parts never weld across assets)."""
    positions, triangles, tri_slot, real, crease, corner = [], [], [], [], [], []
    slots: list[str] = []
    colors: list[np.ndarray] = []
    alphas: list[float] = []
    starts = []
    offset = tri_count = 0
    for p in placed:
        m = p.model
        starts.append(tri_count)
        positions.append(p.world(m.positions))
        triangles.append(m.triangles + offset)
        index = []
        for s, slot in enumerate(m.slots):
            key = f"{p.asset_id}.{slot}"
            if key not in slots:
                slots.append(key)
                colors.append(m.slot_colors[s])
                alphas.append(float(m.slot_alpha[s]) if m.slot_alpha is not None else 1.0)
            index.append(slots.index(key))
        tri_slot.append(np.asarray(index, dtype=np.int64)[m.tri_slot])
        real.append(m.real_edges)
        crease.append(m.crease)
        corner.append(None if m.corner_normals is None else m.corner_normals @ p.rotation.T)
        offset += len(m.positions)
        tri_count += len(m.triangles)
    return ViewModel(
        positions=np.concatenate(positions),
        triangles=np.concatenate(triangles),
        tri_slot=np.concatenate(tri_slot),
        slots=slots,
        slot_colors=np.asarray(colors),
        real_edges=np.concatenate(real),
        source=f"kit {name}: {len(placed)} placements",
        paint=KitPaint(placed, np.asarray(starts)),
        slot_alpha=np.asarray(alphas),
        crease=np.concatenate(crease) if all(c is not None for c in crease) else None,
        corner_normals=np.concatenate(corner) if all(c is not None for c in corner) else None,
    )


def joints(placed: list[Placed]) -> list[dict[str, object]]:
    """Every pair of placements whose bounds meet along one axis: the gap (+) or overlap (-)
    there, and on what share of the joint the pattern steps visibly (None: no pattern)."""
    boxes = []
    for p in placed:
        w = p.world(p.model.positions)
        boxes.append((w.min(axis=0), w.max(axis=0)))
    out = []
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            (lo_i, hi_i), (lo_j, hi_j) = boxes[i], boxes[j]
            sep = np.maximum(lo_j - hi_i, lo_i - hi_j)  # per axis: + gap, - overlap of the extents
            for axis in range(3):
                others = [a for a in range(3) if a != axis]
                if abs(sep[axis]) > JOINT or not (sep[others] < -JOINT).all():
                    continue
                # Which side is which: i below j along the axis, or above it.
                first, second = (i, j) if lo_i[axis] <= lo_j[axis] else (j, i)
                plane = boxes[first][1][axis]
                out.append(
                    {
                        "between": [
                            f"{placed[first].asset_id}#{first + 1}",
                            f"{placed[second].asset_id}#{second + 1}",
                        ],
                        "axis": "xyz"[axis],
                        "at": round(float(plane), 4),
                        "gap_m": round(float(sep[axis]), 4),
                        "pattern_step": _step(placed[first], placed[second], axis, plane, boxes[second]),
                        "turned": round(_turn_between(placed[first], placed[second]), 1),
                    }
                )
    return out


def _turn_between(a: Placed, b: Placed) -> float:
    """Degrees one placement is turned against the other (0..180)."""
    r = a.rotation.T @ b.rotation
    return abs(math.degrees(math.atan2(r[1, 0], r[0, 0])))


def _step(
    a: Placed, b: Placed, axis: int, plane: float, box_b: tuple[np.ndarray, np.ndarray]
) -> float | None:
    """Where `a`'s surface meets the joint, the share of it at which `a`'s own pattern and
    `b`'s, evaluated at the same points, differ visibly: 0 when the pattern runs on across."""
    paint_a, paint_b = a.model.paint, b.model.paint
    if not isinstance(paint_a, PatternPaint) or not isinstance(paint_b, PatternPaint):
        return None
    m = a.model
    v = m.positions[m.triangles]
    area = 0.5 * np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1)
    tri, bary, _ = _even_samples(area)
    local = (m.positions[m.triangles[tri]] * bary[:, :, None]).sum(axis=1)
    world = a.world(local)
    lo_b, hi_b = box_b
    others = [k for k in range(3) if k != axis]
    near = (np.abs(world[:, axis] - plane) < 0.02) & (
        (world[:, others] >= lo_b[others]) & (world[:, others] <= hi_b[others])
    ).all(axis=1)
    if not near.any():
        return None
    tri, bary, world = tri[near], bary[near], world[near]
    q, bend, normal = paint_a.surface.at(tri, bary)
    # End faces turned to the joint are hidden in the finished wall: measure the faces it shows.
    axis_world = np.eye(3)[axis]
    shows = np.abs((normal @ a.rotation.T) @ axis_world) < 0.5
    if not shows.any():
        return None
    tri, bary, world, q, bend, normal = (
        tri[shows],
        bary[shows],
        world[shows],
        q[shows],
        bend[shows],
        normal[shows],
    )
    color_a = paint_a.colors(tri, bary)
    color_b = np.array(color_a)
    covered = np.zeros(len(tri), dtype=bool)
    in_b = b.local(world)
    normal_b = (normal @ a.rotation.T) @ b.rotation
    slot_a = paint_a.tri_slot[tri]
    names_b = list(b.model.slots)
    for s, name in enumerate(a.model.slots):
        pick = np.nonzero(slot_a == s)[0]
        if not len(pick) or name not in names_b:
            continue
        sb = names_b.index(name)
        look = paint_b.looks[sb]
        if look.pattern is None:
            color_b[pick] = look.base_color
        else:
            color_b[pick] = evaluate_points(
                look.pattern,
                in_b[pick] - np.asarray(paint_b.origins[sb]),
                bend[pick],
                normal_b[pick],
                lambda r, out, pts=q[pick]: paint_a.surface.near_creases(pts, r, out),
                look.base_color,
                look.roughness,
            )[0]
        covered[pick] = True
    if not covered.any():
        return None
    # A seam shows where the two sides differ visibly: the share of the joint where they do.
    diff = np.abs(to_srgb(color_a[covered]) - to_srgb(color_b[covered])).max(axis=1)
    return round(float((diff > VISIBLE).mean()), 4)


def joint_lines(found: list[dict[str, object]]) -> list[str]:
    lines = []
    for j in found:
        a, b = j["between"]  # type: ignore[misc]
        notes = []
        gap = float(j["gap_m"])  # type: ignore[arg-type]
        if gap > GAP_FLAG:
            notes.append(f"{gap * 1000:.1f} mm gap")
        elif gap < -GAP_FLAG:
            notes.append(f"overlap {-gap * 1000:.1f} mm")
        step = j["pattern_step"]
        if step is not None and step > STEP_FLAG:  # type: ignore[operator]
            if j.get("turned"):
                why = (
                    f"the two meet turned {j['turned']:.0f} degrees: bricks line up across a turn, noise"
                    " and cells (mottle, cells, spots, grain) do not; keep those subtle at the ends"
                )
            else:
                why = "give the pattern a `period` the tiles fit (the grid step)"
            notes.append(f"pattern steps along {step:.0%} of it: {why}")
        lines.append(
            f"joint {a} | {b} at {j['axis']} = {j['at']:.2f}: "
            + ("; ".join(notes) if notes else "meets cleanly")
        )
    return lines
