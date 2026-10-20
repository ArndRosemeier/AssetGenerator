"""Shape trees as JSON: the form a spec gives `sdf` shapes, so an agent can model without Python.

A node is an object with exactly one key, its kind:

    {"sphere":    {"centre": [x, y, z], "radius": r}}
    {"ellipsoid": {"centre": [x, y, z], "radii": [rx, ry, rz]}}
    {"box":       {"centre": [x, y, z], "size": [sx, sy, sz], "radius": r?}}
    {"capsule":   {"a": [x, y, z], "b": [x, y, z], "radius": r, "radius_b": r?}}
    {"cylinder":  {"a": [x, y, z], "b": [x, y, z], "radius": r, "rounding": r?}}
    {"cone":      {"a": [x, y, z], "b": [x, y, z], "radius": r, "radius_b": r}}  flat-ended (0: a point)
    {"torus":     {"centre": [x, y, z], "radius": r, "thickness": t, "axis": "x" | "y" | "z"?}}
    {"loft":      {"sections": [[z, half_width, half_depth, y?, x?], ...]}}
                  horizontal ellipses up z, flowing smoothly from one to the next, flat at both
                  ends: a torso, a vase, a bottle, a barrel, an oval trunk
    {"sweep":     {"points": [[x, y, z], ...], "radius": r | [r, ...]}}
                  a smooth tube through the points, its radius flowing from one point's to the
                  next: trunks that swell, limbs with muscle, tails, horns, roots, branches
    {"union":     [node, ...]}
    {"smooth_union": {"k": metres, "shapes": [node, ...]}}
    {"subtract":  {"from": node, "cut": [node, ...], "k": metres?}}
    {"intersect": {"shapes": [node, ...], "k": metres?}}
    {"below":     {"height": z, "shape": node}}            the part of shape under z (cut flat on top)
    {"above":     {"height": z, "shape": node}}            the part of shape over z (cut flat below)
    {"move":      {"by": [x, y, z], "shape": node}}
    {"rotate":    {"degrees": [x, y, z], "about": [x, y, z]?, "shape": node}}
                  X first, then Y, then Z, about the point `about` (default the origin): tilt a
                  chest forward about the waist, a head about the neck
    {"scale":     {"by": factor, "shape": node}}
    {"mirror_x":  node}                                     node and its mirror image across x = 0
    {"repeat":    {"count": n, "step": [x, y, z], "shape": node}}   n copies, each `step` further on
    {"repeat":    {"around": n, "start": degrees?, "shape": node}}  n copies turned evenly round Z
    {"scatter":   {"on": node, "shape": node, "count": n?, "seed": s?, "at": [[x, y], ...]?,
                   "spacing": m?, "facing": [x, y, z]?, "angle": degrees?, "sink": m?,
                   "align": bool?, "sizes": [lo, hi]?}}
                  copies of `shape` (modelled at the origin, pointing up) set on the surface of
                  `on`: dropped straight down at each `at` (x, y), and `count` more at seeded
                  places `spacing` apart where it faces within `angle` (90) of `facing` (up);
                  stood along the surface (`align`, default true), sunk `sink` into it, sized
                  between `sizes` (1, 1). Only the copies: union them with `on`.
    {"displace":  {"amount": metres, "scale": per_metre, "seed": int?, "octaves": int?, "shape": node}}
    {"round":     {"radius": metres, "shape": node}}
    {"squash":    {"axis": [x, y, z], "by": factor, "about": [x, y, z], "shape": node}}
                  scaled by `factor` along any direction about a point: a palm flattened, a
                  torso deeper than wide, a foot spread (factor > 1 stretches)
    {"layer":     {"on": node, "thickness": metres, "within": node, "k": metres?}}
                  a layer `thickness` thick over the surface of `on`, where it lies inside
                  `within`: clothing, a sash, bracers, a strap, a helmet, armour plates, moss.
                  Union it with `on`; paint it with the same `within` for its own material.
    {"shell":     {"thickness": metres, "shape": node}}
    {"ref":       "name"}                                   a node from the spec's `parts`

Errors name the path to the bad node (`params.shape.subtract.cut[1].sphere.radius`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping

from assetkit import sdf

Node = object


class SculptError(ValueError):
    """A shape tree that does not parse."""


def build_shape(node: Node, parts: Mapping[str, Node], path: str, _seen: tuple[str, ...] = ()) -> sdf.Shape:
    if not isinstance(node, dict) or len(node) != 1:
        raise SculptError(f"{path}: a shape is an object with exactly one key (its kind), got {node!r:.80}")
    ((kind, body),) = node.items()
    here = f"{path}.{kind}"
    if kind == "ref":
        name = _str(body, here)
        if name not in parts:
            raise SculptError(f"{here}: no part named '{name}'; parts are {sorted(parts)}")
        if name in _seen:
            raise SculptError(f"{here}: part '{name}' refers to itself")
        return build_shape(parts[name], parts, f"parts.{name}", (*_seen, name))
    if kind == "mirror_x":
        return sdf.mirror_x(build_shape(body, parts, here, _seen))
    if kind == "union":
        return sdf.union(*_shapes(body, parts, here, _seen))
    builder = _BUILDERS.get(kind)
    if builder is None:
        kinds = sorted([*_BUILDERS, "ref", "union", "mirror_x"])
        raise SculptError(f"{path}: unknown shape kind '{kind}'; kinds are {kinds}")
    fields = _object(body, here)
    allowed, required = _FIELDS[kind]
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        raise SculptError(f"{here}: unknown key(s) {unknown}; allowed are {sorted(allowed)}")
    missing = sorted(set(required) - set(fields))
    if missing:
        raise SculptError(f"{here}: missing key(s) {missing}")
    try:
        return builder(fields, parts, here, _seen)
    except ValueError as exc:
        if isinstance(exc, SculptError):
            raise
        raise SculptError(f"{here}: {exc}") from exc


def _object(value: Node, path: str) -> dict:
    if not isinstance(value, dict):
        raise SculptError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _str(value: Node, path: str) -> str:
    if not isinstance(value, str):
        raise SculptError(f"{path}: expected a string, got {type(value).__name__}")
    return value


def _num(fields: dict, key: str, path: str, default: float | None = None) -> float:
    value = fields.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SculptError(f"{path}.{key}: expected a number, got {value!r}")
    return float(value)


def _int(fields: dict, key: str, path: str, default: int) -> int:
    value = fields.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SculptError(f"{path}.{key}: expected an integer, got {value!r}")
    return value


def _vec(fields: dict, key: str, path: str) -> tuple[float, float, float]:
    value = fields[key]
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(isinstance(v, bool) or not isinstance(v, int | float) for v in value)
    ):
        raise SculptError(f"{path}.{key}: expected [x, y, z] numbers, got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def _shapes(value: Node, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> list[sdf.Shape]:
    if not isinstance(value, list) or not value:
        raise SculptError(f"{path}: expected a non-empty list of shapes")
    return [build_shape(v, parts, f"{path}[{i}]", seen) for i, v in enumerate(value)]


def _one_or_more(value: Node, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> list[sdf.Shape]:
    return _shapes(value if isinstance(value, list) else [value], parts, path, seen)


Builder = Callable[[dict, Mapping[str, Node], str, tuple[str, ...]], sdf.Shape]


def _smooth_union(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    shapes = _shapes(f["shapes"], parts, f"{path}.shapes", seen)
    k = _num(f, "k", path)
    result = shapes[0]
    for shape in shapes[1:]:
        result = sdf.smooth_union(result, shape, k)
    return result


def _subtract(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    result = build_shape(f["from"], parts, f"{path}.from", seen)
    for cut in _one_or_more(f["cut"], parts, f"{path}.cut", seen):
        result = sdf.subtract(result, cut, _num(f, "k", path, 0.0))
    return result


def _intersect(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    shapes = _shapes(f["shapes"], parts, f"{path}.shapes", seen)
    result = shapes[0]
    for shape in shapes[1:]:
        result = sdf.intersect(result, shape, _num(f, "k", path, 0.0))
    return result


def _inner(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    return build_shape(f["shape"], parts, f"{path}.shape", seen)


_BUILDERS: dict[str, Builder] = {
    "sphere": lambda f, p, path, s: sdf.sphere(_vec(f, "centre", path), _num(f, "radius", path)),
    "ellipsoid": lambda f, p, path, s: sdf.ellipsoid(_vec(f, "centre", path), _vec(f, "radii", path)),
    "box": lambda f, p, path, s: sdf.box(
        _vec(f, "centre", path), _vec(f, "size", path), _num(f, "radius", path, 0.0)
    ),
    "capsule": lambda f, p, path, s: sdf.capsule(
        _vec(f, "a", path),
        _vec(f, "b", path),
        _num(f, "radius", path),
        _num(f, "radius_b", path) if "radius_b" in f else None,
    ),  # fmt: skip
    "cylinder": lambda f, p, path, s: sdf.cylinder(
        _vec(f, "a", path), _vec(f, "b", path), _num(f, "radius", path), _num(f, "rounding", path, 0.0)
    ),
    "cone": lambda f, p, path, s: sdf.cone(
        _vec(f, "a", path), _vec(f, "b", path), _num(f, "radius", path), _num(f, "radius_b", path)
    ),
    "sweep": lambda f, p, path, s: _sweep(f, path),
    "loft": lambda f, p, path, s: _loft(f, path),
    "repeat": lambda f, p, path, s: _repeat(f, p, path, s),
    "scatter": lambda f, p, path, s: _scatter(f, p, path, s),
    "torus": lambda f, p, path, s: sdf.torus(
        _vec(f, "centre", path), _num(f, "radius", path), _num(f, "thickness", path), _axis(f, path)
    ),
    "smooth_union": _smooth_union,
    "subtract": _subtract,
    "intersect": _intersect,
    "below": lambda f, p, path, s: sdf.intersect(
        _inner(f, p, path, s), sdf.half_space(_num(f, "height", path))
    ),
    "above": lambda f, p, path, s: sdf.intersect(
        _inner(f, p, path, s), sdf.half_space(_num(f, "height", path), above=True)
    ),
    "move": lambda f, p, path, s: sdf.move(_inner(f, p, path, s), _vec(f, "by", path)),
    "rotate": lambda f, p, path, s: _rotate(f, p, path, s),
    "scale": lambda f, p, path, s: sdf.scale(_inner(f, p, path, s), _num(f, "by", path)),
    "displace": lambda f, p, path, s: sdf.displace(
        _inner(f, p, path, s),
        _num(f, "amount", path),
        _num(f, "scale", path),
        _int(f, "seed", path, 0),
        _int(f, "octaves", path, 1),
    ),  # fmt: skip
    "round": lambda f, p, path, s: sdf.round_(_inner(f, p, path, s), _num(f, "radius", path)),
    "squash": lambda f, p, path, s: sdf.squash(
        _inner(f, p, path, s), _vec(f, "axis", path), _num(f, "by", path), _vec(f, "about", path)
    ),
    "layer": lambda f, p, path, s: sdf.intersect(
        sdf.round_(build_shape(f["on"], p, f"{path}.on", s), _num(f, "thickness", path)),
        build_shape(f["within"], p, f"{path}.within", s),
        _num(f, "k", path, 0.0),
    ),
    "shell": lambda f, p, path, s: sdf.shell(_inner(f, p, path, s), _num(f, "thickness", path)),
}

_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "sphere": (("centre", "radius"), ("centre", "radius")),
    "ellipsoid": (("centre", "radii"), ("centre", "radii")),
    "box": (("centre", "size", "radius"), ("centre", "size")),
    "capsule": (("a", "b", "radius", "radius_b"), ("a", "b", "radius")),
    "cylinder": (("a", "b", "radius", "rounding"), ("a", "b", "radius")),
    "torus": (("centre", "radius", "thickness", "axis"), ("centre", "radius", "thickness")),
    "cone": (("a", "b", "radius", "radius_b"), ("a", "b", "radius", "radius_b")),
    "sweep": (("points", "radius"), ("points", "radius")),
    "loft": (("sections",), ("sections",)),
    "repeat": (("count", "step", "around", "start", "shape"), ("shape",)),
    "scatter": (
        ("on", "shape", "count", "seed", "at", "spacing", "facing", "angle", "sink", "align", "sizes"),
        ("on", "shape"),
    ),
    "smooth_union": (("k", "shapes"), ("k", "shapes")),
    "subtract": (("from", "cut", "k"), ("from", "cut")),
    "intersect": (("shapes", "k"), ("shapes",)),
    "below": (("height", "shape"), ("height", "shape")),
    "above": (("height", "shape"), ("height", "shape")),
    "move": (("by", "shape"), ("by", "shape")),
    "rotate": (("degrees", "about", "shape"), ("degrees", "shape")),
    "scale": (("by", "shape"), ("by", "shape")),
    "displace": (("amount", "scale", "seed", "octaves", "shape"), ("amount", "scale", "shape")),
    "round": (("radius", "shape"), ("radius", "shape")),
    "squash": (("axis", "by", "about", "shape"), ("axis", "by", "about", "shape")),
    "layer": (("on", "thickness", "within", "k"), ("on", "thickness", "within")),
    "shell": (("thickness", "shape"), ("thickness", "shape")),
}


def _loft(f: dict, path: str) -> sdf.Shape:
    sections = f["sections"]
    ok = (
        isinstance(sections, list)
        and len(sections) >= 2
        and all(
            isinstance(row, list)
            and len(row) in (3, 5)
            and all(isinstance(v, int | float) and not isinstance(v, bool) for v in row)
            for row in sections
        )
    )
    if not ok:
        raise SculptError(
            f"{path}.sections: expected two or more [z, half_width, half_depth] (or [z, w, d, y, x])"
        )
    return sdf.loft(sections)


def _sweep(f: dict, path: str) -> sdf.Shape:
    points = f["points"]
    if not isinstance(points, list) or len(points) < 2:
        raise SculptError(f"{path}.points: expected two or more [x, y, z] points")
    pts = [_vec({"p": p}, "p", f"{path}.points[{i}]") for i, p in enumerate(points)]
    radius = f["radius"]
    if isinstance(radius, list):
        if len(radius) != len(pts) or any(
            isinstance(r, bool) or not isinstance(r, int | float) for r in radius
        ):
            raise SculptError(f"{path}.radius: expected one number, or one per point ({len(pts)})")
        return sdf.sweep(pts, [float(r) for r in radius])
    return sdf.sweep(pts, _num(f, "radius", path))


def _rotate(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    angles = tuple(math.radians(v) for v in _vec(f, "degrees", path))
    inner = _inner(f, parts, path, seen)
    if "about" not in f:
        return sdf.rotate(inner, angles)  # type: ignore[arg-type]
    pivot = _vec(f, "about", path)
    back = tuple(-c for c in pivot)
    return sdf.move(sdf.rotate(sdf.move(inner, back), angles), pivot)  # type: ignore[arg-type]


def _repeat(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    inner = _inner(f, parts, path, seen)
    if "around" in f:
        if "count" in f or "step" in f:
            raise SculptError(f"{path}: either `around` (and `start`) or `count` and `step`")
        n = _int(f, "around", path, 0)
        if n < 1:
            raise SculptError(f"{path}.around: expected a whole number 1 or more")
        return sdf.repeat(inner, n, around=True, start=math.radians(_num(f, "start", path, 0.0)))
    if "count" not in f or "step" not in f:
        raise SculptError(f"{path}: needs `count` and `step`, or `around`")
    n = _int(f, "count", path, 0)
    if n < 1:
        raise SculptError(f"{path}.count: expected a whole number 1 or more")
    return sdf.repeat(inner, n, step=_vec(f, "step", path))


def _scatter(f: dict, parts: Mapping[str, Node], path: str, seen: tuple[str, ...]) -> sdf.Shape:
    on = build_shape(f["on"], parts, f"{path}.on", seen)
    inner = _inner(f, parts, path, seen)
    at_raw = f.get("at", [])
    if not isinstance(at_raw, list) or not all(
        isinstance(xy, list)
        and len(xy) == 2
        and all(isinstance(c, int | float) and not isinstance(c, bool) for c in xy)
        for xy in at_raw
    ):
        raise SculptError(f"{path}.at: expected [[x, y], ...]")
    sizes = f.get("sizes", [1.0, 1.0])
    if not (
        isinstance(sizes, list)
        and len(sizes) == 2
        and all(isinstance(v, int | float) and v > 0 for v in sizes)
    ):
        raise SculptError(f"{path}.sizes: expected [smallest, largest] scale factors")
    align = f.get("align", True)
    if not isinstance(align, bool):
        raise SculptError(f"{path}.align: expected true or false")
    count = _int(f, "count", path, 0)
    if count < 0 or (count == 0 and not at_raw):
        raise SculptError(f"{path}: give a `count` of 1 or more, or `at` places")
    try:
        return sdf.scatter(
            on,
            inner,
            count=count,
            seed=_int(f, "seed", path, 0),
            at=[(float(x), float(y)) for x, y in at_raw],
            spacing=_num(f, "spacing", path, 0.0),
            facing=_vec(f, "facing", path) if "facing" in f else (0.0, 0.0, 1.0),
            angle_deg=_num(f, "angle", path, 90.0),
            sink=_num(f, "sink", path, 0.0),
            align=align,
            sizes=(float(min(sizes)), float(max(sizes))),
        )
    except ValueError as exc:
        raise SculptError(f"{path}: {exc}") from exc


def _axis(fields: dict, path: str) -> str:
    axis = fields.get("axis", "z")
    if axis not in ("x", "y", "z"):
        raise SculptError(f"{path}.axis: expected 'x', 'y' or 'z', got {axis!r}")
    return axis
