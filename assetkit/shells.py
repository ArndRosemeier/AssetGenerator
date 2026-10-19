"""Closed shells built in plain Python, for `MeshBuilder.add` (or `BoxBuilder.add_mesh`).

Every function returns `(vertices, faces)`: a watertight shell whose faces wind
counter-clockwise seen from outside, so QA's manifold and signed-volume checks
hold for whatever a generator puts together from them. Shells may overlap each
other freely (timber and iron do); each stays closed on its own.

Free of `bpy` so the shapes can be checked without Blender.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

Vec = tuple[float, float, float]
Shell = tuple[list[Vec], list[list[int]]]


def lathe(
    profile: Sequence[tuple[float, float]], segments: int, *, start: float = 0.0, end: float = math.tau
) -> Shell:
    """Revolve `profile` [(radius, z), ...] about Z, counter-clockwise in the (radius, z) plane.

    A full turn: the profile runs from the axis at the bottom, out, up and back to the axis at the
    top (first and last radius 0, which become single pole vertices): a bucket, a barrel head.
    A partial turn (`start`/`end`): the profile is a closed loop off the axis, and flat end caps
    close the slice: a barrel stave.
    """
    full = abs((end - start) - math.tau) < 1e-9
    if profile[0][0] != 0.0 or profile[-1][0] != 0.0:
        if full:
            raise ValueError("A full lathe profile must start and end on the axis (radius 0)")
    rings = segments if full else segments + 1
    verts: list[Vec] = []
    faces: list[list[int]] = []
    index: list[list[int]] = []
    for r, z in profile:
        if r == 0.0 and full:
            verts.append((0.0, 0.0, z))
            index.append([len(verts) - 1] * rings)
            continue
        row = []
        for k in range(rings):
            a = start + (end - start) * k / segments
            verts.append((r * math.cos(a), r * math.sin(a), z))
            row.append(len(verts) - 1)
        index.append(row)
    # A partial sweep revolves a closed loop: its last point joins back to its first.
    for i in range(len(profile) - (1 if full else 0)):
        lo, hi = index[i], index[(i + 1) % len(profile)]
        for k in range(segments):
            k1 = (k + 1) % rings if full else k + 1
            quad = [lo[k], lo[k1], hi[k1], hi[k]]
            # Drop repeated pole corners: a triangle fan at the axis.
            face: list[int] = []
            for v in quad:
                if v not in face:
                    face.append(v)
            if len(face) >= 3:
                faces.append(face)
    if not full:
        # The profile is a closed loop in (r, z) when partial: cap both ends with it.
        first = [index[i][0] for i in range(len(profile))]
        last = [index[i][rings - 1] for i in range(len(profile))]
        faces.append(_dedupe(first))
        faces.append(list(reversed(_dedupe(last))))
    return verts, faces


def _dedupe(loop: list[int]) -> list[int]:
    out: list[int] = []
    for v in loop:
        if not out or out[-1] != v:
            out.append(v)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def ring(profile: Sequence[tuple[float, float]], segments: int) -> Shell:
    """A closed loop profile [(radius, z), ...] (counter-clockwise in the (r, z) plane) revolved
    about Z: a hoop, a rim, a torus of any section."""
    verts: list[Vec] = []
    faces: list[list[int]] = []
    n = len(profile)
    for k in range(segments):
        a = math.tau * k / segments
        for r, z in profile:
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for k in range(segments):
        k1 = (k + 1) % segments
        for i in range(n):
            i1 = (i + 1) % n
            faces.append([k * n + i, k1 * n + i, k1 * n + i1, k * n + i1])
    return verts, faces


def sweep(
    path: Sequence[Vec],
    section: Sequence[tuple[float, float]],
    *,
    scale: Callable[[float], tuple[float, float]] = lambda t: (1.0, 1.0),
    up: Vec = (0.0, 0.0, 1.0),
) -> Shell:
    """Sweep a closed `section` [(x, y), ...] (counter-clockwise) along `path`, capped at both ends.
    `scale(t)` (t from 0 to 1 along the path) stretches the section's x and y: tapers, blades.
    The section's y follows `up` (kept square to the path), its x the side."""
    if len(path) < 2:
        raise ValueError("A sweep needs at least two path points")
    verts: list[Vec] = []
    faces: list[list[int]] = []
    n = len(section)
    m = len(path)
    for j, p in enumerate(path):
        a = path[max(j - 1, 0)]
        b = path[min(j + 1, m - 1)]
        t = _norm(_sub(b, a))
        side = _norm(_cross(t, up))
        if _len(side) < 1e-6:
            side = _norm(_cross(t, (1.0, 0.0, 0.0)))
        nup = _cross(side, t)
        sx, sy = scale(j / (m - 1))
        for x, y in section:
            verts.append(_add(p, _add(_mul(side, x * sx), _mul(nup, y * sy))))
    for j in range(m - 1):
        for i in range(n):
            i1 = (i + 1) % n
            faces.append([j * n + i, (j + 1) * n + i, (j + 1) * n + i1, j * n + i1])
    faces.append([i for i in range(n)])
    faces.append([(m - 1) * n + i for i in reversed(range(n))])
    return verts, faces


def circle(radius: float, segments: int) -> list[tuple[float, float]]:
    return [
        (radius * math.cos(math.tau * k / segments), radius * math.sin(math.tau * k / segments))
        for k in range(segments)
    ]


def rect(half_x: float, half_y: float) -> list[tuple[float, float]]:
    return [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)]


def transform(shell: Shell, f: Callable[[Vec], Vec]) -> Shell:
    verts, faces = shell
    return [f(v) for v in verts], faces


def place(shell: Shell, at: Vec, *, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> Shell:
    """Rotate by roll (about Y), then pitch (about X), then yaw (about Z), then move to `at`."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)

    def f(v: Vec) -> Vec:
        x, y, z = v
        x, z = x * cr + z * sr, -x * sr + z * cr
        y, z = y * cp - z * sp, y * sp + z * cp
        x, y = x * cy - y * sy, x * sy + y * cy
        return (x + at[0], y + at[1], z + at[2])

    return transform(shell, f)


def box(lower: Vec, upper: Vec) -> Shell:
    """An axis-aligned box between two corners: eight vertices, six quads."""
    xs, ys, zs = (lower[0], upper[0]), (lower[1], upper[1]), (lower[2], upper[2])
    verts = [(xs[i & 1], ys[(i >> 1) & 1], zs[i >> 2]) for i in range(8)]
    faces = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    return verts, faces


def grid_cube(cuts: int) -> Shell:
    """The unit cube round the origin (side 1) with every face cut into a (cuts + 1)^2 quad grid,
    neighbouring faces sharing their edge vertices: a box to bend into a block or a boulder."""
    if cuts < 0:
        raise ValueError(f"cuts must be 0 or more, got {cuts}")
    n = cuts + 1
    index: dict[tuple[int, int, int], int] = {}
    verts: list[Vec] = []

    def vert(cell: tuple[int, int, int]) -> int:
        if cell not in index:
            index[cell] = len(verts)
            verts.append((cell[0] / n - 0.5, cell[1] / n - 0.5, cell[2] / n - 0.5))
        return index[cell]

    faces: list[list[int]] = []
    # Each face's two grid axes (b, c) with b x c pointing out along the face's own axis a.
    for a, b, c in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        for side in (0, n):
            for u in range(n):
                for v in range(n):
                    quad = []
                    for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                        cell = [0, 0, 0]
                        cell[a], cell[b], cell[c] = side, u + du, v + dv
                        quad.append(vert((cell[0], cell[1], cell[2])))
                    faces.append(quad if side == n else quad[::-1])
    return verts, faces


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(a: Vec) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _norm(a: Vec) -> Vec:
    n = _len(a) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)
