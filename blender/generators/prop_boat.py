"""prop.boat: a ship's boat from her lines (assetkit/boat.py), with assembly pieces on top.

Cutters, jolly boats, gigs, launches: clinker-built boats whose planking follows a curved hull
that no assembly piece can describe. The spec gives her lines and what is built on them; the
generator lays the strakes, keel, stem, transom, timbers, gunwales, thwarts, floor and thole
pins, and adds any `pieces` (oars, a rudder, ring bolts) exactly as prop.assembly does.

    "params": {
      "hull": {
        "length": 5.5, "beam": 1.75, "depth": 0.72,
        "breadth":  [[0, 0.02], [0.12, 0.5], [0.35, 0.92], [0.55, 1.0], [0.85, 0.9], [1, 0.7]],
        "keel":     [[0, 0.42], [0.1, 0.12], [0.3, 0.07], [0.8, 0.07], [1, 0.1]],
        "sheer":    [[0, 0.98], [0.3, 0.76], [0.6, 0.72], [1, 0.84]],
        "fullness": [[0, 0.1], [0.3, 0.8], [0.7, 0.9], [1, 0.6]]
      },
      "build": {"strakes": 8, "plank": 0.012, "thwarts": [[0.3, 0.28], [0.5, 0.28]]},
      "slots": {"planks": "hull", "timber": "wood", "gunwale": "paint"},
      "pieces": [ ...assembly pieces... ],
      "bevel": 0.003
    }

`build` keys (all optional): strakes, plank, lap, keel [sided, moulded], transom, frames
(spacing), frame_size [sided, moulded], gunwale [wide, deep], thwarts [[t, below the sheer], ...],
thwart_size [wide, thick], tholes (true), floor (true). `slots` names the material of each of
the boat's parts. `parts`, `bevel`, `sharp_angle`, `detail`, `settle` as in prop.assembly.
"""

from __future__ import annotations

from collections.abc import Mapping

from assetkit import Asset
from assetkit.assembly import AssemblyError, build_pieces
from assetkit.boat import Build, Lines, boat_shells, curve
from blender.generators.prop_assembly import assemble
from blender.lib.spec import AssetSpec, SpecError, as_bool, as_float, as_int, as_mapping, positive_float, reject_unknown, require_key

MATERIAL_SLOTS: tuple[str, ...] = ()  # from the spec: the boat's `slots` and every piece's slot

_KEYS = ("hull", "build", "slots", "pieces", "parts", "bevel", "sharp_angle", "detail", "settle")
_HULL = ("length", "beam", "depth", "breadth", "keel", "sheer", "fullness")
_BUILD = (
    "strakes", "plank", "lap", "keel", "transom", "frames", "frame_size", "gunwale", "thwarts",
    "thwart_size", "tholes", "floor",
)
_PARTS = ("planks", "timber", "gunwale")


def build(spec: AssetSpec) -> Asset:
    raw = spec.params
    reject_unknown(raw, _KEYS, "params")
    lines = _lines(as_mapping(require_key(raw, "hull", "params"), "params.hull"))
    made = _build(as_mapping(raw.get("build", {}), "params.build"))
    slots = as_mapping(require_key(raw, "slots", "params"), "params.slots")
    reject_unknown(slots, _PARTS, "params.slots")
    missing = [p for p in _PARTS if p not in slots]
    if missing:
        raise SpecError(f"params.slots: give the material of {missing}")
    detail = as_float(raw.get("detail", 1.0), "params.detail")
    if not 0.25 <= detail <= 4.0:
        raise SpecError("params.detail: expected 0.25..4")
    bevel = as_float(raw.get("bevel", 0.0), "params.bevel")
    if bevel < 0:
        raise SpecError("params.bevel: must not be negative")
    # The boat's planks and timbers are too thin to bevel; the pieces decide for themselves.
    pieces = [(shell, str(slots[part]), False, None) for shell, part in boat_shells(lines, made)]
    if "pieces" in raw:
        parts = dict(as_mapping(raw.get("parts", {}), "params.parts"))
        try:
            pieces += build_pieces(raw["pieces"], parts, "params.pieces", detail, bevel)
        except AssemblyError as exc:
            raise SpecError(str(exc)) from exc
    return assemble(spec, pieces, raw)


def _curve(raw: object, path: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list) or not raw:
        raise SpecError(f"{path}: expected [[t, value], ...]")
    out = []
    for i, p in enumerate(raw):
        if not isinstance(p, list) or len(p) != 2:
            raise SpecError(f"{path}[{i}]: expected [t, value]")
        out.append((as_float(p[0], f"{path}[{i}][0]"), as_float(p[1], f"{path}[{i}][1]")))
    ts = [t for t, _ in out]
    if ts != sorted(ts) or len(set(ts)) != len(ts) or ts[0] < 0 or ts[-1] > 1:
        raise SpecError(f"{path}: t must rise from 0 to 1, each once (got {ts})")
    return tuple(out)


def _lines(raw: Mapping[str, object]) -> Lines:
    reject_unknown(raw, _HULL, "params.hull")
    p = "params.hull"
    lines = Lines(
        length=positive_float(require_key(raw, "length", p), f"{p}.length"),
        beam=positive_float(require_key(raw, "beam", p), f"{p}.beam"),
        depth=positive_float(require_key(raw, "depth", p), f"{p}.depth"),
        breadth=_curve(require_key(raw, "breadth", p), f"{p}.breadth"),
        keel=_curve(require_key(raw, "keel", p), f"{p}.keel"),
        sheer=_curve(require_key(raw, "sheer", p), f"{p}.sheer"),
        fullness=_curve(require_key(raw, "fullness", p), f"{p}.fullness"),
    )
    for t in (k / 20 for k in range(21)):
        if curve(lines.sheer)(t) <= curve(lines.keel)(t) + 0.05:
            raise SpecError(f"{p}: the sheer must stand above the keel everywhere (not at t = {t:.2f})")
    return lines


def _pair(raw: object, path: str) -> tuple[float, float]:
    if not isinstance(raw, list) or len(raw) != 2:
        raise SpecError(f"{path}: expected [a, b]")
    return (positive_float(raw[0], f"{path}[0]"), positive_float(raw[1], f"{path}[1]"))


def _build(raw: Mapping[str, object]) -> Build:
    reject_unknown(raw, _BUILD, "params.build")
    p = "params.build"
    d = Build()
    thwarts = raw.get("thwarts", [])
    if not isinstance(thwarts, list):
        raise SpecError(f"{p}.thwarts: expected [[t, below the sheer], ...]")
    made = Build(
        strakes=as_int(raw.get("strakes", d.strakes), f"{p}.strakes"),
        plank=positive_float(raw.get("plank", d.plank), f"{p}.plank"),
        lap=as_float(raw.get("lap", d.lap), f"{p}.lap"),
        keel=_pair(raw["keel"], f"{p}.keel") if "keel" in raw else d.keel,
        transom=positive_float(raw.get("transom", d.transom), f"{p}.transom"),
        frames=positive_float(raw.get("frames", d.frames), f"{p}.frames"),
        frame_size=_pair(raw["frame_size"], f"{p}.frame_size") if "frame_size" in raw else d.frame_size,
        gunwale=_pair(raw["gunwale"], f"{p}.gunwale") if "gunwale" in raw else d.gunwale,
        thwarts=tuple(
            (as_float(t[0], f"{p}.thwarts[{i}][0]"), positive_float(t[1], f"{p}.thwarts[{i}][1]"))
            for i, t in enumerate(thwarts)
            if isinstance(t, list) and len(t) == 2
        ),
        thwart_size=_pair(raw["thwart_size"], f"{p}.thwart_size") if "thwart_size" in raw else d.thwart_size,
        tholes=as_bool(raw.get("tholes", d.tholes), f"{p}.tholes"),
        floor=as_bool(raw.get("floor", d.floor), f"{p}.floor"),
    )
    if not 2 <= made.strakes <= 16:
        raise SpecError(f"{p}.strakes: expected 2..16, got {made.strakes}")
    if not 0 <= made.lap < 0.5:
        raise SpecError(f"{p}.lap: expected 0..0.5 of a strake's width, got {made.lap}")
    if len(made.thwarts) != len(thwarts) or any(not 0.05 <= t <= 0.95 for t, _ in made.thwarts):
        raise SpecError(f"{p}.thwarts: expected [[t, below the sheer], ...] with t in 0.05..0.95")
    return made
