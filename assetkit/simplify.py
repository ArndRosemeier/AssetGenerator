"""Reduce a closed triangle mesh to a triangle budget, keeping its shape and its topology.

Quadric error edge collapse (Garland and Heckbert 1997): repeatedly merge the two ends of
the edge whose removal changes the surface least, placing the merged vertex where the
squared distance to the original faces' planes is smallest. Triangles therefore gather
where the form bends and thin out where it is flat.

Every collapse keeps the mesh a closed 2-manifold (the link condition: the edge's two ends
share exactly the two vertices opposite it) and never flips a face over. A mesh that is
closed, manifold and outward-facing before stays so after: QA's gates hold. Plain Python
floats in the loop (numpy for the set-up), so it runs without Blender.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

Quadric = list[float]  # symmetric 4x4: a11 a12 a13 a14 a22 a23 a24 a33 a34 a44
FOLD_LIMIT = 0.2  # a face may turn by up to ~78 degrees in one collapse, no further
SLIVER = 1e-4  # a face with less area than this share of its longest edge squared has no reliable normal


def simplify(vertices: np.ndarray, faces: np.ndarray, max_triangles: int) -> tuple[np.ndarray, np.ndarray]:
    """Collapse edges until at most `max_triangles` remain (or no edge can go without breaking
    the mesh). Returns compacted (vertices, faces)."""
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if len(faces) <= max_triangles:
        return vertices, faces

    pos = [list(map(float, v)) for v in vertices]
    tris = [list(map(int, f)) for f in faces]
    alive = [True] * len(tris)
    quadric = _quadrics(vertices, faces)
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
        cost = _candidates(quadric[u], quadric[v], pos[u], pos[v])[0][0]
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


def _quadrics(vertices: np.ndarray, faces: np.ndarray) -> list[Quadric]:
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
    return total.tolist()


def _error(q: Quadric, p: list[float]) -> float:
    x, y, z = p
    return (
        q[0] * x * x + 2 * q[1] * x * y + 2 * q[2] * x * z + 2 * q[3] * x
        + q[4] * y * y + 2 * q[5] * y * z + 2 * q[6] * y
        + q[7] * z * z + 2 * q[8] * z + q[9]
    )  # fmt: skip


def _candidates(
    qu: Quadric, qv: Quadric, pu: list[float], pv: list[float]
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
    return sorted(((max(_error(q, p), 0.0), p) for p in candidates), key=lambda pair: pair[0])


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
    surface = [0.0, 0.0, 0.0]
    for f in vert_faces[u] | vert_faces[v]:
        n = _normal([pos[w] for w in tris[f]])
        surface = [s + c for s, c in zip(surface, n, strict=True)]
    surface_length = math.sqrt(sum(c * c for c in surface))
    for f in around:
        corners = [pos[w] for w in tris[f]]
        moved = [target if w in (u, v) else pos[w] for w in tris[f]]
        after = _normal(moved)
        length_after = math.sqrt(sum(c * c for c in after))
        before = _normal(corners)
        length_before = math.sqrt(sum(c * c for c in before))
        longest = max(math.dist(corners[i], corners[(i + 1) % 3]) for i in range(3))
        longest_after = max(math.dist(moved[i], moved[(i + 1) % 3]) for i in range(3))
        sliver_before = length_before < SLIVER * longest * longest
        if length_after < SLIVER * longest_after * longest_after and not sliver_before:
            return True  # would line three corners up: a zero-area face QA rejects
        if length_after < 1e-18:
            return True
        if sliver_before:
            reference, reference_length, limit = surface, surface_length, 0.0
        else:
            reference, reference_length, limit = before, length_before, FOLD_LIMIT
        if (
            sum(x * y for x, y in zip(reference, after, strict=True))
            < limit * reference_length * length_after
        ):
            return True
    return False


def _normal(corners: list[list[float]]) -> tuple[float, float, float]:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = corners
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
