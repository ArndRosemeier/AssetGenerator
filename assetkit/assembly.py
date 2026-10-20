"""Hard-surface props as JSON: exact pieces, placed, repeated and mirrored.

Where a sculpt (assetkit/sculpt.py) is clay, an assembly is a kit of parts: each piece is a
closed shell with its own material slot (iron, glass, wax), exact to the millimetre, with crisp
edges. Pieces may overlap (a strut through a cap); each stays closed, so QA holds.

    {"cylinder": {"a": [0, 0, 0], "b": [0, 0, 0.3], "radius": 0.07}, "slot": "glass"}
    {"box": {"size": [0.016, 0.016, 0.32]}, "at": [0.085, 0, 0.18], "slot": "iron",
     "repeat": {"around": 4, "start": 45}}
    {"group": [...pieces...], "at": [0, 0, 0.4], "mirror": "x"}

Shapes (metres; Z up; front is -Y):

    box       {"size": [x, y, z]} round the origin, or {"lower": [..], "upper": [..]}
    cylinder  {"a": [..], "b": [..], "radius": r, "radius_b": r?}  a rod or cone between points
    sphere    {"centre": [..], "radius": r}
    torus     {"centre": [..], "radius": R, "thickness": t, "axis": "x" | "y" | "z"}  a ring, hoop, handle
    lathe     {"profile": [[r, z], ...]}  turned about Z: caps, bases, bottles, bowls (open ends
              are closed to the axis)
    tube      {"path": [[x, y, z], ...], "radius": r, "smooth": true?}  a bent rod along a path
    extrude   {"outline": [[x, y], ...], "height": h}  a flat outline raised from z = 0: plates,
              blades, brackets
    sheet     {"size": [w, h], "thickness": t?, "divisions": [nx, nz]?}  a thin panel facing -Y,
              divided so it can bend: cloth, banners, sails

Every piece also takes:

    "slot"     its material (required, except in a group, whose pieces carry their own)
    "scale"    a number or [x, y, z], about the origin       applied first
    "rotate"   [x, y, z] degrees, X then Y then Z            then
    "at"       [x, y, z] metres                              then
    "repeat"   {"count": n, "step": [dx, dy, dz]} or {"around": n, "start": degrees}  (round Z)
    "mirror"   "x" | "y": add the mirror image across that plane
    "segments" round shapes: sides of the circle (default from the size: 8..64, and at least 12
               on rods, tubes and rings so they shade round)
    "bevel"    true | false: bevel this piece (or group) or not; by default a piece is bevelled
               when 8 bevel widths thick or more (posts, caps), not when thinner (rivets, wires)
    "bone"     with a rig: the bone it moves with, rigidly (a drum, a crank, a lid)
    "bones"    with a rig: a chain of bones it bends along, blended by distance (cloth, rope)

A `group` is a list of pieces moved, repeated and mirrored together; `{"ref": "name"}` uses
a piece from the spec's `parts`. Standard library only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from assetkit.shells import Shell, Vec, lathe, ring

SPACING = 0.012  # metres of arc per side of a round shape, by default
BEVEL_ROOM = 8.0  # a piece this many bevel widths thick (or more) is bevelled


class AssemblyError(ValueError):
    """An assembly that does not parse; the message names the path to the problem."""


Binding = str | tuple[str, ...] | None  # one bone (rigid), a chain (blended), or none
Piece = tuple[Shell, str, bool, Binding]  # a closed shell, its slot, whether to bevel it, its bones


def build_pieces(
    pieces: object, parts: Mapping[str, object], path: str, detail: float = 1.0, bevel: float = 0.0
) -> list[Piece]:
    """Every closed shell of the assembly with its slot and whether to bevel it, in spec order.
    A piece is bevelled when it is at least BEVEL_ROOM bevel widths thick everywhere (a cap, a
    post), not when thinner (a rivet, a wire, a thin hoop: a bevel would collapse or bloat it);
    its `"bevel": true | false` decides instead."""
    opts = (detail, bevel)
    if not isinstance(pieces, list) or not pieces:
        raise AssemblyError(f"{path}: expected a non-empty list of pieces")
    out: list[Piece] = []
    for i, node in enumerate(pieces):
        out += _piece(node, parts, f"{path}[{i}]", None, opts, depth=0)
    return out


_SHAPES = ("box", "cylinder", "sphere", "torus", "lathe", "tube", "extrude", "sheet", "group", "ref")
_COMMON = ("slot", "scale", "rotate", "at", "repeat", "mirror", "segments", "bevel", "bone", "bones")


def _piece(
    node: object,
    parts: Mapping[str, object],
    path: str,
    slot: str | None,
    opts: tuple[float, float],
    depth: int,
    bevel: bool | None = None,
    binding: Binding = None,
) -> list[Piece]:
    if depth > 16:
        raise AssemblyError(f"{path}: groups and refs nest too deep (a ref to itself?)")
    if not isinstance(node, dict):
        raise AssemblyError(f"{path}: expected a piece object")
    kinds = [k for k in node if k in _SHAPES]
    if len(kinds) != 1:
        raise AssemblyError(
            f"{path}: a piece has exactly one shape key of {list(_SHAPES)}, got {kinds or 'none'}"
        )
    kind = kinds[0]
    unknown = sorted(set(node) - {kind, *_COMMON})
    if unknown:
        raise AssemblyError(f"{path}: unknown key(s) {unknown}; a piece takes {list(_COMMON)}")
    here = f"{path}.{kind}"
    if "slot" in node:
        if not isinstance(node["slot"], str) or not node["slot"]:
            raise AssemblyError(f"{path}.slot: expected a material slot name")
        slot = node["slot"]
    if "bevel" in node:
        if not isinstance(node["bevel"], bool):
            raise AssemblyError(f"{path}.bevel: expected true or false")
        bevel = node["bevel"]
    if "bone" in node and "bones" in node:
        raise AssemblyError(f"{path}: give `bone` (moves rigidly with it) or `bones` (bends along them)")
    if "bone" in node:
        if not isinstance(node["bone"], str) or not node["bone"]:
            raise AssemblyError(f"{path}.bone: expected a bone name")
        binding = node["bone"]
    if "bones" in node:
        chain = node["bones"]
        if not isinstance(chain, list) or not chain or not all(isinstance(b, str) for b in chain):
            raise AssemblyError(f"{path}.bones: expected a list of bone names")
        binding = tuple(chain)

    if kind == "group":
        if not isinstance(node["group"], list) or not node["group"]:
            raise AssemblyError(f"{here}: expected a non-empty list of pieces")
        shells: list[Piece] = []
        for i, child in enumerate(node["group"]):
            shells += _piece(child, parts, f"{here}[{i}]", slot, opts, depth + 1, bevel, binding)
    elif kind == "ref":
        name = node["ref"]
        if not isinstance(name, str) or name not in parts:
            raise AssemblyError(f"{here}: no part named {name!r} in params.parts ({sorted(parts)})")
        shells = _piece(parts[name], parts, f"params.parts.{name}", slot, opts, depth + 1, bevel, binding)
    else:
        if slot is None:
            raise AssemblyError(f"{path}: missing 'slot' (the piece's material)")
        segments = node.get("segments")
        if segments is not None and (
            isinstance(segments, bool) or not isinstance(segments, int) or segments < 3
        ):
            raise AssemblyError(f"{path}.segments: expected a whole number 3 or more")
        body = node[kind]
        if not isinstance(body, dict):
            raise AssemblyError(f"{here}: expected an object")
        shape = _transform(_shape(kind, body, here, segments, opts), node, path)
        if bevel is None:
            lower = [min(v[k] for v in shape[0]) for k in range(3)]
            upper = [max(v[k] for v in shape[0]) for k in range(3)]
            bevel = min(u - lo for lo, u in zip(lower, upper, strict=True)) >= BEVEL_ROOM * opts[1]
        return _arrange([(shape, slot, bevel, binding)], node, path)

    shells = [(_transform(shell, node, path), s, b, w) for shell, s, b, w in shells]
    return _arrange(shells, node, path)


def _arrange(shells: list[Piece], node: dict, path: str) -> list[Piece]:
    """A placed piece's (or group's) repeats and mirror image."""
    if "repeat" in node:
        shells = _repeat(shells, node["repeat"], f"{path}.repeat")
    if "mirror" in node:
        axis = node["mirror"]
        if axis not in ("x", "y"):
            raise AssemblyError(f"{path}.mirror: expected 'x' or 'y'")
        k = "xyz".index(axis)
        shells = shells + [(_mirrored(shell, k), s, b, w) for shell, s, b, w in shells]
    return shells


# --------------------------------------------------------------------------------------------
# Shapes
# --------------------------------------------------------------------------------------------


def _shape(kind: str, f: dict, path: str, segments: int | None, opts: tuple[float, float]) -> Shell:
    detail = opts[0]

    def sides(radius: float, fixed: int | None = segments, low: int = 8, high: int = 64) -> int:
        if fixed is not None:
            return fixed
        return max(low, min(high, round(math.tau * radius / SPACING * detail / 4) * 4))

    if kind == "box":
        _only(f, ("size", "lower", "upper"), path)
        if "size" in f:
            sx, sy, sz = (v / 2 for v in _vec(f, "size", path, positive=True))
            lower, upper = (-sx, -sy, -sz), (sx, sy, sz)
        else:
            lower, upper = _vec(f, "lower", path), _vec(f, "upper", path)
            if not all(u > lo for lo, u in zip(lower, upper, strict=True)):
                raise AssemblyError(f"{path}: `upper` must be above `lower` on every axis")
        return _box(lower, upper)
    if kind == "cylinder":
        _only(f, ("a", "b", "radius", "radius_b"), path)
        a, b = _vec(f, "a", path), _vec(f, "b", path)
        r = _num(f, "radius", path, positive=True)
        rb = _num(f, "radius_b", path, positive=False) if "radius_b" in f else r
        if rb < 0:
            raise AssemblyError(f"{path}.radius_b: must not be negative")
        length = _dist(a, b)
        if length < 1e-6:
            raise AssemblyError(f"{path}: `a` and `b` must differ")
        profile = (
            [(0.0, 0.0), (r, 0.0), (rb, length), (0.0, length)]
            if rb > 0
            else [(0.0, 0.0), (r, 0.0), (0.0, length)]
        )
        return _along(lathe(profile, sides(max(r, rb), low=12)), a, b)
    if kind == "sphere":
        _only(f, ("centre", "radius"), path)
        c, r = _vec(f, "centre", path), _num(f, "radius", path, positive=True)
        n = sides(r)
        rows = max(4, n // 2)
        profile = [
            (r * math.sin(math.pi * i / rows), -r * math.cos(math.pi * i / rows)) for i in range(rows + 1)
        ]
        profile[0], profile[-1] = (0.0, -r), (0.0, r)
        verts, faces = lathe(profile, n)
        return [(x + c[0], y + c[1], z + c[2]) for x, y, z in verts], faces
    if kind == "torus":
        _only(f, ("centre", "radius", "thickness", "axis"), path)
        c = _vec(f, "centre", path)
        big, t = _num(f, "radius", path, positive=True), _num(f, "thickness", path, positive=True)
        if t / 2 >= big:
            raise AssemblyError(f"{path}: `thickness` must be under twice the `radius`")
        axis = f.get("axis", "z")
        if axis not in ("x", "y", "z"):
            raise AssemblyError(f"{path}.axis: expected 'x', 'y' or 'z'")
        minor = sides(t / 2, None, low=12, high=16)
        section = [
            (big + t / 2 * math.cos(math.tau * k / minor), t / 2 * math.sin(math.tau * k / minor))
            for k in range(minor)
        ]
        verts, faces = ring(section, sides(big))
        verts = [_axis_from_z(v, axis) for v in verts]
        return [(x + c[0], y + c[1], z + c[2]) for x, y, z in verts], faces
    if kind == "lathe":
        _only(f, ("profile",), path)
        raw = f.get("profile")
        if not isinstance(raw, list) or len(raw) < 2:
            raise AssemblyError(f"{path}.profile: expected [[radius, z], ...], two points or more")
        profile = [_pair(p, f"{path}.profile[{i}]") for i, p in enumerate(raw)]
        if any(r < 0 for r, _ in profile):
            raise AssemblyError(f"{path}.profile: radii must not be negative")
        if profile[0][0] > 0:
            profile.insert(0, (0.0, profile[0][1]))
        if profile[-1][0] > 0:
            profile.append((0.0, profile[-1][1]))
        if profile[-1][1] < profile[0][1]:
            profile.reverse()  # bottom to top, so the faces point outward
        biggest = max(r for r, _ in profile)
        if biggest <= 0:
            raise AssemblyError(f"{path}.profile: needs a radius above 0")
        return lathe(profile, sides(biggest))
    if kind == "tube":
        _only(f, ("path", "radius", "smooth"), path)
        raw = f.get("path")
        if not isinstance(raw, list) or len(raw) < 2:
            raise AssemblyError(f"{path}.path: expected [[x, y, z], ...], two points or more")
        points = [_triple(p, f"{path}.path[{i}]") for i, p in enumerate(raw)]
        r = _num(f, "radius", path, positive=True)
        smooth = f.get("smooth", True)
        if not isinstance(smooth, bool):
            raise AssemblyError(f"{path}.smooth: expected true or false")
        if smooth and len(points) > 2:
            points = _catmull_rom(points, max(2, round(8 * detail)))
        return _tube(points, r, sides(r, low=12, high=16))
    if kind == "sheet":
        _only(f, ("size", "thickness", "divisions"), path)
        size = f.get("size")
        if not (isinstance(size, list) and len(size) == 2 and all(_is_number(v) and v > 0 for v in size)):
            raise AssemblyError(f"{path}.size: expected [width, height], positive")
        t = _num(f, "thickness", path, positive=True) if "thickness" in f else 0.004
        if "divisions" in f:
            div = f["divisions"]
            if not (
                isinstance(div, list) and len(div) == 2 and all(isinstance(v, int) and v >= 1 for v in div)
            ):
                raise AssemblyError(f"{path}.divisions: expected [across, down], whole numbers 1 or more")
            nx, nz = div
        else:  # about 6 cm squares, so it can bend smoothly
            nx = max(2, min(64, round(size[0] / 0.06 * detail)))
            nz = max(2, min(64, round(size[1] / 0.06 * detail)))
        return _sheet(float(size[0]), float(size[1]), t, nx, nz)
    if kind == "extrude":
        _only(f, ("outline", "height"), path)
        raw = f.get("outline")
        if not isinstance(raw, list) or len(raw) < 3:
            raise AssemblyError(f"{path}.outline: expected [[x, y], ...], three points or more")
        outline = [_pair(p, f"{path}.outline[{i}]") for i, p in enumerate(raw)]
        h = _num(f, "height", path, positive=True)
        return _extrude(outline, h)
    raise AssertionError(kind)


def _box(lower: Vec, upper: Vec) -> Shell:
    xs, ys, zs = (lower[0], upper[0]), (lower[1], upper[1]), (lower[2], upper[2])
    verts = [(xs[i & 1], ys[(i >> 1) & 1], zs[i >> 2]) for i in range(8)]
    faces = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    return verts, faces


def _along(shell: Shell, a: Vec, b: Vec) -> Shell:
    """A shell built along +Z from the origin, turned to run from `a` towards `b`."""
    d = _sub(b, a)
    z = _unit(d)
    helper = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
    x = _unit(_cross(helper, z))
    y = _cross(z, x)
    verts, faces = shell
    return [
        (
            a[0] + vx * x[0] + vy * y[0] + vz * z[0],
            a[1] + vx * x[1] + vy * y[1] + vz * z[1],
            a[2] + vx * x[2] + vy * y[2] + vz * z[2],
        )
        for vx, vy, vz in verts
    ], faces


def _axis_from_z(v: Vec, axis: str) -> Vec:
    x, y, z = v
    if axis == "x":
        return (z, x, y)  # (x, y, z) -> (z, x, y) is a rotation: winding kept
    if axis == "y":
        return (y, z, x)
    return v


def _tube(points: list[Vec], r: float, n: int) -> Shell:
    """A round rod along `points`, capped, with frames carried along the path (no twisting)."""
    verts: list[Vec] = []
    faces: list[list[int]] = []
    m = len(points)
    tangent = [_unit(_sub(points[min(j + 1, m - 1)], points[max(j - 1, 0)])) for j in range(m)]
    helper = (0.0, 0.0, 1.0) if abs(tangent[0][2]) < 0.9 else (1.0, 0.0, 0.0)
    side = _unit(_cross(tangent[0], helper))
    for j in range(m):
        t = tangent[j]
        side = _unit(_sub(side, _mul(t, _dot(side, t))))  # carried: keep square to the path
        up = _cross(t, side)
        for k in range(n):
            a = math.tau * k / n
            verts.append(_add(points[j], _add(_mul(side, r * math.cos(a)), _mul(up, r * math.sin(a)))))
    for j in range(m - 1):
        for k in range(n):
            k1 = (k + 1) % n
            faces.append([j * n + k, j * n + k1, (j + 1) * n + k1, (j + 1) * n + k])
    faces.append(list(reversed(range(n))))
    faces.append([(m - 1) * n + k for k in range(n)])
    return _outward(verts, faces)


def _sheet(w: float, h: float, t: float, nx: int, nz: int) -> Shell:
    """A thin panel, `w` across X and `h` down Z round the origin, `t` thick along Y, its faces
    divided nx by nz so it can bend: cloth, banners, sails, paper, leather."""
    verts: list[Vec] = []
    faces: list[list[int]] = []
    for y in (-t / 2, t / 2):
        for j in range(nz + 1):
            for i in range(nx + 1):
                verts.append((-w / 2 + w * i / nx, y, h / 2 - h * j / nz))
    stride = (nx + 1) * (nz + 1)

    def at(side: int, i: int, j: int) -> int:
        return side * stride + j * (nx + 1) + i

    for j in range(nz):
        for i in range(nx):
            faces.append([at(0, i, j), at(0, i, j + 1), at(0, i + 1, j + 1), at(0, i + 1, j)])
            faces.append([at(1, i, j), at(1, i + 1, j), at(1, i + 1, j + 1), at(1, i, j + 1)])
    rim = [(i, 0) for i in range(nx)] + [(nx, j) for j in range(nz)]
    rim += [(i, nz) for i in range(nx, 0, -1)] + [(0, j) for j in range(nz, 0, -1)]
    for k in range(len(rim)):
        (i0, j0), (i1, j1) = rim[k], rim[(k + 1) % len(rim)]
        faces.append([at(0, i0, j0), at(0, i1, j1), at(1, i1, j1), at(1, i0, j0)])
    return _outward(verts, faces)


def _extrude(outline: list[tuple[float, float]], h: float) -> Shell:
    area = sum(
        x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1], strict=True)
    )
    if abs(area) < 1e-12:
        raise AssemblyError("extrude: the outline has no area")
    if area < 0:
        outline = list(reversed(outline))
    n = len(outline)
    verts = [(x, y, 0.0) for x, y in outline] + [(x, y, h) for x, y in outline]
    faces = [list(reversed(range(n))), [n + k for k in range(n)]]
    for k in range(n):
        k1 = (k + 1) % n
        faces.append([k, k1, n + k1, n + k])
    return verts, faces


def _catmull_rom(points: list[Vec], steps: int) -> list[Vec]:
    out: list[Vec] = []
    ext = [points[0], *points, points[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(
                tuple(  # type: ignore[arg-type]
                    0.5
                    * (
                        2 * p1[k]
                        + (-p0[k] + p2[k]) * t
                        + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                        + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3
                    )
                    for k in range(3)
                )
            )
    out.append(points[-1])
    return out


def _outward(verts: list[Vec], faces: list[list[int]]) -> Shell:
    """Flip every face if the shell's signed volume is negative."""
    volume = 0.0
    for face in faces:
        a = verts[face[0]]
        for k in range(1, len(face) - 1):
            b, c = verts[face[k]], verts[face[k + 1]]
            volume += _dot(a, _cross(b, c))
    if volume < 0:
        faces = [list(reversed(face)) for face in faces]
    return verts, faces


# --------------------------------------------------------------------------------------------
# Placing
# --------------------------------------------------------------------------------------------


def _transform(shell: Shell, node: dict, path: str) -> Shell:
    verts, faces = shell
    flip = False
    if "scale" in node:
        raw = node["scale"]
        if _is_number(raw):
            sx = sy = sz = float(raw)
        else:
            sx, sy, sz = _vec(node, "scale", path)
        if min(abs(sx), abs(sy), abs(sz)) < 1e-9:
            raise AssemblyError(f"{path}.scale: must not be zero")
        flip = sx * sy * sz < 0
        verts = [(x * sx, y * sy, z * sz) for x, y, z in verts]
    if "rotate" in node:
        rx, ry, rz = (math.radians(v) for v in _vec(node, "rotate", path))
        verts = [_rot(v, rx, ry, rz) for v in verts]
    if "at" in node:
        ox, oy, oz = _vec(node, "at", path)
        verts = [(x + ox, y + oy, z + oz) for x, y, z in verts]
    if flip:
        faces = [list(reversed(face)) for face in faces]
    return verts, faces


def _rot(v: Vec, rx: float, ry: float, rz: float) -> Vec:
    x, y, z = v
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x, y, z)


def _repeat(shells: list[Piece], raw: object, path: str) -> list[Piece]:
    if not isinstance(raw, dict):
        raise AssemblyError(f"{path}: expected {{'count', 'step'}} or {{'around', 'start'}}")
    out: list[Piece] = []
    if "around" in raw:
        _only(raw, ("around", "start"), path)
        n = raw["around"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise AssemblyError(f"{path}.around: expected a whole number 1 or more")
        start = math.radians(_num(raw, "start", path, positive=False)) if "start" in raw else 0.0
        for k in range(n):
            a = start + math.tau * k / n
            for (verts, faces), slot, bevel, binding in shells:
                out.append((([_rot(v, 0.0, 0.0, a) for v in verts], faces), slot, bevel, binding))
        return out
    _only(raw, ("count", "step"), path)
    n = raw.get("count")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise AssemblyError(f"{path}.count: expected a whole number 1 or more")
    dx, dy, dz = _vec(raw, "step", path)
    for k in range(n):
        for (verts, faces), slot, bevel, binding in shells:
            out.append(
                (([(x + k * dx, y + k * dy, z + k * dz) for x, y, z in verts], faces), slot, bevel, binding)
            )
    return out


def _mirrored(shell: Shell, k: int) -> Shell:
    verts, faces = shell
    return (
        [tuple(-c if i == k else c for i, c in enumerate(v)) for v in verts],  # type: ignore[misc]
        [list(reversed(face)) for face in faces],
    )


def bevelled_triangles(mesh: object, marks: Sequence[float] | None = None, angle_deg: float = 30.0) -> int:
    """About how many triangles a one-segment bevel of edges sharper than `angle_deg` (between
    vertices marked 0.5 or more, with `marks`) adds to a mesh (`assetkit.Mesh`): a strip of two
    per edge, a corner patch where three meet."""
    verts = mesh.vertices  # type: ignore[attr-defined]
    normals = []
    for face in mesh.faces:  # type: ignore[attr-defined]
        n = (0.0, 0.0, 0.0)
        for k in range(len(face)):  # Newell's method: right for any planar polygon
            a, b = verts[face[k]], verts[face[(k + 1) % len(face)]]
            n = _add(
                n,
                ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])),
            )
        normals.append(_unit(n))
    owners: dict[tuple[int, int], list[int]] = {}
    for f, face in enumerate(mesh.faces):  # type: ignore[attr-defined]
        for k in range(len(face)):
            a, b = face[k], face[(k + 1) % len(face)]
            owners.setdefault((min(a, b), max(a, b)), []).append(f)
    limit = math.cos(math.radians(angle_deg))
    sharp = [
        e
        for e, fs in owners.items()
        if len(fs) == 2
        and _dot(normals[fs[0]], normals[fs[1]]) < limit
        and (marks is None or (marks[e[0]] >= 0.5 and marks[e[1]] >= 0.5))
    ]
    corners: dict[int, int] = {}
    for a, b in sharp:
        corners[a] = corners.get(a, 0) + 1
        corners[b] = corners.get(b, 0) + 1
    return 2 * len(sharp) + 2 * sum(1 for n in corners.values() if n >= 3)


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def _only(f: dict, keys: Sequence[str], path: str) -> None:
    unknown = sorted(set(f) - set(keys))
    if unknown:
        raise AssemblyError(f"{path}: unknown key(s) {unknown}; allowed are {list(keys)}")


def _is_number(v: object) -> bool:
    return not isinstance(v, bool) and isinstance(v, int | float)


def _num(f: dict, key: str, path: str, positive: bool) -> float:
    if key not in f:
        raise AssemblyError(f"{path}: missing '{key}'")
    v = f[key]
    if not _is_number(v):
        raise AssemblyError(f"{path}.{key}: expected a number, got {v!r}")
    if positive and v <= 0:
        raise AssemblyError(f"{path}.{key}: must be positive")
    return float(v)


def _vec(f: dict, key: str, path: str, positive: bool = False) -> Vec:
    if key not in f:
        raise AssemblyError(f"{path}: missing '{key}'")
    v = f[key]
    if not (isinstance(v, list) and len(v) == 3 and all(_is_number(c) for c in v)):
        raise AssemblyError(f"{path}.{key}: expected [x, y, z]")
    if positive and min(v) <= 0:
        raise AssemblyError(f"{path}.{key}: every value must be positive")
    return (float(v[0]), float(v[1]), float(v[2]))


def _pair(v: object, path: str) -> tuple[float, float]:
    if not (isinstance(v, list) and len(v) == 2 and all(_is_number(c) for c in v)):
        raise AssemblyError(f"{path}: expected [a, b]")
    return (float(v[0]), float(v[1]))


def _triple(v: object, path: str) -> Vec:
    if not (isinstance(v, list) and len(v) == 3 and all(_is_number(c) for c in v)):
        raise AssemblyError(f"{path}: expected [x, y, z]")
    return (float(v[0]), float(v[1]), float(v[2]))


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dist(a: Vec, b: Vec) -> float:
    return math.sqrt(_dot(_sub(a, b), _sub(a, b)))


def _unit(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 1.0)
