# -*- coding: utf-8 -*-
"""Cut an exact elliptical rim loop into a mesh, so a carved maw has an edge.

Why this exists
---------------
``carve_orc_mouth_cavity`` displaces every vertex inside the aperture ellipse
back onto a bore profile, and paints a polygon dark when the mean falloff of its
vertices clears a threshold. Both of those decisions are taken per existing
element, so both boundaries -- where the geometry stops moving and where the
dark interior stops -- can only follow the mesh's own topology. On a face
sampled at ~6 mm that turns a smooth ellipse into a zig-zag of whole polygons,
which is the ragged, torn-looking rim in the 18:50 stills. Worse, the material
threshold (mean falloff >= 0.35) sits at normalised radius ~0.85 rather than at
the rim, so between 0.85 and 1.0 there is a ring of carved-back skin painted as
skin -- a recessed shelf that gives the maw a second, offset ragged edge.

The fix is to give the boundary its own geometry. Cut the mesh along the exact
radial == 1 contour first; afterwards no edge straddles the rim, so:

  * the vertices on the loop have falloff exactly 0 and are never displaced,
    which makes the carve's own boundary the exact ellipse;
  * every face is wholly inside or wholly outside, so "is this polygon the
    interior" becomes an exact test instead of a threshold on an average.

The cut point is solved rather than projected. ``radial == 1`` is an elliptical
cylinder and an edge is a straight segment, so the crossing is a root of a
quadratic; taking that root puts the new vertex exactly on the contour AND
exactly on the original edge. Projecting an interpolated point onto the ellipse
instead would pull it off the surface and leave a bump around the whole rim.

This module knows nothing about MakeHuman, orcs or ``MouthAperture``: it takes a
callable mapping a position to aperture coordinates. That is what lets it be
tested on synthetic meshes without the bake script -- see ``_selftest``.
"""
from __future__ import annotations

import math

import bmesh

# Mesh vertex coordinates are single precision, so a vertex cannot sit on the
# ellipse more precisely than the last bit of its own coordinates. That bound is
# scale-dependent in a way that matters here: a head is authored around
# z = 1.6 m, so the absolute placement error is ~1e-7 m, and dividing by a 16 mm
# half-height turns it into ~6e-6 of radial error -- roughly a hundred times what
# the same cut achieves on a test mesh centred on the origin. A fixed tolerance
# calibrated on the latter refuses every real head.
#
# So derive the tolerance from the coordinate magnitude and the ellipse size, and
# use the same number for "is this vertex already on the rim" and for "did the
# placement land where the solve said". The slack is bits of headroom over the
# bound; at 8 the tolerance on a MakeHuman head works out around 1e-4 of radial,
# which is 1.6 um of position on a 16 mm half-height -- geometrically nothing,
# while still an order of magnitude tighter than the nearest neighbouring vertex.
FLOAT32_EPS = 1.19209290e-07
RIM_PLACEMENT_SLACK_BITS = 8.0
# Floor for meshes authored near the origin, where the scale-derived bound goes
# to zero but the arithmetic still has to round somewhere.
RIM_MIN_RADIAL_TOL = 1e-7


class RimCutError(RuntimeError):
    """Raised when the contour cannot be cut as a single clean loop.

    Always carries the counts that failed. A ragged rim is a look bug; a
    half-cut rim is a broken mesh, so this refuses rather than carrying on.
    """


def radial_tolerance(
    coord_scale: float, half_width: float, half_height: float
) -> float:
    """Radial slop a single-precision vertex placement can actually achieve."""
    smallest = min(abs(half_width), abs(half_height))
    if smallest <= 0.0:
        raise RimCutError(
            f"degenerate rim ellipse half=({half_width}, {half_height})"
        )
    return max(
        RIM_MIN_RADIAL_TOL,
        RIM_PLACEMENT_SLACK_BITS * FLOAT32_EPS * abs(coord_scale) / smallest,
    )


def ellipse_crossing_fraction(
    ua: float, wa: float, ub: float, wb: float, half_width: float, half_height: float
) -> float:
    """Where the segment A->B crosses ``radial == 1``, as a fraction of A->B.

    Exact: substituting the parametrised segment into the ellipse equation gives
    a quadratic in ``t``, and with A strictly inside and B strictly outside
    exactly one root lies in ``[0, 1]``.
    """
    if half_width <= 0.0 or half_height <= 0.0:
        raise RimCutError(
            f"degenerate rim ellipse half=({half_width}, {half_height})"
        )
    b = ua / half_width
    e = wa / half_height
    a = (ub - ua) / half_width
    c = (wb - wa) / half_height
    qa = a * a + c * c
    if qa <= 0.0:
        raise RimCutError(
            f"edge has no extent in the rim plane (u={ua:.6f}->{ub:.6f}, "
            f"w={wa:.6f}->{wb:.6f}), so it cannot cross the contour"
        )
    qb = 2.0 * (a * b + c * e)
    qc = b * b + e * e - 1.0
    disc = qb * qb - 4.0 * qa * qc
    if disc < 0.0:
        raise RimCutError(
            f"no real crossing for an edge that straddles the contour "
            f"(disc={disc:.6e}, u={ua:.6f}->{ub:.6f}, w={wa:.6f}->{wb:.6f})"
        )
    root = math.sqrt(disc)
    for t in ((-qb + root) / (2.0 * qa), (-qb - root) / (2.0 * qa)):
        if 0.0 <= t <= 1.0:
            return t
    raise RimCutError(
        f"both crossings fall outside the edge (t={(-qb + root) / (2.0 * qa):.6f}, "
        f"{(-qb - root) / (2.0 * qa):.6f}); A was reported inside and B outside, so "
        f"the classification and the geometry disagree"
    )


def cut_rim_loop(
    bm: bmesh.types.BMesh,
    *,
    to_uwd,
    half_width: float,
    half_height: float,
    front_max_d: float,
) -> list:
    """Cut ``bm`` along ``radial == 1`` and return the new rim vertices.

    ``to_uwd(co) -> (u, w, d)`` maps a vertex position into aperture
    coordinates: ``u`` and ``w`` across the rim plane, ``d`` into the head.

    ``front_max_d`` keeps the cut on the front of the face. The rim ellipse is a
    cylinder along the view axis, so it meets a closed head in two loops -- the
    mouth and a matching ring on the back of the skull. Front verts near the
    mouth sit at ``d`` around zero while the back of the head is a whole head
    depth away, so a single threshold separates them cleanly.

    Returns ``(rim_vertices, stats)``. Afterwards every face is wholly inside or
    wholly outside the rim, and the returned vertices lie exactly on it.
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    coords = {v: to_uwd(v.co) for v in bm.verts}
    # Tolerance is a property of the mesh's coordinate magnitude, not a constant.
    # See radial_tolerance.
    coord_scale = max(
        (max(abs(c) for c in v.co) for v in bm.verts), default=1.0
    )
    tol = radial_tolerance(coord_scale, half_width, half_height)

    def radial(v) -> float:
        u, w, _d = coords[v]
        return math.hypot(u / half_width, w / half_height)

    def on_front(v) -> bool:
        return coords[v][2] < front_max_d

    # Vertices the mesh already puts on the contour, within the precision a
    # single-precision coordinate can express. Their edges must not be cut -- the
    # crossing is at the existing vertex, and cutting would make a zero-length
    # sliver -- but they ARE part of the rim, and must join the loop. Leaving
    # them out is what broke it: the faces around such a vertex hold one cut
    # vertex instead of two, connect_verts finds no pair, and the ring comes out
    # open at that point. Symmetric meshes make this likely rather than exotic;
    # the synthetic head lands four verts at radius 0.99994.
    already_on_rim = [
        v for v in bm.verts if on_front(v) and abs(radial(v) - 1.0) <= tol
    ]
    on_rim_set = set(already_on_rim)

    straddling = []
    for e in bm.edges:
        va, vb = e.verts
        if not (on_front(va) and on_front(vb)):
            continue
        if va in on_rim_set or vb in on_rim_set:
            continue
        ra, rb = radial(va), radial(vb)
        if (ra < 1.0) == (rb < 1.0):
            continue
        straddling.append((e, va, vb, ra))

    if not straddling and not already_on_rim:
        raise RimCutError(
            f"no edge crosses the rim ellipse half=({half_width:.4f}, "
            f"{half_height:.4f}) on the front sheet (d < {front_max_d:.4f}) — "
            f"the aperture is not on this mesh, or the mesh has no geometry there"
        )

    rim_verts = []
    for e, va, vb, ra in straddling:
        inner, outer = (va, vb) if ra < 1.0 else (vb, va)
        ui, wi, di = coords[inner]
        uo, wo, do = coords[outer]
        t = ellipse_crossing_fraction(ui, wi, uo, wo, half_width, half_height)
        # edge_split measures fac from the vertex it is given, so pass `inner`.
        _new_edge, new_vert = bmesh.utils.edge_split(e, inner, t)
        # Place it on the exact solved crossing rather than trusting the split's
        # own interpolation, which is the same lerp but recomputed from possibly
        # already-moved endpoints.
        new_vert.co = inner.co + (outer.co - inner.co) * t
        coords[new_vert] = (
            ui + (uo - ui) * t,
            wi + (wo - wi) * t,
            di + (do - di) * t,
        )
        rim_verts.append(new_vert)

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Every face the contour passes through now holds two rim verts -- cut ones,
    # already-on-rim ones, or one of each. Connecting them turns the scattered
    # points into a real edge loop, which is what makes the interior a closed
    # region rather than a set of polygons.
    #
    # More than two CUT verts in one face means the contour genuinely crosses
    # that polygon twice, which no amount of connecting can resolve into a single
    # rim. Already-on-rim verts are not counted here: two of them adjacent simply
    # means an existing edge runs along the contour, which is fine. The
    # authoritative validation either way is the closed-ring check below.
    cut_set = set(rim_verts)
    for f in bm.faces:
        hits = [v for v in f.verts if v in cut_set]
        if len(hits) > 2:
            raise RimCutError(
                f"face with {len(hits)} cut vertices at "
                f"{[tuple(round(c, 4) for c in v.co) for v in hits]} — the contour "
                f"re-enters the same polygon, so the mesh is too coarse here for a "
                f"single clean rim; subdivide the aperture region further"
            )
    loop_verts = rim_verts + already_on_rim
    bmesh.ops.connect_verts(bm, verts=loop_verts)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    stats = assert_rim_is_clean(
        bm, loop_verts, half_width, half_height, to_uwd, front_max_d, tol
    )
    return loop_verts, stats


def assert_rim_is_clean(
    bm, rim_verts: list, half_width, half_height, to_uwd, front_max_d, tol: float
) -> dict:
    """Check what the cut is actually for, not a proxy for it.

    The property the carve and the interior paint depend on is that **no polygon
    straddles the rim** -- every face wholly inside it or wholly outside. That is
    what makes the displacement boundary and the material boundary the ellipse
    rather than the topology.

    This used to assert instead that the rim was one simple closed ring, on the
    reasoning that an open rim means ``connect_verts`` missed a pair. On the real
    donor that reasoning is wrong twice over:

    * the glTF importer splits a mesh along its UV seams, so ``male_body``
      arrives with 1137 duplicate vertices and 2266 boundary edges and the
      surface is cut into patches. A contour crossing a seam cannot be one ring
      in that representation however correct the cut is;
    * MakeHuman's base mesh carries an inner mouth bag, a second sheet 20-35 mm
      behind the lip. The rim ellipse is a cylinder, so it cuts that too, and the
      chain there ends where the bag does. No depth threshold separates the two
      sheets: measured on the donor, verts near the rim contour run continuously
      from 0 to 50 mm deep, because a 71 mm wide aperture reaches out to where
      the face itself curves back as far as the bag is.

    The ring property is therefore unattainable, and it was never the thing that
    mattered. A missed ``connect_verts`` pair leaves a face with verts on both
    sides of the contour, so the straddling check above catches it; the degree
    count adds nothing the straddling check does not already prove. It is logged
    instead, so a regression still shows up as a number.
    """
    rim_set = set(rim_verts)
    worst_r = 0.0
    for v in rim_verts:
        u, w, _d = to_uwd(v.co)
        worst_r = max(worst_r, abs(math.hypot(u / half_width, w / half_height) - 1.0))
    if worst_r > tol:
        raise RimCutError(
            f"a cut vertex sits {worst_r:.3e} off the rim ellipse, more than the "
            f"{tol:.3e} a single-precision placement at this coordinate scale can "
            f"be held to; the crossing solve and the placement disagree"
        )

    straddling = []
    for f in bm.faces:
        radii = []
        for v in f.verts:
            u, w, d = to_uwd(v.co)
            if d >= front_max_d:
                radii = []
                break
            radii.append(math.hypot(u / half_width, w / half_height))
        if not radii:
            continue
        if min(radii) < 1.0 - tol and max(radii) > 1.0 + tol:
            straddling.append(f)
    if straddling:
        sample = [
            tuple(round(c, 4) for c in f.calc_center_median()) for f in straddling[:6]
        ]
        raise RimCutError(
            f"{len(straddling)} face(s) of {len(bm.faces)} still straddle the rim "
            f"after the cut, e.g. centred at {sample} — the displacement and the "
            f"interior paint would fall back to following the topology, which is "
            f"the ragged edge this cut exists to remove"
        )

    degree = {v: 0 for v in rim_verts}
    for e in bm.edges:
        va, vb = e.verts
        if va in rim_set and vb in rim_set:
            degree[va] += 1
            degree[vb] += 1
    ends = sum(1 for d in degree.values() if d < 2)
    branches = sum(1 for d in degree.values() if d > 2)
    return {
        "rim_verts": len(rim_verts),
        "chain_ends": ends,
        "branches": branches,
        "worst_radial_error": worst_r,
    }


def _selftest() -> int:
    """Cut the contour on synthetic surfaces and check the loop it produces.

    Runs headless under the ``bpy`` PyPI module as well as inside Blender: it
    only needs ``bmesh``.
    """
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    half_width, half_height = 0.031, 0.0163

    # A flat sheet in the rim plane, coarse enough that the polygon boundary and
    # the ellipse disagree badly -- which is the situation on the real face.
    #
    # ``lift`` puts the sheet at a realistic head height. That matters: mesh
    # coordinates are single precision, so a cut vertex 1.6 m from the origin
    # cannot sit on the ellipse to better than ~1e-7 m, which is ~6e-6 of radial
    # error on a 16 mm half-height. A tolerance calibrated on an origin-centred
    # sheet is a hundred times tighter than any real head can meet, and the first
    # version of this selftest passed at the origin while the same cut refused
    # every synthetic head in orc_carve_integration_check.
    for segs, lift, label in (
        (8, 0.0, "coarse grid at origin"),
        (14, 0.0, "medium grid at origin"),
        (24, 0.0, "fine grid at origin"),
        (18, 1.60, "grid at head height"),
    ):

        def to_uwd(co, lift=lift):
            return (float(co.x), float(co.z) - lift, float(co.y))

        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=segs, y_segments=segs, size=0.09)
        # create_grid lies in XY; rotate into the XZ rim plane.
        for v in bm.verts:
            v.co = (v.co.x, 0.0, v.co.y + lift)
        before_faces = len(bm.faces)
        try:
            rim, _stats = cut_rim_loop(
                bm,
                to_uwd=to_uwd,
                half_width=half_width,
                half_height=half_height,
                front_max_d=0.031,
            )
        except RimCutError as exc:
            check(f"{label} cuts a loop", False, f"refused: {exc}")
            bm.free()
            continue
        tol = radial_tolerance(
            max(max(abs(c) for c in v.co) for v in bm.verts),
            half_width,
            half_height,
        )

        def rad(v, lift=lift):
            u, w, _d = to_uwd(v.co, lift)
            return math.hypot(u / half_width, w / half_height)

        worst = max(abs(rad(v) - 1.0) for v in rim)
        # Perimeter of the cut ring, against Ramanujan's ellipse approximation.
        rim_set = set(rim)
        ring = [
            e for e in bm.edges if e.verts[0] in rim_set and e.verts[1] in rim_set
        ]
        perim = sum((e.verts[0].co - e.verts[1].co).length for e in ring)
        a, b = half_width, half_height
        h = ((a - b) / (a + b)) ** 2
        exact = math.pi * (a + b) * (1.0 + 3.0 * h / (10.0 + math.sqrt(4.0 - 3.0 * h)))
        check(
            f"{label} cuts a closed loop on the exact ellipse",
            worst <= tol and len(ring) == len(rim),
            f"{len(rim)} verts, {len(ring)} ring edges, faces "
            f"{before_faces}->{len(bm.faces)}, worst radial error {worst:.2e} "
            f"against a float32 bound of {tol:.2e}",
        )
        check(
            f"{label} ring perimeter matches the ellipse",
            perim <= exact * (1.0 + tol) and perim >= 0.80 * exact,
            f"inscribed perimeter {perim * 1000:.2f} mm vs ellipse "
            f"{exact * 1000:.2f} mm ({100.0 * perim / exact:.1f}%)",
        )
        # The whole point: no face may straddle the rim any more. Judged with the
        # same float32 bound, because a cut vertex lands on the contour only to
        # within that, and a tighter test would read it as inside and report
        # every outside face that merely touches the loop.
        straddlers = 0
        for f in bm.faces:
            rs = [rad(v) for v in f.verts]
            if min(rs) < 1.0 - tol and max(rs) > 1.0 + tol:
                straddlers += 1
        check(
            f"{label} leaves no face straddling the rim",
            straddlers == 0,
            f"{straddlers} straddling face(s) of {len(bm.faces)}",
        )
        bm.free()

    def to_uwd(co):
        return (float(co.x), float(co.z), float(co.y))

    # A curved sheet, so the cut has to hold on a surface that is not planar.
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=18, y_segments=18, size=0.09)
    for v in bm.verts:
        x, z = float(v.co.x), float(v.co.y)
        v.co = (x, 0.35 * (x * x + z * z), z)  # bulges away from the camera
    try:
        rim, _stats = cut_rim_loop(
            bm,
            to_uwd=to_uwd,
            half_width=half_width,
            half_height=half_height,
            front_max_d=0.031,
        )
        worst = max(
            abs(math.hypot(v.co.x / half_width, v.co.z / half_height) - 1.0)
            for v in rim
        )
        tol = radial_tolerance(
            max(max(abs(c) for c in v.co) for v in bm.verts),
            half_width,
            half_height,
        )
        # Each cut vertex must still lie on the segment it was cut from, i.e. on
        # the original surface. Check it against the analytic bulge.
        off = max(abs(v.co.y - 0.35 * (v.co.x**2 + v.co.z**2)) for v in rim)
        check(
            "curved sheet keeps cut verts on the ellipse and on the surface",
            worst <= tol and off <= 2.0e-4,
            f"{len(rim)} verts, worst radial error {worst:.2e} (bound "
            f"{tol:.2e}), worst deviation from the surface {off * 1000:.3f} mm "
            f"(chord vs arc, not a bump)",
        )
    except RimCutError as exc:
        check("curved sheet keeps cut verts on the ellipse", False, f"refused: {exc}")
    bm.free()

    # Two parallel sheets, only one of them on the front: the back of the skull
    # must be left alone.
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=16, y_segments=16, size=0.09)
    for v in bm.verts:
        v.co = (v.co.x, 0.0, v.co.y)
    back = bmesh.new()
    bmesh.ops.create_grid(back, x_segments=16, y_segments=16, size=0.09)
    for v in back.verts:
        v.co = (v.co.x, 0.20, v.co.y)
    tmp = bmesh.new()
    for src in (bm, back):
        me_verts = [tmp.verts.new(v.co) for v in src.verts]
        tmp.verts.index_update()
        idx = {v: i for i, v in enumerate(src.verts)}
        for f in src.faces:
            tmp.faces.new([me_verts[idx[v]] for v in f.verts])
    bm.free()
    back.free()
    tmp.verts.ensure_lookup_table()
    try:
        rim, _stats = cut_rim_loop(
            tmp,
            to_uwd=to_uwd,
            half_width=half_width,
            half_height=half_height,
            front_max_d=0.031,
        )
        touched_back = [v for v in rim if v.co.y > 0.10]
        check(
            "front sheet only: the back of the skull is not cut",
            not touched_back,
            f"{len(rim)} cut verts, {len(touched_back)} of them on the back sheet",
        )
    except RimCutError as exc:
        check("front sheet only", False, f"refused: {exc}")
    tmp.free()

    # A mesh so coarse the contour crosses one quad twice must be refused, not
    # silently half-cut.
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.09)
    for v in bm.verts:
        v.co = (v.co.x, 0.0, v.co.y)
    try:
        cut_rim_loop(
            bm,
            to_uwd=to_uwd,
            half_width=half_width,
            half_height=half_height,
            front_max_d=0.031,
        )
        check(
            "refuses a mesh too coarse to hold the contour",
            False,
            "accepted a single-quad sheet",
        )
    except RimCutError as exc:
        check("refuses a mesh too coarse to hold the contour", True, str(exc)[:110])
    bm.free()

    if failures:
        print(f"\nRIM SELFTEST FAILED: {failures}")
        return 1
    print("\nRIM SELFTEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
