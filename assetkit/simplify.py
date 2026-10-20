"""Reduce a closed triangle mesh to a triangle budget, keeping its shape and its topology.

Quadric error edge collapse (Garland and Heckbert 1997): repeatedly merge the two ends of
the edge whose removal changes the surface least, placing the merged vertex where the
squared distance to the original faces' planes is smallest. Triangles therefore gather
where the form bends and thin out where it is flat.

Every collapse keeps the mesh a closed 2-manifold (the link condition: the edge's two ends
share exactly the two vertices opposite it) and never flips a face over. A mesh that is
closed, manifold and outward-facing before stays so after: QA's gates hold.

Most of the way, collapses go in batches (`_batched`): every edge is priced at once in numpy
and the cheapest whose neighbourhoods do not touch collapse together, each tested as above.
Untouched neighbourhoods keep each test true when all happen at once. The last stretch (from
BATCH_STOP times the budget) goes one collapse at a time, cheapest first, in plain Python.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

Quadric = list[float]  # symmetric 4x4: a11 a12 a13 a14 a22 a23 a24 a33 a34 a44
FOLD_LIMIT = 0.2  # a face may turn by up to ~78 degrees in one collapse, no further
SLIVER = 1e-4  # a face with less area than this share of its longest edge squared has no reliable normal


def simplify(
    vertices: np.ndarray, faces: np.ndarray, max_triangles: int, weights: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Collapse edges until at most `max_triangles` remain (or no edge can go without breaking
    the mesh). Returns compacted (vertices, faces). `weights` (one per vertex) scale how much
    moving each vertex costs: above 1 keeps detail there (a thin limb), below 1 lets it go."""
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if len(faces) <= max_triangles:
        return vertices, faces
    q = _quadric_array(vertices, faces, weights)
    # Most of the way in batches (many independent collapses at once, in numpy); the last
    # stretch one collapse at a time, cheapest first, as Garland and Heckbert do it.
    vertices, faces, q = _batched(vertices, faces, q, int(max_triangles * BATCH_STOP))
    if len(faces) <= max_triangles:
        return _compact(vertices, faces)

    pos = [list(map(float, v)) for v in vertices]
    tris = [list(map(int, f)) for f in faces]
    alive = [True] * len(tris)
    quadric = q.tolist()
    vert_faces: list[set[int]] = [set() for _ in pos]
    for index, (a, b, c) in enumerate(tris):
        vert_faces[a].add(index)
        vert_faces[b].add(index)
        vert_faces[c].add(index)
    dead = [False] * len(pos)
    version = [0] * len(pos)

    heap: list[tuple[float, int, int, int, int]] = []

    def push(u: int, v: int) -> None:
        if u > v:
            u, v = v, u
        cost = min(c for c, _ in _candidates(quadric[u], quadric[v], pos[u], pos[v], ordered=False))
        heapq.heappush(heap, (cost, u, v, version[u], version[v]))

    edges = {tuple(sorted((f[i], f[(i + 1) % 3]))) for f in tris for i in range(3)}
    for u, v in edges:
        push(u, v)

    remaining = len(tris)
    while remaining > max_triangles and heap:
        queued, u, v, stamp_u, stamp_v = heapq.heappop(heap)
        if dead[u] or dead[v] or version[u] != stamp_u or version[v] != stamp_v:
            continue
        shared = vert_faces[u] & vert_faces[v]
        if len(shared) != 2:
            continue
        ring_u = _ring(u, vert_faces, tris)
        ring_v = _ring(v, vert_faces, tris)
        opposite = {w for f in shared for w in tris[f] if w != u and w != v}
        if ring_u & ring_v != opposite or len(ring_u | ring_v) <= 4:
            continue  # would pinch the surface (or close a tetrahedron on itself)
        q = [x + y for x, y in zip(quadric[u], quadric[v], strict=True)]
        # The cheapest place that turns no face over (the quadric's minimum often does on a
        # curve; the edge's own ends rarely do).
        choice = next(
            ((cost, p) for cost, p in _candidates(quadric[u], quadric[v], pos[u], pos[v])
             if not _folds(u, v, p, shared, vert_faces, tris, pos)),
            None,
        )  # fmt: skip
        if choice is None:
            continue
        cost, target = choice
        if cost > queued * (1 + 1e-9) + 1e-30:
            # Dearer than its place in the queue promised: wait for its turn at the true price.
            heapq.heappush(heap, (cost, u, v, stamp_u, stamp_v))
            continue

        for f in shared:
            alive[f] = False
            for w in tris[f]:
                vert_faces[w].discard(f)
        remaining -= 2
        for f in vert_faces[v]:
            tris[f] = [u if w == v else w for w in tris[f]]
            vert_faces[u].add(f)
        vert_faces[v] = set()
        dead[v] = True
        pos[u] = target
        quadric[u] = q
        version[u] += 1
        for w in _ring(u, vert_faces, tris):
            push(u, w)

    kept = [tris[i] for i in range(len(tris)) if alive[i]]
    used = sorted({w for f in kept for w in f})
    remap = {old: new for new, old in enumerate(used)}
    return (
        np.asarray([pos[i] for i in used], dtype=np.float64),
        np.asarray([[remap[w] for w in f] for f in kept], dtype=np.int64),
    )


def _quadric_array(vertices: np.ndarray, faces: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    cross = np.cross(b - a, c - a)
    # Written out rather than norm/einsum, so every numpy build rounds alike (see sdf._dot).
    area = np.sqrt(cross[:, 0] * cross[:, 0] + cross[:, 1] * cross[:, 1] + cross[:, 2] * cross[:, 2])
    normal = cross / np.maximum(area, 1e-30)[:, None]
    d = -(normal[:, 0] * a[:, 0] + normal[:, 1] * a[:, 1] + normal[:, 2] * a[:, 2])
    plane = np.concatenate([normal, d[:, None]], axis=1)
    rows = (0, 0, 0, 0, 1, 1, 1, 2, 2, 3)
    cols = (0, 1, 2, 3, 1, 2, 3, 2, 3, 3)
    per_face = plane[:, rows] * plane[:, cols] * (area / 2)[:, None]
    total = np.zeros((len(vertices), 10))
    for k in range(3):
        np.add.at(total, faces[:, k], per_face)
    if weights is not None:
        total *= np.asarray(weights, dtype=np.float64)[:, None]
    return total


BATCH_STOP = 1.25  # batches stop at this many times the budget; single collapses finish
BATCH_SHARE = 0.12  # at most this share of the vertices collapse in one batch


def _compact(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    used = np.unique(faces)
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return vertices[used], remap[faces]


def _batched(
    pos: np.ndarray, faces: np.ndarray, q: np.ndarray, stop: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Collapse edges in rounds until `stop` triangles remain: each round prices every edge,
    keeps those whose collapse keeps the mesh a closed manifold without turned-over or
    collapsed faces (the same tests as one at a time), and takes the cheapest that touch no
    other chosen edge's neighbourhood, so their tests stay true when all happen at once."""
    pos, q = pos.copy(), q.copy()
    for _ in range(64):
        if len(faces) <= stop:
            break
        n_vert = len(pos)
        # Edges with their two faces and the two corners opposite.
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        tail = np.concatenate([a, b, c])
        head = np.concatenate([b, c, a])
        lo, hi = np.minimum(tail, head), np.maximum(tail, head)
        key = lo * n_vert + hi
        order = np.argsort(key, kind="stable")
        key_sorted = key[order]
        start = np.concatenate([[True], key_sorted[1:] != key_sorted[:-1]])
        counts = np.diff(np.concatenate([np.nonzero(start)[0], [len(key_sorted)]]))
        first = np.nonzero(start)[0]
        manifold = counts == 2
        e_first = order[first[manifold]]
        e_u, e_v = lo[e_first], hi[e_first]
        e_key = key_sorted[first[manifold]]
        # Neighbours of each vertex (CSR) for the link condition and the neighbourhoods.
        nb_from = np.concatenate([e_u, e_v])
        nb_to = np.concatenate([e_v, e_u])
        nb_order = np.argsort(nb_from, kind="stable")
        nb_from, nb_to = nb_from[nb_order], nb_to[nb_order]
        nb_start = np.searchsorted(nb_from, np.arange(n_vert + 1))
        degree = np.diff(nb_start)
        # Link condition: u and v share exactly the two opposite corners, and the merged
        # neighbourhood keeps more than four vertices (else a tetrahedron closes on itself).
        reps = degree[e_u]
        edge_of = np.repeat(np.arange(len(e_u)), reps)
        w = nb_to[_expand(nb_start[e_u], reps)]
        probe = np.minimum(e_v[edge_of], w) * n_vert + np.maximum(e_v[edge_of], w)
        found = np.searchsorted(e_key, probe)
        found = np.minimum(found, len(e_key) - 1)
        common = np.bincount(
            edge_of, weights=(e_key[found] == probe) & (w != e_v[edge_of]), minlength=len(e_u)
        )
        link_ok = (common == 2) & (degree[e_u] + degree[e_v] - 2 > 4)
        # Price and place each collapse (the cheapest of the quadric's minimum, the ends, the middle).
        target, cost = _place(q[e_u] + q[e_v], pos[e_u], pos[e_v])
        candidates = np.nonzero(link_ok)[0]
        if not len(candidates):
            break
        candidates = candidates[np.argsort(cost[candidates], kind="stable")]
        want = min(int(BATCH_SHARE * len(np.unique(faces))), (len(faces) - stop + 1) // 2)
        # Test the cheapest few times as many as wanted for folds, then take the cheapest of
        # those that pass whose neighbourhoods do not touch.
        pool = candidates[: max(4 * want, 64)]
        pool = pool[~_folds_batch(e_u[pool], e_v[pool], target[pool], pos, faces)]
        locked = np.zeros(n_vert, dtype=bool)
        chosen = []
        for i in pool.tolist():
            u, v = int(e_u[i]), int(e_v[i])
            if locked[u] or locked[v]:
                continue
            chosen.append(i)
            locked[nb_to[nb_start[u] : nb_start[u + 1]]] = True
            locked[nb_to[nb_start[v] : nb_start[v + 1]]] = True
            locked[u] = locked[v] = True
            if len(chosen) >= want:
                break
        if not chosen:
            break
        chosen_arr = np.array(chosen, dtype=np.int64)
        keep, gone = e_u[chosen_arr], e_v[chosen_arr]
        pos[keep] = target[chosen_arr]
        q[keep] = q[keep] + q[gone]
        remap = np.arange(n_vert)
        remap[gone] = keep
        faces = remap[faces]
        faces = faces[
            (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 2] != faces[:, 0])
        ]
    return pos, faces, q


def _expand(starts: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """The indices start..start+count of every (start, count), one after another."""
    total = int(counts.sum())
    offsets = np.repeat(np.cumsum(counts) - counts, counts)
    return np.repeat(starts, counts) + np.arange(total) - offsets


def _place(qs: np.ndarray, pu: np.ndarray, pv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per edge: where the merged vertex goes and what it costs (as `_candidates`, cheapest)."""
    a11, a12, a13, a14, a22, a23, a24, a33, a34 = (qs[:, k] for k in range(9))
    det = a11 * (a22 * a33 - a23 * a23) - a12 * (a12 * a33 - a23 * a13) + a13 * (a12 * a23 - a22 * a13)
    big = np.maximum(np.maximum(np.abs(a11), np.abs(a22)), np.maximum(np.abs(a33), 1e-30))
    scale = big * big * big
    middle = (pu + pv) / 2
    solvable = np.abs(det) > 1e-9 * scale
    safe = np.where(solvable, det, 1.0)
    bx, by, bz = -a14, -a24, -a34
    x = (bx * (a22 * a33 - a23 * a23) - a12 * (by * a33 - a23 * bz) + a13 * (by * a23 - a22 * bz)) / safe
    y = (a11 * (by * a33 - a23 * bz) - bx * (a12 * a33 - a23 * a13) + a13 * (a12 * bz - by * a13)) / safe
    z = (a11 * (a22 * bz - by * a23) - a12 * (a12 * bz - by * a13) + bx * (a12 * a23 - a22 * a13)) / safe
    best = np.stack([x, y, z], axis=1)
    d = best - middle
    e = pu - pv
    near = (d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1] + d[:, 2] * d[:, 2]) <= (
        e[:, 0] * e[:, 0] + e[:, 1] * e[:, 1] + e[:, 2] * e[:, 2]
    )
    options = [pu, pv, middle, np.where((solvable & near)[:, None], best, middle)]
    costs = np.stack([np.maximum(_error_batch(qs, p), 0.0) for p in options], axis=1)
    pick = np.argmin(costs, axis=1)
    stacked = np.stack(options, axis=1)
    return stacked[np.arange(len(pick)), pick], costs[np.arange(len(pick)), pick]


def _error_batch(q: np.ndarray, p: np.ndarray) -> np.ndarray:
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    return (
        q[:, 0] * x * x + 2 * q[:, 1] * x * y + 2 * q[:, 2] * x * z + 2 * q[:, 3] * x
        + q[:, 4] * y * y + 2 * q[:, 5] * y * z + 2 * q[:, 6] * y
        + q[:, 7] * z * z + 2 * q[:, 8] * z + q[:, 9]
    )  # fmt: skip


def _folds_batch(
    e_u: np.ndarray, e_v: np.ndarray, target: np.ndarray, pos: np.ndarray, faces: np.ndarray
) -> np.ndarray:
    """Per edge: would moving both ends to `target` turn a surrounding face over, flatten it
    to nothing or line its corners up (the batch form of `_folds`)."""
    n_vert = len(pos)
    # Faces round each vertex (CSR).
    corner_v = faces.reshape(-1)
    corner_f = np.repeat(np.arange(len(faces)), 3)
    order = np.argsort(corner_v, kind="stable")
    corner_v, corner_f = corner_v[order], corner_f[order]
    start = np.searchsorted(corner_v, np.arange(n_vert + 1))
    counts_u = start[e_u + 1] - start[e_u]
    counts_v = start[e_v + 1] - start[e_v]
    edge_of = np.concatenate(
        [np.repeat(np.arange(len(e_u)), counts_u), np.repeat(np.arange(len(e_v)), counts_v)]
    )
    idx = np.concatenate([_expand(start[e_u], counts_u), _expand(start[e_v], counts_v)])
    face = corner_f[idx]
    tri = faces[face]
    u, v = e_u[edge_of], e_v[edge_of]
    has_u = (tri == u[:, None]).any(axis=1)
    has_v = (tri == v[:, None]).any(axis=1)
    shared = has_u & has_v
    corners = pos[tri]
    moved = np.where(
        ((tri == u[:, None]) | (tri == v[:, None]))[:, :, None], target[edge_of][:, None, :], corners
    )
    before, longest = _face_batch(corners)
    after, longest_after = _face_batch(moved)
    len_b = np.sqrt(before[:, 0] ** 2 + before[:, 1] ** 2 + before[:, 2] ** 2)
    len_a = np.sqrt(after[:, 0] ** 2 + after[:, 1] ** 2 + after[:, 2] ** 2)
    sliver_before = len_b < SLIVER * longest
    # The surface's normal round the edge: every face round u or v, summed (for slivers).
    surface = np.zeros((len(e_u), 3))
    once = ~(shared & (np.arange(len(edge_of)) >= counts_u.sum()))  # a face on the edge: count it once
    for k in range(3):
        surface[:, k] = np.bincount(edge_of[once], weights=before[once, k], minlength=len(e_u))
    len_s = np.sqrt(surface[:, 0] ** 2 + surface[:, 1] ** 2 + surface[:, 2] ** 2)
    ref = np.where(sliver_before[:, None], surface[edge_of], before)
    ref_len = np.where(sliver_before, len_s[edge_of], len_b)
    limit = np.where(sliver_before, 0.0, FOLD_LIMIT)
    dot = ref[:, 0] * after[:, 0] + ref[:, 1] * after[:, 1] + ref[:, 2] * after[:, 2]
    bad = (
        (len_a < 1e-18)
        | ((len_a < SLIVER * longest_after) & ~sliver_before)
        | (dot < limit * ref_len * len_a)
    )
    bad &= ~shared  # the two faces on the edge itself disappear
    return np.bincount(edge_of, weights=bad, minlength=len(e_u)) > 0


def _face_batch(corners: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(N, 3, 3) triangles: area-weighted normals and longest edges squared (as `_face`)."""
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    u, v = b - a, c - a
    w = v - u
    normal = np.stack(
        [
            u[:, 1] * v[:, 2] - u[:, 2] * v[:, 1],
            u[:, 2] * v[:, 0] - u[:, 0] * v[:, 2],
            u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0],
        ],
        axis=1,
    )
    sq = lambda x: x[:, 0] * x[:, 0] + x[:, 1] * x[:, 1] + x[:, 2] * x[:, 2]  # noqa: E731
    return normal, np.maximum(np.maximum(sq(u), sq(v)), sq(w))


def _error(q: Quadric, p: list[float]) -> float:
    x, y, z = p
    return (
        q[0] * x * x + 2 * q[1] * x * y + 2 * q[2] * x * z + 2 * q[3] * x
        + q[4] * y * y + 2 * q[5] * y * z + 2 * q[6] * y
        + q[7] * z * z + 2 * q[8] * z + q[9]
    )  # fmt: skip


def _candidates(
    qu: Quadric, qv: Quadric, pu: list[float], pv: list[float], ordered: bool = True
) -> list[tuple[float, list[float]]]:
    """Places for the merged vertex with the error each costs, cheapest first: the quadric's
    minimum when it is well defined and near the edge, the two ends and the middle."""
    q = [x + y for x, y in zip(qu, qv, strict=True)]
    a11, a12, a13, a14, a22, a23, a24, a33, a34, _ = q
    det = a11 * (a22 * a33 - a23 * a23) - a12 * (a12 * a33 - a23 * a13) + a13 * (a12 * a23 - a22 * a13)
    scale = max(abs(a11), abs(a22), abs(a33), 1e-30) ** 3
    middle = [(x + y) / 2 for x, y in zip(pu, pv, strict=True)]
    candidates = [pu, pv, middle]
    if abs(det) > 1e-9 * scale:
        bx, by, bz = -a14, -a24, -a34
        x = (bx * (a22 * a33 - a23 * a23) - a12 * (by * a33 - a23 * bz) + a13 * (by * a23 - a22 * bz)) / det
        y = (a11 * (by * a33 - a23 * bz) - bx * (a12 * a33 - a23 * a13) + a13 * (a12 * bz - by * a13)) / det
        z = (a11 * (a22 * bz - by * a23) - a12 * (a12 * bz - by * a13) + bx * (a12 * a23 - a22 * a13)) / det
        length = math.dist(pu, pv)
        if math.dist((x, y, z), middle) <= length:  # a far minimum is a sliver's artefact, not a fit
            candidates.insert(0, [x, y, z])
    priced = [(max(_error(q, p), 0.0), p) for p in candidates]
    return sorted(priced, key=lambda pair: pair[0]) if ordered else priced


def _ring(u: int, vert_faces: list[set[int]], tris: list[list[int]]) -> set[int]:
    return {w for f in vert_faces[u] for w in tris[f] if w != u}


def _folds(
    u: int,
    v: int,
    target: list[float],
    shared: set[int],
    vert_faces: list[set[int]],
    tris: list[list[int]],
    pos: list[list[float]],
) -> bool:
    """Would moving u and v to `target` turn a surrounding face over (or flatten it to nothing)?

    A sliver's own normal is noise, so it is held to the surface's: the summed normal of the
    faces round the edge.
    """
    around = (vert_faces[u] | vert_faces[v]) - shared
    surface: tuple[float, float, float] | None = None  # worked out only if a sliver needs it
    for f in around:
        a, b, c = tris[f]
        pa, pb, pc = pos[a], pos[b], pos[c]
        before, longest = _face(pa, pb, pc)
        ma = target if a in (u, v) else pa
        mb = target if b in (u, v) else pb
        mc = target if c in (u, v) else pc
        after, longest_after = _face(ma, mb, mc)
        length_after = math.sqrt(after[0] * after[0] + after[1] * after[1] + after[2] * after[2])
        if length_after < 1e-18:
            return True
        length_before = math.sqrt(before[0] * before[0] + before[1] * before[1] + before[2] * before[2])
        sliver_before = length_before < SLIVER * longest
        if length_after < SLIVER * longest_after and not sliver_before:
            return True  # would line three corners up: a zero-area face QA rejects
        if sliver_before:
            if surface is None:
                sx = sy = sz = 0.0
                for g in vert_faces[u] | vert_faces[v]:
                    ga, gb, gc = tris[g]
                    n = _normal3(pos[ga], pos[gb], pos[gc])
                    sx, sy, sz = sx + n[0], sy + n[1], sz + n[2]
                surface = (sx, sy, sz)
            reference, limit = surface, 0.0
            reference_length = math.sqrt(surface[0] ** 2 + surface[1] ** 2 + surface[2] ** 2)
        else:
            reference, reference_length, limit = before, length_before, FOLD_LIMIT
        dot = reference[0] * after[0] + reference[1] * after[1] + reference[2] * after[2]
        if dot < limit * reference_length * length_after:
            return True
    return False


def _normal3(a: list[float], b: list[float], c: list[float]) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _face(a: list[float], b: list[float], c: list[float]) -> tuple[tuple[float, float, float], float]:
    """A triangle's (area-weighted) normal and its longest edge squared."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    wx, wy, wz = vx - ux, vy - uy, vz - uz
    longest = max(ux * ux + uy * uy + uz * uz, vx * vx + vy * vy + vz * vz, wx * wx + wy * wy + wz * wz)
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx), longest
