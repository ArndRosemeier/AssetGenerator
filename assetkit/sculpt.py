"""Shape trees as JSON: the form a spec gives `sdf` shapes, so an agent can model without Python.

A node is an object with exactly one key, its kind:

    {"sphere":    {"centre": [x, y, z], "radius": r}}
    {"ellipsoid": {"centre": [x, y, z], "radii": [rx, ry, rz]}}
    {"box":       {"centre": [x, y, z], "size": [sx, sy, sz], "radius": r?}}
    {"capsule":   {"a": [x, y, z], "b": [x, y, z], "radius": r, "radius_b": r?}}
    {"cylinder":  {"a": [x, y, z], "b": [x, y, z], "radius": r, "rounding": r?}}
    {"torus":     {"centre": [x, y, z], "radius": r, "thickness": t, "axis": "x" | "y" | "z"?}}
    {"union":     [node, ...]}
    {"smooth_union": {"k": metres, "shapes": [node, ...]}}
    {"subtract":  {"from": node, "cut": [node, ...], "k": metres?}}
    {"intersect": {"shapes": [node, ...], "k": metres?}}
    {"below":     {"height": z, "shape": node}}            the part of shape under z (cut flat on top)
    {"above":     {"height": z, "shape": node}}            the part of shape over z (cut flat below)
    {"move":      {"by": [x, y, z], "shape": node}}
    {"rotate":    {"degrees": [x, y, z], "shape": node}}   X first, then Y, then Z, about the origin
    {"scale":     {"by": factor, "shape": node}}
    {"mirror_x":  node}                                     node and its mirror image across x = 0
    {"displace":  {"amount": metres, "scale": per_metre, "seed": int?, "octaves": int?, "shape": node}}
    {"round":     {"radius": metres, "shape": node}}
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
    "rotate": lambda f, p, path, s: sdf.rotate(
        _inner(f, p, path, s), tuple(math.radians(v) for v in _vec(f, "degrees", path))
    ),
    "scale": lambda f, p, path, s: sdf.scale(_inner(f, p, path, s), _num(f, "by", path)),
    "displace": lambda f, p, path, s: sdf.displace(
        _inner(f, p, path, s),
        _num(f, "amount", path),
        _num(f, "scale", path),
        _int(f, "seed", path, 0),
        _int(f, "octaves", path, 1),
    ),  # fmt: skip
    "round": lambda f, p, path, s: sdf.round_(_inner(f, p, path, s), _num(f, "radius", path)),
    "shell": lambda f, p, path, s: sdf.shell(_inner(f, p, path, s), _num(f, "thickness", path)),
}

_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "sphere": (("centre", "radius"), ("centre", "radius")),
    "ellipsoid": (("centre", "radii"), ("centre", "radii")),
    "box": (("centre", "size", "radius"), ("centre", "size")),
    "capsule": (("a", "b", "radius", "radius_b"), ("a", "b", "radius")),
    "cylinder": (("a", "b", "radius", "rounding"), ("a", "b", "radius")),
    "torus": (("centre", "radius", "thickness", "axis"), ("centre", "radius", "thickness")),
    "smooth_union": (("k", "shapes"), ("k", "shapes")),
    "subtract": (("from", "cut", "k"), ("from", "cut")),
    "intersect": (("shapes", "k"), ("shapes",)),
    "below": (("height", "shape"), ("height", "shape")),
    "above": (("height", "shape"), ("height", "shape")),
    "move": (("by", "shape"), ("by", "shape")),
    "rotate": (("degrees", "shape"), ("degrees", "shape")),
    "scale": (("by", "shape"), ("by", "shape")),
    "displace": (("amount", "scale", "seed", "octaves", "shape"), ("amount", "scale", "shape")),
    "round": (("radius", "shape"), ("radius", "shape")),
    "shell": (("thickness", "shape"), ("thickness", "shape")),
}


def _axis(fields: dict, path: str) -> str:
    axis = fields.get("axis", "z")
    if axis not in ("x", "y", "z"):
        raise SculptError(f"{path}.axis: expected 'x', 'y' or 'z', got {axis!r}")
    return axis
