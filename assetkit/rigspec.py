"""Rigs as JSON: bones, what each carries, legs, and clips. Needs numpy.

    "rig": {
      "bones": {
        "body":    {"head": [0, 0.2, 0.2], "tail": [0, -0.15, 0.22]},
        "head":    {"parent": "body", "head": [0, -0.12, 0.24], "tail": [0, -0.3, 0.24]},
        "thigh.L": {"parent": "body", "from": "thigh"},
        "shin.L":  {"parent": "thigh.L", "from": "shin"},
        "foot.L":  {"parent": "shin.L", "head": [0.23, 0.25, 0.03], "tail": [0.23, 0.32, 0.01]}
      },
      "carry": {"body": ["body"], "head": ["head", "eye"], "foot.L": ["foot"]},
      "legs": {"hind.L": {"upper": "thigh.L", "lower": "shin.L", "foot": "foot.L"}},
      "softness": {"default": 0.015, "head": 0.008},
      "clips": {"Walk": {"seconds": 1.0, "loop": true, "motions": [...]}}
    }

- A bone is placed by `head` and `tail` (spec coordinates, as the shape), or taken `from` a
  capsule or cylinder part (head at its `a`, tail at its `b`). Model limbs as capsules and the
  skeleton follows them.
- Every '*.L' bone (on the +X side, the creature's left) gets its mirrored '*.R' twin, and so
  does every '*.L' leg: model one side.
- `carry` says which parts each bone carries: their surface follows the bone. A bone taken
  `from` a part carries it unless `carry` names the bone. A '.R' twin carries the mirror image
  of its '.L' bone's parts. Skin weights come from the distance to these parts, falling off
  over `softness` metres (default 2% of the shape's size): smaller is a crisper joint.
- `legs` name two-bone limbs (upper, lower, optional foot) for `gait` (see assetkit/motion.py);
  `knee` gives the bend direction for a leg modelled straight.
- `clips`: see assetkit/motion.py. Clip names become the glTF animation names. Each lasts
  exactly its `seconds`: without an `fps`, the rig takes the first of 24, 30, 25, 60, ... at
  which every length is a whole number of frames (1.2 s and 0.9 s give 30).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from assetkit import sdf
from assetkit.figure import Figure
from assetkit.motion import MotionError, build_clips
from assetkit.rig import Bone, Clip, Leg, Skeleton, Vec, add, mirror, twin_name


class RigError(ValueError):
    """A rig that does not parse; the message names the path to the problem."""


@dataclass(frozen=True)
class Rig:
    skeleton: Skeleton
    legs: dict[str, Leg]
    carriers: dict[str, list[sdf.Shape]]
    softness: dict[str, float]
    default_softness: float
    clips: tuple[Clip, ...]


def build_rig(
    raw: object,
    parts: Mapping[str, object],
    shape_of: Callable[[str], sdf.Shape],
    size: float,
    offset: Vec,
    path: str,
    figure: Figure | None = None,
) -> Rig:
    """`parts` are the spec's part nodes, `shape_of` builds one; `offset` is how far the mesh was
    moved after meshing (settling), applied to the bones and the carried parts alike. With a
    `figure`, its bones, what they carry, its legs and its clips come first; the spec adds
    bones (a tail, a jaw) and clips, and replaces a clip of the same name."""
    spec = _object(raw, path)
    _only(spec, ("bones", "carry", "legs", "softness", "fps", "clips"), path)

    bones_raw = _object(spec.get("bones", {}), f"{path}.bones")
    if not bones_raw and figure is None:
        raise RigError(f"{path}.bones: a rig needs bones")
    bones: list[Bone] = []
    carried: dict[str, list[str]] = {}
    preset: dict[str, list[sdf.Shape]] = {}
    if figure is not None:
        bones += [Bone(b.name, add(b.head, offset), add(b.tail, offset), b.parent) for b in figure.bones]
        preset = {name: list(shapes) for name, shapes in figure.carry.items()}
    for name, value in bones_raw.items():
        here = f"{path}.bones.{name}"
        if name.endswith(".R"):
            raise RigError(f"{here}: model the left side ('.L', +X); the '.R' twin is made for you")
        fields = _object(value, here)
        _only(fields, ("head", "tail", "from", "parent"), here)
        parent = fields.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise RigError(f"{here}.parent: expected a bone name")
        if "from" in fields:
            if "head" in fields or "tail" in fields:
                raise RigError(f"{here}: give `from` or `head`/`tail`, not both")
            part = fields["from"]
            head, tail = _ends(part, parts, f"{here}.from")
            carried[name] = [part]
        else:
            if "head" not in fields or "tail" not in fields:
                raise RigError(f"{here}: needs `head` and `tail`, or `from` a capsule part")
            head, tail = _vec(fields["head"], f"{here}.head"), _vec(fields["tail"], f"{here}.tail")
        bones.append(Bone(name, add(head, offset), add(tail, offset), parent))
    try:
        skeleton = Skeleton.with_twins(bones)
    except ValueError as exc:
        raise RigError(f"{path}.bones: {exc}") from exc

    for name, value in _object(spec.get("carry", {}), f"{path}.carry").items():
        here = f"{path}.carry.{name}"
        if name not in skeleton or name.endswith(".R"):
            raise RigError(f"{here}: no bone '{name}' (name '.L' bones; twins follow)")
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise RigError(f"{here}: expected a list of part names")
        for part in value:
            if part not in parts:
                raise RigError(f"{here}: no part '{part}'; parts are {sorted(parts)}")
        carried[name] = list(value)
    if not carried and not preset:
        raise RigError(f"{path}.carry: no bone carries a part, so nothing would move")

    carriers: dict[str, list[sdf.Shape]] = {}
    for name, shapes in preset.items():
        if name in carried:
            continue
        moved = [sdf.move(shape, offset) for shape in shapes]
        carriers[name] = moved
        twin = twin_name(name)
        if name.endswith(".L") and twin is not None:
            carriers[twin] = [sdf.flip_x(s) for s in moved]
    for name, part_names in carried.items():
        shapes = [sdf.move(shape_of(p), offset) for p in part_names]
        carriers[name] = shapes
        twin = twin_name(name)
        if name.endswith(".L") and twin is not None:
            carriers[twin] = [sdf.flip_x(s) for s in shapes]

    legs: dict[str, Leg] = {}
    if figure is not None:
        for name, leg in figure.legs.items():
            legs[name] = leg
            twin = twin_name(name)
            if twin is not None:
                legs[twin] = Leg(
                    twin_name(leg.upper) or leg.upper,
                    twin_name(leg.lower) or leg.lower,
                    (twin_name(leg.foot) or leg.foot) if leg.foot else None,
                    None,
                )
    for name, value in _object(spec.get("legs", {}), f"{path}.legs").items():
        here = f"{path}.legs.{name}"
        fields = _object(value, here)
        _only(fields, ("upper", "lower", "foot", "knee"), here)
        for key in ("upper", "lower", "foot"):
            bone = fields.get(key)
            if bone is None and key == "foot":
                continue
            if not isinstance(bone, str) or bone not in skeleton:
                raise RigError(f"{here}.{key}: no bone {bone!r}; bones are {list(skeleton.names)}")
        knee = _vec(fields["knee"], f"{here}.knee") if "knee" in fields else None
        leg = Leg(fields["upper"], fields["lower"], fields.get("foot"), knee)
        legs[name] = leg
        twin = twin_name(name)
        if name.endswith(".L") and twin is not None:
            legs[twin] = Leg(
                twin_name(leg.upper) or leg.upper,
                twin_name(leg.lower) or leg.lower,
                (twin_name(leg.foot) or leg.foot) if leg.foot else None,
                mirror(knee) if knee else None,
            )
    softness_raw = spec.get("softness", figure.default_softness if figure is not None else 0.02 * size)
    if isinstance(softness_raw, int | float) and not isinstance(softness_raw, bool):
        default_softness, softness = float(softness_raw), {}
        if figure is not None:
            softness = _with_twins(figure.softness)
    else:
        fields = _object(softness_raw, f"{path}.softness")
        default_softness = float(fields.get("default", 0.02 * size))
        softness = _with_twins(figure.softness) if figure is not None else {}
        for name, value in fields.items():
            if name == "default":
                continue
            if name not in skeleton:
                raise RigError(f"{path}.softness.{name}: no bone '{name}'")
            softness[name] = float(value)
            twin = twin_name(name)
            if name.endswith(".L") and twin:
                softness.setdefault(twin, float(value))
    for name, value in [("default", default_softness), *softness.items()]:
        if value <= 0:
            raise RigError(f"{path}.softness.{name}: must be positive")

    if figure is not None:
        spec = {**spec, "clips": {**figure.clips, **_object(spec.get("clips", {}), f"{path}.clips")}}
    try:
        clips = build_clips(spec, skeleton, legs, path)
    except MotionError as exc:
        raise RigError(str(exc)) from exc
    return Rig(skeleton, legs, carriers, softness, default_softness, tuple(clips))


def _with_twins(values: Mapping[str, float]) -> dict[str, float]:
    out = dict(values)
    for name, value in values.items():
        twin = twin_name(name)
        if name.endswith(".L") and twin is not None:
            out.setdefault(twin, value)
    return out


def _ends(part: object, parts: Mapping[str, object], path: str) -> tuple[Vec, Vec]:
    if not isinstance(part, str) or part not in parts:
        raise RigError(f"{path}: no part {part!r}; parts are {sorted(parts)}")
    node = parts[part]
    if isinstance(node, dict) and len(node) == 1:
        ((kind, fields),) = node.items()
        if kind in ("capsule", "cylinder") and isinstance(fields, dict) and "a" in fields and "b" in fields:
            return _vec(fields["a"], f"parts.{part}.{kind}.a"), _vec(fields["b"], f"parts.{part}.{kind}.b")
    raise RigError(f"{path}: part '{part}' is not a capsule or cylinder; give the bone `head` and `tail`")


def _object(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise RigError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _only(fields: dict, allowed: tuple[str, ...], path: str) -> None:
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        raise RigError(f"{path}: unknown key(s) {unknown}; allowed are {sorted(allowed)}")


def _vec(value: object, path: str) -> Vec:
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, int | float) for v in value)):
        raise RigError(f"{path}: expected [x, y, z]")
    return (float(value[0]), float(value[1]), float(value[2]))
