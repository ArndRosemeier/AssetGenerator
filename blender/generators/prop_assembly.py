"""prop.assembly: a hard-surface prop written in the spec as exact pieces (assetkit/assembly.py).

Lanterns, cages, chests, tools, furniture, fittings: anything made of turned, cut and bent parts
with crisp edges. A new prop is a new spec, not new code.

    "params": {
      "parts":  {"post": {"box": {"size": [0.016, 0.016, 0.3]}, "slot": "iron"}},
      "pieces": [
        {"lathe": {"profile": [[0.1, 0], [0.1, 0.02], [0.08, 0.03]]}, "slot": "iron"},
        {"ref": "post", "at": [0.08, 0, 0.18], "repeat": {"around": 4, "start": 45}},
        {"cylinder": {"a": [0, 0, 0.03], "b": [0, 0, 0.33], "radius": 0.07}, "slot": "glass"}
      ],
      "bevel": 0.002
    }

`bevel` (metres, default 0) rounds edges sharper than 30 degrees on pieces at least 8 bevels
thick (or marked `"bevel": true`), so edges catch light and wear patterns find them;
`sharp_angle` (default 35) keeps edges that turn more hard in the shading and rounds the rest;
`detail` (default 1) scales how many sides round shapes get; `settle` (default true) centres
the footprint on the origin and stands the prop on z = 0.
Material slots are the spec's materials, each used by some piece. Patterns on them are written
in the pieces' coordinates.

A `rig` makes it move: a drum and its crank, a lid, a wheel, a banner.

    "rig": {
      "bones": {"frame": {"head": [0, 0, 0], "tail": [0, 0, 0.3]},
                "wheel": {"parent": "frame", "head": [-0.4, 0, 1], "tail": [0.4, 0, 1]}},
      "clips": {"Turn": {"seconds": 4, "motions": [{"spin": {"bone": "wheel", "turns": 1}}]}}
    }

A piece with `"bone": "wheel"` turns rigidly with it; one with `"bones": [...]` (a `sheet`,
a `tube`) bends along that chain, each vertex shared by the nearest bones over `softness`
metres (default 0.05); a piece with neither moves with the root bone. Clips use the motions
of assetkit/motion.py: `spin` turns a bone about its own axis, `wave` ripples a chain,
`keys` poses it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from assetkit import Asset, Bevel, MeshBuilder, Part, ShadeSmooth, Unwrap
from assetkit.assembly import AssemblyError, bevelled_triangles, build_pieces
from assetkit.motion import MotionError, build_clips
from assetkit.rig import Bone, Skeleton, Skin, Vec, add, dot, length, scale, sub
from blender.lib.spec import AssetSpec, SpecError, as_bool, as_float, as_mapping, reject_unknown, require_key

MATERIAL_SLOTS: tuple[str, ...] = ()  # from the spec: every slot a piece uses

_KEYS = ("pieces", "parts", "bevel", "sharp_angle", "detail", "settle", "rig")


def build(spec: AssetSpec) -> Asset:
    raw = spec.params
    reject_unknown(raw, _KEYS, "params")
    parts = dict(as_mapping(raw.get("parts", {}), "params.parts"))
    detail = as_float(raw.get("detail", 1.0), "params.detail")
    if not 0.25 <= detail <= 4.0:
        raise SpecError("params.detail: expected 0.25..4")
    bevel = as_float(raw.get("bevel", 0.0), "params.bevel")
    if bevel < 0:
        raise SpecError("params.bevel: must not be negative")
    try:
        pieces = build_pieces(require_key(raw, "pieces", "params"), parts, "params.pieces", detail, bevel)
    except AssemblyError as exc:
        raise SpecError(str(exc)) from exc

    used = list(dict.fromkeys(slot for _, slot, _, _ in pieces))
    unknown = [s for s in used if s not in spec.materials]
    if unknown:
        raise SpecError(
            f"params.pieces: slot(s) {unknown} have no material; materials are {sorted(spec.materials)}"
        )
    unused = sorted(set(spec.materials) - set(used))
    if unused:
        raise SpecError(f"materials: {unused} are used by no piece")

    builder = MeshBuilder(used)
    marks: list[float] = []
    for shell, slot, bevelled, _ in pieces:
        builder.add(shell, slot)
        marks += [1.0 if bevelled else 0.0] * len(shell[0])
    builder.set_point_attribute("bevel", marks)
    mesh = builder.build()
    expected = mesh.triangle_count() + (bevelled_triangles(mesh, marks) if bevel > 0 else 0)
    if expected > spec.qa.max_triangles:
        raise SpecError(
            f"params.pieces: about {expected} triangles after the bevel ({mesh.triangle_count()} before), "
            f"over qa.max_triangles {spec.qa.max_triangles}: a lower `detail`, fewer `segments` on "
            "small round pieces, fewer pieces, or no bevel"
        )
    unsettled = mesh
    if as_bool(raw.get("settle", True), "params.settle"):
        mesh = mesh.settled()
    offset = tuple(a - b for a, b in zip(mesh.vertices[0], unsettled.vertices[0], strict=True))

    finish = (
        *((Bevel(width=bevel, segments=1, angle_deg=30.0, only="bevel"),) if bevel > 0 else ()),
        ShadeSmooth(sharp_angle_deg=as_float(raw.get("sharp_angle", 35.0), "params.sharp_angle")),
        Unwrap(),
    )
    if "rig" not in raw:
        return Asset((Part(spec.asset_id, mesh, spec.materials, finish, pattern_origin=offset),))
    try:
        skeleton, skin, clips = _rig(raw["rig"], pieces, mesh.vertices, offset, "params.rig")
    except (MotionError, ValueError) as exc:
        raise SpecError(str(exc)) from exc
    part = Part(spec.asset_id, mesh, spec.materials, finish, skin=skin, pattern_origin=offset)
    return Asset((part,), skeleton=skeleton, clips=tuple(clips))


def _rig(
    raw: object, pieces: list, vertices: Sequence[Vec], offset: Vec, path: str
) -> tuple[Skeleton, Skin, list]:
    """Bones, each vertex's weights and the clips. A piece with `bone` moves rigidly with it; one
    with `bones` bends along them, each vertex shared by the nearest of them over `softness`
    metres; a piece with neither moves with the root bone."""
    if not isinstance(raw, dict):
        raise MotionError(f"{path}: expected an object with `bones` and `clips`")
    unknown = sorted(set(raw) - {"bones", "softness", "fps", "clips"})
    if unknown:
        raise MotionError(f"{path}: unknown key(s) {unknown}; a rig takes bones, softness, fps, clips")
    bones_raw = raw.get("bones")
    if not isinstance(bones_raw, dict) or not bones_raw:
        raise MotionError(f"{path}.bones: a rig needs bones")
    bones = []
    for name, fields in bones_raw.items():
        here = f"{path}.bones.{name}"
        if not isinstance(fields, dict) or "head" not in fields or "tail" not in fields:
            raise MotionError(f"{here}: needs `head` and `tail` (and a `parent`, but for the root)")
        extra = sorted(set(fields) - {"head", "tail", "parent"})
        if extra:
            raise MotionError(f"{here}: unknown key(s) {extra}")
        head, tail = (_vec3(fields[k], f"{here}.{k}") for k in ("head", "tail"))
        bones.append(Bone(name, add(head, offset), add(tail, offset), fields.get("parent")))
    try:
        skeleton = Skeleton.with_twins(bones)
    except ValueError as exc:
        raise MotionError(f"{path}.bones: {exc}") from exc
    roots = [b.name for b in skeleton.bones if b.parent is None]
    softness = raw.get("softness", 0.05)
    if isinstance(softness, bool) or not isinstance(softness, int | float) or softness <= 0:
        raise MotionError(f"{path}.softness: expected metres, positive")
    index = {name: i for i, name in enumerate(skeleton.names)}
    indices: list[tuple[int, ...]] = []
    weights: list[tuple[float, ...]] = []
    at = 0
    for shell, _, _, binding in pieces:
        count = len(shell[0])
        points = vertices[at : at + count]
        at += count
        if binding is None:
            if len(roots) != 1:
                raise MotionError(
                    f"{path}: pieces without a `bone` move with the root, but there are "
                    f"{len(roots)} roots {roots}"
                )
            binding = roots[0]
        if isinstance(binding, str):
            if binding not in index:
                raise MotionError(f"{path}: a piece names bone '{binding}'; bones are {list(skeleton.names)}")
            indices += [(index[binding],)] * count
            weights += [(1.0,)] * count
            continue
        for name in binding:
            if name not in index:
                raise MotionError(f"{path}: a piece names bone '{name}'; bones are {list(skeleton.names)}")
        segments = [(skeleton[name].head, skeleton[name].tail) for name in binding]
        for p in points:
            near = [_to_segment(p, a, b) for a, b in segments]
            nearest = min(near)
            share = [math.exp(-(d - nearest) / softness) for d in near]
            picked = sorted(range(len(share)), key=lambda k: -share[k])[:4]
            kept = [k for k in picked if share[k] >= 0.01 * share[picked[0]]]
            total = math.fsum(share[k] for k in kept)
            normed = [share[k] / total for k in kept]
            normed[-1] = 1.0 - math.fsum(normed[:-1])
            indices.append(tuple(index[binding[k]] for k in kept))
            weights.append(tuple(normed))
    skin = Skin(bones=tuple(skeleton.names), indices=tuple(indices), weights=tuple(weights))
    clips = build_clips(raw, skeleton, {}, path)
    return skeleton, skin, clips


def _vec3(value: object, path: str) -> Vec:
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, int | float) for v in value)):
        raise MotionError(f"{path}: expected [x, y, z]")
    return (float(value[0]), float(value[1]), float(value[2]))


def _to_segment(p: Vec, a: Vec, b: Vec) -> float:
    ab = sub(b, a)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / max(dot(ab, ab), 1e-18)))
    return length(sub(p, add(a, scale(ab, t))))
