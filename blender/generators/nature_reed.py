"""Stylized reed clump for water margins.

Tall thin stalks rising from a tight base, each arcing away from vertical and
carrying a seed head at the tip. Rooted in mud, so the base is on Z=0 and the
footprint is small: a reed bed is made of many of these, not one big mesh.

Two crossed cards per stalk, the same trick the grass tuft uses — a readable
silhouette from any angle without alpha textures.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Matrix, Vector

from blender.lib.scene import make_material, shade_flat, unwrap, world_bounds
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_int,
    positive_float,
    positive_int,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ("stalks", "heads")

_PARAM_KEYS = (
    "height",
    "stalk_count",
    "stalk_width",
    "splay",
    "lean",
    "head_length",
    "seed",
)

# A clump is instanced by the hundred along a bank, so the budget is per stalk.
_MAX_STALKS = 20


@dataclass(frozen=True)
class ReedParams:
    height: float
    stalk_count: int
    stalk_width: float
    splay: float
    lean: float
    head_length: float
    seed: int


def parse_params(raw: Mapping[str, object]) -> ReedParams:
    path = "params"
    reject_unknown(raw, _PARAM_KEYS, path)
    params = ReedParams(
        height=positive_float(require_key(raw, "height", path), f"{path}.height"),
        stalk_count=positive_int(require_key(raw, "stalk_count", path), f"{path}.stalk_count"),
        stalk_width=positive_float(
            require_key(raw, "stalk_width", path), f"{path}.stalk_width"
        ),
        splay=positive_float(require_key(raw, "splay", path), f"{path}.splay"),
        lean=positive_float(require_key(raw, "lean", path), f"{path}.lean"),
        head_length=positive_float(
            require_key(raw, "head_length", path), f"{path}.head_length"
        ),
        seed=as_int(require_key(raw, "seed", path), f"{path}.seed"),
    )
    if params.stalk_count > _MAX_STALKS:
        raise SpecError(f"params.stalk_count must be <= {_MAX_STALKS} for clutter budgets.")
    if params.head_length >= params.height:
        raise SpecError(
            f"params.head_length ({params.head_length}) must be shorter than the stalk "
            f"it sits on ({params.height})."
        )
    if params.seed < 0:
        raise SpecError("params.seed must be non-negative.")
    return params


def _card(
    bm: bmesh.types.BMesh,
    spine: list[Vector],
    widths: list[float],
    yaw: float,
    material_index: int,
) -> None:
    """A ribbon following `spine`, `widths` wide, facing across `yaw`."""
    across = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    rungs: list[list[bmesh.types.BMVert]] = []
    for point, width in zip(spine, widths):
        offset = across * (width * 0.5)
        rungs.append([bm.verts.new(point - offset), bm.verts.new(point + offset)])
    bm.verts.ensure_lookup_table()
    for lower, upper in zip(rungs, rungs[1:]):
        face = bm.faces.new((lower[0], lower[1], upper[1], upper[0]))
        face.material_index = material_index


def _stalk(
    bm: bmesh.types.BMesh,
    params: ReedParams,
    rng: random.Random,
    index: int,
) -> None:
    angle = math.tau * (index / params.stalk_count) + rng.uniform(-0.4, 0.4)
    radius = rng.uniform(0.0, params.splay)
    base = Vector((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
    out = Vector((math.cos(angle), math.sin(angle), 0.0))

    height = params.height * rng.uniform(0.7, 1.05)
    lean = params.lean * rng.uniform(0.5, 1.3)
    width = params.stalk_width * rng.uniform(0.8, 1.2)
    # Quadratic arc: straight out of the water, bending over towards the tip.
    spine = [
        base,
        base + out * (lean * 0.25) + Vector((0.0, 0.0, height * 0.55)),
        base + out * lean + Vector((0.0, 0.0, height)),
    ]
    widths = [width, width * 0.85, width * 0.55]
    for yaw in (angle, angle + math.pi * 0.5):
        _card(bm, spine, widths, yaw, 0)

    # Seed head: a fat spindle carrying on in the direction the stalk was going.
    tip = spine[-1]
    carry = (spine[-1] - spine[-2]).normalized() * params.head_length
    head = [tip, tip + carry * 0.5, tip + carry]
    head_widths = [width * 1.2, width * 3.4, 0.001]
    for yaw in (angle, angle + math.pi * 0.5):
        _card(bm, head, head_widths, yaw, 1)


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    require_materials(spec.materials, MATERIAL_SLOTS, spec.generator)
    params = parse_params(spec.params)
    rng = random.Random(params.seed)

    bm = bmesh.new()
    for index in range(params.stalk_count):
        _stalk(bm, params, rng, index)

    mesh = bpy.data.meshes.new(spec.asset_id)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(spec.asset_id, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    for slot in MATERIAL_SLOTS:
        mesh.materials.append(make_material(slot, spec.materials[slot]))

    lower, upper = world_bounds([obj])
    shift = Vector((-(lower.x + upper.x) * 0.5, -(lower.y + upper.y) * 0.5, -lower.z))
    if shift.length > 1e-6:
        mesh.transform(Matrix.Translation(shift))
        mesh.update()

    shade_flat(obj)
    unwrap(obj)
    return [obj]
