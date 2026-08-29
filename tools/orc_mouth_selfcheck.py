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
    "TUSK_ROOT_BURY_HEAD_W_FRAC",
    "TUSK_AXIS_SPLAY",
    "TUSK_AXIS_OUTWARD",
    "TUSK_LENGTH_HEAD_W_FRAC",
    "TUSK_RADIUS_BASE_HEAD_W_FRAC",
    "TUSK_RADIUS_TIP_HEAD_W_FRAC",
    "TUSK_SEGMENTS",
    "TUSK_APERTURE_MARGIN",
    "TUSK_FRONT_D_FRAC",
    "TUSK_MIN_FRONT_FRAC",
    "TUSK_MIN_W_SPAN_HH_FRAC",
    "TUSK_MIN_AXIS_RISE_DOT",
    "TUSK_BURIED_MAX_RADIAL",
    "TUSK_BASE_MAX_RADIAL",
    "TUSK_RIM_CROSS_MAX_D",
    "TUSK_MIN_PROTRUSION_M",
    "TUSK_MAX_PROTRUSION_M",
    "TUSK_ROOT_MIN_BURY_M",
    "TUSK_EMERGENT_CLEARANCE_M",
    "TUSK_MIN_EMERGENT_M",
    "TUSK_EMERGENT_SAMPLES",
    "CAVITY_MIN_ACHIEVED_DEPTH_FRAC",
    "CAVITY_MIN_CARVED_VERTS",
    "CAVITY_INTERIOR_RADIAL_EPS",
    "MOUTH_LIP_ROLL_M",
    "MOUTH_LIP_ROLL_BAND",
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
    """Mirror of ``tusk_seat_in_body_space``.

    The base is placed BEHIND the cavity wall at its own (u, w): that is what
    roots the tusk in the gum. e99b3a1 placed it at a fixed fraction of the
    nominal depth, which left it floating 22 mm in front of the gum surface.
    """
    hw, hh, wid = ap.half_width, ap.half_height, ap.head_width
    u0 = sign_x * K["TUSK_SEAT_U_FRAC"] * hw
    w0 = K["TUSK_SEAT_W_FRAC"] * hh
    d0 = ap.bore_depth(u0, w0) + K["TUSK_ROOT_BURY_HEAD_W_FRAC"] * wid
    base = (ap.center_x + u0, ap.center_y + d0, ap.center_z + w0)
    axis = _norm((sign_x * K["TUSK_AXIS_SPLAY"], -K["TUSK_AXIS_OUTWARD"], 1.0))
    return (
        base,
        axis,
        K["TUSK_LENGTH_HEAD_W_FRAC"] * wid,
        K["TUSK_RADIUS_BASE_HEAD_W_FRAC"] * wid,
        K["TUSK_RADIUS_TIP_HEAD_W_FRAC"] * wid,
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
) -> tuple[list[str], dict[str, float]]:
    """Every check from ``assert_tusks_in_mouth_for_current_pose``."""
    verts = cone_verts(base, axis, length, r_base, r_tip, phase)
    margin = K["TUSK_APERTURE_MARGIN"]
    worst_buried_radial = 0.0
    min_d, max_d = 1e9, -1e9
    w_lo, w_hi = 1e9, -1e9
    front = 0
    front_limit = K["TUSK_FRONT_D_FRAC"] * ap.depth
    for p in verts:
        u, w, d = ap.aperture_coords(p)
        # Containment applies to buried geometry only. Ivory in open air is
        # allowed to be wherever the silhouette wants it.
        if d >= ap.bore_depth(u, w) - K["TUSK_EMERGENT_CLEARANCE_M"]:
            worst_buried_radial = max(
                worst_buried_radial,
                math.hypot(
                    u / (ap.half_width + margin), w / (ap.half_height + margin)
                ),
            )
        min_d, max_d = min(min_d, d), max(max_d, d)
        w_lo, w_hi = min(w_lo, w), max(w_hi, w)
        if d <= front_limit:
            front += 1
    front_frac = front / float(len(verts))

    # Rooting, emergence, rim crossing and protrusion: mirrors
    # tusk_centreline_metrics.
    bu, bw, bd = ap.aperture_coords(base)
    root_bury = bd - ap.bore_depth(bu, bw)
    base_radial = ap.radial(bu, bw)
    samples = int(K["TUSK_EMERGENT_SAMPLES"])
    step = length / samples
    emergent = 0.0
    for i in range(samples):
        q = _add(base, _mul(axis, (i + 0.5) * step))
        qu, qw, qd = ap.aperture_coords(q)
        if qd < ap.bore_depth(qu, qw) - K["TUSK_EMERGENT_CLEARANCE_M"]:
            emergent += step
    # None means the centre line never leaves the rim footprint, which is not a
    # failure -- see tusk_centreline_metrics.
    rim_cross_d: float | None = None
    prev_r = base_radial
    for i in range(1, samples + 1):
        q = _add(base, _mul(axis, i * step))
        qu, qw, _qd = ap.aperture_coords(q)
        r = ap.radial(qu, qw)
        if prev_r <= 1.0 < r:
            t = (1.0 - prev_r) / (r - prev_r)
            s_cross = (i - 1) * step + t * step
            rim_cross_d = ap.aperture_coords(_add(base, _mul(axis, s_cross)))[2]
            break
        prev_r = r
    tip_protrusion = -ap.aperture_coords(_add(base, _mul(axis, length)))[2]

    fails = []
    if worst_buried_radial > K["TUSK_BURIED_MAX_RADIAL"]:
        fails.append(
            f"buried_radial={worst_buried_radial:.3f} > "
            f"{K['TUSK_BURIED_MAX_RADIAL']} (root under the cheekbone)"
        )
    if base_radial > K["TUSK_BASE_MAX_RADIAL"]:
        fails.append(
            f"base_radial={base_radial:.3f} > {K['TUSK_BASE_MAX_RADIAL']} "
            f"(rooted beside the opening, not inside it)"
        )
    if rim_cross_d is not None and rim_cross_d > K["TUSK_RIM_CROSS_MAX_D"]:
        fails.append(
            f"rim_cross_d={rim_cross_d * 1000:.1f}mm behind the lip plane at the "
            f"rim — the shaft passes through the lip"
        )
    if tip_protrusion < K["TUSK_MIN_PROTRUSION_M"]:
        fails.append(
            f"protrusion={tip_protrusion * 1000:.1f}mm — the tip never crosses "
            f"the lip plane, so it cannot break the silhouette"
        )
    if tip_protrusion > K["TUSK_MAX_PROTRUSION_M"]:
        fails.append(f"protrusion={tip_protrusion * 1000:.1f}mm — sabre, not tusk")
    if max_d > ap.depth + margin:
        fails.append(f"max_d={max_d * 1000:.1f}mm through the cavity floor")
    if root_bury < K["TUSK_ROOT_MIN_BURY_M"]:
        fails.append(f"root_bury={root_bury * 1000:.1f}mm — not rooted in the gum")
    if emergent < K["TUSK_MIN_EMERGENT_M"]:
        fails.append(f"emergent={emergent * 1000:.1f}mm of ivory in open air")
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
    metrics = {
        "buried_radial": worst_buried_radial,
        "base_radial": base_radial,
        "rim_cross_d": rim_cross_d,
        "protrusion": tip_protrusion,
        "min_d": min_d,
        "max_d": max_d,
        "root_bury": root_bury,
        "emergent": emergent,
        "w_span": w_hi - w_lo,
        "tip_w_frac": ap.aperture_coords(_add(base, _mul(axis, length)))[1]
        / ap.half_height,
    }
    return fails, metrics


def tusk_metrics(
    ap: MG.MouthAperture,
) -> tuple[dict[str, float], list[tuple[float, float, list[str]]]]:
    """Worst-case metrics over both sides and every ring phase."""
    worst = {
        "buried_radial": 0.0,
        "base_radial": 0.0,
        "rim_cross_d": -1e9,
        "protrusion": 1e9,
        "min_d": 1e9,
        "max_d": -1e9,
        "root_bury": 1e9,
        "emergent": 1e9,
        "w_span": 1e9,
        "tip_w_frac": 0.0,
    }
    fails = []
    for sign_x in (-1.0, 1.0):
        base, axis, length, rb, rt = tusk_seat(ap, sign_x)
        for k in range(36):
            phase = 2.0 * math.pi * k / 36
            f, m = gate_tusk(ap, base, axis, length, rb, rt, phase)
            if f:
                fails.append((sign_x, round(phase, 3), f))
            worst["buried_radial"] = max(worst["buried_radial"], m["buried_radial"])
            worst["base_radial"] = max(worst["base_radial"], m["base_radial"])
            if m["rim_cross_d"] is not None:
                worst["rim_cross_d"] = max(
                    worst["rim_cross_d"], m["rim_cross_d"]
                )
            worst["protrusion"] = min(worst["protrusion"], m["protrusion"])
            worst["min_d"] = min(worst["min_d"], m["min_d"])
            worst["max_d"] = max(worst["max_d"], m["max_d"])
            worst["root_bury"] = min(worst["root_bury"], m["root_bury"])
            worst["emergent"] = min(worst["emergent"], m["emergent"])
            worst["w_span"] = min(worst["w_span"], m["w_span"])
            worst["tip_w_frac"] = m["tip_w_frac"]
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
    # Front sheet only, mirroring aperture_region_edge_stats: rim radius is a
    # cylinder, so a radius test alone also picks up the back of the skull.
    inside = [
        ap.aperture_coords(p)[2] < 2.0 * ap.depth
        and ap.radial(*ap.aperture_coords(p)[:2]) <= K["CAVITY_SUBDIV_REGION_R"]
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
    """Mirror of ``carve_orc_mouth_cavity``'s displacement, paint and gates.

    ``rim_jaggedness`` is the point of the rim cut, so it is measured here: how
    far the painted interior boundary wanders from the rim ellipse. Before the
    cut that distance is a whole polygon; after it, zero by construction. This
    harness does not replay the cut itself (that needs bmesh and is tested in
    ``orc_mouth_rim._selftest``), so the number it reports is the *uncut* case --
    the baseline the cut has to beat.
    """
    falloff = []
    disp = []
    inside = []
    front = []
    for p in pts:
        u, w, d = ap.aperture_coords(p)
        f = ap.falloff(u, w)
        falloff.append(f)
        disp.append(max(0.0, ap.depth * f - d))
        inside.append(ap.radial(u, w) <= 1.0 + K["CAVITY_INTERIOR_RADIAL_EPS"])
        front.append(d < ap.depth)
    carved = sum(1 for i in range(len(pts)) if falloff[i] > 0.0 and disp[i] > 0.0)
    deepest = max(
        (ap.depth * falloff[i] for i in range(len(pts)) if disp[i] > 0.0), default=0.0
    )
    # The exact test the bake now uses: every vert inside the rim and on the
    # front sheet.
    painted = sum(1 for f in faces if all(inside[j] and front[j] for j in f))
    # How ragged the boundary is without a cut: the worst distance from the rim
    # ellipse of any vert on a polygon that straddles it.
    jag = 0.0
    for f in faces:
        rs = [ap.radial(*ap.aperture_coords(pts[j])[:2]) for j in f]
        if not all(front[j] for j in f):
            continue
        if min(rs) < 1.0 and max(rs) > 1.0:
            for j, r in zip(f, rs, strict=True):
                u, w, _d = ap.aperture_coords(pts[j])
                scale = 0.0 if r <= 0.0 else 1.0 / r
                jag = max(jag, math.hypot(u - u * scale, w - w * scale))
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
        "rim_jaggedness": jag,
    }, fails


def run_head(
    name: str,
    rings: int,
    per_ring: int,
    *,
    expect_refusal: bool = False,
    **kw: float | int,
) -> list[str]:
    pts, faces = meshed_head(rings, per_ring, **kw)
    try:
        ap = MG.solve_mouth_aperture(pts)
    except MG.MouthGeometryError as exc:
        if expect_refusal:
            print(f"ok   {name}: refused as expected — {str(exc)[:120]}")
            return []
        print(f"FAIL {name}: solver refused this head")
        print(f"       {exc}")
        return [f"{name}: solver refused"]
    if expect_refusal:
        print(
            f"FAIL {name}: solver accepted a head it should refuse "
            f"({ap.describe()})"
        )
        return [f"{name}: expected a refusal"]
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
        f"interior_polys={carve['painted']} bore_edge<={carve['worst_edge'] * 1000:.0f}mm "
        f"uncut_rim_jag={carve['rim_jaggedness'] * 1000:.1f}mm  "
        f"tusk buried_r<={tusk['buried_radial']:.2f} "
        f"base_r<={tusk['base_radial']:.2f} "
        f"rim_cross_d<="
        + (
            "none"
            if tusk["rim_cross_d"] <= -1e8
            else f"{tusk['rim_cross_d'] * 1000:.1f}mm"
        )
        + "  "
        f"protrude>={tusk['protrusion'] * 1000:.1f}mm "
        f"root_bury>={tusk['root_bury'] * 1000:.1f}mm "
        f"emergent>={tusk['emergent'] * 1000:.1f}mm "
        f"tip_w={tusk['tip_w_frac']:+.2f}hh "
        f"len={K['TUSK_LENGTH_HEAD_W_FRAC'] * ap.head_width * 1000:.0f}mm"
    )
    for p in problems:
        print(f"       {p}")
    return problems


def legacy_seat_e99b3a1(
    ap: MG.MouthAperture, sign_x: float
) -> tuple[Vec, Vec, float, float, float]:
    """The seat e99b3a1 shipped: base at a fixed fraction of the NOMINAL depth.

    Kept so the fix cannot silently regress. The Walk still of that bake read
    the tusks as cones painted on the lower lip, and these numbers say why: the
    base landed 22 mm in front of the gum surface (rooted in nothing) and the
    front vertex reached 2 mm behind the lip plane (so a three-quarter
    silhouette passed the lip contour).
    """
    hw, hh, dp = ap.half_width, ap.half_height, ap.depth
    base = (
        ap.center_x + sign_x * 0.38 * hw,
        ap.center_y + 0.24 * dp,
        ap.center_z - 0.55 * hh,
    )
    axis = _norm((-sign_x * 0.18, -0.15, 1.0))
    return base, axis, 1.30 * hh, 0.28 * hh, 0.08 * hh


def check_legacy_seat_refused() -> list[str]:
    """The previous seat must fail the rooting and inset checks."""
    ap = MG.solve_mouth_aperture(MG._synthetic_head())
    base, axis, length, rb, rt = legacy_seat_e99b3a1(ap, 1.0)
    fails, m = gate_tusk(ap, base, axis, length, rb, rt, 0.0)
    print(
        f"e99b3a1 seat under the new gate: inset={m['min_d'] * 1000:.1f}mm "
        f"root_bury={m['root_bury'] * 1000:.1f}mm "
        f"emergent={m['emergent'] * 1000:.1f}mm "
        f"buried_radial={m['buried_radial']:.2f}"
    )
    problems = []
    if not any("root_bury" in f for f in fails):
        problems.append("the new gate does not catch the unrooted base")
    for f in fails:
        print(f"  refused: {f}")
    if problems:
        for p in problems:
            print(f"[FAIL] legacy seat regression: {p}")
    else:
        print(
            "[ok  ] legacy seat regression: the e99b3a1 seat is refused for its "
            "unrooted base"
        )
    return problems


def check_recessed_tusk_refused() -> list[str]:
    """The 18:50 seat must fail the protrusion gate.

    That bake seated the tusks at 0.40 of the half-width with only 0.22 of
    forward lean, which the old gate not merely permitted but REQUIRED: it
    refused any vertex within 4 mm of the lip plane. The tip came out ~13 mm
    behind the lip, so the ivory could never break the face silhouette and was
    visible only down a maw aimed at the camera. Replay it so the fix cannot
    silently regress into a recessed tusk again.
    """
    ap = MG.solve_mouth_aperture(MG._synthetic_head())
    hw, hh, wid = ap.half_width, ap.half_height, ap.head_width
    u0 = 0.40 * hw
    w0 = -0.72 * hh
    d0 = ap.bore_depth(u0, w0) + 0.25 * hh
    base = (ap.center_x + u0, ap.center_y + d0, ap.center_z + w0)
    axis = _norm((0.26, -0.22, 1.0))
    fails, m = gate_tusk(ap, base, axis, 1.35 * hh, 0.32 * hh, 0.08 * hh, 0.0)
    print(
        f"18:50 seat under the new gate: protrusion={m['protrusion'] * 1000:.1f}mm "
        f"base_radial={m['base_radial']:.2f} "
        f"emergent={m['emergent'] * 1000:.1f}mm (head_width={wid * 1000:.0f}mm)"
    )
    problems = []
    if not any("protrusion" in f for f in fails):
        problems.append("the new gate accepts a tusk that never crosses the lip")
    for f in fails:
        print(f"  refused: {f}")
    if problems:
        for p in problems:
            print(f"[FAIL] recessed tusk regression: {p}")
    else:
        print(
            "[ok  ] recessed tusk regression: the 18:50 seat is refused for "
            "never crossing the lip plane"
        )
    return problems


def main() -> int:
    print(f"constants read from {BAKE.name}; BORE_PLATEAU_R={MG.BORE_PLATEAU_R}")
    # ``expect_refusal`` heads are too coarse between the mouth and the nostrils
    # to locate a nose base, so the solver refuses rather than gating the
    # aperture top rim against the lip itself. See MG.MIN_UPPER_LIP_FRAC.
    cases = (
        ("baseline", 64, 48, {}),
        ("narrow head", 64, 48, {"half_width": 0.066}),
        ("broad head", 64, 48, {"half_width": 0.088}),
        ("long face", 64, 48, {"chin_z": 1.532, "nose_z": 1.642, "mouth_z": 1.596}),
        ("short face", 64, 48, {"chin_z": 1.562, "nose_z": 1.628, "mouth_z": 1.603}),
        ("receding chin", 64, 48, {"chin_front_y": -0.072}),
        ("jutting chin", 64, 48, {"chin_front_y": -0.098}),
        # Both of these sample the region between lip and nostrils at 8-11 mm,
        # which on a ring-topology head is 3-4 distinct heights with no philtrum
        # recess among them. The solver refuses rather than gating the aperture
        # top rim against a landmark that is not in the data. The real donor
        # resolves 708 midline verts there, so this only bites on proxies.
        ("low-poly proxy", 26, 20, {"expect_refusal": True}),
        ("coarse-ish", 34, 26, {"expect_refusal": True}),
        ("dense", 96, 72, {}),
        # The real donor's proportions, measured off assets/humans/male_base.glb.
        # Without these the sweep is variations on a head the bake never sees:
        # the real skull cloud is 176 mm wide with a 61 mm face where the default
        # fixture is 155 mm wide with an 87 mm face, so everything sized off head
        # width comes out a third larger on a face with a third less room.
        ("makehuman male_base", 64, 48, dict(MG.MAKEHUMAN_MALE_BASE)),
        ("makehuman male_base dense", 96, 72, dict(MG.MAKEHUMAN_MALE_BASE)),
    )
    failed = []
    for name, rings, per_ring, kw in cases:
        if run_head(name, rings, per_ring, **kw):
            failed.append(name)
    print()
    if check_legacy_seat_refused():
        failed.append("legacy seat regression")
    print()
    if check_recessed_tusk_refused():
        failed.append("recessed tusk regression")
    if failed:
        print(f"\nSELFCHECK FAILED on {failed}")
        return 1
    print("\nSELFCHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
