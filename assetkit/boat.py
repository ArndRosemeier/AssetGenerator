"""A ship's boat from her lines: clinker strakes, keel, stem, transom, timbers, gunwales, thwarts.

Where an assembly (assetkit/assembly.py) is a kit of exact parts, a boat's planking follows a
curved hull no part can describe: each strake is a band of the hull's surface between two
girths, laid so its lower edge laps outside the strake below (clinker). This module turns a
boat's lines into closed shells; `prop.boat` (blender/generators/prop_boat.py) adds them to
assembly pieces (oars, rowlocks, a rudder).

The lines (metres; Z up; the bow is -Y, the stern +Y, the keel's underside at z = 0 amidships):

    length, beam, depth   overall length, greatest breadth, sheer height amidships
    breadth  [[t, share], ...]   half-breadth at the sheer as a share of beam / 2, t from the
                                 stem (0) to the transom (1)
    keel     [[t, height], ...]  the keel's top (the rabbet), m above the base: its rocker
    sheer    [[t, height], ...]  the sheer, m above the base
    fullness [[t, f], ...]       the section's shape: 0 a straight V, 1 a round-bilged U

Between the given t, values run on a smooth monotone curve. A section at t is the curve from the
keel (v = 0) to the sheer (v = 1): z rises evenly with v, the half-breadth as
mix(v, 1 - (1 - v)^2.6, fullness) of the breadth there.

Standard library only.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from assetkit.shells import Shell, Vec, _add, _cross, _mul, _norm, _sub, box, sweep, triangulate

BILGE = 2.6  # how fast a full section turns at the bilge (the power of 1 - v)
STATIONS = 40  # samples along the boat for strakes and gunwales
ACROSS = 3  # samples across a strake (lower edge, middle, upper edge)
FRAME_SAMPLES = 10  # samples up a timber
EPS = 1e-4  # metres: the step for numeric derivatives


@dataclass(frozen=True)
class Lines:
    length: float
    beam: float
    depth: float
    breadth: tuple[tuple[float, float], ...]
    keel: tuple[tuple[float, float], ...]
    sheer: tuple[tuple[float, float], ...]
    fullness: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Build:
    """What is built on the lines, metres: strakes and their plank, the lap (share of a strake's
    width), the keel and stem (sided, moulded below the rabbet), the transom's thickness, the
    timbers' spacing and size (sided, moulded), the gunwale (wide, deep), thwarts as [t, below
    the sheer] with their size (wide, thick), and thole pins beside each thwart."""

    strakes: int = 7
    plank: float = 0.012
    lap: float = 0.15
    keel: tuple[float, float] = (0.06, 0.07)
    transom: float = 0.035
    frames: float = 0.25
    frame_size: tuple[float, float] = (0.032, 0.026)
    gunwale: tuple[float, float] = (0.045, 0.04)
    thwarts: tuple[tuple[float, float], ...] = ()
    thwart_size: tuple[float, float] = (0.22, 0.03)
    tholes: bool = True
    floor: bool = True


def curve(points: Sequence[tuple[float, float]]) -> Callable[[float], float]:
    """A smooth monotone (Fritsch-Carlson) curve through [(t, value), ...], flat beyond the ends."""
    ts = [p[0] for p in points]
    vs = [p[1] for p in points]
    n = len(ts)
    if n == 1:
        return lambda t: vs[0]
    d = [(vs[i + 1] - vs[i]) / (ts[i + 1] - ts[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0.0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9.0:
            k = 3.0 / math.sqrt(s)
            m[i], m[i + 1] = k * a * d[i], k * b * d[i]

    def at(t: float) -> float:
        if t <= ts[0]:
            return vs[0]
        if t >= ts[-1]:
            return vs[-1]
        i = max(k for k in range(n - 1) if ts[k] <= t)
        h = ts[i + 1] - ts[i]
        u = (t - ts[i]) / h
        h00, h10 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u
        h01, h11 = -2 * u**3 + 3 * u**2, u**3 - u**2
        return h00 * vs[i] + h10 * h * m[i] + h01 * vs[i + 1] + h11 * h * m[i + 1]

    return at


class Hull:
    """The boat's moulded surface (starboard side) as a function of (t, v)."""

    def __init__(self, lines: Lines) -> None:
        self.lines = lines
        self._b = curve(lines.breadth)
        self._k = curve(lines.keel)
        self._s = curve(lines.sheer)
        self._f = curve(lines.fullness)

    def y(self, t: float) -> float:
        return (t - 0.5) * self.lines.length

    def keel(self, t: float) -> float:
        return self._k(t)

    def sheer(self, t: float) -> float:
        return self._s(t)

    def half(self, t: float) -> float:
        return self.lines.beam / 2 * self._b(t)

    def point(self, t: float, v: float) -> Vec:
        f = min(1.0, max(0.0, self._f(t)))
        g = (1 - f) * v + f * (1 - (1 - v) ** BILGE)
        zk, zs = self._k(t), self._s(t)
        return (self.half(t) * g, self.y(t), zk + (zs - zk) * v)

    def normal(self, t: float, v: float) -> Vec:
        """Outward (starboard) unit normal."""
        t0, t1 = max(0.0, t - EPS), min(1.0, t + EPS)
        v0, v1 = max(0.0, v - EPS), min(1.0, v + EPS)
        du = _sub(self.point(t1, v), self.point(t0, v))
        dv = _sub(self.point(t, v1), self.point(t, v0))
        n = _cross(dv, du)
        if n[0] < 0:
            n = (-n[0], -n[1], -n[2])
        return _norm(n)

    def v_at(self, t: float, z: float) -> float:
        zk, zs = self._k(t), self._s(t)
        return min(1.0, max(0.0, (z - zk) / (zs - zk)))


def boat_shells(lines: Lines, build: Build) -> list[tuple[Shell, str]]:
    """Every closed shell of the boat with its part: 'planks' (the strakes), 'timber' (keel,
    stem, transom, timbers, thwarts, floor, tholes), 'gunwale' (the gunwale and the sheer strake,
    painted). Both sides; symmetric in x."""
    hull = Hull(lines)
    out: list[tuple[Shell, str]] = []
    side: list[tuple[Shell, str]] = []
    n = build.strakes
    for i in range(n):
        lo = i / n - (build.lap / n if i else 0.0)
        hi = (i + 1) / n
        # The sheer strake is painted with the gunwale.
        # Neighbouring strakes end a hair apart inside the transom, so their ends never share a plane.
        end = 1.0 - 0.002 * (i % 2)
        side.append((_strake(hull, lo, hi, build.plank, i > 0, end), "gunwale" if i == n - 1 else "planks"))
    for t in _frame_stations(lines.length, build.frames):
        side.append((_timber(hull, t, build.frame_size), "timber"))
    side.append((_gunwale(hull, build.plank, build.gunwale), "gunwale"))
    for shell, part in side:
        out.append((shell, part))
        out.append((_mirror_x(shell), part))
    out.append((_keel(hull, build.keel), "timber"))
    out.append((_stem(hull, build.keel), "timber"))
    out.append((_transom(hull, build.transom, build.plank), "timber"))
    for t, below in build.thwarts:
        out += [(s, "timber") for s in _thwart(hull, t, below, build.thwart_size, build.tholes, build.gunwale)]
    if build.floor:
        out += [(s, "timber") for s in _floor(hull, build.thwarts)]
    return out


# --- Pieces ---------------------------------------------------------------------------------


def _strake(hull: Hull, lo: float, hi: float, plank: float, raised: bool, end: float = 1.0) -> Shell:
    """A strake between girths `lo` and `hi`: its inside lies on the hull at its upper edge and
    one plank out at its lower edge (where it laps over the strake below), so each land shows."""
    inner: list[list[Vec]] = []
    outer: list[list[Vec]] = []
    for j in range(STATIONS + 1):
        t = end * j / STATIONS
        row_in, row_out = [], []
        for k in range(ACROSS):
            u = k / (ACROSS - 1)
            v = lo + (hi - lo) * u
            p, nrm = hull.point(t, v), hull.normal(t, v)
            off = plank * (1 - u) if raised else 0.0
            row_in.append(_add(p, _mul(nrm, off)))
            row_out.append(_add(p, _mul(nrm, off + plank)))
        inner.append(row_in)
        outer.append(row_out)
    return _slab(outer, inner)


def _timber(hull: Hull, t: float, size: tuple[float, float]) -> Shell:
    """A bent timber (rib) inside the planking at t, from the keel to the gunwale."""
    sided, moulded = size
    y0 = hull.y(t) - sided / 2
    y1 = y0 + sided
    outer, inner = [], []
    for k in range(FRAME_SAMPLES + 1):
        v = 0.04 + 0.92 * k / FRAME_SAMPLES
        p, nrm = hull.point(t, v), hull.normal(t, v)
        # In the section's plane: drop the normal's y so the timber stays square to the keel.
        nn = _norm((nrm[0], 0.0, nrm[2]))
        a = _add(p, _mul(nn, -0.0015))  # just inside the planking: never in a strake's plane
        b = _add(p, _mul(nn, -moulded))
        outer.append([(a[0], y0, a[2]), (a[0], y1, a[2])])
        inner.append([(b[0], y0, b[2]), (b[0], y1, b[2])])
    return _slab(outer, inner)


def _gunwale(hull: Hull, plank: float, size: tuple[float, float]) -> Shell:
    """The gunwale along the sheer, outside the top strake, its top a little above the sheer."""
    wide, deep = size
    top, bottom = [], []
    for j in range(STATIONS + 1):
        t = 0.015 + 0.985 * j / STATIONS
        p = hull.point(t, 1.0)
        nrm = _norm((hull.normal(t, 1.0)[0], 0.0, 0.0001))
        out_ = _add(p, _mul(nrm, plank + wide * 0.55))
        in_ = _add(p, _mul(nrm, -wide * 0.45))
        top.append([(in_[0], p[1], p[2] + deep * 0.25), (out_[0], p[1], p[2] + deep * 0.25)])
        bottom.append([(in_[0], p[1], p[2] - deep * 0.75), (out_[0], p[1], p[2] - deep * 0.75)])
    return _slab(top, bottom)


def _keel(hull: Hull, size: tuple[float, float]) -> Shell:
    sided, moulded = size
    path = [(0.0, hull.y(t), hull.keel(t) - moulded / 2 + 0.01) for t in _steps(0.02, 1.0, STATIONS)]
    return sweep(path, [(-sided / 2, -moulded / 2), (sided / 2, -moulded / 2), (sided / 2, moulded / 2), (-sided / 2, moulded / 2)])


def _stem(hull: Hull, size: tuple[float, float]) -> Shell:
    """The stem: from the keel's fore end up past the sheer, raked forward, covering the strakes' hood ends."""
    sided, moulded = size
    z0, z1 = hull.keel(0.0) - moulded * 0.5, hull.sheer(0.0) + 0.06
    y0 = hull.y(0.0)
    rake = 0.04
    path = [(0.0, y0 + 0.06, hull.keel(0.04) - moulded / 2 + 0.01), (0.0, y0 + 0.01, z0 + 0.02)]
    path += [(0.0, y0 - rake * (z - z0) / (z1 - z0), z) for z in (z0 + (z1 - z0) * k / 8 for k in range(1, 9))]
    # The stem's middle sits on the planks' ends: shift it forward by half its moulding.
    return sweep(path, [(-sided / 2, -moulded / 2), (sided / 2, -moulded / 2), (sided / 2, moulded / 2), (-sided / 2, moulded / 2)], up=(0.0, -1.0, 0.0))


def _transom(hull: Hull, thick: float, plank: float) -> Shell:
    """The transom board at the stern, its outline the last section, a little proud of the planking."""
    t = 1.0
    proud = 2 * plank + 0.006
    loop: list[tuple[float, float]] = []
    for k in range(13):
        v = 1 - k / 12
        p, nrm = hull.point(t, v), hull.normal(t, v)
        q = _add(p, _mul(_norm((nrm[0], 0.0, nrm[2])), proud))
        loop.append((q[0], q[2]))
    zt = hull.sheer(t) + 0.03
    loop = [(loop[0][0], zt)] + loop
    loop = loop + [(-x, z) for x, z in reversed(loop[1:-1])] + [(-loop[0][0], zt)]
    loop = _dedupe2(loop)
    y0 = hull.y(t) - thick * 0.6
    y1 = y0 + thick
    return _prism(loop, y0, y1)


def _thwart(
    hull: Hull, t: float, below: float, size: tuple[float, float], tholes: bool, gunwale: tuple[float, float]
) -> list[Shell]:
    wide, thick = size
    h = hull.sheer(t) - below
    x = hull.point(t, hull.v_at(t, h))[0] - 0.004
    y = hull.y(t)
    out = [box((-x, y - wide / 2, h - thick), (x, y + wide / 2, h))]
    # Risers carry the thwart: a block under each end, against the timbers.
    xr = hull.point(t, hull.v_at(t, h - thick - 0.03))[0]
    out.append(box((xr - 0.055, y - wide / 2 - 0.01, h - thick - 0.05), (xr - 0.005, y + wide / 2 + 0.01, h - thick + 0.002)))
    out.append(box((-xr + 0.005, y - wide / 2 - 0.01, h - thick - 0.05), (-xr + 0.055, y + wide / 2 + 0.01, h - thick + 0.002)))
    if tholes:
        top = hull.sheer(t) + gunwale[1] * 0.25
        xg = hull.point(t, 1.0)[0] + 0.01
        for s in (-1.0, 1.0):
            for dy in (-0.035, 0.035):
                yy = y + wide / 2 + 0.1 + dy
                out.append(box((s * xg - 0.011, yy - 0.011, top - 0.01), (s * xg + 0.011, yy + 0.011, top + 0.12)))
    return out


def _floor(hull: Hull, thwarts: Sequence[tuple[float, float]]) -> list[Shell]:
    """Bottom boards over the timbers, between the first and last thwart."""
    if not thwarts:
        return []
    t0 = max(0.08, min(t for t, _ in thwarts) - 0.06)
    t1 = min(0.95, max(t for t, _ in thwarts) + 0.06)
    out = []
    for x in (-0.14, 0.0, 0.14):
        path = []
        for t in _steps(t0, t1, 12):
            v = 0.12
            z = hull.point(t, v)[2] - 0.02
            path.append((x, hull.y(t), z + 0.008))
        out.append(sweep(path, [(-0.06, -0.008), (0.06, -0.008), (0.06, 0.008), (-0.06, 0.008)]))
    return out


# --- Shell helpers --------------------------------------------------------------------------


def _slab(outer: list[list[Vec]], inner: list[list[Vec]]) -> Shell:
    """A closed slab between two grids of the same shape (rows along, columns across): outer
    faces wound outward, inner reversed, edge strips round the rim, end caps."""
    rows, cols = len(outer), len(outer[0])
    verts = [p for row in outer for p in row] + [p for row in inner for p in row]
    off = rows * cols

    def o(j: int, k: int) -> int:
        return j * cols + k

    faces: list[list[int]] = []
    for j in range(rows - 1):
        for k in range(cols - 1):
            faces.append([o(j, k), o(j, k + 1), o(j + 1, k + 1), o(j + 1, k)])
            faces.append([off + o(j, k), off + o(j + 1, k), off + o(j + 1, k + 1), off + o(j, k + 1)])
        faces.append([o(j, 0), o(j + 1, 0), off + o(j + 1, 0), off + o(j, 0)])
        faces.append([o(j, cols - 1), off + o(j, cols - 1), off + o(j + 1, cols - 1), o(j + 1, cols - 1)])
    for k in range(cols - 1):
        faces.append([o(0, k), off + o(0, k), off + o(0, k + 1), o(0, k + 1)])
        faces.append([o(rows - 1, k), o(rows - 1, k + 1), off + o(rows - 1, k + 1), off + o(rows - 1, k)])
    return _outward(verts, faces)


def _prism(loop: list[tuple[float, float]], y0: float, y1: float) -> Shell:
    """An outline in (x, z) extruded along y, its caps cut into triangles."""
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:] + loop[:1], strict=True))
    if area < 0:
        loop = loop[::-1]
    n = len(loop)
    verts = [(x, y0, z) for x, z in loop] + [(x, y1, z) for x, z in loop]
    tris = triangulate(loop)
    faces = [[a, b, c] for a, b, c in tris] + [[n + c, n + b, n + a] for a, b, c in tris]
    for k in range(n):
        k1 = (k + 1) % n
        faces.append([k, n + k, n + k1, k1])
    return _outward(verts, faces)


def _outward(verts: list[Vec], faces: list[list[int]]) -> Shell:
    """Turn every face round when the shell's signed volume says it is inside out."""
    vol = 0.0
    for f in faces:
        a = verts[f[0]]
        for i in range(1, len(f) - 1):
            b, c = verts[f[i]], verts[f[i + 1]]
            vol += a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if vol < 0:
        faces = [list(reversed(f)) for f in faces]
    return verts, faces


def _mirror_x(shell: Shell) -> Shell:
    verts, faces = shell
    return [(-x, y, z) for x, y, z in verts], [list(reversed(f)) for f in faces]


def _frame_stations(length: float, spacing: float) -> list[float]:
    count = max(1, int(length * 0.86 / spacing))
    return [0.07 + 0.86 * (k + 0.5) / count for k in range(count)]


def _steps(a: float, b: float, n: int) -> list[float]:
    return [a + (b - a) * k / n for k in range(n + 1)]


def _dedupe2(loop: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in loop:
        if not out or abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if abs(out[0][0] - out[-1][0]) + abs(out[0][1] - out[-1][1]) <= 1e-6:
        out.pop()
    return out
