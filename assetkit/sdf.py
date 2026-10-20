"""Shapes as signed distance functions: say what a form is, not where its vertices go.

A shape is a tree of primitives (sphere, capsule, rounded box, ...) combined with
unions, subtractions and intersections, sharp or smooth, moved, turned, mirrored and
roughened with noise. `mesh` turns it into one closed, outward-facing shell with a
triangle budget, ready for `MeshBuilder.add`:

    body = sdf.capsule((0, -0.3, 0.25), (0, 0.3, 0.3), 0.18)
    head = sdf.sphere((0, 0.45, 0.4), 0.14)
    shape = sdf.smooth_union(body, head, k=0.08).displace(0.01, scale=8.0, seed=3)
    builder.add(sdf.mesh(shape, max_triangles=4000), "skin")

Distances are in metres, negative inside. Smooth operations blend over `k` metres.
Meshing: marching tetrahedra (always closed and manifold), then quadric edge collapse
to the budget (assetkit/simplify.py). Needs numpy.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from assetkit.noise import noise_array
from assetkit.shells import Shell, Vec

Bounds = tuple[np.ndarray, np.ndarray]


@dataclass(frozen=True)
class Shape:
    """A distance function with conservative bounds (the surface lies inside them)."""

    distance: Callable[[np.ndarray], np.ndarray]
    lower: tuple[float, float, float]
    upper: tuple[float, float, float]
    label: str = "shape"

    def __call__(self, points: np.ndarray) -> np.ndarray:
        return self.distance(points)

    # Chainable forms of the operations below.
    def union(self, *others: Shape) -> Shape:
        return union(self, *others)

    def smooth_union(self, other: Shape, k: float) -> Shape:
        return smooth_union(self, other, k)

    def subtract(self, other: Shape, k: float = 0.0) -> Shape:
        return subtract(self, other, k)

    def intersect(self, other: Shape, k: float = 0.0) -> Shape:
        return intersect(self, other, k)

    def move(self, offset: Vec) -> Shape:
        return move(self, offset)

    def rotate(self, angles: Vec) -> Shape:
        return rotate(self, angles)

    def scale(self, factor: float) -> Shape:
        return scale(self, factor)

    def mirror_x(self) -> Shape:
        return mirror_x(self)

    def displace(self, amount: float, scale: float, seed: int = 0, octaves: int = 1) -> Shape:
        return displace(self, amount, scale, seed, octaves)

    def round(self, radius: float) -> Shape:
        return round_(self, radius)

    def shell(self, thickness: float) -> Shape:
        return shell(self, thickness)


def _dot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise dot product in a fixed order. Not `@` or `einsum`: those go through BLAS and
    SIMD reductions whose rounding differs between numpy builds, and the same spec must give
    the same mesh bit for bit everywhere (Blender 4.5 ships numpy 1.26, 5.2 numpy 2)."""
    a = np.atleast_2d(a)
    b = np.atleast_2d(b)
    total = a[:, 0] * b[:, 0]
    for i in range(1, a.shape[1]):
        total = total + a[:, i] * b[:, i]
    return total


def _length(a: np.ndarray) -> np.ndarray:
    """Row-wise length in a fixed order (see `_dot`)."""
    return np.sqrt(_dot(a, a))


def _box_bounds(lower: Sequence[float], upper: Sequence[float]) -> tuple[tuple, tuple]:
    return (tuple(float(v) for v in lower), tuple(float(v) for v in upper))


def _vec(v: Sequence[float]) -> np.ndarray:
    return np.asarray(v, dtype=np.float64)


# --------------------------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------------------------


def sphere(centre: Vec, radius: float) -> Shape:
    c = _vec(centre)
    _positive(radius, "sphere radius")
    lo, hi = _box_bounds(c - radius, c + radius)
    return Shape(lambda p: _length(p - c) - radius, lo, hi, "sphere")


def ellipsoid(centre: Vec, radii: Vec) -> Shape:
    """An ellipsoid; the distance is a close bound (exact for a sphere)."""
    c, r = _vec(centre), _vec(radii)
    for value in r:
        _positive(value, "ellipsoid radius")

    def distance(p: np.ndarray) -> np.ndarray:
        q = (p - c) / r
        k0 = _length(q)
        k1 = _length(q / r)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)

    lo, hi = _box_bounds(c - r, c + r)
    return Shape(distance, lo, hi, "ellipsoid")


def box(centre: Vec, size: Vec, radius: float = 0.0) -> Shape:
    """A box of `size` round `centre`, its edges rounded by `radius` (inside the size)."""
    c, half = _vec(centre), _vec(size) / 2
    if radius < 0 or radius >= half.min():
        raise ValueError(f"box radius {radius} must be in [0, {half.min()})")
    inner = half - radius

    def distance(p: np.ndarray) -> np.ndarray:
        q = np.abs(p - c) - inner
        outside = _length(np.maximum(q, 0.0))
        inside = np.minimum(q.max(axis=1), 0.0)
        return outside + inside - radius

    lo, hi = _box_bounds(c - half, c + half)
    return Shape(distance, lo, hi, "box")


def capsule(a: Vec, b: Vec, radius: float, radius_b: float | None = None) -> Shape:
    """A rounded segment from `a` to `b`; with `radius_b`, tapering from `radius` at a to it at b
    (a round cone: limbs, horns, roots, stalks)."""
    pa, pb = _vec(a), _vec(b)
    ra = radius
    rb = radius if radius_b is None else radius_b
    _positive(ra, "capsule radius")
    if rb < 0:
        raise ValueError(f"capsule radius_b must be >= 0, got {rb}")
    ba = pb - pa
    length2 = float(ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2])

    if radius_b is None or abs(ra - rb) < 1e-12 or length2 < 1e-18:

        def distance(p: np.ndarray) -> np.ndarray:
            if length2 < 1e-18:
                return _length(p - pa) - ra
            t = np.clip(_dot(p - pa, ba) / length2, 0.0, 1.0)
            return _length(p - (pa + t[:, None] * ba)) - ra

    else:
        length = math.sqrt(length2)
        axis = ba / length
        if abs(ra - rb) >= length:
            raise ValueError("capsule: the radii differ by more than its length (one end swallows the other)")
        # Round cone (Inigo Quilez): exact distance to the hull of two spheres.
        sin_a = (ra - rb) / length
        cos_a = math.sqrt(1.0 - sin_a * sin_a)

        def distance(p: np.ndarray) -> np.ndarray:
            ap = p - pa
            y = _dot(ap, axis)
            x = _length(ap - y[:, None] * axis)
            k = -x * sin_a + y * cos_a  # position along the slanted side
            d = x * cos_a + y * sin_a - ra
            d = np.where(k < 0.0, np.sqrt(x * x + y * y) - ra, d)
            d = np.where(k > length * cos_a, np.sqrt(x * x + (y - length) ** 2) - rb, d)
            return d

    big = max(ra, rb)
    lo, hi = _box_bounds(np.minimum(pa, pb) - big, np.maximum(pa, pb) + big)
    return Shape(distance, lo, hi, "capsule")


def cylinder(a: Vec, b: Vec, radius: float, rounding: float = 0.0) -> Shape:
    """A flat-ended cylinder from `a` to `b`, its rims rounded by `rounding`."""
    pa, pb = _vec(a), _vec(b)
    _positive(radius, "cylinder radius")
    ba = pb - pa
    length = math.sqrt(float(ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2]))
    _positive(length, "cylinder length")
    axis = ba / length
    if rounding < 0 or rounding >= min(radius, length / 2):
        raise ValueError(f"cylinder rounding {rounding} must be in [0, {min(radius, length / 2)})")

    def distance(p: np.ndarray) -> np.ndarray:
        ap = p - pa
        along = _dot(ap, axis)
        y = along - length / 2
        x = _length(ap - along[:, None] * axis)
        q = np.stack([x - (radius - rounding), np.abs(y) - (length / 2 - rounding)], axis=1)
        return np.minimum(q.max(axis=1), 0.0) + _length(np.maximum(q, 0.0)) - rounding

    lo, hi = _box_bounds(np.minimum(pa, pb) - radius, np.maximum(pa, pb) + radius)
    return Shape(distance, lo, hi, "cylinder")


def cone(a: Vec, b: Vec, radius: float, radius_b: float) -> Shape:
    """A flat-ended cone from `a` (radius) to `b` (radius_b, 0 for a point): a barnacle, a
    spike, a lampshade, a stump. Exact distance (after Inigo Quilez's capped cone)."""
    pa, pb = _vec(a), _vec(b)
    if radius < 0 or radius_b < 0 or radius + radius_b <= 0:
        raise ValueError(f"cone radii must be >= 0 and not both 0, got {radius}, {radius_b}")
    ba = pb - pa
    baba = float(ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2])
    _positive(baba, "cone length")
    ra, rb = radius, radius_b
    rba = rb - ra
    k = rba * rba + baba

    def distance(p: np.ndarray) -> np.ndarray:
        ap = p - pa
        papa = _dot(ap, ap)
        paba = _dot(ap, ba) / baba
        x = np.sqrt(np.maximum(papa - paba * paba * baba, 0.0))
        cax = np.maximum(0.0, x - np.where(paba < 0.5, ra, rb))
        cay = np.abs(paba - 0.5) - 0.5
        f = np.clip((rba * (x - ra) + paba * baba) / k, 0.0, 1.0)
        cbx = x - ra - f * rba
        cby = paba - f
        sign = np.where((cbx < 0.0) & (cay < 0.0), -1.0, 1.0)
        return sign * np.sqrt(np.minimum(cax * cax + cay * cay * baba, cbx * cbx + cby * cby * baba))

    r = max(ra, rb)
    lo, hi = _box_bounds(np.minimum(pa, pb) - r, np.maximum(pa, pb) + r)
    return Shape(distance, lo, hi, "cone")


def repeat(
    shape: Shape, count: int, step: Vec | None = None, around: bool = False, start: float = 0.0
) -> Shape:
    """`count` copies of `shape`: each `step` further on, or (`around`) turned evenly round the
    Z axis starting `start` radians on (legs, ribs, segments, spikes, barnacles)."""
    if count < 1:
        raise ValueError(f"repeat count must be at least 1, got {count}")
    if around:
        copies = [rotate(shape, (0.0, 0.0, start + math.tau * k / count)) for k in range(count)]
    else:
        if step is None:
            raise ValueError("repeat needs a step (or around)")
        copies = [move(shape, tuple(k * c for c in step)) for k in range(count)]  # type: ignore[arg-type]
    return union(*copies)


def scatter(
    on: Shape,
    shape: Shape,
    *,
    count: int = 0,
    seed: int = 0,
    at: Sequence[tuple[float, float]] = (),
    spacing: float = 0.0,
    facing: Vec = (0.0, 0.0, 1.0),
    angle_deg: float = 90.0,
    sink: float = 0.0,
    align: bool = True,
    sizes: tuple[float, float] = (1.0, 1.0),
) -> Shape:
    """Copies of `shape` (modelled at the origin, pointing up +Z) set on the surface of `on`:
    one dropped straight down at each `at` (x, y), and `count` more at seeded places no closer
    than `spacing` to each other, where the surface faces within `angle_deg` of `facing`. Each
    copy stands along the surface normal (or upright without `align`), is sunk `sink` metres
    into it, turned at random about its own axis and scaled between `sizes`. Just the copies:
    union them with `on` (and paint them with the same node). Barnacles, warts, rivets, spikes."""
    import random

    rng = random.Random(seed)
    lower, upper = _vec(on.lower), _vec(on.upper)
    want = np.asarray(facing, dtype=np.float64)
    want = want / max(float(np.sqrt(_dot(want[None], want[None])[0])), 1e-12)
    limit = math.cos(math.radians(angle_deg))

    def drop(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Where rays straight down at `xy` meet the surface: points, normals, and which hit."""
        p = np.stack([xy[:, 0], xy[:, 1], np.full(len(xy), upper[2] + 0.01)], axis=1)
        hit = np.zeros(len(xy), dtype=bool)
        step = float((upper - lower).max()) * 1e-4
        for _ in range(256):
            d = on(p)
            hit |= d < step
            gone = p[:, 2] < lower[2]  # missed: passed below the shape
            p[:, 2] -= np.where(hit | gone, 0.0, np.maximum(d, step))
            if (hit | gone).all():
                break
        hit &= p[:, 2] >= lower[2] - step
        h = step * 4
        grad = np.stack([on(p + o) - on(p - o) for o in np.eye(3) * h], axis=1)
        normal = grad / np.maximum(_length(grad), 1e-12)[:, None]
        return p, normal, hit

    spots: list[tuple[np.ndarray, np.ndarray]] = []
    if at:
        p, n, hit = drop(np.asarray(at, dtype=np.float64))
        for k in range(len(at)):
            if not hit[k]:
                raise ValueError(f"scatter: nothing below ({at[k][0]}, {at[k][1]}) to set a copy on")
            spots.append((p[k], n[k]))
    if count > 0:
        tries = count * 40
        xy = np.array(
            [(rng.uniform(lower[0], upper[0]), rng.uniform(lower[1], upper[1])) for _ in range(tries)]
        )
        p, n, hit = drop(xy)
        placed = 0
        for k in range(tries):
            if placed >= count:
                break
            if not hit[k] or float(_dot(n[k : k + 1], want[None])[0]) < limit:
                continue
            if any(float(_length((p[k] - q)[None])[0]) < spacing for q, _ in spots):
                continue
            spots.append((p[k], n[k]))
            placed += 1
        if placed < count:
            raise ValueError(
                f"scatter: room for only {placed} of {count} copies {spacing} m apart facing within "
                f"{angle_deg} degrees of {list(facing)}: fewer, closer, or a wider angle"
            )
    copies = []
    for point, normal in spots:
        size = rng.uniform(*sizes)
        spin = rng.uniform(0.0, math.tau)
        piece = rotate(scale(shape, size), (0.0, 0.0, spin))
        if align:
            ax = math.acos(max(-1.0, min(1.0, float(normal[2]))))
            az = math.atan2(float(normal[0]), -float(normal[1])) if ax > 1e-9 else 0.0
            piece = rotate(piece, (ax, 0.0, az))
            base = point - normal * sink
        else:
            base = point - np.array([0.0, 0.0, sink])
        copies.append(move(piece, tuple(float(c) for c in base)))  # type: ignore[arg-type]
    if not copies:
        raise ValueError("scatter: no copies (give `count` or `at`)")
    return union(*copies)


def torus(centre: Vec, radius: float, thickness: float, axis: str = "z") -> Shape:
    """A ring of `radius` round `axis` through `centre`, its tube `thickness` across (radius)."""
    c = _vec(centre)
    _positive(radius, "torus radius")
    _positive(thickness, "torus thickness")
    i = "xyz".index(axis)
    plane = [j for j in range(3) if j != i]

    def distance(p: np.ndarray) -> np.ndarray:
        q = p - c
        ring = _length(q[:, plane]) - radius
        return np.sqrt(ring * ring + q[:, i] ** 2) - thickness

    extent = np.full(3, radius + thickness)
    extent[i] = thickness
    lo, hi = _box_bounds(c - extent, c + extent)
    return Shape(distance, lo, hi, "torus")


def half_space(height: float, above: bool = False) -> Shape:
    """Everything below z = `height` (or above it): cut a shape flat with `intersect`.
    Unbounded: never mesh it on its own."""
    inf = 1e9
    if above:
        return Shape(lambda p: height - p[:, 2], (-inf, -inf, height), (inf, inf, inf), "half_space")
    return Shape(lambda p: p[:, 2] - height, (-inf, -inf, -inf), (inf, inf, height), "half_space")


# --------------------------------------------------------------------------------------------
# Combinations
# --------------------------------------------------------------------------------------------


def union(*shapes: Shape) -> Shape:
    if not shapes:
        raise ValueError("union needs at least one shape")
    boxes = [(_vec(s.lower), _vec(s.upper)) for s in shapes]

    def distance(p: np.ndarray) -> np.ndarray:
        result = shapes[0](p)
        for s, (lo, hi) in zip(shapes[1:], boxes[1:], strict=True):
            # A shape is no nearer than its bounding box: where the box is already further than
            # the nearest shape so far, the minimum cannot change, so skip the work there.
            gap = _length(np.maximum(np.maximum(lo - p, p - hi), 0.0))
            near = gap < result
            if near.all():
                result = np.minimum(result, s(p))
            elif near.any():
                result[near] = np.minimum(result[near], s(p[near]))
        return result

    return Shape(distance, *_union_bounds(shapes, 0.0), "union")


def smooth_union(a: Shape, b: Shape, k: float) -> Shape:
    """A union whose seam is filled over `k` metres, like clay pressed together."""
    _positive(k, "smooth_union k")

    def distance(p: np.ndarray) -> np.ndarray:
        da, db = a(p), b(p)
        h = np.clip(0.5 + 0.5 * (db - da) / k, 0.0, 1.0)
        return db + (da - db) * h - k * h * (1.0 - h)

    return Shape(distance, *_union_bounds((a, b), k * 0.25), "smooth_union")


def subtract(a: Shape, b: Shape, k: float = 0.0) -> Shape:
    """`a` with `b` carved out; with `k`, the cut's edge rounded over `k` metres."""

    def distance(p: np.ndarray) -> np.ndarray:
        da, db = a(p), b(p)
        if k <= 0.0:
            return np.maximum(da, -db)
        h = np.clip(0.5 - 0.5 * (da + db) / k, 0.0, 1.0)
        return da + (-db - da) * h + k * h * (1.0 - h)

    return Shape(distance, a.lower, a.upper, "subtract")


def intersect(a: Shape, b: Shape, k: float = 0.0) -> Shape:
    def distance(p: np.ndarray) -> np.ndarray:
        da, db = a(p), b(p)
        if k <= 0.0:
            return np.maximum(da, db)
        h = np.clip(0.5 - 0.5 * (db - da) / k, 0.0, 1.0)
        return db + (da - db) * h + k * h * (1.0 - h)

    lo = np.maximum(a.lower, b.lower)
    hi = np.minimum(a.upper, b.upper)
    if np.any(lo > hi):
        raise ValueError("intersect: the two shapes' bounds do not overlap")
    return Shape(distance, *_box_bounds(lo, hi), "intersect")


def move(shape: Shape, offset: Vec) -> Shape:
    o = _vec(offset)
    return Shape(
        lambda p: shape(p - o), *_box_bounds(_vec(shape.lower) + o, _vec(shape.upper) + o), shape.label
    )


def rotate(shape: Shape, angles: Vec) -> Shape:
    """Turn about the origin by XYZ Euler `angles` (radians): X first, then Y, then Z."""
    m = _euler(angles)

    def distance(p: np.ndarray) -> np.ndarray:
        # The inverse rotation (m transposed) applied to each row, written out (see `_dot`).
        return shape(np.stack([_dot(p, m[:, j]) for j in range(3)], axis=1))

    corners = np.array(
        [
            [x, y, z]
            for x in (shape.lower[0], shape.upper[0])
            for y in (shape.lower[1], shape.upper[1])
            for z in (shape.lower[2], shape.upper[2])
        ]
    )
    turned = np.stack([_dot(corners, m[j]) for j in range(3)], axis=1)
    return Shape(distance, *_box_bounds(turned.min(axis=0), turned.max(axis=0)), shape.label)


def scale(shape: Shape, factor: float) -> Shape:
    _positive(factor, "scale factor")
    return Shape(
        lambda p: shape(p / factor) * factor,
        *_box_bounds(_vec(shape.lower) * factor, _vec(shape.upper) * factor),
        shape.label,
    )


def mirror_x(shape: Shape) -> Shape:
    """The shape and its mirror image across x = 0 (model one side of a creature, get both)."""

    def distance(p: np.ndarray) -> np.ndarray:
        q = p.copy()
        q[:, 0] = np.abs(q[:, 0])
        return shape(q)

    reach = max(abs(shape.lower[0]), abs(shape.upper[0]))
    return Shape(
        distance,
        (-reach, shape.lower[1], shape.lower[2]),
        (reach, shape.upper[1], shape.upper[2]),
        shape.label,
    )


def flip_x(shape: Shape) -> Shape:
    """The shape's mirror image across x = 0 alone (`mirror_x` keeps both)."""

    def distance(p: np.ndarray) -> np.ndarray:
        q = p.copy()
        q[:, 0] = -q[:, 0]
        return shape(q)

    return Shape(
        distance,
        (-shape.upper[0], shape.lower[1], shape.lower[2]),
        (-shape.lower[0], shape.upper[1], shape.upper[2]),
        shape.label,
    )


def displace(shape: Shape, amount: float, scale: float, seed: int = 0, octaves: int = 1) -> Shape:
    """Push the surface in and out by up to about `amount` metres of noise with features
    `1 / scale` metres across; more octaves add finer detail at half the amount each."""
    _positive(scale, "displace scale")
    offset = np.array([seed * 31.7, seed * 17.3, seed * 47.1])

    def distance(p: np.ndarray) -> np.ndarray:
        d = shape(p)
        total = np.zeros(len(p))
        weight, freq = 1.0, scale
        for _ in range(octaves):
            q = p * freq + offset
            total += weight * noise_array(q[:, 0], q[:, 1], q[:, 2])
            weight, freq = weight * 0.5, freq * 2.0
        return d - amount * total

    pad = abs(amount) * 2.0
    return Shape(distance, *_box_bounds(_vec(shape.lower) - pad, _vec(shape.upper) + pad), shape.label)


def round_(shape: Shape, radius: float) -> Shape:
    """Grow the shape by `radius`, rounding its edges."""
    return Shape(
        lambda p: shape(p) - radius,
        *_box_bounds(_vec(shape.lower) - radius, _vec(shape.upper) + radius),
        shape.label,
    )


def shell(shape: Shape, thickness: float) -> Shape:
    """A hollow skin `thickness` thick around the surface (cut it open with `subtract`)."""
    _positive(thickness, "shell thickness")
    half = thickness / 2
    return Shape(
        lambda p: np.abs(shape(p)) - half,
        *_box_bounds(_vec(shape.lower) - half, _vec(shape.upper) + half),
        shape.label,
    )


def _union_bounds(shapes: Sequence[Shape], pad: float) -> tuple[tuple, tuple]:
    lo = np.min([s.lower for s in shapes], axis=0) - pad
    hi = np.max([s.upper for s in shapes], axis=0) + pad
    return _box_bounds(lo, hi)


def _euler(angles: Vec) -> np.ndarray:
    rx, ry, rz = angles
    cx, sx, cy, sy, cz, sz = (
        math.cos(rx),
        math.sin(rx),
        math.cos(ry),
        math.sin(ry),
        math.cos(rz),
        math.sin(rz),
    )
    # Rz @ Ry @ Rx, multiplied out by hand (see `_dot`).
    return np.array(
        [
            [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx],
        ]
    )


def _positive(value: float, what: str) -> None:
    if not value > 0:
        raise ValueError(f"{what} must be positive, got {value}")


# --------------------------------------------------------------------------------------------
# Meshing
# --------------------------------------------------------------------------------------------

# Freudenthal split of a cube into six tetrahedra round its main diagonal (corner 0 to 7, corner
# bits x=1, y=2, z=4). Neighbouring cubes split their shared faces the same way, so the surface
# is closed and manifold.
_TETS = np.array(
    [[0, a, a | b, 7] for a, b in ((1, 2), (1, 4), (2, 1), (2, 4), (4, 1), (4, 2))],
    dtype=np.int64,
)
_TET_EDGES = np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64)


def _edge(i: int, j: int) -> int:
    return int(np.nonzero((_TET_EDGES[:, 0] == min(i, j)) & (_TET_EDGES[:, 1] == max(i, j)))[0][0])


def _case_table() -> list[list[list[int]]]:
    """For each inside-mask of a tetrahedron's four corners: its triangles, as tet edge indices."""
    table: list[list[list[int]]] = []
    for mask in range(16):
        inside = [c for c in range(4) if mask >> c & 1]
        outside = [c for c in range(4) if not mask >> c & 1]
        if len(inside) in (0, 4):
            table.append([])
        elif len(inside) in (1, 3):
            lone = inside[0] if len(inside) == 1 else outside[0]
            others = [c for c in range(4) if c != lone]
            table.append([[_edge(lone, others[0]), _edge(lone, others[1]), _edge(lone, others[2])]])
        else:
            i, j = inside
            k, m = outside
            quad = [_edge(i, k), _edge(i, m), _edge(j, m), _edge(j, k)]
            table.append([[quad[0], quad[1], quad[2]], [quad[0], quad[2], quad[3]]])
    return table


_CASES = _case_table()


def mesh(shape: Shape, max_triangles: int = 4000, detail: float = 4.0) -> Shell:
    """One closed shell of `shape` with at most `max_triangles` triangles.

    The shape is sampled finely enough to give about `detail` times the budget, then
    simplified, so triangles gather where the form changes and thin out where it is flat.
    """
    if max_triangles < 8:
        raise ValueError(f"max_triangles must be at least 8, got {max_triangles}")
    lower, upper = _vec(shape.lower), _vec(shape.upper)
    if not np.all(np.isfinite(lower)) or np.any(upper - lower > 1e6):
        raise ValueError("mesh: the shape is unbounded (a half_space must be intersected with something)")
    cell = _cell_size(shape, lower, upper, max_triangles * detail)
    verts, faces = _march(shape, lower, upper, cell)
    if len(faces) == 0:
        raise ValueError("mesh: the shape is empty (nothing has a negative distance)")
    depth = _half_thickness(shape, verts, cell)
    # Thin parts (legs, fingers, horns) thinner than a cell across their radius: sample again,
    # finer (up to half the step), so they are resolved at all. Shapes without them pay nothing.
    thin = float(np.percentile(depth, 10))
    if thin < cell * 0.9:
        cell = max(thin, cell * FINEST)
        verts, faces = _march(shape, lower, upper, cell)
        depth = _half_thickness(shape, verts, cell)
    verts, faces, depth = _drop_crumbs(verts, faces, cell, depth)
    from assetkit.simplify import simplify

    # Simplify to most of the budget, weighing each vertex by how thin the shape is there; then
    # spend the rest splitting edges that are long for the thickness where they lie (thin limbs
    # sampled by only a cell or two), each new vertex put on the true surface; then even out.
    weights = np.clip((float(np.median(depth)) / depth) ** 2, 0.25, 64.0)
    verts, faces = simplify(verts, faces, max(8, int(max_triangles * REFINE_SHARE)), weights)
    verts = _project(shape, verts, faces, cell)
    verts, faces = _refine(shape, verts, faces, max_triangles, cell)
    verts = _relax(shape, verts, faces, cell)
    return [tuple(map(float, v)) for v in verts], [list(map(int, f)) for f in faces]


REFINE_SHARE = 0.85  # of the budget left after simplifying; refining thin parts takes the rest
FINEST = 0.5  # thin parts may halve the sampling step (four times the triangles to simplify)


def _half_thickness(shape: Shape, points: np.ndarray, cell: float) -> np.ndarray:
    """Per surface point, half the shape's thickness there: the deepest it gets straight in
    (at least half a cell)."""
    h = cell * 0.5
    grad = np.stack(
        [shape(points + np.eye(3)[k] * h) - shape(points - np.eye(3)[k] * h) for k in range(3)], axis=1
    )
    normal = grad / np.maximum(_length(grad), 1e-12)[:, None]
    lower, upper = _vec(shape.lower), _vec(shape.upper)
    reach = float((upper - lower).max())
    depth = np.zeros(len(points))
    t = cell * 0.5
    while t < reach:
        depth = np.maximum(depth, -shape(points - normal * t))
        t *= 1.5
    return np.maximum(depth, cell * 0.5)


def _refine(
    shape: Shape, verts: np.ndarray, faces: np.ndarray, budget: int, cell: float
) -> tuple[np.ndarray, np.ndarray]:
    """Split the edges longest for the thickness where they lie (each split adds two
    triangles), new vertices on the surface, until the budget is spent or every edge is short
    enough: about 0.7 half-thicknesses, some nine around a round limb."""
    verts = [tuple(v) for v in verts.tolist()]
    tris = [list(f) for f in faces.tolist()]
    for _ in range(12):
        room = (budget - len(tris)) // 2
        if room <= 0:
            break
        edge_faces: dict[tuple[int, int], list[int]] = {}
        for index, f in enumerate(tris):
            for k in range(3):
                a, b = f[k], f[(k + 1) % 3]
                edge_faces.setdefault((min(a, b), max(a, b)), []).append(index)
        edges = [e for e, owners in edge_faces.items() if len(owners) == 2]
        ends = np.array(edges, dtype=np.int64)
        pos = np.array(verts)
        mid = (pos[ends[:, 0]] + pos[ends[:, 1]]) / 2
        length = _length(pos[ends[:, 0]] - pos[ends[:, 1]])
        half = _half_thickness(shape, mid, cell)
        ratio = length / (0.7 * half)
        # Thinner than the sampling resolved, the coarse mesh is not the shape there (a thin
        # wall meshes as a slab or a hole): adding vertices to it would only show that.
        ratio[half < 0.75 * cell] = 0.0
        order = np.argsort(-ratio, kind="stable")
        used: set[int] = set()
        chosen = []
        for i in order:
            if ratio[i] <= 1.0 or len(chosen) >= room:
                break
            owners = edge_faces[edges[i]]
            if owners[0] in used or owners[1] in used:
                continue
            used.update(owners)
            chosen.append(i)
        if not chosen:
            break
        new_points = _project_points(shape, mid[chosen], cell)
        for i, point in zip(chosen, new_points, strict=True):
            a, b = edges[i]
            m = len(verts)
            verts.append(tuple(point))
            for index in edge_faces[(a, b)]:
                f = tris[index]
                k = next(k for k in range(3) if {f[k], f[(k + 1) % 3]} == {a, b})
                p, q, r = f[k], f[(k + 1) % 3], f[(k + 2) % 3]
                tris[index] = [p, m, r]
                tris.append([m, q, r])
    return np.array(verts, dtype=np.float64), np.array(tris, dtype=np.int64)


def _project_points(shape: Shape, points: np.ndarray, cell: float) -> np.ndarray:
    h = cell * 0.25
    moved = points.copy()
    for _ in range(4):
        d = shape(moved)
        grad = np.stack([(shape(moved + o) - shape(moved - o)) / (2 * h) for o in np.eye(3) * h], axis=1)
        moved = moved - (d / np.maximum(_dot(grad, grad), 1e-12))[:, None] * grad
    return moved


def _relax(shape: Shape, verts: np.ndarray, faces: np.ndarray, cell: float, rounds: int = 3) -> np.ndarray:
    """Even out the triangles: move each vertex half way to its neighbours' centre along the
    surface, then back onto it (a move that would turn a face over is undone)."""
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    count = np.bincount(edges[:, 0], minlength=len(verts)).astype(np.float64)
    h = cell * 0.25
    for _ in range(rounds):
        centre = np.zeros_like(verts)
        np.add.at(centre, edges[:, 0], verts[edges[:, 1]])
        centre /= np.maximum(count, 1.0)[:, None]
        grad = np.stack([(shape(verts + o) - shape(verts - o)) / (2 * h) for o in np.eye(3) * h], axis=1)
        normal = grad / np.maximum(_length(grad), 1e-12)[:, None]
        step = centre - verts
        step -= _dot(step, normal)[:, None] * normal
        verts = _project(shape, verts + 0.5 * step, faces, cell, start=verts)
    return verts


def _drop_crumbs(
    verts: np.ndarray, faces: np.ndarray, cell: float, values: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Drop loose bits smaller than the sampling can resolve: under two cells across. They are
    what is left of a feature thinner than a cell (the tip of a thin horn or ear), not a part of
    the shape; a real separate piece is bigger. Thicken the feature to keep it."""
    parent = np.arange(len(verts))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in faces:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    roots = np.array([find(f[0]) for f in faces])
    keep = np.ones(len(faces), dtype=bool)
    for root in np.unique(roots):
        mine = roots == root
        pts = verts[np.unique(faces[mine])]
        if (pts.max(axis=0) - pts.min(axis=0)).max() < 2 * cell:
            keep[mine] = False
    if keep.all():
        return verts, faces, values
    faces = faces[keep]
    used = np.unique(faces)
    remap = np.full(len(verts), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[faces], (None if values is None else values[used])


def reduce(shape: Shape, shell_mesh: Shell, max_triangles: int) -> Shell:
    """A shell from `mesh` simplified further to `max_triangles` (and put back on the surface):
    cheaper than meshing again when a budget turns out a little too high."""
    from assetkit.simplify import simplify

    verts = np.asarray(shell_mesh[0], dtype=np.float64)
    faces = np.asarray(shell_mesh[1], dtype=np.int64)
    verts, faces = simplify(verts, faces, max_triangles)
    edges = verts[faces[:, [1, 2, 0]]].reshape(-1, 3) - verts[faces].reshape(-1, 3)
    cell = float(np.median(_length(edges))) * 0.5
    verts = _project(shape, verts, faces, cell)
    return [tuple(map(float, v)) for v in verts], [list(map(int, f)) for f in faces]


def _project(
    shape: Shape, verts: np.ndarray, faces: np.ndarray, cell: float, start: np.ndarray | None = None
) -> np.ndarray:
    """Pull each vertex onto the true surface (simplifying leaves curved parts a little inside),
    a few Newton steps along the distance gradient. A vertex whose move would turn a face over
    stays where it was (at `start`, when given: where it was before the caller moved it)."""
    h = cell * 0.25
    offsets = np.eye(3) * h
    moved = verts.copy()
    if start is not None:
        verts = start
    for _ in range(3):
        d = shape(moved)
        grad = np.stack([(shape(moved + o) - shape(moved - o)) / (2 * h) for o in offsets], axis=1)
        moved = moved - (d / np.maximum(_dot(grad, grad), 1e-12))[:, None] * grad
    before = _face_normals(verts, faces)
    for _ in range(4):
        after = _face_normals(moved, faces)
        bad = _dot(before, after) <= 0.2 * _length(before) * _length(after)
        if not bad.any():
            break
        keep = np.unique(faces[bad])
        moved[keep] = verts[keep]
    return moved


def _face_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    return np.cross(b - a, c - a)


def _cell_size(shape: Shape, lower: np.ndarray, upper: np.ndarray, triangles: float) -> float:
    """Pick the sampling step for about `triangles` triangles: a coarse pass estimates the area."""
    coarse = max((upper - lower).max() / 24, 1e-4)
    _, faces_coarse = _march(shape, lower, upper, coarse)
    # Marching tetrahedra gives about 7 triangles per cell crossed by the surface.
    crossed = max(len(faces_coarse) / 7.0, 1.0)
    area_cells = crossed * coarse * coarse
    return float(np.clip(math.sqrt(area_cells * 7.0 / triangles), coarse / 16, coarse))


def _march(shape: Shape, lower: np.ndarray, upper: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    # Shifted by an odd fraction of a cell, so flat faces at round coordinates (a box's sides)
    # never lie exactly on samples: that would stack many vertices on one point.
    lo = lower - (2 + np.array([0.1372, 0.2913, 0.4157])) * cell
    counts = np.ceil((upper + 2 * cell - lo) / cell).astype(int) + 1
    if np.prod(counts) > 60_000_000:
        raise ValueError(f"mesh: a grid of {counts.tolist()} samples is too fine; lower the budget")
    axes = [lo[i] + cell * np.arange(counts[i]) for i in range(3)]
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    points = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    values = shape(points)
    values[values == 0.0] = 1e-12  # a sample exactly on the surface would make a zero-area triangle
    nx, ny, nz = counts
    inside = (values < 0).reshape(nx, ny, nz)

    # Cubes whose corners disagree about inside: the only ones the surface crosses.
    corner_offsets = [(c & 1, c >> 1 & 1, c >> 2 & 1) for c in range(8)]
    stack = np.stack(
        [inside[dx : nx - 1 + dx, dy : ny - 1 + dy, dz : nz - 1 + dz] for dx, dy, dz in corner_offsets]
    )
    active = np.argwhere(stack.any(axis=0) & ~stack.all(axis=0))
    if len(active) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

    def index(ijk: np.ndarray) -> np.ndarray:
        return (ijk[..., 0] * ny + ijk[..., 1]) * nz + ijk[..., 2]

    corners = np.stack([index(active + np.array(off)) for off in corner_offsets], axis=1)  # (A, 8)
    tets = corners[:, _TETS].reshape(-1, 4)  # (6A, 4) grid sample indices
    tet_inside = values[tets] < 0
    code = (tet_inside * np.array([1, 2, 4, 8])).sum(axis=1)

    tri_edges: list[np.ndarray] = []  # (n, 3, 2) grid sample pairs per triangle corner
    tri_tet: list[np.ndarray] = []
    for case in range(1, 15):
        chosen = np.nonzero(code == case)[0]
        if len(chosen) == 0:
            continue
        for triangle in _CASES[case]:
            pairs = _TET_EDGES[triangle]  # (3, 2) tet-local corners
            tri_edges.append(tets[chosen][:, pairs])  # (n, 3, 2)
            tri_tet.append(chosen)
    edges = np.concatenate(tri_edges)
    owner = np.concatenate(tri_tet)

    # One vertex per grid edge the surface crosses, shared by every triangle that uses it.
    a, b = np.minimum(edges[..., 0], edges[..., 1]), np.maximum(edges[..., 0], edges[..., 1])
    keys = a.astype(np.int64) * len(values) + b
    unique, inverse = np.unique(keys.ravel(), return_inverse=True)
    ea, eb = unique // len(values), unique % len(values)
    va, vb = values[ea], values[eb]
    t = va / (va - vb)
    verts = points[ea] + t[:, None] * (points[eb] - points[ea])
    faces = inverse.reshape(-1, 3)

    # Wind every triangle to face out of its tetrahedron's inside corners.
    tet_points = points[tets[owner]]  # (F, 4, 3)
    weights = tet_inside[owner]
    inner = (tet_points * weights[..., None]).sum(axis=1) / weights.sum(axis=1, keepdims=True)
    outer = (tet_points * ~weights[..., None]).sum(axis=1) / (~weights).sum(axis=1, keepdims=True)
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    normal = np.cross(v1 - v0, v2 - v0)
    flip = _dot(normal, outer - inner) < 0
    faces[flip] = faces[flip][:, ::-1]
    return verts, faces


def paint(
    shell_mesh: Shell, regions: dict[str, Shape], default: str, reach: float, shape: Shape | None = None
) -> tuple[Shell, list[str]]:
    """A material slot per face: a face inside a region, or within `reach` metres of it, takes
    that region's slot (the deepest region where they overlap); every other face takes
    `default`. A region can be a part of the shape (its eyes, its horns) or any volume laid
    over it (moss over the top, rust along the bottom).

    Given the `shape` the shell was meshed from, the mesh is first cut along each region's edge
    (where its distance is `reach`), the new vertices put on the surface, so borders follow the
    region exactly instead of zigzagging along whole triangles. Returns the shell and the slots.
    """
    verts = np.asarray(shell_mesh[0], dtype=np.float64)
    faces = np.asarray(shell_mesh[1], dtype=np.int64)
    if shape is not None:
        for region in regions.values():
            verts, faces = _cut(verts, faces, region(verts) - reach, region, reach, shape)
    centres = verts[faces].mean(axis=1)
    slots = np.full(len(faces), default, dtype=object)
    best = np.full(len(faces), reach)
    for name, region in regions.items():
        d = region(centres)
        closer = d <= best
        slots[closer] = name
        best = np.where(closer, d, best)
    shell_out = ([tuple(map(float, v)) for v in verts], [list(map(int, f)) for f in faces])
    return shell_out, [str(slot) for slot in slots]


SNAP = 0.2  # a crossing this close to a vertex (share of the edge) moves the vertex instead


def _cut(
    verts: np.ndarray, faces: np.ndarray, level: np.ndarray, region: Shape, reach: float, shape: Shape
) -> tuple[np.ndarray, np.ndarray]:
    """Split the mesh along level = 0: a new vertex on every edge that crosses it, each face
    divided along the crossing. The mesh stays closed and manifold; winding is kept."""
    verts = verts.copy()
    level = level.copy()
    edge_len = _length(verts[faces[:, [1, 2, 0]]].reshape(-1, 3) - verts[faces].reshape(-1, 3))
    h = max(float(np.median(edge_len)) * 0.02, 1e-7)

    # Crossings near a vertex move that vertex onto the border (no sliver triangles).
    pairs = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    pairs = np.unique(np.sort(pairs, axis=1), axis=0)
    la, lb = level[pairs[:, 0]], level[pairs[:, 1]]
    crossing = (la < 0) != (lb < 0)
    t = np.where(crossing, la / np.where(crossing, la - lb, 1.0), 0.5)
    snapped = np.zeros(len(verts), dtype=bool)
    for (a, b), tt, cross in zip(pairs, t, crossing, strict=True):
        if not cross:
            continue
        near, other, share = (a, b, tt) if tt < 0.5 else (b, a, 1.0 - tt)
        if share < SNAP and not snapped[near] and not snapped[other]:
            verts[near] = verts[near] + share * (verts[other] - verts[near])
            snapped[near] = True
    if snapped.any():
        verts[snapped] = _onto(shape, verts[snapped], h)
        level[snapped] = 0.0

    new_index: dict[tuple[int, int], int] = {}
    added: list[np.ndarray] = []

    def crossing_vertex(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key not in new_index:
            ta = level[a] / (level[a] - level[b])
            added.append(verts[a] + ta * (verts[b] - verts[a]))
            new_index[key] = len(verts) + len(added) - 1
        return new_index[key]

    out: list[list[int]] = []
    for face in faces:
        levels = [level[w] for w in face]
        if not min(levels) < 0.0 < max(levels):
            out.append([int(w) for w in face])  # all on one side (or only touching the border)
            continue
        # Walk the face's edges, inserting the crossing points: the ring has exactly two border
        # points (two crossings, or one crossing and a vertex on the border).
        ring: list[int] = []
        cuts: list[int] = []
        for k in range(3):
            a, b = int(face[k]), int(face[(k + 1) % 3])
            if level[a] == 0.0:
                cuts.append(len(ring))
            ring.append(a)
            if level[a] != 0.0 and level[b] != 0.0 and (level[a] < 0) != (level[b] < 0):
                cuts.append(len(ring))
                ring.append(crossing_vertex(a, b))
        i, j = cuts
        for polygon in (ring[i : j + 1], ring[j:] + ring[: i + 1]):
            for m in range(1, len(polygon) - 1):
                out.append([polygon[0], polygon[m], polygon[m + 1]])
    if added:
        fresh = _onto(shape, np.asarray(added), h)
        verts = np.concatenate([verts, fresh])
    return verts, np.asarray(out, dtype=np.int64)


def _onto(shape: Shape, points: np.ndarray, h: float) -> np.ndarray:
    """Points moved onto the surface: two Newton steps along the distance gradient."""
    for _ in range(2):
        d = shape(points)
        g = np.stack([(shape(points + o) - shape(points - o)) / (2 * h) for o in np.eye(3) * h], axis=1)
        points = points - (d / np.maximum(_dot(g, g), 1e-12))[:, None] * g
    return points
