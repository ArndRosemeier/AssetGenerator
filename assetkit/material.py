"""Material recipes: a material's look as layers over its surface, written in JSON.

A spec's material can carry a `pattern`; the kit evaluates it at any surface point (from the
point, its normal and how sharply the surface bends there), so it can be baked into textures
on any UV layout, and previewed without one:

    "bark": {"base_color": [0.17, 0.11, 0.07, 1], "roughness": 0.9, "metallic": 0.0,
             "pattern": {"layers": [
               {"grain": {"color": [0.08, 0.05, 0.03], "axis": "z", "spacing": 0.03, "warp": 1.5}},
               {"mottle": {"color": [0.3, 0.22, 0.12], "scale": 5, "coverage": 0.35}},
               {"cavities": {"color": [0.03, 0.02, 0.01], "radius": 0.03}}
             ]}}

Layers paint over the material's own colour in order, each through a mask (0..1) times its
`amount` (default 1); a layer with `roughness` blends that too, and one with `relief` (metres,
+ raised, - sunk) shapes the surface in the normal map: bark grooves, raised plates, cracks.
Colours are linear RGB 0..1, as `base_color`. Masks:

    mottle    patches of noise: `scale` (features per metre), `coverage` (0..1, share of the
              surface), `contrast` (edge sharpness), `octaves`, `seed`, `stretch` ([x, y, z]:
              [1, 1, 5] makes streaks five times taller than wide: bark, rain stains)
    grain     stripes: `axis` x | y | z (strata, planks) or radial (rings round the Z axis: a
              cut log), `spacing` (metres between lines), `warp` (wobble, in spacings),
              `sharpness` (thin lines when high), `seed`
    spots     round spots: `size` (diameter, metres), `spacing` (default twice the size),
              `density` (share of places with a spot), `softness` (0 crisp .. 1 blurred), `seed`
    gradient  along `axis` x | y | z: full at `from`, none at `to` (metres): grime at a base;
              `breakup` 0..1 makes the line ragged
    facing    where the surface faces `direction` ([0, 0, 1]: up) within `angle` degrees (45),
              fading over `soft` more (20): moss and snow on tops; `breakup`, `scale`, `seed`
    cells     cells `size` across: lines `width` wide where they meet (plates, scales, cracks,
              cobbles); `fill` 0..1 paints each cell's inside by a random share
    edges     where the surface bends outward tighter than `radius` metres: worn, lighter edges
    cavities  where it bends inward tighter than `radius`: dirt in creases
    (edges and cavities take `breakup` 0..1 to break the mask up with noise)
    bricks    the mortar joints of a running bond: `size` [length, height] (courses up Z, bricks
              along X and Y, so every wall face and corner shows the bond), `mortar` (joint
              width, 0.012), `fill` 0..1 paints each brick by a random share, `seed`

A pattern's `period` (metres, or [x, y, z]; 0: no repeat) makes every layer repeat after it,
each fitting a whole number of its features in: tiles laid side by side on that grid continue
one another's pattern.

Parsing is standard library only (so a spec is checked before Blender starts); evaluating
needs numpy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

Color = tuple[float, float, float]


class PatternError(ValueError):
    """A pattern that does not parse; the message names the path to the problem."""


@dataclass(frozen=True)
class Layer:
    kind: str
    color: Color
    amount: float
    roughness: float | None
    params: Mapping[str, object] = field(default_factory=dict)
    #: Metres the layer raises (+) or sinks (-) the surface where it paints, baked into the
    #: normal map: grooves in bark, raised plates, cracks.
    relief: float = 0.0
    #: Metres after which the layer repeats along x, y, z (0: never), from the pattern's `period`.
    period: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Pattern:
    layers: tuple[Layer, ...]
    period: tuple[float, float, float] = (0.0, 0.0, 0.0)


_KINDS: dict[str, dict[str, object]] = {
    # kind: {param: default (None = required)}
    "mottle": {"scale": 6.0, "coverage": 0.5, "contrast": 2.0, "octaves": 3, "seed": 0, "stretch": None},
    "grain": {"axis": "z", "spacing": None, "warp": 1.0, "sharpness": 2.0, "seed": 0},
    "spots": {"size": None, "spacing": None, "density": 0.7, "softness": 0.3, "seed": 0},
    "gradient": {"axis": "z", "from": None, "to": None, "breakup": 0.0, "seed": 0},
    "facing": {"direction": None, "angle": 45.0, "soft": 20.0, "breakup": 0.0, "scale": 8.0, "seed": 0},
    "cells": {"size": None, "width": None, "fill": 0.0, "seed": 0},
    "edges": {"radius": 0.05, "breakup": 0.0, "seed": 0},
    "cavities": {"radius": 0.05, "breakup": 0.0, "seed": 0},
    "bricks": {"size": None, "mortar": 0.012, "fill": 0.0, "seed": 0},
}
_COMMON = ("color", "amount", "roughness", "relief")


def parse_pattern(raw: object, path: str) -> Pattern:
    if not isinstance(raw, dict):
        raise PatternError(f"{path}: expected an object with `layers`")
    unknown = sorted(set(raw) - {"layers", "period"})
    if unknown:
        raise PatternError(f"{path}: unknown key(s) {unknown}; a pattern has `layers` (and `period`)")
    layers_raw = raw.get("layers")
    if not isinstance(layers_raw, list) or not layers_raw:
        raise PatternError(f"{path}.layers: expected a non-empty list")
    period = _period(raw.get("period", 0), f"{path}.period")
    layers = tuple(_layer(v, f"{path}.layers[{i}]") for i, v in enumerate(layers_raw))
    return Pattern(tuple(replace(layer, period=period) for layer in layers), period)


def _period(raw: object, path: str) -> tuple[float, float, float]:
    """`period`: metres after which the pattern repeats, one number for every axis or [x, y, z]
    (0: that axis never repeats)."""
    values = [raw, raw, raw] if _is_number(raw) else raw
    if not (isinstance(values, list) and len(values) == 3 and all(_is_number(v) and v >= 0 for v in values)):
        raise PatternError(f"{path}: expected metres (a number, or [x, y, z]; 0 for no repeat), got {raw!r}")
    return (float(values[0]), float(values[1]), float(values[2]))


def _layer(raw: object, path: str) -> Layer:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise PatternError(f"{path}: a layer is an object with one key, its kind: {sorted(_KINDS)}")
    ((kind, body),) = raw.items()
    here = f"{path}.{kind}"
    if kind not in _KINDS:
        raise PatternError(f"{path}: unknown layer '{kind}'; layers are {sorted(_KINDS)}")
    if not isinstance(body, dict):
        raise PatternError(f"{here}: expected an object")
    defaults = _KINDS[kind]
    unknown = sorted(set(body) - set(defaults) - set(_COMMON))
    if unknown:
        raise PatternError(f"{here}: unknown key(s) {unknown}; allowed are {sorted([*defaults, *_COMMON])}")
    color_raw = body.get("color")
    if not (
        isinstance(color_raw, list) and len(color_raw) in (3, 4) and all(_is_number(c) for c in color_raw)
    ):
        raise PatternError(f"{here}.color: expected [r, g, b] (linear 0..1)")
    if not all(0.0 <= c <= 1.0 for c in color_raw):
        raise PatternError(f"{here}.color: values must be 0..1")
    amount = _number(body, "amount", here, 1.0, 0.0, 1.0)
    roughness = _number(body, "roughness", here, None, 0.0, 1.0) if "roughness" in body else None
    relief = _number(body, "relief", here, 0.0, -0.05, 0.05)
    params: dict[str, object] = {}
    for key, default in defaults.items():
        if key == "direction":
            value = body.get(key, [0.0, 0.0, 1.0])
            if not (isinstance(value, list) and len(value) == 3 and all(_is_number(x) for x in value)):
                raise PatternError(f"{here}.direction: expected [x, y, z]")
            length = sum(float(x) * float(x) for x in value) ** 0.5
            if length < 1e-9:
                raise PatternError(f"{here}.direction: must not be zero")
            params[key] = tuple(float(x) / length for x in value)
        elif key == "stretch":
            value = body.get(key, [1.0, 1.0, 1.0])
            if not (
                isinstance(value, list) and len(value) == 3 and all(_is_number(x) and x > 0 for x in value)
            ):
                raise PatternError(f"{here}.stretch: expected [x, y, z], positive numbers")
            params[key] = tuple(float(x) for x in value)
        elif kind == "bricks" and key == "size":
            value = body.get(key)
            if not (
                isinstance(value, list) and len(value) == 2 and all(_is_number(x) and x > 0 for x in value)
            ):
                raise PatternError(f"{here}.size: expected [length, height] in metres, both positive")
            params[key] = (float(value[0]), float(value[1]))
        elif key in ("axis",):
            value = body.get(key, default)
            allowed = ("x", "y", "z", "radial") if kind == "grain" else ("x", "y", "z")
            if value not in allowed:
                raise PatternError(f"{here}.axis: expected one of {list(allowed)}")
            params[key] = value
        elif key in ("octaves", "seed"):
            value = body.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PatternError(f"{here}.{key}: expected a whole number 0 or more")
            params[key] = value
        else:
            if default is None and key not in body:
                if (kind, key) in (("spots", "spacing"), ("cells", "width")):
                    continue
                raise PatternError(f"{here}: missing '{key}'")
            params[key] = _number(body, key, here, default, None, None)  # type: ignore[arg-type]
    for key in ("scale", "spacing", "size", "radius", "contrast", "sharpness"):
        if key in params and kind != "bricks" and params[key] <= 0:  # type: ignore[operator]
            raise PatternError(f"{here}.{key}: must be positive")
    if kind == "facing" and not (0.0 <= params["angle"] <= 180.0 and params["soft"] >= 0.0):  # type: ignore[operator]
        raise PatternError(f"{here}: `angle` is 0..180 degrees and `soft` 0 or more")
    for key in ("coverage", "density", "softness", "breakup", "fill"):
        if key in params and not 0.0 <= params[key] <= 1.0:  # type: ignore[operator]
            raise PatternError(f"{here}.{key}: expected 0..1")
    if kind == "spots" and "spacing" in params and params["spacing"] < params["size"]:  # type: ignore[operator]
        raise PatternError(f"{here}.spacing: at least the spot size ({params['size']})")
    if kind == "bricks" and params["mortar"] < 0:  # type: ignore[operator]
        raise PatternError(f"{here}.mortar: 0 or more metres")
    if kind == "gradient" and params["from"] == params["to"]:
        raise PatternError(f"{here}: `from` and `to` must differ")
    color = (float(color_raw[0]), float(color_raw[1]), float(color_raw[2]))
    return Layer(kind, color, amount, roughness, params, relief)


def _is_number(v: object) -> bool:
    return not isinstance(v, bool) and isinstance(v, int | float)


def _number(
    fields: dict, key: str, path: str, default: float | None, lo: float | None, hi: float | None
) -> float:
    if key not in fields:
        if default is None:
            raise PatternError(f"{path}: missing '{key}'")
        return float(default)
    value = fields[key]
    if not _is_number(value):
        raise PatternError(f"{path}.{key}: expected a number, got {value!r}")
    value = float(value)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise PatternError(f"{path}.{key}: expected {lo}..{hi}, got {value}")
    return value


# --------------------------------------------------------------------------------------------
# Evaluation (numpy)
# --------------------------------------------------------------------------------------------


def evaluate(
    pattern: Pattern,
    surface: Surface,
    tri: object,
    bary: object,
    base_color: Color,
    base_roughness: float,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[object, object]:
    """Linear colour (N, 3) and roughness (N,) of the pattern at N points of `surface`, each
    given as a triangle index and barycentric weights (N, 3) in it. The pattern's coordinates
    have their origin at `origin` (in the surface's)."""
    import numpy as np

    q, bend, normal = surface.at(tri, bary)
    p = q - np.asarray(origin, dtype=np.float64)
    return evaluate_points(pattern, p, bend, normal, _creases_at(surface, q), base_color, base_roughness)


def evaluate_points(
    pattern: Pattern,
    points: object,
    bend: object,
    normals: object,
    creases: Callable[[float, bool], object],
    base_color: Color,
    base_roughness: float,
) -> tuple[object, object]:
    """`evaluate` at points given in pattern coordinates, with the surface's bend (N,) and
    unit normals (N, 3) there, and `creases(radius, outward)` (N,): how near each lies to a
    crease. A kit evaluates one tile's pattern on its neighbour's surface with it."""
    import numpy as np

    p = np.asarray(points, dtype=np.float64)
    color = np.tile(np.asarray(base_color, dtype=np.float64), (len(p), 1))
    rough = np.full(len(p), float(base_roughness))
    for layer in pattern.layers:
        m = _mask(layer, p, bend, normals, creases) * layer.amount
        color += (np.asarray(layer.color) - color) * m[:, None]
        if layer.roughness is not None:
            rough += (layer.roughness - rough) * m
    return np.clip(color, 0.0, 1.0), np.clip(rough, 0.0, 1.0)


def detail_normals(
    pattern: Pattern | None,
    surface: Surface,
    tri: object,
    bary: object,
    base: object,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    shape: Callable[[object], object] | None = None,
    step: float = 0.001,
) -> object:
    """Unit normals (N, 3) of the finished surface at N points of `surface` whose shipped
    normals are `base` (N, 3): moved onto the exact `shape` (a distance function in pattern
    coordinates, a sculpt's own) where given, and tilted by the pattern's `relief`. What the
    low mesh cannot hold, a normal map can: the bake stores these against `base`."""
    import numpy as np

    q, bend, _ = surface.at(tri, bary)
    o = np.asarray(origin, dtype=np.float64)
    n = np.asarray(base, dtype=np.float64)
    n = n / np.maximum(np.sqrt((n * n).sum(axis=1)), 1e-30)[:, None]
    if shape is not None:
        p = q - o
        h = step * 0.5
        d = shape(p)
        for _ in range(2):  # Newton steps onto the exact surface
            g = _gradient(shape, p, h, d)
            p = p - (d / np.maximum((g * g).sum(axis=1), 1e-12))[:, None] * g
            d = shape(p)
        exact = _gradient(shape, p, h, d)
        exact /= np.maximum(np.sqrt((exact * exact).sum(axis=1)), 1e-30)[:, None]
        # Where the projection went astray (to another part of the shape), keep the base normal.
        moved = np.sqrt(((p - (q - o)) ** 2).sum(axis=1))
        good = (np.abs(d) < step) & (moved < 0.05) & ((exact * n).sum(axis=1) > 0.2)
        n = np.where(good[:, None], exact, n)
    if pattern is not None and any(layer.relief != 0.0 for layer in pattern.layers):
        helper = np.where(np.abs(n[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
        t1 = np.cross(n, helper)
        t1 /= np.maximum(np.sqrt((t1 * t1).sum(axis=1)), 1e-30)[:, None]
        t2 = np.cross(n, t1)
        p0 = q - o

        def height(offset: object) -> object:
            pp = p0 + offset
            return _relief(pattern, pp, bend, n, _creases_at(surface, pp + o))

        e = step
        flat = height(t1 * 0.0)
        slope1 = (height(t1 * e) - flat) / e
        slope2 = (height(t2 * e) - flat) / e
        n = n - slope1[:, None] * t1 - slope2[:, None] * t2
        n /= np.maximum(np.sqrt((n * n).sum(axis=1)), 1e-30)[:, None]
    return n


def _gradient(shape: Callable[[object], object], p: object, h: float, here: object) -> object:
    """Forward differences from `here` (the distance at `p`): three evaluations, not six."""
    import numpy as np

    return np.stack([(shape(p + o) - here) / h for o in np.eye(3) * h], axis=1)


def _relief(
    pattern: Pattern, p: object, bend: object, normal: object, creases: Callable[[float, bool], object]
) -> object:
    """The surface's height (metres) the layers' relief adds at pattern-space points `p`."""
    import numpy as np

    total = np.zeros(len(p))  # type: ignore[arg-type]
    for layer in pattern.layers:
        if layer.relief != 0.0:
            total += layer.relief * layer.amount * _mask(layer, p, bend, normal, creases)
    return total


def coverage(
    pattern: Pattern,
    surface: Surface,
    tri: object,
    bary: object,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    weights: object | None = None,
) -> list[float]:
    """Per layer, the share of the given points it paints (its mask times its amount, averaged,
    by `weights` when given): a layer near 0 is invisible, one near 1 paints over everything
    beneath it."""
    import numpy as np

    q, bend, normal = surface.at(tri, bary)
    p = q - np.asarray(origin, dtype=np.float64)
    w = np.ones(len(q)) if weights is None else np.asarray(weights, dtype=np.float64)
    out = []
    for layer in pattern.layers:
        m = _mask(layer, p, bend, normal, _creases_at(surface, q)) * layer.amount
        out.append(float((m * w).sum() / max(w.sum(), 1e-30)))
    return out


def _creases_at(surface: Surface, points: object) -> Callable[[float, bool], object]:
    return lambda radius, outward: surface.near_creases(points, radius, outward)


def _mask(
    layer: Layer, p: object, c: object, normal: object, creases: Callable[[float, bool], object]
) -> object:
    import numpy as np

    k = layer.params
    per = layer.period
    if layer.kind == "mottle":
        # Stretch lengthens features along an axis: [1, 1, 4] gives streaks four times as tall.
        stretch = np.asarray(k["stretch"])
        n = _fbm(p / stretch, float(k["scale"]), int(k["octaves"]), int(k["seed"]), np.asarray(per) / stretch)  # type: ignore[arg-type, operator]
        threshold = (0.5 - float(k["coverage"])) * 0.6  # type: ignore[arg-type]
        return np.clip(0.5 + (n - threshold) * float(k["contrast"]) * 2.0, 0.0, 1.0)  # type: ignore[arg-type]
    if layer.kind == "grain":
        spacing = float(k["spacing"])  # type: ignore[arg-type]
        axis = str(k["axis"])
        if axis != "radial":
            spacing = _fit(spacing, per["xyz".index(axis)])
        u = _axis(p, axis)
        warp = float(k["warp"]) * spacing * _fbm(p, 1.0 / (4.0 * spacing), 2, int(k["seed"]), per)  # type: ignore[arg-type]
        stripes = 0.5 + 0.5 * np.cos(2.0 * np.pi * (u + warp) / spacing)
        return stripes ** float(k["sharpness"])  # type: ignore[arg-type]
    if layer.kind == "spots":
        size = float(k["size"])  # type: ignore[arg-type]
        spacing = float(k.get("spacing", 2.0 * size))  # type: ignore[arg-type]
        r = size / 2.0
        # Spots are balls in space, cut by the surface. Cells of this size put about one spot
        # centre within reach of each spacing x spacing patch of surface, so `spacing` and
        # `density` mean what they say on the surface (a ball's slice is a disc there).
        cell = (4.0 / 3.0 * r * spacing * spacing) ** (1.0 / 3.0)
        d = _nearest_spot(p, cell, float(k["density"]), int(k["seed"]), per)  # type: ignore[arg-type]
        inner = r * (1.0 - float(k["softness"]))  # type: ignore[arg-type]
        return 1.0 - _smoothstep(inner, r + 1e-9, d)
    if layer.kind == "gradient":
        lo, hi = float(k["from"]), float(k["to"])  # type: ignore[arg-type]
        u = _axis(p, str(k["axis"]))
        if float(k["breakup"]) > 0:  # type: ignore[arg-type]
            # A ragged line: the fade moves by up to half its length with noise its own size.
            span = abs(hi - lo)
            u = u + float(k["breakup"]) * span * 1.4 * _fbm(p, 1.0 / span, 3, int(k["seed"]), per)  # type: ignore[arg-type, operator]
        return 1.0 - _smoothstep(lo, hi, u)
    if layer.kind == "facing":
        # Where the surface faces `direction` within `angle` (full), fading over `soft` more
        # degrees: moss and snow on tops, dust on ledges, rust streaks under overhangs.
        d = np.asarray(k["direction"])
        cos = (normal * d).sum(axis=1)  # type: ignore[operator]
        angle, soft = float(k["angle"]), float(k["soft"])  # type: ignore[arg-type]
        if float(k["breakup"]) > 0:  # type: ignore[arg-type]
            cos = cos + float(k["breakup"]) * 1.2 * _fbm(p, float(k["scale"]), 3, int(k["seed"]), per)  # type: ignore[arg-type]
        full = np.cos(np.radians(angle))
        none = np.cos(np.radians(min(angle + max(soft, 1e-3), 180.0)))
        return _smoothstep(none, full, cos)
    if layer.kind == "cells":
        # Voronoi cells `size` across: lines `width` wide where cells meet (plates, scales,
        # cracks, cobbles), and with `fill` each cell's inside painted by a random share.
        size = float(k["size"])  # type: ignore[arg-type]
        width = float(k.get("width", 0.08 * size))  # type: ignore[arg-type]
        f1, f2, cell = _cells(p, size, int(k["seed"]), per)  # type: ignore[arg-type]
        lines = 1.0 - _smoothstep(0.0, width, f2 - f1)
        fill = float(k["fill"])  # type: ignore[arg-type]
        return np.maximum(lines, fill * cell) if fill > 0 else lines
    if layer.kind in ("edges", "cavities"):
        outward = layer.kind == "edges"
        bend = c if outward else -c  # type: ignore[operator]
        r = float(k["radius"])  # type: ignore[arg-type]
        # Smooth bends (a sculpt's shoulders, the crease where a leg joins) by curvature, sharp
        # ones (a bevelled crate's corners, which no vertex curvature sees) by distance.
        m = np.maximum(_smoothstep(0.5 / r, 1.5 / r, bend), creases(r, outward))
        breakup = float(k["breakup"])  # type: ignore[arg-type]
        if breakup > 0:
            n = _fbm(p, 0.6 / r, 2, int(k["seed"]), per)  # type: ignore[arg-type]
            m *= np.clip(1.0 - breakup * (0.5 - 2.0 * n), 0.0, 1.0)
        return m
    if layer.kind == "bricks":
        return _bricks(p, normal, k, per)
    raise AssertionError(layer.kind)


def _fit(length: float, period: float) -> float:
    """`length` nudged so a whole number of it fills `period` (unchanged when 0: no repeat)."""
    if period <= 0:
        return length
    return period / max(1, round(period / length))


def _sizes(size: float, period: object) -> object:
    """A feature size per axis, each fitted to that axis's period."""
    import numpy as np

    return np.array([_fit(size, float(q)) for q in period])  # type: ignore[attr-defined]


def _counts(sizes: object, period: object) -> object:
    """Whole features per period per axis (0: no repeat), for wrapping lattice indices."""
    import numpy as np

    per = np.asarray(period, dtype=np.float64)
    return np.where(per > 0, np.round(per / np.asarray(sizes)), 0).astype(np.int64)


def _wrap(index: object, count: object) -> object:
    import numpy as np

    return np.where(count > 0, index % np.maximum(count, 1), index)


def _bricks(p: object, normal: object, k: Mapping[str, object], period: tuple[float, float, float]) -> object:
    """Running bond: courses `height` tall up z, bricks `length` long along both x and y, each
    course shifted half a brick, so any wall face (and its corners) shows the bond. Mortar
    joints `mortar` wide; with `fill`, each brick painted by a random share of it."""
    import numpy as np

    length, height = k["size"]  # type: ignore[misc]
    length_x, length_y = _fit(float(length), period[0]), _fit(float(length), period[1])
    height = _fit(float(height), period[2])
    if period[2] > 0 and round(period[2] / height) % 2:  # an even number of courses repeats
        height = period[2] / (round(period[2] / height) + 1)
    sizes = np.array([length_x, length_y, height])
    counts = _counts(sizes, period)
    course = np.floor(p[:, 2] / height)  # type: ignore[index]
    shift = np.where(course % 2 == 1, 0.5, 0.0)
    gx = p[:, 0] / length_x + shift  # type: ignore[index]
    gy = p[:, 1] / length_y + shift  # type: ignore[index]
    gz = p[:, 2] / height  # type: ignore[index]
    # Distance (metres) to the nearest joint along each axis that runs across the surface (a
    # face turned to an axis would lie in that axis's joint plane), the nearest of them all.
    n = np.abs(np.asarray(normal))
    joint = np.minimum.reduce(
        [
            np.where(n[:, a] < 0.7, np.abs(g - np.round(g)) * s, np.inf)
            for a, (g, s) in enumerate(((gx, length_x), (gy, length_y), (gz, height)))
        ]
    )
    mortar = float(k["mortar"])  # type: ignore[arg-type]
    half = 0.5 * mortar
    lines = 1.0 - _smoothstep(0.8 * half, 1.2 * half + 1e-9, joint) if mortar > 0 else np.zeros(len(joint))
    fill = float(k["fill"])  # type: ignore[arg-type]
    if fill <= 0:
        return lines
    ix = _wrap(np.floor(gx).astype(np.int64), counts[0])
    iy = _wrap(np.floor(gy).astype(np.int64), counts[1])
    iz = _wrap(course.astype(np.int64), counts[2])
    return np.maximum(lines, fill * _hash(ix, iy, iz, int(k["seed"]), 21))  # type: ignore[arg-type]


def _smoothstep(lo: float, hi: float, x: object) -> object:
    import numpy as np

    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)  # type: ignore[operator]
    return t * t * (3.0 - 2.0 * t)


def _axis(p: object, axis: str) -> object:
    import numpy as np

    if axis == "radial":
        return np.sqrt(p[:, 0] * p[:, 0] + p[:, 1] * p[:, 1])  # type: ignore[index]
    return p[:, "xyz".index(axis)]  # type: ignore[index]


def _fbm(p: object, scale: float, octaves: int, seed: int, period: object = (0.0, 0.0, 0.0)) -> object:
    """Fractal noise in about [-0.7, 0.7], features 1/scale metres across; repeating every
    `period` metres along each axis where that is above 0 (the scale nudged to fit)."""
    import numpy as np

    from assetkit.noise import noise_array

    offset = np.array([seed * 31.7 + 5.3, seed * 17.3 + 11.1, seed * 47.1 + 2.9])
    total = np.zeros(len(p))  # type: ignore[arg-type]
    per = np.asarray(period, dtype=np.float64)
    freq = 1.0 / _sizes(1.0 / scale, per) if (per > 0).any() else scale
    weight, norm = 1.0, 0.0
    for _ in range(max(1, octaves)):
        q = p * freq + offset  # type: ignore[operator]
        cells = tuple(int(c) for c in np.where(per > 0, np.round(per * freq), 0))
        total += weight * noise_array(q[:, 0], q[:, 1], q[:, 2], cells)  # type: ignore[arg-type]
        norm += weight
        weight, freq = weight * 0.5, freq * 2.0
    return total / norm


def _hash(ix: object, iy: object, iz: object, seed: int, salt: int) -> object:
    """A deterministic number in [0, 1) per integer cell (64-bit mixing, wraps by design)."""
    import numpy as np

    with np.errstate(over="ignore"):
        h = (
            ix.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)  # type: ignore[attr-defined]
            ^ iy.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)  # type: ignore[attr-defined]
            ^ iz.astype(np.uint64) * np.uint64(0x165667B19E3779F9)  # type: ignore[attr-defined]
            ^ np.uint64((seed * 0x27D4EB2F165667C5 + salt * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF)
        )
        h ^= h >> np.uint64(31)
        h *= np.uint64(0xBF58476D1CE4E5B9)
        h ^= h >> np.uint64(29)
    return (h >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def _cells(
    p: object, size: float, seed: int, period: object = (0.0, 0.0, 0.0)
) -> tuple[object, object, object]:
    """Cellular noise: distances to the nearest and second nearest cell centre (one jittered
    centre per `size` cube) and a random number in [0, 1) for the nearest one's cell; repeating
    every `period` metres along each axis where that is above 0."""
    import numpy as np

    sizes = _sizes(size, period)
    counts = _counts(sizes, period)
    q = p / sizes  # type: ignore[operator]
    base = np.floor(q).astype(np.int64)
    f1 = np.full(len(q), np.inf)
    f2 = np.full(len(q), np.inf)
    tag = np.zeros(len(q))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cx, cy, cz = base[:, 0] + dx, base[:, 1] + dy, base[:, 2] + dz
                hx, hy, hz = _wrap(cx, counts[0]), _wrap(cy, counts[1]), _wrap(cz, counts[2])
                jx = cx + _hash(hx, hy, hz, seed, 11)
                jy = cy + _hash(hx, hy, hz, seed, 12)
                jz = cz + _hash(hx, hy, hz, seed, 13)
                d = np.sqrt(
                    ((q[:, 0] - jx) * sizes[0]) ** 2
                    + ((q[:, 1] - jy) * sizes[1]) ** 2
                    + ((q[:, 2] - jz) * sizes[2]) ** 2
                )
                nearer = d < f1
                f2 = np.where(nearer, f1, np.minimum(f2, d))
                tag = np.where(nearer, _hash(hx, hy, hz, seed, 14), tag)
                f1 = np.where(nearer, d, f1)
    return f1, f2, tag


def _nearest_spot(
    p: object, spacing: float, density: float, seed: int, period: object = (0.0, 0.0, 0.0)
) -> object:
    """Distance to the nearest spot centre: one jittered candidate per `spacing` cube, present
    with probability `density` (cellular noise); repeating every `period` where above 0."""
    import numpy as np

    sizes = _sizes(spacing, period)
    counts = _counts(sizes, period)
    q = p / sizes  # type: ignore[operator]
    base = np.floor(q).astype(np.int64)
    best = np.full(len(q), np.inf)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cx, cy, cz = base[:, 0] + dx, base[:, 1] + dy, base[:, 2] + dz
                hx, hy, hz = _wrap(cx, counts[0]), _wrap(cy, counts[1]), _wrap(cz, counts[2])
                present = _hash(hx, hy, hz, seed, 7) < density
                jx = cx + _hash(hx, hy, hz, seed, 1)
                jy = cy + _hash(hx, hy, hz, seed, 2)
                jz = cz + _hash(hx, hy, hz, seed, 3)
                d = np.sqrt(
                    ((q[:, 0] - jx) * sizes[0]) ** 2
                    + ((q[:, 1] - jy) * sizes[1]) ** 2
                    + ((q[:, 2] - jz) * sizes[2]) ** 2
                )
                best = np.where(present, np.minimum(best, d), best)
    return best


SHARP_DEG = 20.0  # an edge whose faces turn by more is a crease, not part of a smooth bend
# A crease this sharp or sharper wears (or collects dirt) fully. 45 degrees, so a right-angled
# edge reads the same before a one-segment bevel and after it (two creases of 45 degrees).
FULL_DEG = 45.0


class Surface:
    """What a pattern needs to know about a triangle mesh: where a point lies, how sharply the
    surface bends there, and where its creases are. Built once per mesh; needs numpy."""

    def __init__(self, vertices: object, triangles: object) -> None:
        import numpy as np

        v = np.asarray(vertices, dtype=np.float64)
        f = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
        self.vertices, self.triangles = v, f
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cross = np.cross(b - a, c - a)
        twice_area = np.sqrt((cross * cross).sum(axis=1))
        normal = cross / np.maximum(twice_area, 1e-30)[:, None]
        centre = (a + b + c) / 3.0

        # Each undirected edge with the (first) two faces that share it.
        directed = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        owner = np.tile(np.arange(len(f)), 3)
        key = np.sort(directed, axis=1)
        order = np.lexsort((key[:, 1], key[:, 0]))
        key, owner = key[order], owner[order]
        pair = np.nonzero((key[1:] == key[:-1]).all(axis=1))[0]
        pair = pair[np.concatenate([[True], pair[1:] != pair[:-1] + 1])] if len(pair) else pair
        ends = key[pair]
        f1, f2 = owner[pair], owner[pair + 1]
        cos = np.clip((normal[f1] * normal[f2]).sum(axis=1), -1.0, 1.0)
        angle = np.arccos(cos)
        mid = (v[ends[:, 0]] + v[ends[:, 1]]) / 2.0
        # Outward (convex) when the second face falls away below the first one's plane.
        convex = ((centre[f2] - mid) * normal[f1]).sum(axis=1) < 0
        signed = np.where(convex, angle, -angle)
        length = np.sqrt(((v[ends[:, 0]] - v[ends[:, 1]]) ** 2).sum(axis=1))
        sharp = angle >= np.radians(SHARP_DEG)

        # Mean curvature per vertex from the smooth edges round it (sum of turn x length over
        # 4x the vertex's area: 1/R on a sphere of radius R), smoothed over two rings.
        area = np.zeros(len(v))
        for k in range(3):
            np.add.at(area, f[:, k], twice_area / 6.0)
        turn = np.where(sharp, 0.0, signed * length)
        total = np.zeros(len(v))
        np.add.at(total, ends[:, 0], turn)
        np.add.at(total, ends[:, 1], turn)
        bend = total / np.maximum(4.0 * area, 1e-30)
        both = np.concatenate([ends, ends[:, ::-1]])
        count = np.maximum(np.bincount(both[:, 0], minlength=len(v)), 1).astype(np.float64)
        for _ in range(2):
            near = np.zeros(len(v))
            np.add.at(near, both[:, 0], bend[both[:, 1]])
            bend = 0.5 * bend + 0.5 * near / count
        self.bend = bend
        vertex_normal = np.zeros_like(v)
        for k in range(3):
            np.add.at(vertex_normal, f[:, k], cross)  # area-weighted
        self.normals = vertex_normal / np.maximum(np.sqrt((vertex_normal**2).sum(axis=1)), 1e-30)[:, None]

        self.crease_a = v[ends[sharp, 0]]
        self.crease_b = v[ends[sharp, 1]]
        self.crease_convex = convex[sharp]
        full = np.radians(FULL_DEG) - np.radians(SHARP_DEG)
        self.crease_strength = np.clip((angle[sharp] - np.radians(SHARP_DEG)) / full, 0.0, 1.0)

    def at(self, tri: object, bary: object) -> tuple[object, object, object]:
        """Points (N, 3), their bend (N,: 1/metres, outward positive) and unit normals (N, 3)
        for triangle indices (N,) and barycentric weights (N, 3)."""
        import numpy as np

        corners = self.triangles[np.asarray(tri, dtype=np.int64)]
        w = np.asarray(bary, dtype=np.float64)
        points = (self.vertices[corners] * w[:, :, None]).sum(axis=1)
        bend = (self.bend[corners] * w).sum(axis=1)
        normal = (self.normals[corners] * w[:, :, None]).sum(axis=1)
        normal /= np.maximum(np.sqrt((normal * normal).sum(axis=1)), 1e-30)[:, None]
        return points, bend, normal

    def near_creases(self, points: object, radius: float, outward: bool) -> object:
        """Per point, 1 on an outward (or inward) crease falling to 0 at `radius` from it,
        scaled by how sharp the crease is."""
        import numpy as np

        p = np.asarray(points, dtype=np.float64)
        out = np.zeros(len(p))
        pick = self.crease_convex == outward
        a, b, strength = self.crease_a[pick], self.crease_b[pick], self.crease_strength[pick]
        if not len(a) or not len(p):
            return out
        # A grid of cells (at least `radius` across, coarser when the creases are long next
        # to it): each crease is listed in every cell within `radius` of it, all in numpy.
        size = radius
        while True:
            lo = np.floor((np.minimum(a, b) - radius) / size).astype(np.int64)
            hi = np.floor((np.maximum(a, b) + radius) / size).astype(np.int64)
            span = hi - lo + 1
            if int(span.prod(axis=1).sum()) <= 400_000 or size > 1e3:
                break
            size *= 2.0
        count = span.prod(axis=1)
        owner = np.repeat(np.arange(len(a)), count)
        local = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
        sy, sz = span[owner, 1], span[owner, 2]
        cell_of = lo[owner] + np.stack([local // (sy * sz), (local // sz) % sy, local % sz], axis=1)
        base = cell_of.min(axis=0)
        dims = cell_of.max(axis=0) - base + 1

        def encode(c: object) -> object:
            c = c - base  # type: ignore[operator]
            inside = ((c >= 0) & (c < dims)).all(axis=1)
            return np.where(inside, (c[:, 0] * dims[1] + c[:, 1]) * dims[2] + c[:, 2], -1)

        keys = encode(cell_of)
        order = np.argsort(keys, kind="stable")
        keys, owner = keys[order], owner[order]
        point_key = encode(np.floor(p / size).astype(np.int64))
        first = np.searchsorted(keys, point_key, side="left")
        last = np.searchsorted(keys, point_key, side="right")
        first = np.where(point_key < 0, last, first)
        hits = last - first
        total = np.cumsum(hits)
        start = 0
        while start < len(p):  # in chunks of about two million (point, crease) pairs
            done = int(total[start - 1]) if start else 0
            end = max(int(np.searchsorted(total, done + 2_000_000, side="right")), start + 1)
            h = hits[start:end]
            if h.sum():
                idx = np.repeat(np.arange(start, end), h)
                near = owner[np.repeat(first[start:end] - (np.cumsum(h) - h), h) + np.arange(len(idx))]
                q, sa = p[idx], a[near]
                d = b[near] - sa
                t = np.clip(((q - sa) * d).sum(axis=1) / np.maximum((d * d).sum(axis=1), 1e-30), 0.0, 1.0)
                gap = q - (sa + t[:, None] * d)
                dist = np.sqrt((gap * gap).sum(axis=1))
                value = (1.0 - _smoothstep(0.0, radius, dist)) * strength[near]
                some = np.nonzero(h)[0]  # pairs come grouped by point: the max per group
                out[start + some] = np.maximum.reduceat(value, (np.cumsum(h) - h)[some])
            start = end
        return out
