"""
Curated MPFB face morphs for Character Studio human exports.

Asset Lab copy of City's `tools/mpfb_face_morphs.py`. The slider set and the
resulting morph names are identical on purpose: Character Studio and City read
the same 28 glTF morphs. The only difference is that MPFB is not vendored in
this repo, so the target library location must be injected with
`configure_targets_root()` before baking.

Each slider is bipolar in Godot [-1, 1] and ships as two glTF morphs:
  <slider>__pos  <- abs(value) when value > 0
  <slider>__neg  <- abs(value) when value < 0

Baked after macro shape keys are collapsed into Basis, while the MH vertex
index space is still intact (before helper masks / deletes).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import bpy

_TARGETS_ROOT: Path | None = None

# slider key -> MH target stems for the positive / negative extremes.
FACE_SLIDERS: dict[str, dict[str, list[str]]] = {
    "face_head_width": {
        "pos": ["head-scale-horiz-incr"],
        "neg": ["head-scale-horiz-decr"],
    },
    "face_head_depth": {
        "pos": ["head-scale-depth-incr"],
        "neg": ["head-scale-depth-decr"],
    },
    "face_forehead": {
        "pos": ["forehead-scale-vert-incr"],
        "neg": ["forehead-scale-vert-decr"],
    },
    "face_brow_height": {
        "pos": ["eyebrows-trans-up"],
        "neg": ["eyebrows-trans-down"],
    },
    "face_eye_size": {
        "pos": ["l-eye-scale-incr", "r-eye-scale-incr"],
        "neg": ["l-eye-scale-decr", "r-eye-scale-decr"],
    },
    "face_eye_spacing": {
        "pos": ["l-eye-trans-out", "r-eye-trans-out"],
        "neg": ["l-eye-trans-in", "r-eye-trans-in"],
    },
    "face_nose_width": {
        "pos": ["nose-scale-horiz-incr"],
        "neg": ["nose-scale-horiz-decr"],
    },
    "face_nose_length": {
        "pos": ["nose-scale-depth-incr"],
        "neg": ["nose-scale-depth-decr"],
    },
    "face_nose_tip": {
        "pos": ["nose-point-up"],
        "neg": ["nose-point-down"],
    },
    "face_cheekbones": {
        "pos": ["l-cheek-bones-incr", "r-cheek-bones-incr"],
        "neg": ["l-cheek-bones-decr", "r-cheek-bones-decr"],
    },
    "face_jaw_width": {
        "pos": ["chin-width-incr"],
        "neg": ["chin-width-decr"],
    },
    "face_chin": {
        "pos": ["chin-prominent-incr"],
        "neg": ["chin-prominent-decr"],
    },
    "face_mouth_width": {
        "pos": ["mouth-scale-horiz-incr"],
        "neg": ["mouth-scale-horiz-decr"],
    },
    "face_lip_fullness": {
        "pos": ["mouth-upperlip-volume-incr", "mouth-lowerlip-volume-incr"],
        "neg": ["mouth-upperlip-volume-decr", "mouth-lowerlip-volume-decr"],
    },
}

MORPH_COUNT = len(FACE_SLIDERS) * 2


def configure_targets_root(targets_root: Path) -> None:
    """Point the baker at an MPFB `mpfb/data/targets` directory."""
    global _TARGETS_ROOT
    root = Path(targets_root)
    if not root.is_dir():
        raise FileNotFoundError(f"MPFB targets root does not exist: {root}")
    _TARGETS_ROOT = root


def morph_name(slider: str, side: str) -> str:
    if side not in ("pos", "neg"):
        raise ValueError(f"side must be pos|neg, got {side!r}")
    return f"{slider}__{side}"


def resolve_target(stem: str) -> Path:
    if _TARGETS_ROOT is None:
        raise RuntimeError("call configure_targets_root() before resolving MPFB targets")
    gz = list(_TARGETS_ROOT.rglob(f"{stem}.target.gz"))
    if gz:
        return gz[0]
    plain = list(_TARGETS_ROOT.rglob(f"{stem}.target"))
    if plain:
        return plain[0]
    raise FileNotFoundError(f"MPFB target not found: {stem} under {_TARGETS_ROOT}")


def bake_face_morphs(
    basemesh: bpy.types.Object,
    *,
    mpfb_import: Callable[[str], object],
    log: Callable[[str], None],
) -> list[str]:
    """Load curated face targets onto basemesh as named shape keys. Returns morph names."""
    TargetService = mpfb_import("services.targetservice").TargetService

    if basemesh.data.shape_keys is None:
        basemesh.shape_key_add(name="Basis")

    bpy.context.view_layer.objects.active = basemesh
    basemesh.select_set(True)

    created: list[str] = []
    for slider, sides in FACE_SLIDERS.items():
        for side in ("pos", "neg"):
            stems: list[str] = sides[side]
            name = morph_name(slider, side)
            _bake_combined_morph(basemesh, TargetService, name, stems, log)
            created.append(name)

    # Leave all face morphs at rest for export.
    for key in basemesh.data.shape_keys.key_blocks:
        if key.name != "Basis":
            key.value = 0.0

    log(f"Face morphs baked: {len(created)} keys ({len(FACE_SLIDERS)} sliders)")
    return created


def _zero_all_shape_keys(basemesh: bpy.types.Object) -> None:
    if basemesh.data.shape_keys is None:
        return
    for key in basemesh.data.shape_keys.key_blocks:
        key.value = 0.0


def apply_mask_modifiers_shape_key_safe(
    obj: bpy.types.Object,
    *,
    log: Callable[[str], None],
) -> None:
    """Apply MASK modifiers by deleting hidden verts in Edit mode.

    Blender refuses `modifier_apply` when shape keys exist; deleting verts remaps
    shape-key data and is the shape-key-safe equivalent for Mask modifiers.
    """
    masks = [m for m in obj.modifiers if m.type == "MASK"]
    if not masks:
        return

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    to_delete: set[int] = set()
    for mod in masks:
        vg_name = mod.vertex_group
        if not vg_name:
            log(f"Mask {mod.name}: no vertex group - skipping")
            continue
        vg = obj.vertex_groups.get(vg_name)
        if vg is None:
            log(f"Mask {mod.name}: missing vertex group {vg_name!r}")
            continue
        invert = bool(mod.invert_vertex_group)
        # Read weights off the vertices; vertex_group.weight() logs a Blender error
        # for every vertex outside the group, which is most of the mesh.
        group_index = vg.index
        for v in obj.data.vertices:
            weight = next((g.weight for g in v.groups if g.group == group_index), 0.0)
            in_group = weight > 0.1
            # Default Mask: keep verts in the group. Invert: hide verts in the group.
            hidden = (not in_group) if not invert else in_group
            if hidden:
                to_delete.add(v.index)

    if to_delete:
        for v in obj.data.vertices:
            v.select = v.index in to_delete
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.delete(type="VERT")
        bpy.ops.object.mode_set(mode="OBJECT")
        log(
            f"Shape-key-safe mask delete: removed ~{len(to_delete)} verts; "
            f"remaining={len(obj.data.vertices)}"
        )

    for mod in list(masks):
        name = mod.name
        obj.modifiers.remove(mod)
        log(f"Removed mask modifier {name}")


def _bake_combined_morph(
    basemesh: bpy.types.Object,
    TargetService,
    name: str,
    stems: list[str],
    log: Callable[[str], None],
) -> None:
    if basemesh.data.shape_keys and name in basemesh.data.shape_keys.key_blocks:
        raise RuntimeError(f"Shape key already exists: {name}")

    _zero_all_shape_keys(basemesh)

    temps: list[bpy.types.ShapeKey] = []
    for i, stem in enumerate(stems):
        path = resolve_target(stem)
        temp_name = f"_tmp_face_{name}_{i}"
        sk = TargetService.load_target(basemesh, str(path), weight=1.0, name=temp_name)
        if sk is None:
            raise RuntimeError(f"Failed to load target {stem} from {path}")
        temps.append(sk)

    bpy.context.view_layer.update()
    key = basemesh.shape_key_add(name=name, from_mix=True)
    key.value = 0.0

    for sk in temps:
        basemesh.shape_key_remove(sk)

    _zero_all_shape_keys(basemesh)
    log(f"  shape key {name} <- {', '.join(stems)}")
