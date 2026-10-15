"""A signed distance field on a voxel grid, and surface nets to mesh it.

Numpy only (it ships with Blender), so the sculpt needs no add-on and no extra
package. Distances are negative inside. Each shape is evaluated only inside its
own bounding box (grown by its blend radius), so a body of a hundred shapes at
4 mm stays a few seconds.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

Vec = tuple[float, float, float]
Field = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]


def _len3(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    return np.sqrt(x * x + y * y + z * z)


def round_cone(a: Vec, b: Vec, ra: float, rb: float) -> Field:
    """A capsule whose radius runs from `ra` at `a` to `rb` at `b` (Quilez's exact round cone)."""
    ax, ay, az = a
    bax, bay, baz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    l2 = bax * bax + bay * bay + baz * baz
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2

    def f(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        px, py, pz = x - ax, y - ay, z - az
        yv = px * bax + py * bay + pz * baz
        zv = yv - l2
        qx, qy, qz = px * l2 - bax * yv, py * l2 - bay * yv, pz * l2 - baz * yv
        x2 = qx * qx + qy * qy + qz * qz
        y2 = yv * yv * l2
        z2 = zv * zv * l2
        k = np.sign(rr) * rr * rr * x2
        out = (np.sqrt(x2 * a2 * il2) + yv * rr) * il2 - ra
        cap_b = np.sign(zv) * a2 * z2 > k
        cap_a = np.sign(yv) * a2 * y2 < k
        out = np.where(cap_b, np.sqrt(x2 + z2) * il2 - rb, out)
        out = np.where(cap_a, np.sqrt(x2 + y2) * il2 - ra, out)
        return out

    return f


def ellipsoid(c: Vec, r: Vec, rot: np.ndarray | None = None) -> Field:
    """An ellipsoid of radii `r` about `c`, turned by the 3x3 matrix `rot` (its columns are the axes)."""
    cx, cy, cz = c
    rx, ry, rz = r
    m = np.eye(3) if rot is None else np.asarray(rot, dtype=float)

    def f(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        px, py, pz = x - cx, y - cy, z - cz
        lx = px * m[0, 0] + py * m[1, 0] + pz * m[2, 0]
        ly = px * m[0, 1] + py * m[1, 1] + pz * m[2, 1]
        lz = px * m[0, 2] + py * m[1, 2] + pz * m[2, 2]
        k0 = _len3(lx / rx, ly / ry, lz / rz)
        k1 = _len3(lx / (rx * rx), ly / (ry * ry), lz / (rz * rz))
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)

    return f


def flattened(inner: Field, c: Vec, axis: Vec, factor: float) -> Field:
    """`inner`, squashed by `factor` along `axis` about `c` (ears, lips): space is stretched, distances scaled back."""
    n = np.asarray(axis, dtype=float)
    n /= np.linalg.norm(n)

    def f(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        d = (x - c[0]) * n[0] + (y - c[1]) * n[1] + (z - c[2]) * n[2]
        s = d * (1.0 / factor - 1.0)
        return inner(x + n[0] * s, y + n[1] * s, z + n[2] * s) * factor

    return f


def rotation(forward: Vec, up: Vec = (0.0, 0.0, 1.0)) -> np.ndarray:
    """Axes (as columns x, y, z) with y along `forward` and z as near `up` as it can be."""
    y = np.asarray(forward, dtype=float)
    y /= np.linalg.norm(y)
    z = np.asarray(up, dtype=float)
    z = z - y * float(np.dot(z, y))
    z /= np.linalg.norm(z)
    x = np.cross(y, z)
    return np.stack([x, y, z], axis=1)


@dataclass(frozen=True)
class Shape:
    """One piece of the sculpt: its field, its box, how softly it joins, and the bone that carries it."""

    field: Field
    lo: Vec
    hi: Vec
    blend: float
    bone: str
    carve: bool = False


def box_of_round_cone(a: Vec, b: Vec, ra: float, rb: float) -> tuple[Vec, Vec]:
    r = max(ra, rb)
    lo = tuple(min(a[i], b[i]) - r for i in range(3))
    hi = tuple(max(a[i], b[i]) + r for i in range(3))
    return lo, hi  # type: ignore[return-value]


def box_of_ellipsoid(c: Vec, r: Vec) -> tuple[Vec, Vec]:
    m = max(r)
    return (c[0] - m, c[1] - m, c[2] - m), (c[0] + m, c[1] + m, c[2] + m)


class Grid:
    """A regular grid of `step` covering `lo`..`hi`, holding the field (large and positive where nothing is)."""

    def __init__(self, lo: Vec, hi: Vec, step: float) -> None:
        self.step = step
        self.lo = np.asarray(lo, dtype=float)
        self.n = tuple(int(np.ceil((hi[i] - lo[i]) / step)) + 1 for i in range(3))
        self.axes = [self.lo[i] + np.arange(self.n[i]) * step for i in range(3)]
        self.values = np.full(self.n, 1.0, dtype=np.float32)

    def _slices(self, lo: Vec, hi: Vec) -> tuple[slice, slice, slice] | None:
        out = []
        for i in range(3):
            a = int(np.floor((lo[i] - self.lo[i]) / self.step))
            b = int(np.ceil((hi[i] - self.lo[i]) / self.step)) + 1
            a, b = max(a, 0), min(b, self.n[i])
            if a >= b:
                return None
            out.append(slice(a, b))
        return out[0], out[1], out[2]

    def local(
        self, lo: Vec, hi: Vec
    ) -> tuple[tuple[slice, slice, slice], np.ndarray, np.ndarray, np.ndarray] | None:
        sl = self._slices(lo, hi)
        if sl is None:
            return None
        x, y, z = np.meshgrid(self.axes[0][sl[0]], self.axes[1][sl[1]], self.axes[2][sl[2]], indexing="ij")
        return sl, x, y, z

    def add(self, shape: Shape) -> None:
        g = shape.blend
        lo = (shape.lo[0] - g, shape.lo[1] - g, shape.lo[2] - g)
        hi = (shape.hi[0] + g, shape.hi[1] + g, shape.hi[2] + g)
        got = self.local(lo, hi)
        if got is None:
            return
        sl, x, y, z = got
        d = shape.field(x, y, z).astype(np.float32)
        cur = self.values[sl]
        if shape.carve:
            self.values[sl] = smooth_max(cur, -d, g)
        else:
            self.values[sl] = smooth_min(cur, d, g)


def smooth_min(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smooth_max(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    return -smooth_min(-a, -b, k)


def surface_nets(grid: Grid) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (one per cell the surface crosses, at the mean of its edge crossings) and quads, outward facing."""
    v = grid.values
    inside = v < 0
    nx, ny, nz = v.shape
    # Corners of every cell, and the 12 edges as corner pairs.
    corners = [(i, j, k) for k in (0, 1) for j in (0, 1) for i in (0, 1)]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    cv = [v[i : nx - 1 + i, j : ny - 1 + j, k : nz - 1 + k] for (i, j, k) in corners]
    acc = np.zeros((nx - 1, ny - 1, nz - 1, 3), dtype=np.float32)
    cnt = np.zeros((nx - 1, ny - 1, nz - 1), dtype=np.float32)
    for a, b in edges:
        va, vb = cv[a], cv[b]
        cross = (va < 0) != (vb < 0)
        t = np.where(cross, va / np.where(cross, va - vb, 1.0), 0.0)
        pa, pb = np.asarray(corners[a], dtype=np.float32), np.asarray(corners[b], dtype=np.float32)
        for axis in range(3):
            acc[..., axis] += np.where(cross, pa[axis] + (pb[axis] - pa[axis]) * t, 0.0)
        cnt += cross
    active = cnt > 0
    index = np.full(active.shape, -1, dtype=np.int64)
    ids = np.nonzero(active)
    index[ids] = np.arange(len(ids[0]))
    local = acc[ids] / cnt[ids][:, None]
    verts = np.stack(ids, axis=1).astype(np.float32) + local
    verts = grid.lo + verts * grid.step

    quads = []
    # An edge of the grid along `axis` that the surface crosses gives a quad of the four cells round it.
    for axis in range(3):
        o1, o2 = [(1, 2), (0, 2), (0, 1)][axis]
        sl_a = [slice(None)] * 3
        sl_b = [slice(None)] * 3
        sl_a[axis] = slice(0, v.shape[axis] - 1)
        sl_b[axis] = slice(1, v.shape[axis])
        a_in = inside[tuple(sl_a)]
        b_in = inside[tuple(sl_b)]
        cross = a_in != b_in
        e = np.nonzero(cross)
        flip = a_in[e]
        base = np.stack(e, axis=1)

        def cell(d1: int, d2: int, base: np.ndarray = base, o1: int = o1, o2: int = o2) -> np.ndarray:
            c = base.copy()
            c[:, o1] -= d1
            c[:, o2] -= d2
            ok = (c >= 0).all(axis=1) & (c[:, 0] < nx - 1) & (c[:, 1] < ny - 1) & (c[:, 2] < nz - 1)
            c = np.clip(c, 0, None)
            c[:, 0] = np.minimum(c[:, 0], nx - 2)
            c[:, 1] = np.minimum(c[:, 1], ny - 2)
            c[:, 2] = np.minimum(c[:, 2], nz - 2)
            out = index[c[:, 0], c[:, 1], c[:, 2]]
            return np.where(ok, out, -1)

        q = np.stack([cell(1, 1), cell(0, 1), cell(0, 0), cell(1, 0)], axis=1)
        good = (q >= 0).all(axis=1)
        q, flip = q[good], flip[good]
        # Orientation: the quad's normal follows from inside to outside along `axis`.
        q = np.where(flip[:, None] == (axis == 1), q, q[:, ::-1])
        quads.append(q)
    faces = np.concatenate(quads, axis=0)
    # One consistent winding from the rule above; turn it outward if it came out inward (negative volume).
    p = verts[faces]
    vol = (
        np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum()
        + np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 2], p[:, 3])).sum()
    )
    if vol < 0:
        faces = faces[:, ::-1]
    return verts.astype(np.float64), faces
