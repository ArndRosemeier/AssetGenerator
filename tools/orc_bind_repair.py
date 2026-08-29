# -*- coding: utf-8 -*-
"""Pure skin-weight repair for torn bind seams. No bpy, no Blender.

``bake_human_orc`` gathers vertex weights and adjacency, hands them here, and
writes the result back. Everything in this module is plain Python so the
algorithm can be tested without Blender -- which matters because the failure it
fixes only shows up under a pose, and the bake that reveals it runs on another
machine.

The defect
----------
``Punch:Punch_Cross@13 stretched male_body torso edge 0.2129 verts=(1876, 1891)
spine=(1.00, 0.00) head=(0.00, 0.00)``.

Two adjacent verts driven by disjoint bones separate by whatever those bones
do. Linear blend skinning puts vert ``i`` at ``sum_b w[i][b] * M_b * rest[i]``,
so for neighbours with nearly equal rest positions the posed edge length is
driven by ``sum_b |w[a][b] - w[b][b]|``: a weight cliff *is* a tear, and no
amount of moving rest positions changes it. Earlier passes tried to flatten or
skip restyle on that vertex pair, and the measured length did not budge --
0.2129 on b4d8e69 and again on af0e428, restyles sharing almost no torso code.

The repair
----------
Spread the cliff over several vertex rings so no single edge carries the whole
weight difference. Dilate the torn verts by ``rings``, hold the outer ring
fixed, and run Jacobi Laplacian smoothing on the interior. A transition spread
over ``k`` edges carries about ``1/k`` of the weight difference per edge, so the
worst posed edge drops by roughly the same factor.

Two properties make this safe to apply without being able to look at the result:

* **No new extremes.** Each updated weight set is a convex combination of the
  vert's own weights and its neighbours', so every vert's posed position stays
  inside the convex hull of what its neighbourhood already produced. Smoothing
  cannot invent a spike.
* **Monotone.** Jacobi smoothing with ``0 < lam <= 1`` is non-expansive on the
  weight field, so the maximum neighbour weight difference never increases.

Run ``python tools/orc_bind_repair.py`` for the self-test.
"""
from __future__ import annotations

WeightMap = dict[int, float]
Adjacency = list[list[int]]

# Weights below this are dropped rather than carried as noise.
WEIGHT_PRUNE = 1e-4


class BindRepairError(RuntimeError):
    """Raised when a bind cannot be repaired without inventing influence."""


def normalise_weights(acc: WeightMap, *, prune: float = WEIGHT_PRUNE) -> WeightMap:
    """Prune noise and rescale to sum 1. Empty in, empty out."""
    pruned = {gi: w for gi, w in acc.items() if w > prune}
    total = sum(pruned.values())
    if total <= 0.0:
        return {}
    return {gi: w / total for gi, w in pruned.items()}


def dilate(adjacency: Adjacency, seed: set[int], rings: int) -> set[int]:
    """Grow ``seed`` outward by ``rings`` edge steps."""
    if rings < 0:
        raise ValueError(f"dilate needs rings >= 0, got {rings}")
    region = set(int(i) for i in seed)
    for _ring in range(rings):
        region |= {j for i in region for j in adjacency[i]}
    return region


def interior_of(adjacency: Adjacency, region: set[int]) -> set[int]:
    """Verts of ``region`` whose whole neighbourhood is also in ``region``.

    The complement is the boundary ring, which is held fixed so smoothing
    cannot leak influence across the rest of the body.
    """
    return {i for i in region if all(j in region for j in adjacency[i])}


def smooth_weights_jacobi(
    adjacency: Adjacency,
    weights: list[WeightMap],
    interior: set[int],
    *,
    lam: float,
    iterations: int,
    prune: float = WEIGHT_PRUNE,
) -> dict[int, WeightMap]:
    """Laplacian-smooth ``weights`` on ``interior``, boundary held fixed.

    Jacobi rather than Gauss-Seidel: every vert in a pass reads the previous
    pass's weights, so the result does not depend on iteration order. Returns
    only the verts that changed.
    """
    if not 0.0 < lam <= 1.0:
        raise ValueError(f"smooth_weights_jacobi needs 0 < lam <= 1, got {lam}")
    if iterations < 1:
        raise ValueError(f"smooth_weights_jacobi needs iterations >= 1, got {iterations}")
    cur = list(weights)
    order = sorted(interior)
    for _it in range(iterations):
        updates: dict[int, WeightMap] = {}
        for i in order:
            neighbours = adjacency[i]
            if not neighbours:
                continue
            acc: WeightMap = {}
            for gi, w in cur[i].items():
                acc[gi] = acc.get(gi, 0.0) + (1.0 - lam) * w
            share = lam / float(len(neighbours))
            for j in neighbours:
                for gi, w in cur[j].items():
                    acc[gi] = acc.get(gi, 0.0) + share * w
            blended = normalise_weights(acc, prune=prune)
            if blended:
                updates[i] = blended
        for i, w in updates.items():
            cur[i] = w
    return {i: cur[i] for i in order}


def rehome_from_neighbours(
    adjacency: Adjacency,
    weights: list[WeightMap],
    unbound: set[int],
    *,
    max_passes: int,
) -> dict[int, WeightMap]:
    """Give unbound verts the average of their bound neighbours' weights.

    Averaging over *all* bound neighbours is the point. 0240d6e copied a single
    source vert's groups onto its partner and dragged clavicle verts onto the
    chest, which is how Idle came to read as a neck pinched off the shoulders.

    Raises if an island has no bound neighbour anywhere: there is nothing to
    average and inventing a bone would be a guess.
    """
    cur = list(weights)
    pending = set(int(i) for i in unbound)
    fixed: dict[int, WeightMap] = {}
    for _step in range(max_passes):
        just_fixed = []
        for i in sorted(pending):
            acc: WeightMap = {}
            donors = 0
            for j in adjacency[i]:
                if j in pending:
                    continue
                for gi, w in cur[j].items():
                    acc[gi] = acc.get(gi, 0.0) + w
                donors += 1
            if donors == 0:
                continue
            blended = normalise_weights(acc)
            if not blended:
                continue
            cur[i] = blended
            fixed[i] = blended
            just_fixed.append(i)
        for i in just_fixed:
            pending.discard(i)
        if not just_fixed or not pending:
            break
    if pending:
        raise BindRepairError(
            f"{len(pending)} vert(s) have no bound neighbour anywhere "
            f"({sorted(pending)[:12]}) — an unbound island; refusing to invent "
            f"a bone for it"
        )
    return fixed


# --------------------------------------------------------------------------
# Self-test: linear blend skinning on synthetic seams, ground truth known.
# --------------------------------------------------------------------------


def _chain(n: int) -> Adjacency:
    return [[j for j in (i - 1, i + 1) if 0 <= j < n] for i in range(n)]


def _grid(w: int, h: int) -> tuple[Adjacency, list[tuple[int, int]]]:
    adj: Adjacency = [[] for _ in range(w * h)]
    coords = []
    for y in range(h):
        for x in range(w):
            coords.append((x, y))
            i = y * w + x
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    adj[i].append(ny * w + nx)
    return adj, coords


def _posed_edge_lengths(
    adjacency: Adjacency,
    weights: list[WeightMap],
    rest: list[tuple[float, float]],
    bone_offset: dict[int, tuple[float, float]],
) -> float:
    """Worst posed edge under linear blend skinning with pure-translation bones."""
    posed = []
    for i, w in enumerate(weights):
        px, py = rest[i]
        for gi, ww in w.items():
            ox, oy = bone_offset[gi]
            px += ww * ox
            py += ww * oy
        posed.append((px, py))
    worst = 0.0
    for i, neighbours in enumerate(adjacency):
        for j in neighbours:
            if j <= i:
                continue
            d = ((posed[i][0] - posed[j][0]) ** 2 + (posed[i][1] - posed[j][1]) ** 2) ** 0.5
            worst = max(worst, d)
    return worst


P, Q = 0, 1
# Punch_Cross throws the shoulder ~21 cm away from the sternum. That separation
# is the measured 0.2129 the gate refused.
# Offset perpendicular to the vertex spacing: the punch swings the shoulder
# across the body, not along the row of verts, so the torn edge measures
# sqrt(spacing^2 + separation^2) rather than spacing + separation.
BONES = {P: (0.0, 0.0), Q: (0.0, 0.2129)}
SPACING = 0.010  # 1 cm vertex spacing, typical for this mesh in the chest


def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    # --- 1-D seam: a chain of verts, half on each bone, no blend anywhere.
    n = 41
    adj = _chain(n)
    rest = [(i * SPACING, 0.0) for i in range(n)]
    seam = n // 2
    weights = [{P: 1.0} if i < seam else {Q: 1.0} for i in range(n)]
    before = _posed_edge_lengths(adj, weights, rest, BONES)
    check(
        "1-D seam tears before repair",
        abs(before - 0.2129) < 5e-4,
        f"worst posed edge {before:.4f} (bone separation {BONES[Q][1]:.4f}, "
        f"the length the Punch gate refused)",
    )

    print("\n  rings/iterations sweep (target 0.12, gate 0.14):")
    for rings, iterations in ((1, 10), (2, 10), (3, 16), (4, 24)):
        w = [dict(x) for x in weights]
        region = dilate(adj, {seam - 1, seam}, rings)
        interior = interior_of(adj, region)
        updates = smooth_weights_jacobi(
            adj, w, interior, lam=0.5, iterations=iterations
        )
        for i, nw in updates.items():
            w[i] = nw
        after = _posed_edge_lengths(adj, w, rest, BONES)
        print(
            f"    rings={rings} iters={iterations}: region={len(region)} "
            f"interior={len(interior)} worst={after:.4f} "
            f"({before / max(after, 1e-9):.1f}x shorter)"
        )
        if (rings, iterations) == (2, 10):
            check(
                "2 rings / 10 iterations clears the 0.12 repair target",
                after <= 0.12,
                f"worst posed edge {after:.4f} <= 0.12",
            )
        if (rings, iterations) == (4, 24):
            check(
                "4 rings / 24 iterations leaves a wide margin",
                after <= 0.07,
                f"worst posed edge {after:.4f} <= 0.07",
            )

    # --- weights stay normalised and non-negative.
    w = [dict(x) for x in weights]
    region = dilate(adj, {seam - 1, seam}, 3)
    interior = interior_of(adj, region)
    updates = smooth_weights_jacobi(adj, w, interior, lam=0.5, iterations=16)
    bad_sum = [
        (i, round(sum(nw.values()), 6))
        for i, nw in updates.items()
        if abs(sum(nw.values()) - 1.0) > 1e-9
    ]
    bad_sign = [(i, nw) for i, nw in updates.items() if any(v < 0.0 for v in nw.values())]
    check(
        "smoothed weights stay normalised and non-negative",
        not bad_sum and not bad_sign,
        f"{len(updates)} verts updated; bad_sum={bad_sum[:3]} bad_sign={bad_sign[:3]}",
    )

    # --- boundary is untouched, so influence cannot leak across the body.
    outside = [i for i in range(n) if i not in interior]
    leaked = [i for i in outside if i in updates]
    check(
        "boundary and everything beyond it are untouched",
        not leaked,
        f"{len(outside)} verts outside the interior, {len(leaked)} changed",
    )

    # --- monotone: the worst neighbour weight difference never grows.
    def max_weight_gap(ws: list[WeightMap]) -> float:
        worst = 0.0
        for i, neighbours in enumerate(adj):
            for j in neighbours:
                keys = set(ws[i]) | set(ws[j])
                gap = sum(abs(ws[i].get(k, 0.0) - ws[j].get(k, 0.0)) for k in keys)
                worst = max(worst, gap)
        return worst

    w = [dict(x) for x in weights]
    region = dilate(adj, {seam - 1, seam}, 3)
    interior = interior_of(adj, region)
    gaps = [max_weight_gap(w)]
    for _ in range(12):
        updates = smooth_weights_jacobi(adj, w, interior, lam=0.5, iterations=1)
        for i, nw in updates.items():
            w[i] = nw
        gaps.append(max_weight_gap(w))
    check(
        "smoothing is monotone in the worst weight gap",
        all(b <= a + 1e-9 for a, b in zip(gaps[:-1], gaps[1:], strict=True)),
        f"gap {gaps[0]:.3f} -> {gaps[-1]:.3f} over {len(gaps) - 1} iterations",
    )

    # --- 2-D seam on a quad grid, closer to a real chest/shoulder seam.
    gw, gh = 21, 15
    gadj, coords = _grid(gw, gh)
    grest = [(x * SPACING, y * SPACING) for x, y in coords]
    gseam = gw // 2
    gweights = [{P: 1.0} if x < gseam else {Q: 1.0} for x, _y in coords]
    gbefore = _posed_edge_lengths(gadj, gweights, grest, BONES)
    seed = {
        i for i, (x, _y) in enumerate(coords) if x in (gseam - 1, gseam)
    }
    region = dilate(gadj, seed, 2)
    interior = interior_of(gadj, region)
    updates = smooth_weights_jacobi(gadj, gweights, interior, lam=0.5, iterations=10)
    for i, nw in updates.items():
        gweights[i] = nw
    gafter = _posed_edge_lengths(gadj, gweights, grest, BONES)
    check(
        "2-D grid seam clears the repair target",
        gafter <= 0.12,
        f"worst posed edge {gbefore:.4f} -> {gafter:.4f} "
        f"(region={len(region)} interior={len(interior)})",
    )

    # --- a frozen vert (weighted only to a group no bone drives) re-homes.
    n2 = 21
    adj2 = _chain(n2)
    rest2 = [(i * SPACING, 0.0) for i in range(n2)]
    w2 = [{P: 1.0} for _ in range(n2)]
    frozen = n2 // 2
    w2[frozen] = {}  # inert group only: nothing the armature drives
    # The frozen vert cannot be posed at all, which is the strand: model it by
    # giving the rest of the chain a bone that moves.
    w2_moving = [dict(x) for x in w2]
    for i in range(n2):
        if i != frozen:
            w2_moving[i] = {Q: 1.0}
    before2 = _posed_edge_lengths(adj2, w2_moving, rest2, BONES)
    check(
        "a frozen vert tears from its moving neighbours",
        before2 > 0.14,
        f"worst posed edge {before2:.4f} > gate 0.14",
    )
    fixed = rehome_from_neighbours(adj2, w2_moving, {frozen}, max_passes=8)
    for i, nw in fixed.items():
        w2_moving[i] = nw
    after2 = _posed_edge_lengths(adj2, w2_moving, rest2, BONES)
    check(
        "re-homing from neighbours removes the strand entirely",
        after2 <= SPACING + 1e-9,
        f"worst posed edge {before2:.4f} -> {after2:.4f} "
        f"(re-homed to {fixed[frozen]})",
    )

    # --- the tear criterion, against the two real measurements we have.
    # An edge is flagged when it exceeds the absolute cap, or is stretched past
    # the ratio AND has grown by a visible amount.
    print("\n  tear criterion vs the measured cases:")

    def flagged(posed: float, rest: float, *, limit_m: float, limit_stretch: float,
                min_excess: float) -> bool:
        return posed > limit_m or (
            posed / rest > limit_stretch and (posed - rest) > min_excess
        )

    gate = dict(limit_m=0.14, limit_stretch=2.6, min_excess=0.015)
    repair = dict(limit_m=0.12, limit_stretch=2.0, min_excess=0.012)
    cases = (
        # (name, posed, rest, must the gate flag it?)
        ("b4d8e69/af0e428 Punch bind seam", 0.2129, 0.010, True),
        ("f4d2059 Punch chest band", 0.0911, 0.010, True),
        ("46fc7b0 Death ball_l/foot_l toe seam", 0.0108, 0.00278, False),
        ("ordinary trunk edge under Walk", 0.0112, 0.010, False),
        ("p99.9 trunk edge (2.67x, small)", 0.0080, 0.003, False),
    )
    for name, posed, rest, want in cases:
        got = flagged(posed, rest, **gate)
        got_repair = flagged(posed, rest, **repair)
        check(
            f"gate {'flags' if want else 'passes'}: {name}",
            got == want,
            f"{posed * 1000:.1f} mm from {rest * 1000:.2f} mm rest = "
            f"{posed / rest:.2f}x, grew {(posed - rest) * 1000:.1f} mm -> "
            f"gate={'flag' if got else 'pass'} repair="
            f"{'flag' if got_repair else 'pass'}",
        )
    check(
        "the repair target is strictly tighter than the gate",
        all(
            flagged(p, r, **gate) <= flagged(p, r, **repair)
            for name, p, r, _w in cases
        ),
        "anything the gate refuses, the repair would have tried to fix",
    )

    # --- an unbound island must fail loudly, not be guessed at.
    adj3 = _chain(9)
    w3: list[WeightMap] = [{} for _ in range(9)]
    try:
        rehome_from_neighbours(adj3, w3, set(range(9)), max_passes=8)
    except BindRepairError as exc:
        check("refuses a fully unbound island", True, str(exc)[:90])
    else:
        check("refuses a fully unbound island", False, "accepted an unbound island")

    if failures:
        print(f"\nBIND REPAIR SELFTEST FAILED: {failures}")
        return 1
    print("\nBIND REPAIR SELFTEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
