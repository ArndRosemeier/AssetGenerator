"""Sculpted organic forms: the spec's `params.shape` is the shape itself, as a tree.

`organic.sculpt` meshes a signed-distance shape tree (assetkit/sculpt.py lists the
nodes) into one closed shell within a triangle budget, paints regions of it with
other materials, and settles it on the ground. Rocks, stumps, roots, bodies, horns,
fungus, bone: anything soft or worn that boxes and lathes model badly. A new form is
a new spec, not new code.

    "params": {
      "parts": {"head": {"sphere": {"centre": [0, 0.3, 0.4], "radius": 0.12}}},
      "shape": {"smooth_union": {"k": 0.06, "shapes": [{"ref": "head"}, ...]}},
      "base_slot": "skin",
      "paint": {"eye": {"sphere": {...}}},
      "max_triangles": 4000
    }

Optional: `paint_reach` (metres; default 1% of the shape's size), `smooth` (default
true), `sharp_angle` (degrees; smooth shading keeps edges sharper than this hard),
`settle` (default true: footprint centred on the origin, lowest point on z = 0).
"""

from __future__ import annotations

from assetkit import Asset, MeshBuilder, Part, ShadeFlat, ShadeSmooth, Unwrap, sdf
from assetkit.sculpt import SculptError, build_shape
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_bool,
    as_float,
    as_int,
    as_mapping,
    as_str,
    reject_unknown,
    require_key,
    require_materials,
)

MATERIAL_SLOTS: tuple[str, ...] = ()  # from the spec: base_slot plus each paint region

_KEYS = (
    "shape",
    "parts",
    "base_slot",
    "paint",
    "paint_reach",
    "max_triangles",
    "smooth",
    "sharp_angle",
    "settle",
)


def build(spec: AssetSpec) -> Asset:
    raw = spec.params
    reject_unknown(raw, _KEYS, "params")
    parts = dict(as_mapping(raw.get("parts", {}), "params.parts"))
    paint_raw = as_mapping(raw.get("paint", {}), "params.paint")
    base_slot = as_str(require_key(raw, "base_slot", "params"), "params.base_slot")
    budget = as_int(require_key(raw, "max_triangles", "params"), "params.max_triangles")
    if not 8 <= budget <= spec.qa.max_triangles:
        raise SpecError(
            f"params.max_triangles: {budget} must be 8..{spec.qa.max_triangles} (qa.max_triangles)"
        )
    if base_slot in paint_raw:
        raise SpecError(
            f"params.paint: '{base_slot}' is the base slot; paint regions need slots of their own"
        )
    slots = (base_slot, *paint_raw)
    require_materials(spec.materials, slots, spec.generator)

    try:
        shape = build_shape(require_key(raw, "shape", "params"), parts, "params.shape")
        regions = {name: build_shape(node, parts, f"params.paint.{name}") for name, node in paint_raw.items()}
        size = max(u - lo for lo, u in zip(shape.lower, shape.upper, strict=True))
        reach = as_float(raw.get("paint_reach", 0.01 * size), "params.paint_reach")
        shell, face_slots = _meshed(shape, regions, base_slot, reach, budget)
    except (SculptError, ValueError) as exc:
        raise SpecError(str(exc)) from exc

    builder = MeshBuilder(slots)
    builder.add_painted(shell[0], shell[1], face_slots)
    mesh = builder.build()
    if as_bool(raw.get("settle", True), "params.settle"):
        mesh = mesh.settled()

    if as_bool(raw.get("smooth", True), "params.smooth"):
        sharp = raw.get("sharp_angle")
        shading = ShadeSmooth(
            sharp_angle_deg=None if sharp is None else as_float(sharp, "params.sharp_angle")
        )
    else:
        shading = ShadeFlat()
    return Asset((Part(spec.asset_id, mesh, spec.materials, (shading, Unwrap())),))


def _meshed(
    shape: sdf.Shape, regions: dict[str, sdf.Shape], base_slot: str, reach: float, budget: int
) -> tuple[sdf.Shell, list[str]]:
    """Mesh and paint within `budget` triangles. Cutting along paint borders adds triangles,
    so while it overshoots, mesh again leaving room for what the borders took."""
    target = budget
    for _ in range(4):
        shell = sdf.mesh(shape, max_triangles=target)
        if not regions:
            return shell, [base_slot] * len(shell[1])
        painted, face_slots = sdf.paint(shell, regions, base_slot, reach, shape=shape)
        if len(painted[1]) <= budget:
            return painted, face_slots
        border = len(painted[1]) - len(shell[1])
        target = min(target - 1, budget - border - budget // 50)
        if target < 8:
            break
    raise ValueError(f"painting needs {len(painted[1])} triangles, over the budget of {budget}")
