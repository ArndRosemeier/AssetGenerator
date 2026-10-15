"""Mushrooms that are monsters, built from the very shells the props' mushrooms are (blender/lib/mushroom.py),
so one stands among them unseen; rigged and animated with the quadruped generator's skeleton, poses and
clips (quadruped_generator/pose.py, clips.py).

`params.species` picks the monster (species below): the toadstool, a fly agaric that pulls its roots out of
the ground and walks on them (toadstool.py); the puffcap, a pale cave mushroom, rooted, that puffs spores
(puffcap.py). The mushroom's own numbers are the props' (mush_fly_agaric, mush_cave_pale), times `scale`.

Materials: the mushroom's slots (cap, gills, stalk, ring, spots) and the species' own (`root`, `eye`), as
vertex colours on two materials: `skin` (drawn as the props are) and `eye` (the eyes, and the slots
`params.glow` names, such as a puffcap's gills: drawn throwing the light back).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import bpy
import numpy as np
from mathutils import Matrix

from blender.generators.mushroom_creature import puffcap, toadstool
from blender.generators.mushroom_creature.parts import Plan
from blender.generators.quadruped_generator import plain_material
from blender.generators.quadruped_generator.clips import Clip, bake_clips
from blender.generators.quadruped_generator.pose import Rig
from blender.generators.quadruped_generator.skin import MAX_INFLUENCES, armature_for, bind
from blender.lib.mushroom import CAP_SHAPES, Mushroom
from blender.lib.scene import activate, unwrap
from blender.lib.spec import AssetSpec, SpecError, as_float, as_int, as_str, require_materials


@dataclass(frozen=True)
class Species:
    #: The skeleton and the skinned pieces, from the mushroom.
    plan: Callable[[Mushroom], Plan]
    clips: list[Clip]
    #: Slots besides the mushroom's own.
    slots: tuple[str, ...]
    #: The props' mushroom it is (the numbers a spec starts from).
    shape: str


SPECIES: dict[str, Species] = {
    "toadstool": Species(toadstool.plan, toadstool.CLIPS, ("root", "eye"), "dome"),
    "puffcap": Species(puffcap.plan, puffcap.CLIPS, (), "flat"),
}

#: The mushroom's numbers (blender/lib/mushroom.py), as in a prop.kit mushroom spec; lengths are scaled.
LENGTHS = ("cap_radius", "cap_height", "stalk_height", "stalk_radius", "lean")
COUNTS = ("gills", "spots", "segments")
FLAGS = ("ring", "volva")


@dataclass
class Params:
    species: str
    mushroom: Mushroom
    glow: tuple[str, ...] = field(default_factory=tuple)


def parse(raw: Mapping[str, object]) -> Params:
    known = {"species", "seed", "scale", "cap_shape", "bulb", "glow", *LENGTHS, *COUNTS, *FLAGS}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise SpecError(f"params: unknown key(s) {unknown}; allowed keys are {sorted(known)}")
    species = as_str(raw.get("species"), "params.species")
    if species not in SPECIES:
        raise SpecError(f"params.species: unknown '{species}'; have {sorted(SPECIES)}")
    scale = as_float(raw.get("scale", 1.0), "params.scale")
    shape = as_str(raw.get("cap_shape", SPECIES[species].shape), "params.cap_shape")
    if shape not in CAP_SHAPES:
        raise SpecError(f"params.cap_shape: unknown '{shape}'; have {sorted(CAP_SHAPES)}")
    m = Mushroom(cap_shape=shape, seed=as_int(raw.get("seed", 1), "params.seed"))
    for key in LENGTHS:
        if key in raw:
            setattr(m, key, as_float(raw[key], f"params.{key}") * scale)
        else:
            setattr(m, key, getattr(m, key) * scale)
    for key in COUNTS:
        if key in raw:
            setattr(m, key, as_int(raw[key], f"params.{key}"))
    for key in FLAGS:
        if key in raw:
            setattr(m, key, as_float(raw[key], f"params.{key}") > 0.5)
    if "bulb" in raw:
        m.bulb = as_float(raw["bulb"], "params.bulb")
    # As prop.kit sizes a mushroom's spots: by its cap.
    m.spot_radius = m.cap_radius * 0.12
    glow = raw.get("glow", [])
    if not isinstance(glow, list) or not all(isinstance(g, str) for g in glow):
        raise SpecError("params.glow: expected a list of slot names")
    return Params(species, m, tuple(glow))


def _weights(plan: Plan, names: list[str], verts: list[np.ndarray]) -> np.ndarray:
    """Each piece's vertices go to its bones, by distance to each bone (softly, by the piece's softness)."""
    col = {n: i for i, n in enumerate(names)}
    head = {b.name: np.asarray(b.head) for b in plan.body.bones}
    tail = {b.name: np.asarray(b.tail) for b in plan.body.bones}
    rows = []
    for piece, v in zip(plan.pieces, verts, strict=True):
        w = np.zeros((len(v), len(names)))
        if len(piece.bones) == 1:
            w[:, col[piece.bones[0]]] = 1.0
            rows.append(w)
            continue
        d = np.empty((len(v), len(piece.bones)))
        for j, n in enumerate(piece.bones):
            a, ab = head[n], tail[n] - head[n]
            t = np.clip(((v - a) @ ab) / float(ab @ ab), 0.0, 1.0)
            d[:, j] = np.linalg.norm(v - (a + t[:, None] * ab), axis=1)
        k = np.exp(-(d - d.min(axis=1, keepdims=True)) / piece.soft)
        cut = np.sort(k, axis=1)[:, -min(MAX_INFLUENCES, k.shape[1])][:, None]
        k = np.where((k >= cut) & (k >= 0.01), k, 0.0)
        k /= k.sum(axis=1, keepdims=True)
        for j, n in enumerate(piece.bones):
            w[:, col[n]] = k[:, j]
        rows.append(w)
    return np.concatenate(rows, axis=0)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    params = parse(spec.params)
    kind = SPECIES[params.species]
    plan = kind.plan(params.mushroom)
    slots = sorted({p.slot for p in plan.pieces})
    require_materials(spec.materials, slots, spec.generator)

    verts = [np.asarray(p.shell[0], dtype=float) for p in plan.pieces]
    # The footprint centred on the origin, the lowest of it on the ground; the skeleton with it.
    every = np.concatenate(verts, axis=0)
    lo, hi = every.min(axis=0), every.max(axis=0)
    offset = (-float(lo[0] + hi[0]) / 2, -float(lo[1] + hi[1]) / 2, -float(lo[2]))
    verts = [v + np.asarray(offset) for v in verts]
    plan = Plan(plan.body.moved(offset), plan.pieces)

    points: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    glowing: list[bool] = []
    colours: list[tuple[float, ...]] = []
    for piece, v in zip(plan.pieces, verts, strict=True):
        base = len(points)
        points.extend(map(tuple, v))
        faces.extend([base + i for i in f] for f in piece.shell[1])
        glowing.extend([piece.slot == "eye" or piece.slot in params.glow] * len(piece.shell[1]))
        colours.extend([tuple(spec.materials[piece.slot].base_color)] * len(v))

    me = bpy.data.meshes.new(spec.asset_id)
    me.from_pydata(points, [], faces)
    me.update()
    obj = bpy.data.objects.new(spec.asset_id, me)
    bpy.data.scenes[0].collection.objects.link(obj)
    skin = plain_material("skin", spec.materials["cap"])
    eye = plain_material("eye", spec.materials["eye" if "eye" in spec.materials else "gills"])
    me.materials.append(skin)
    me.materials.append(eye)
    me.polygons.foreach_set("material_index", [1 if g else 0 for g in glowing])
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", np.asarray(colours, dtype=np.float32).ravel())
    for polygon in me.polygons:
        polygon.use_smooth = True
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=0.7)
    unwrap(obj)
    # A creature with nothing glowing (no eyes, no glow): an empty slot would not survive the export.
    if not any(glowing):
        me.materials.pop(index=1)

    names = [b.name for b in plan.body.bones]
    armature = armature_for(spec.asset_id, plan.body)
    bind(obj, armature, names, _weights(plan, names, verts))
    activate(armature)
    bake_clips(armature, Rig(armature, plan.body), kind.clips)
    armature.data.pose_position = "REST"
    bpy.context.scene.frame_set(1)
    obj.matrix_world = Matrix.Identity(4)
    return [obj, armature]
