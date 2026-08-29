# -*- coding: utf-8 -*-
"""Check the orc maw and tusk geometry without Blender.

``tools/bake_human_orc.py`` cannot be exercised outside Blender, but the part
of it that kept going wrong is pure geometry: where the mouth is, how deep the
cavity is, and whether the tusks end up standing in that cavity or buried in
its wall. This script reimplements exactly that arithmetic -- the tusk seat
from ``tusk_seat_in_body_space`` and every containment check from
``assert_tusks_in_mouth_for_current_pose`` -- against the synthetic heads in
``orc_mouth_geometry``, and reads the real constants out of the bake script so
the two cannot drift apart.

Run before handing a bake to the Art Pipeline::

    python tools/orc_mouth_geometry.py     # the mouth solver's own self-test
    python tools/orc_mouth_selfcheck.py    # maw + tusk containment

What it cannot check: anything that needs Blender (bone parenting, skinning,
rendering). The transform chain from body space to bone-parent space is
verified in the bake script itself by ``assert_tusk_rigid_bind``, which runs on
every still.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path

import orc_mouth_geometry as MG

Vec = tuple[float, float, float]
Face = tuple[int, ...]
Edge = tuple[int, int]

BAKE = Path(__file__).resolve().parent / "bake_human_orc.py"

WANTED = (
    "TUSK_SEAT_U_FRAC",
    "TUSK_SEAT_W_FRAC",
    "TUSK_SEAT_D_FRAC",
    "TUSK_AXIS_MEDIAL",
    "TUSK_AXIS_OUTWARD",
    "TUSK_LENGTH_HH_FRAC",
    "TUSK_RADIUS_BASE_HH_FRAC",
    "TUSK_RADIUS_TIP_HH_FRAC",
    "TUSK_SEGMENTS",
    "TUSK_APERTURE_MARGIN",
    "TUSK_FRONT_D_FRAC",
    "TUSK_MIN_FRONT_FRAC",
    "TUSK_MIN_W_SPAN_HH_FRAC",
    "TUSK_MIN_AXIS_RISE_DOT",
    "TUSK_BORE_CLEARANCE_M",
    "CAVITY_MIN_ACHIEVED_DEPTH_FRAC",
    "CAVITY_MIN_CARVED_VERTS",
    "CAVITY_INTERIOR_POLY_FALLOFF",
    "CAVITY_SUBDIV_TARGET_SAMPLES",
    "CAVITY_SUBDIV_REGION_R",
    "CAVITY_SUBDIV_MAX_PASSES",
    "CAVITY_SUBDIV_MIN_BUDGET",
    "CAVITY_SUBDIV_MAX_ADDED_FRAC",
)


def read_bake_constants() -> dict[str, float]:
    """Pull the module-level constants out of bake_human_orc without importing bpy."""
    tree = ast.parse(BAKE.read_text(encoding="utf-8"), filename=str(BAKE))
    found: dict[str, float] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in WANTED:
            continue
        found[target.id] = ast.literal_eval(node.value)
    missing = [n for n in WANTED if n not in found]
    if missing:
        raise SystemExit(
            f"{BAKE.name} no longer defines {missing} at module level; this "
            f"self-check reads the real constants on purpose, so update it "
            f"alongside the bake script"
        )
    return found


K = read_bake_constants()


# --- small vector helpers (no numpy, no mathutils) --------------------------


def _norm(v: Vec) -> Vec:
    n = math.sqrt(sum(c * c for c in v))
    if n <= 0.0:
        raise ValueError("cannot normalise a zero vector")
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _add(*vs: Vec) -> Vec:
    return tuple(sum(c) for c in zip(*vs, strict=True))


def _mul(v: Vec, s: float) -> Vec:
    return (v[0] * s, v[1] * s, v[2] * s)


def _axis_frame(axis: Vec, phase: float) -> tuple[Vec, Vec]:
    """``_axis_frame`` from the bake script, rotated by ``phase``.

    The bake script builds the frame in head-local space, so the ring's phase
    relative to the aperture is not fixed. A cone is rotationally symmetric but
    the aperture ellipse is not, so every check sweeps the phase.
    """
    helper = (1.0, 0.0, 0.0)
    if abs(_dot(axis, helper)) > 0.90:
        helper = (0.0, 0.0, 1.0)
    x = _norm(_cross(axis, helper))
    y = _norm(_cross(axis, x))
    c, s = math.cos(phase), math.sin(phase)
    return _add(_mul(x, c), _mul(y, s)), _add(_mul(x, -s), _mul(y, c))


def tusk_seat(
    ap: MG.MouthAperture, sign_x: float
) -> tuple[Vec, Vec, float, float, float]:
    """Mirror of ``tusk_seat_in_body_space``."""
    hw, hh, dp = ap.half_width, ap.half_height, ap.depth
    base = (
        ap.center_x + sign_x * K["TUSK_SEAT_U_FRAC"] * hw,
        ap.center_y + K["TUSK_SEAT_D_FRAC"] * dp,
        ap.center_z + K["TUSK_SEAT_W_FRAC"] * hh,
    )
    axis = _norm((-sign_x * K["TUSK_AXIS_MEDIAL"], -K["TUSK_AXIS_OUTWARD"], 1.0))
    return (
        base,
        axis,
        K["TUSK_LENGTH_HH_FRAC"] * hh,
        K["TUSK_RADIUS_BASE_HH_FRAC"] * hh,
        K["TUSK_RADIUS_TIP_HH_FRAC"] * hh,
    )


def cone_verts(
    base: Vec,
    axis: Vec,
    length: float,
    r_base: float,
    r_tip: float,
    phase: float,
) -> list[Vec]:
    """``bmesh.ops.create_cone(cap_ends=True, cap_tris=True)`` vertex layout."""
    right, binormal = _axis_frame(axis, phase)
    segments = int(K["TUSK_SEGMENTS"])
    out = []
    for radius, rise in ((r_base, 0.0), (r_tip, length)):
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            out.append(
                _add(
                    base,
                    _mul(right, radius * math.cos(a)),
                    _mul(binormal, radius * math.sin(a)),
                    _mul(axis, rise),
                )
            )
    out.append(base)  # cap_tris centre verts
    out.append(_add(base, _mul(axis, length)))
    return out


def gate_tusk(
    ap: MG.MouthAperture,
    base: Vec,
    axis: Vec,
    length: float,
    r_base: float,
    r_tip: float,
    phase: float,
) -> list[str]:
    """Every check from ``assert_tusks_in_mouth_for_current_pose``."""
    verts = cone_verts(base, axis, length, r_base, r_tip, phase)
    margin = K["TUSK_APERTURE_MARGIN"]
    worst_radial = 0.0
    min_d, max_d = 1e9, -1e9
    w_lo, w_hi = 1e9, -1e9
    front = 0
    worst_buried = -1e9
    front_limit = K["TUSK_FRONT_D_FRAC"] * ap.depth
    for p in verts:
        u, w, d = ap.aperture_coords(p)
        worst_radial = max(
            worst_radial,
            math.hypot(u / (ap.half_width + margin), w / (ap.half_height + margin)),
        )
        wall = ap.depth * MG.bore_frac(ap.radial(u, w))
        worst_buried = max(worst_buried, d - (wall - K["TUSK_BORE_CLEARANCE_M"]))
        min_d, max_d = min(min_d, d), max(max_d, d)
        w_lo, w_hi = min(w_lo, w), max(w_hi, w)
        if d <= front_limit:
            front += 1
    front_frac = front / float(len(verts))
    fails = []
    if worst_radial > 1.0:
        fails.append(f"radial={worst_radial:.3f} > 1 (cheek / chin-needle class)")
    if min_d < -margin:
        fails.append(f"min_d={min_d * 1000:.1f}mm past the lip plane")
    if max_d > ap.depth + margin:
        fails.append(f"max_d={max_d * 1000:.1f}mm through the cavity floor")
    if worst_buried > 0.0:
        fails.append(f"buried {worst_buried * 1000:.1f}mm in the cavity wall")
    if front_frac < K["TUSK_MIN_FRONT_FRAC"]:
        fails.append(f"front_frac={front_frac:.3f} (buried at the back)")
    if (w_hi - w_lo) < K["TUSK_MIN_W_SPAN_HH_FRAC"] * ap.half_height:
        fails.append(f"w_span={(w_hi - w_lo) * 1000:.1f}mm too short")
    if _dot(axis, (0.0, 0.0, 1.0)) < K["TUSK_MIN_AXIS_RISE_DOT"]:
        fails.append("axis does not rise out of the maw")
    if -axis[1] < 0.0:
        fails.append("axis leans into the throat")
    if base[2] >= ap.center_z:
        fails.append("rooted at or above the aperture centre line")
    return fails


def tusk_metrics(
    ap: MG.MouthAperture,
) -> tuple[dict[str, float], list[tuple[float, float, list[str]]]]:
    """Worst-case metrics over both sides and every ring phase."""
    worst = {
        "radial": 0.0,
        "min_d": 1e9,
        "max_d": -1e9,
        "clearance": 1e9,
        "front_frac": 1.0,
        "w_span": 1e9,
    }
    fails = []
    for sign_x in (-1.0, 1.0):
        base, axis, length, rb, rt = tusk_seat(ap, sign_x)
        for k in range(36):
            phase = 2.0 * math.pi * k / 36
            f = gate_tusk(ap, base, axis, length, rb, rt, phase)
            if f:
                fails.append((sign_x, round(phase, 3), f))
            verts = cone_verts(base, axis, length, rb, rt, phase)
            for p in verts:
                u, w, d = ap.aperture_coords(p)
                worst["radial"] = max(worst["radial"], ap.radial(u, w))
                worst["min_d"] = min(worst["min_d"], d)
                worst["max_d"] = max(worst["max_d"], d)
                wall = ap.depth * MG.bore_frac(ap.radial(u, w))
                worst["clearance"] = min(worst["clearance"], wall - d)
            ws = [ap.aperture_coords(p)[1] for p in verts]
            worst["w_span"] = min(worst["w_span"], max(ws) - min(ws))
    return worst, fails


# --- carve simulation ------------------------------------------------------


def meshed_head(
    rings: int, per_ring: int, **kw: float | int
) -> tuple[list[Vec], list[Face]]:
    """Synthetic head as a quad grid (ring-major, matching _synthetic_head)."""
    pts = list(MG._synthetic_head(rings=rings, per_ring=per_ring, **kw))
    n_rings = len(pts) // per_ring
    quads = []
    for i in range(n_rings - 1):
        for j in range(per_ring):
            quads.append(
                (
                    i * per_ring + j,
                    i * per_ring + (j + 1) % per_ring,
                    (i + 1) * per_ring + (j + 1) % per_ring,
                    (i + 1) * per_ring + j,
                )
            )
    return pts, quads


def unique_edges(faces: list[Face]) -> list[Edge]:
    seen = {}
    for f in faces:
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            seen[(min(a, b), max(a, b))] = True
    return list(seen)


def _dist(p: Vec, q: Vec) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q, strict=True)))


def region_edges(
    pts: list[Vec], faces: list[Face], ap: MG.MouthAperture
) -> tuple[list[Edge], float]:
    inside = [
        ap.radial(*ap.aperture_coords(p)[:2]) <= K["CAVITY_SUBDIV_REGION_R"]
        for p in pts
    ]
    picked = [e for e in unique_edges(faces) if inside[e[0]] or inside[e[1]]]
    mean = (
        sum(_dist(pts[a], pts[b]) for a, b in picked) / len(picked) if picked else 0.0
    )
    return picked, mean


def subdivide(
    pts: list[Vec], faces: list[Face], ap: MG.MouthAperture
) -> tuple[list[Vec], list[Face]]:
    """Midpoint-cut the region, grid-fill fully cut quads, fan the rest."""
    picked = set(region_edges(pts, faces, ap)[0])
    mid = {}
    for a, b in picked:
        mid[(a, b)] = len(pts)
        pts.append(tuple(0.5 * (pts[a][k] + pts[b][k]) for k in range(3)))
    out = []
    for f in faces:
        cuts = [
            mid.get((min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)])))
            for k in range(len(f))
        ]
        if all(c is None for c in cuts):
            out.append(f)
            continue
        if len(f) == 4 and all(c is not None for c in cuts):
            centre = len(pts)
            pts.append(tuple(sum(pts[i][k] for i in f) / 4.0 for k in range(3)))
            for k in range(4):
                out.append((f[k], cuts[k], centre, cuts[(k - 1) % 4]))
            continue
        ring = []
        for k in range(len(f)):
            ring.append(f[k])
            if cuts[k] is not None:
                ring.append(cuts[k])
        for k in range(1, len(ring) - 1):
            out.append((ring[0], ring[k], ring[k + 1]))
    return pts, out


def carve_metrics(
    ap: MG.MouthAperture, pts: list[Vec], faces: list[Face]
) -> tuple[dict[str, float], list[str]]:
    """Mirror of ``carve_orc_mouth_cavity``'s displacement and gates."""
    falloff = []
    disp = []
    for p in pts:
        u, w, d = ap.aperture_coords(p)
        f = ap.falloff(u, w)
        falloff.append(f)
        disp.append(max(0.0, ap.depth * f - d))
    carved = sum(1 for i in range(len(pts)) if falloff[i] > 0.0 and disp[i] > 0.0)
    deepest = max(
        (ap.depth * falloff[i] for i in range(len(pts)) if disp[i] > 0.0), default=0.0
    )
    painted = sum(
        1
        for f in faces
        if sum(falloff[j] for j in f) / len(f) >= K["CAVITY_INTERIOR_POLY_FALLOFF"]
    )
    moved = [(p[0], p[1] + disp[i], p[2]) for i, p in enumerate(pts)]
    worst_edge = 0.0
    for a, b in unique_edges(faces):
        if disp[a] > 0.0 or disp[b] > 0.0:
            worst_edge = max(worst_edge, _dist(moved[a], moved[b]))
    fails = []
    if carved < K["CAVITY_MIN_CARVED_VERTS"]:
        fails.append(f"carved {carved} < {int(K['CAVITY_MIN_CARVED_VERTS'])}")
    if deepest < K["CAVITY_MIN_ACHIEVED_DEPTH_FRAC"] * ap.depth:
        fails.append(f"deepest {deepest * 1000:.1f}mm too shallow")
    if painted <= 0:
        fails.append("no interior polygons, the maw would render as skin")
    return {
        "carved": carved,
        "deepest": deepest,
        "painted": painted,
        "worst_edge": worst_edge,
    }, fails


def run_head(
    name: str, rings: int, per_ring: int, **kw: float | int
) -> list[str]:
    pts, faces = meshed_head(rings, per_ring, **kw)
    ap = MG.solve_mouth_aperture(pts)
    start = len(pts)
    target = ap.half_width / K["CAVITY_SUBDIV_TARGET_SAMPLES"]
    budget = max(
        K["CAVITY_SUBDIV_MIN_BUDGET"], int(K["CAVITY_SUBDIV_MAX_ADDED_FRAC"] * start)
    )
    passes = 0
    for _ in range(int(K["CAVITY_SUBDIV_MAX_PASSES"])):
        picked, mean = region_edges(pts, faces, ap)
        if mean <= target or len(pts) - start + len(picked) > budget:
            break
        pts, faces = subdivide(pts, faces, ap)
        passes += 1
    carve, carve_fails = carve_metrics(ap, pts, faces)
    tusk, tusk_fails = tusk_metrics(ap)
    problems = [f"carve: {m}" for m in carve_fails]
    if tusk_fails:
        problems.append(
            f"tusk: {len(tusk_fails)} of 72 side/phase combos fail, e.g. {tusk_fails[0]}"
        )
    print(
        f"{'FAIL' if problems else 'ok  '} {name}: "
        f"maw {ap.half_width * 2000:.0f}x{ap.half_height * 2000:.0f}x"
        f"{ap.depth * 1000:.0f}mm  verts {start}->{len(pts)} (+{passes} subdiv)  "
        f"carved={carve['carved']} deepest={carve['deepest'] * 1000:.0f}mm "
        f"interior_polys={carve['painted']} bore_edge<={carve['worst_edge'] * 1000:.0f}mm  "
        f"tusk radial<={tusk['radial']:.2f} d=[{tusk['min_d'] * 1000:.1f},"
        f"{tusk['max_d'] * 1000:.1f}]mm wall_clear>={tusk['clearance'] * 1000:.1f}mm "
        f"len={K['TUSK_LENGTH_HH_FRAC'] * ap.half_height * 1000:.0f}mm"
    )
    for p in problems:
        print(f"       {p}")
    return problems


def main() -> int:
    print(f"constants read from {BAKE.name}; BORE_PLATEAU_R={MG.BORE_PLATEAU_R}")
    cases = (
        ("baseline", 64, 48, {}),
        ("narrow head", 64, 48, {"half_width": 0.066}),
        ("broad head", 64, 48, {"half_width": 0.088}),
        ("long face", 64, 48, {"chin_z": 1.532, "nose_z": 1.642, "mouth_z": 1.596}),
        ("short face", 64, 48, {"chin_z": 1.562, "nose_z": 1.628, "mouth_z": 1.603}),
        ("low-poly proxy", 26, 20, {}),
        ("coarse-ish", 34, 26, {}),
        ("dense", 96, 72, {}),
    )
    failed = []
    for name, rings, per_ring, kw in cases:
        if run_head(name, rings, per_ring, **kw):
            failed.append(name)
    if failed:
        print(f"\nSELFCHECK FAILED on {failed}")
        return 1
    print("\nSELFCHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
