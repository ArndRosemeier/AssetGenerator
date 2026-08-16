"""
Blender headless script: modular MPFB humans for Character Studio.

Character Studio assembles a character at runtime, so this exports parts rather
than finished outfits:

  {sex}_base.glb              nude body + eyes + 28 face morphs
  {sex}_dressed_{suit}.glb    same body with that suit's delete mask applied, so
                              no skin pokes through it
  pieces/{sex}_{id}.glb       one garment on the shared game_engine rig, no body

Every piece is fitted against an identically generated body, so all exports
share one rest pose and Godot can bind the garment meshes to the body skeleton.

Asset Lab owns this pipeline but does not vendor MPFB: Blender 4.2, the MPFB
plugin and the MakeHuman CC0 system assets are read from the City checkout.
Nothing under the City tree is written to. Outputs land in assets/humans/.

Run via:
  tools\\character_studio\\export_humans.bat
  (or) <city>\\tools\\vendor\\blender\\...\\blender.exe --background \\
       --python tools/character_studio/blender_export_humans.py

Environment:
  CITY_ROOT     override the City checkout (default: <AssetGenerator>/../City)
  STUDIO_ONLY   comma-separated subset of export ids
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CITY_ROOT = Path(os.environ.get("CITY_ROOT", str(ROOT.parent / "City")))
VENDOR = CITY_ROOT / "tools" / "vendor"
MPFB_SRC = VENDOR / "mpfb2_plugin" / "mpfb"
ASSETS_DIR = VENDOR / "makehuman_system_assets"
TARGETS_ROOT = MPFB_SRC / "data" / "targets"
# Community / pack clothes fetched by fetch_medieval_clothes.py (not in City).
EXTRA_CLOTHES_DIR = SCRIPT_DIR / "makehuman_extra_assets" / "clothes"

# MPFB writes into its user data dir; keep that inside Asset Lab so an export
# never mutates the City checkout.
USER_DATA_OVERRIDE = SCRIPT_DIR / ".mpfb_user_data"
OUT_DIR = ROOT / "assets" / "humans"
PIECES_SUBDIR = "pieces"
WARDROBE_JSON = OUT_DIR / "wardrobe.json"

EYES_MHCLO = ASSETS_DIR / "eyes" / "low-poly" / "low-poly.mhclo"
EYE_TEXTURE = ASSETS_DIR / "eyes" / "materials" / "brown_eye.png"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from mpfb_face_morphs import (  # noqa: E402
    MORPH_COUNT,
    apply_mask_modifiers_shape_key_safe,
    bake_face_morphs,
    configure_targets_root,
)

SEXES = ("male", "female")

# Suit entry: (id, label) or (id, label, (mhclo_part, ...)) for multi-piece suits.
# Multi-piece suits stamp every part's delete mask on the dressed body and export
# all part meshes into one piece GLB so the editor still has a single Suit slot.
SuitEntry = tuple[str, str] | tuple[str, str, tuple[str, ...]]


def _suit_id(entry: SuitEntry) -> str:
    return entry[0]


def _suit_label(entry: SuitEntry) -> str:
    return entry[1]


def _suit_parts(entry: SuitEntry) -> tuple[str, ...]:
    if len(entry) == 3:
        return entry[2]
    return (entry[0],)


# MakeHuman CC0 civilian wardrobe + free medieval/early-medieval community clothes.
WARDROBE_SUITS: dict[str, list[SuitEntry]] = {
    "male": [
        ("male_casualsuit01", "Casual 01"),
        ("male_casualsuit02", "Casual 02"),
        ("male_casualsuit03", "Casual 03"),
        ("male_worksuit01", "Work 01"),
        ("male_elegantsuit01", "Elegant 01"),
        ("monks_robe", "Monk Robe"),
        ("donitz_monk_robe", "Monk Robe (Pack)"),
        ("donitz_monk_robe_hood_off", "Monk Robe Hood Off"),
        (
            "monk_robe_hooded",
            "Monk Robe + Hood",
            ("donitz_monk_robe", "donitz_monk_robe_hood"),
        ),
        (
            "monk_robe_hood_down",
            "Monk Robe + Hood Down",
            ("donitz_monk_robe", "donitz_monk_robe_hood_down"),
        ),
        (
            "viking",
            "Viking",
            ("tunicviking", "pantsviking"),
        ),
        (
            "viking_soft",
            "Viking (Soft)",
            ("rehmanpolanski_viking_tunic", "rehmanpolanski_viking_pants"),
        ),
        ("germanic_clothes", "Germanic"),
    ],
    "female": [
        ("female_casualsuit01", "Casual 01"),
        ("female_casualsuit02", "Casual 02"),
        ("female_sportsuit01", "Sport 01"),
        ("female_elegantsuit01", "Elegant 01"),
        ("monks_robe", "Monk Robe"),
        ("donitz_monk_robe", "Monk Robe (Pack)"),
        ("donitz_monk_robe_hood_off", "Monk Robe Hood Off"),
        (
            "monk_robe_hooded",
            "Monk Robe + Hood",
            ("donitz_monk_robe", "donitz_monk_robe_hood"),
        ),
        (
            "monk_robe_hood_down",
            "Monk Robe + Hood Down",
            ("donitz_monk_robe", "donitz_monk_robe_hood_down"),
        ),
        (
            "viking",
            "Viking",
            ("tunicviking", "pantsviking"),
        ),
        (
            "viking_soft",
            "Viking (Soft)",
            ("rehmanpolanski_viking_tunic", "rehmanpolanski_viking_pants"),
        ),
        ("germanic_clothes", "Germanic"),
        ("viking_dress", "Viking Dress"),
        ("medievaldress", "Medieval Dress"),
    ],
}

# Shoes / hair / eyebrows are unisex mhclo assets, but each one is fitted and
# exported per sex so its weights match the body it will be bound to.
WARDROBE_SHOES: list[tuple[str, str]] = [
    ("shoes01", "Shoes 01"),
    ("shoes02", "Shoes 02"),
    ("shoes03", "Shoes 03"),
    ("shoes04", "Shoes 04"),
    ("shoes05", "Shoes 05"),
    ("bootsviking", "Viking Boots"),
    ("rehmanpolanski_viking_boots", "Viking Boots (Pack)"),
]

WARDROBE_HAIR: list[tuple[str, str]] = [
    ("afro01", "Afro 01"),
    ("bob01", "Bob 01"),
    ("bob02", "Bob 02"),
    ("braid01", "Braid 01"),
    ("long01", "Long 01"),
    ("ponytail01", "Ponytail 01"),
    ("short01", "Short 01"),
    ("short02", "Short 02"),
    ("short03", "Short 03"),
    ("short04", "Short 04"),
]

WARDROBE_EYEBROWS: list[tuple[str, str]] = [
    ("eyebrow001", "Eyebrow 01"),
    ("eyebrow002", "Eyebrow 02"),
    ("eyebrow003", "Eyebrow 03"),
    ("eyebrow004", "Eyebrow 04"),
    ("eyebrow005", "Eyebrow 05"),
    ("eyebrow006", "Eyebrow 06"),
    ("eyebrow007", "Eyebrow 07"),
    ("eyebrow008", "Eyebrow 08"),
    ("eyebrow009", "Eyebrow 09"),
    ("eyebrow010", "Eyebrow 10"),
    ("eyebrow011", "Eyebrow 11"),
    ("eyebrow012", "Eyebrow 12"),
]

# slot -> (MakeHuman asset root under the system pack, MPFB object_type)
SLOT_ASSET_KIND: dict[str, tuple[str, str]] = {
    "suit": ("clothes", "Clothes"),
    "shoes": ("clothes", "Clothes"),
    "hair": ("hair", "Hair"),
    "eyebrows": ("eyebrows", "Eyebrows"),
}

WARDROBE_SLOTS: tuple[str, ...] = ("suit", "shoes", "hair", "eyebrows")


def wardrobe_items(sex: str) -> list[dict]:
    """Every modular piece Character Studio can equip on this sex, in slot order."""
    if sex not in WARDROBE_SUITS:
        raise KeyError(f"unknown sex {sex!r}; expected one of {SEXES}")
    items: list[dict] = []
    suit_folder, suit_type = SLOT_ASSET_KIND["suit"]
    for entry in WARDROBE_SUITS[sex]:
        parts = _suit_parts(entry)
        items.append(
            {
                "id": _suit_id(entry),
                "slot": "suit",
                "label": _suit_label(entry),
                "asset_folder": suit_folder,
                "asset_type": suit_type,
                "parts": list(parts),
            }
        )
    for slot, entries in (
        ("shoes", WARDROBE_SHOES),
        ("hair", WARDROBE_HAIR),
        ("eyebrows", WARDROBE_EYEBROWS),
    ):
        asset_folder, asset_type = SLOT_ASSET_KIND[slot]
        for asset_id, label in entries:
            items.append(
                {
                    "id": asset_id,
                    "slot": slot,
                    "label": label,
                    "asset_folder": asset_folder,
                    "asset_type": asset_type,
                    "parts": [asset_id],
                }
            )
    return items


def _piece_id(sex: str, garment: str) -> str:
    return f"{sex}_{garment}"


def _piece_out(sex: str, garment: str) -> str:
    return f"{PIECES_SUBDIR}/{_piece_id(sex, garment)}.glb"


def _dressed_out(sex: str, suit: str) -> str:
    return f"{sex}_dressed_{suit}.glb"


def build_specs() -> list[dict]:
    """Bodies first (cheap, most useful), then one export per garment piece."""
    specs: list[dict] = []
    for sex in SEXES:
        specs.append(
            {"id": f"{sex}_base", "kind": "body", "sex": sex, "garments": [], "out": f"{sex}_base.glb"}
        )
    # One body per suit: the delete mask has to match the suit that is actually
    # worn, or a short sleeve exposes the hole a long one carved out. Shoes never
    # mask the body, so any shoe fits any of these.
    for sex in SEXES:
        for entry in WARDROBE_SUITS[sex]:
            suit = _suit_id(entry)
            specs.append(
                {
                    "id": f"{sex}_dressed_{suit}",
                    "kind": "body",
                    "sex": sex,
                    "garments": list(_suit_parts(entry)),
                    "out": _dressed_out(sex, suit),
                }
            )
    for sex in SEXES:
        for item in wardrobe_items(sex):
            specs.append(
                {
                    "id": _piece_id(sex, item["id"]),
                    "kind": "piece",
                    "sex": sex,
                    "item": item,
                    "out": _piece_out(sex, item["id"]),
                }
            )
    return specs


def _log(msg: str) -> None:
    print(f"[studio-export] {msg}", flush=True)


def _mpfb_import(path: str):
    """Import a submodule from whichever MPFB package name is active."""
    errors: list[str] = []
    for root in ("bl_ext.user_default.mpfb", "mpfb"):
        try:
            return __import__(f"{root}.{path}", fromlist=["*"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{root}.{path}: {exc}")
    raise ImportError(" ; ".join(errors))


def _ensure_mpfb_enabled() -> None:
    # Prefer the real user_default repo path. The extensions/.user staging tree
    # accepts a copy but Blender 4.2 does not load addons from there.
    candidates = [
        Path(bpy.utils.user_resource("EXTENSIONS")) / "user_default" / "mpfb",
        Path(os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\4.2\extensions\user_default\mpfb")),
        Path(os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\mpfb")),
    ]
    try:
        candidates.insert(0, Path(bpy.utils.extension_path_user("bl_ext.user_default")) / "mpfb")
    except Exception:  # noqa: BLE001
        pass

    errors: list[str] = []
    for target in candidates:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(MPFB_SRC, target)
            _log(f"Installed MPFB to {target}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"install {target}: {exc}")
            _log(f"Install candidate failed {target}: {exc}")
            continue

        for mod in ("bl_ext.user_default.mpfb", "mpfb"):
            try:
                bpy.ops.preferences.addon_enable(module=mod)
                _log(f"Enabled addon module: {mod}")
                bpy.ops.wm.save_userpref()
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"enable {mod} after {target}: {exc}")
                _log(f"Could not enable {mod}: {exc}")

    raise RuntimeError("Failed to enable MPFB addon/extension; " + " | ".join(errors))


def _install_system_assets() -> None:
    data_dir = USER_DATA_OVERRIDE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    addon = bpy.context.preferences.addons.get("mpfb") or bpy.context.preferences.addons.get(
        "bl_ext.user_default.mpfb"
    )
    if addon is None:
        raise RuntimeError("MPFB addon preferences not available after enabling the addon")
    addon.preferences.mpfb_user_data = str(USER_DATA_OVERRIDE)
    bpy.ops.wm.save_userpref()
    _log(f"Set mpfb_user_data={USER_DATA_OVERRIDE}")

    for name in ("clothes", "eyebrows", "eyelashes", "eyes", "hair", "proxymeshes", "skins"):
        src = ASSETS_DIR / name
        if not src.is_dir():
            raise FileNotFoundError(f"MakeHuman system assets missing folder: {src}")
        dst = data_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        _log(f"Installed asset folder {name}")

    # Overlay community/pack clothes (medieval, etc.) without mutating City.
    if EXTRA_CLOTHES_DIR.is_dir():
        clothes_dst = data_dir / "clothes"
        extra_count = 0
        for asset_dir in sorted(EXTRA_CLOTHES_DIR.iterdir()):
            if not asset_dir.is_dir():
                continue
            dest = clothes_dst / asset_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(asset_dir, dest)
            extra_count += 1
        _log(f"Overlayed {extra_count} extra clothes from {EXTRA_CLOTHES_DIR}")
    else:
        _log(f"No extra clothes dir at {EXTRA_CLOTHES_DIR}")

    AssetService = _mpfb_import("services.assetservice").AssetService
    AssetService.update_all_asset_lists()
    _log("Asset lists updated")


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.armatures):
        bpy.data.armatures.remove(block)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)


def _macro(gender: float) -> dict:
    TargetService = _mpfb_import("services.targetservice").TargetService
    d = TargetService.get_default_macro_info_dict()
    d["gender"] = gender
    d["age"] = 0.5
    d["muscle"] = 0.55 if gender > 0.5 else 0.45
    d["weight"] = 0.5
    d["height"] = 0.55 if gender > 0.5 else 0.5
    d["proportions"] = 0.5
    d["cupsize"] = 0.55 if gender < 0.5 else 0.15
    d["firmness"] = 0.5
    d["race"] = {"asian": 0.2, "caucasian": 0.6, "african": 0.2}
    return d


def _mhclo_path(folder_name: str, asset_folder: str = "clothes") -> Path:
    candidates: list[Path] = []
    if asset_folder == "clothes":
        candidates.append(EXTRA_CLOTHES_DIR / folder_name)
        candidates.append(USER_DATA_OVERRIDE / "data" / "clothes" / folder_name)
    candidates.append(ASSETS_DIR / asset_folder / folder_name)
    for folder in candidates:
        matches = sorted(folder.glob("*.mhclo"))
        if matches:
            return matches[0]
    raise FileNotFoundError(
        f"No .mhclo for {folder_name!r} under {asset_folder}; looked in {candidates}"
    )


def _equip_eyes(basemesh) -> object:
    """Fit the MakeHuman low-poly eyeballs and weight them to the head bone."""
    HumanService = _mpfb_import("services.humanservice").HumanService
    ObjectService = _mpfb_import("services.objectservice").ObjectService

    if not EYES_MHCLO.is_file():
        raise FileNotFoundError(f"MakeHuman eyes asset missing: {EYES_MHCLO}")

    HumanService.add_mhclo_asset(
        str(EYES_MHCLO),
        basemesh,
        asset_type="Eyes",
        subdiv_levels=0,
        material_type="GAMEENGINE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=False,
        import_weights=True,
    )
    eyes_objs = list(
        ObjectService.find_all_objects_of_type_amongst_nearest_relatives(basemesh, "Eyes")
    )
    if len(eyes_objs) != 1:
        raise RuntimeError(f"expected exactly one Eyes object, got {[o.name for o in eyes_objs]}")
    eyes = eyes_objs[0]
    eyes.name = "Eyes"
    _log(f"Equipped eyes: verts={len(eyes.data.vertices)}")
    return eyes


def _assign_eye_material(eyes) -> None:
    """Flat iris texture beats the MakeHuman litsphere shader once it reaches Godot."""
    if not EYE_TEXTURE.is_file():
        raise FileNotFoundError(f"Eye diffuse texture missing: {EYE_TEXTURE}")
    mat = bpy.data.materials.new(name="eye_brown")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("new material has no Principled BSDF node")
    bsdf.inputs["Roughness"].default_value = 0.25
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(EYE_TEXTURE))
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    eyes.data.materials.clear()
    eyes.data.materials.append(mat)
    _log(f"Eye texture: {EYE_TEXTURE.name}")


def _strip_shape_keys_keeping_mix(obj) -> None:
    """Bake the current shape-key mix into the mesh and drop the keys."""
    if obj.data.shape_keys is None:
        return
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Shape-only bake: disable armature AND masks. Evaluating masks here would
    # delete helper verts and renumber indices before the face targets load.
    disabled: list = []
    for mod in obj.modifiers:
        if mod.type in ("ARMATURE", "MASK"):
            disabled.append((mod, mod.show_viewport, mod.show_render))
            mod.show_viewport = False
            mod.show_render = False
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    old_mesh = obj.data
    obj.data = new_mesh
    bpy.data.meshes.remove(old_mesh)
    for mod, show_v, show_r in disabled:
        mod.show_viewport = True if mod.type == "ARMATURE" else show_v
        mod.show_render = True if mod.type == "ARMATURE" else show_r
    _log(f"Baked shape keys into {obj.name} (masks deferred)")


def _apply_non_armature_modifiers(obj) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for mod in obj.modifiers:
        if mod.type == "ARMATURE":
            mod.show_viewport = True
            mod.show_render = True
    for mod in list(obj.modifiers):
        if mod.type == "SUBSURF":
            obj.modifiers.remove(mod)
    has_shape_keys = obj.data.shape_keys is not None
    # Shape keys block modifier_apply for Mask; delete the hidden verts instead.
    if has_shape_keys:
        apply_mask_modifiers_shape_key_safe(obj, log=_log)
    for mod in list(obj.modifiers):
        if mod.type == "ARMATURE":
            continue
        bpy.ops.object.modifier_apply(modifier=mod.name)
        _log(f"Applied modifier {mod.name} on {obj.name}")


def _delete_non_body_vertices(basemesh) -> None:
    """Fallback: drop verts outside the 'body' group (removes helper geometry)."""
    body = basemesh.vertex_groups.get("body")
    if body is None:
        raise RuntimeError("no 'body' vertex group; cannot strip helper geometry")
    bpy.ops.object.select_all(action="DESELECT")
    basemesh.select_set(True)
    bpy.context.view_layer.objects.active = basemesh
    body_index = body.index
    for v in basemesh.data.vertices:
        weight = next((g.weight for g in v.groups if g.group == body_index), 0.0)
        v.select = weight < 0.1
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    _log(f"Stripped non-body verts; remaining={len(basemesh.data.vertices)}")


def _limit_weights_to_four(obj) -> None:
    """Godot/glTF only use 4 influences per vertex; extras pose the mesh wrong."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)


def _assign_unweighted_verts(obj, preferred_bones: tuple[str, ...]) -> None:
    """Stop the glTF exporter from inventing a neutral_bone for stray verts.

    Clothes (especially shoes) often lack torso groups, so callers pass a short
    preferred list; the first group that exists on the mesh is used.
    """
    fallback = None
    chosen = ""
    for bone_name in preferred_bones:
        fallback = obj.vertex_groups.get(bone_name)
        if fallback is not None:
            chosen = bone_name
            break
    # Read weights off the vertices rather than probing vertex_group.weight(), which
    # logs a Blender error for every vertex that is not in the group.
    deform_indices = {
        vg.index
        for vg in obj.vertex_groups
        if vg.name != "body" and not vg.name.startswith("joint-")
    }
    unweighted = [
        v.index
        for v in obj.data.vertices
        if sum(g.weight for g in v.groups if g.group in deform_indices) <= 1e-4
    ]
    if not unweighted:
        _log(f"{obj.name}: all verts already weighted")
        return
    if fallback is None:
        raise RuntimeError(
            f"{obj.name}: {len(unweighted)} unweighted verts and none of "
            f"{preferred_bones} exist as vertex groups"
        )
    fallback.add(unweighted, 1.0, "REPLACE")
    _log(f"{obj.name}: assigned {len(unweighted)} unweighted verts to {chosen}")


def _assign_skin_material(basemesh, sex: str) -> None:
    mat = bpy.data.materials.new(name=f"{sex}_skin")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("new material has no Principled BSDF node")
    bsdf.inputs["Base Color"].default_value = (
        (0.86, 0.68, 0.54, 1.0) if sex == "female" else (0.78, 0.58, 0.44, 1.0)
    )
    bsdf.inputs["Roughness"].default_value = 0.65

    # Prefer the young lightskinned textures City already uses. Avoid matching
    # "*male*" against "*female*" filenames.
    preferred = (
        ASSETS_DIR / "skins" / "young_caucasian_female" / "young_lightskinned_female_diffuse.png"
        if sex == "female"
        else ASSETS_DIR / "skins" / "young_caucasian_male" / "young_lightskinned_male_diffuse.png"
    )
    if preferred.is_file():
        tex_path = preferred
    else:
        token = "female" if sex == "female" else "male"
        tex_path = next(
            (
                p
                for p in sorted((ASSETS_DIR / "skins").rglob("*diffuse*.png"))
                if token in p.name
                and (token != "male" or "female" not in p.name)
                and "darkskinned" not in p.name
            ),
            None,
        )
    if tex_path is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(tex_path))
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        _log(f"Skin texture: {tex_path.name}")
    else:
        _log("Skin texture not found; using solid skin color")

    basemesh.data.materials.clear()
    basemesh.data.materials.append(mat)


def _log_rig_alignment(basemesh, armature, *, require_pelvis_in_mesh: bool) -> None:
    """Bone pivots must sit inside the mesh (hip near pelvis height, not near feet).

    Clothed exports delete large lower-body chunks under garments, so the pelvis
    ratio is only enforced for nude bases.
    """
    zs = [(basemesh.matrix_world @ v.co).z for v in basemesh.data.vertices]
    mesh_min, mesh_max = min(zs), max(zs)
    _log(f"Mesh world Z range [{mesh_min:.3f}, {mesh_max:.3f}] height={mesh_max - mesh_min:.3f}")

    bpy.context.view_layer.update()
    pelvis = armature.pose.bones.get("pelvis")
    if pelvis is None:
        raise RuntimeError("game_engine rig has no pelvis bone")
    head = armature.matrix_world @ pelvis.head
    rel = (head.z - mesh_min) / max(mesh_max - mesh_min, 1e-6)
    _log(f"Pelvis height ratio along mesh={rel:.3f} (expect ~0.5 for nude)")
    if require_pelvis_in_mesh and rel < 0.35:
        raise RuntimeError(f"pelvis sits at {rel:.3f} of mesh height - rig fit failed")


def _create_rigged_human(sex: str):
    """Fresh macro-shaped body on the game_engine rig. Identical for every export."""
    HumanService = _mpfb_import("services.humanservice").HumanService

    _clear_scene()
    gender = 0.05 if sex == "female" else 0.95
    # Keep helper geometry until AFTER rigging - game_engine bone placement needs joints.
    basemesh = HumanService.create_human(
        mask_helpers=True,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=_macro(gender),
    )
    basemesh.name = f"{sex}_body"
    _log(f"Created basemesh {basemesh.name} verts={len(basemesh.data.vertices)}")

    armature = HumanService.add_builtin_rig(basemesh, "game_engine", import_weights=True)
    if armature is None:
        raise RuntimeError("Failed to add game_engine rig")
    armature.name = f"{sex}_armature"
    _log(f"Added rig {armature.name} bones={len(armature.data.bones)}")
    return basemesh, armature


def _equip_assets(basemesh, items: list[dict], spec_id: str) -> list:
    """Fit one or more mhclo assets and return the resulting mesh objects in order."""
    HumanService = _mpfb_import("services.humanservice").HumanService
    ObjectService = _mpfb_import("services.objectservice").ObjectService

    equipped: list = []
    for item in items:
        asset_type = str(item["asset_type"])
        before = {
            obj.name
            for obj in ObjectService.find_all_objects_of_type_amongst_nearest_relatives(
                basemesh, asset_type
            )
        }
        asset_path = _mhclo_path(str(item["id"]), str(item["asset_folder"]))
        _log(f"Equipping {asset_path.name} as {asset_type}")
        HumanService.add_mhclo_asset(
            str(asset_path),
            basemesh,
            asset_type=asset_type,
            subdiv_levels=0,
            material_type="GAMEENGINE",
            set_up_rigging=True,
            interpolate_weights=True,
            import_subrig=False,
            import_weights=True,
        )
        after = [
            obj
            for obj in ObjectService.find_all_objects_of_type_amongst_nearest_relatives(
                basemesh, asset_type
            )
            if obj.name not in before
        ]
        if len(after) != 1:
            raise RuntimeError(
                f"{spec_id}: expected one new {asset_type} after {item['id']}, got "
                f"{[o.name for o in after]}"
            )
        equipped.append(after[0])
    return equipped


def _equip_clothes(basemesh, garments: list[str], spec_id: str) -> list:
    """Body delete-masks only come from Clothes; suits use this helper."""
    items = [
        {"id": garment, "asset_folder": "clothes", "asset_type": "Clothes"}
        for garment in garments
    ]
    return _equip_assets(basemesh, items, spec_id)


def _export_selection(out_rel: str, *, with_morphs: bool) -> Path:
    out_glb = OUT_DIR / out_rel
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    if out_glb.exists():
        out_glb.unlink()

    bpy.ops.export_scene.gltf(
        filepath=str(out_glb),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_animations=False,
        export_skins=True,
        export_morph=with_morphs,
        export_yup=True,
    )
    _log(f"Exported {out_glb} ({out_glb.stat().st_size} bytes)")
    return out_glb


def _export_body(spec: dict) -> Path:
    """Nude base, or the dressed base whose garment delete-masks have been applied."""
    sex = spec["sex"]
    garments: list[str] = spec["garments"]
    basemesh, armature = _create_rigged_human(sex)

    # Eyes and clothes both fit against the macro-shaped basemesh, so equip them
    # before the shape keys are collapsed. The garments here exist only to stamp
    # their delete groups onto the body; they are dropped before export.
    eyes = _equip_eyes(basemesh)
    clothes_objs = _equip_clothes(basemesh, garments, spec["id"])

    # Bake macros into Basis, then face morphs while MH vertex indices still match
    # the target files, then strip helpers and the masked-away skin.
    _strip_shape_keys_keeping_mix(basemesh)
    morphs = bake_face_morphs(basemesh, mpfb_import=_mpfb_import, log=_log)
    if len(morphs) != MORPH_COUNT:
        raise RuntimeError(f"baked {len(morphs)} face morphs, expected {MORPH_COUNT}")
    _apply_non_armature_modifiers(basemesh)
    if len(basemesh.data.vertices) > 14000:
        _log(f"Vert count still high ({len(basemesh.data.vertices)}); deleting non-body verts")
        _delete_non_body_vertices(basemesh)

    _assign_unweighted_verts(basemesh, ("spine_03", "pelvis"))
    _limit_weights_to_four(basemesh)
    _assign_skin_material(basemesh, sex)

    _apply_non_armature_modifiers(eyes)
    _assign_unweighted_verts(eyes, ("head", "spine_03"))
    _limit_weights_to_four(eyes)
    _assign_eye_material(eyes)

    for clothes in clothes_objs:
        bpy.data.objects.remove(clothes, do_unlink=True)
    if clothes_objs:
        _log(f"Dropped {len(clothes_objs)} garment objects; body keeps their delete masks")

    _log_rig_alignment(basemesh, armature, require_pelvis_in_mesh=not garments)

    bpy.ops.object.select_all(action="DESELECT")
    basemesh.select_set(True)
    armature.select_set(True)
    eyes.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return _export_selection(spec["out"], with_morphs=True)


def _export_piece(spec: dict) -> Path:
    """A wardrobe piece on the shared rig, with no body and no face morphs.

    Multi-part suits (e.g. viking tunic + pants) equip every part and export them
    together so Character Studio still binds one Suit path.
    """
    item: dict = spec["item"]
    parts: list[str] = list(item.get("parts") or [item["id"]])
    basemesh, armature = _create_rigged_human(spec["sex"])
    equip_items = [
        {
            "id": part_id,
            "asset_folder": item["asset_folder"],
            "asset_type": item["asset_type"],
        }
        for part_id in parts
    ]
    pieces = _equip_assets(basemesh, equip_items, spec["id"])

    bpy.ops.object.select_all(action="DESELECT")
    for piece in pieces:
        _apply_non_armature_modifiers(piece)
        _assign_unweighted_verts(piece, ("head", "spine_03", "pelvis", "foot_l", "foot_r"))
        _limit_weights_to_four(piece)
        _log(f"{spec['id']}: {item['slot']} part verts={len(piece.data.vertices)}")
        piece.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return _export_selection(spec["out"], with_morphs=False)


def _create_and_export(spec: dict) -> Path:
    if spec["kind"] == "body":
        return _export_body(spec)
    if spec["kind"] == "piece":
        return _export_piece(spec)
    raise RuntimeError(f"{spec['id']}: unknown export kind {spec['kind']!r}")


def _selected_specs(specs: list[dict]) -> list[dict]:
    only = os.environ.get("STUDIO_ONLY", "").strip()
    if not only:
        return specs
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    known = {s["id"] for s in specs}
    missing = wanted - known
    if missing:
        raise RuntimeError(f"STUDIO_ONLY unknown ids: {sorted(missing)} (known: {sorted(known)})")
    return [s for s in specs if s["id"] in wanted]


def _write_wardrobe_json() -> None:
    """Runtime catalogue. Always full, even when STUDIO_ONLY exported a subset."""
    items: list[dict] = []
    for sex in SEXES:
        for item in wardrobe_items(sex):
            items.append(
                {
                    "id": item["id"],
                    "sex": sex,
                    "slot": item["slot"],
                    "label": item["label"],
                    "path": _piece_out(sex, item["id"]),
                }
            )
    payload = {
        "slots": list(WARDROBE_SLOTS),
        "bodies": [
            {
                "sex": sex,
                "nude": f"{sex}_base.glb",
                # suit id -> the body whose skin under that suit has been deleted
                "dressed": {
                    _suit_id(entry): _dressed_out(sex, _suit_id(entry))
                    for entry in WARDROBE_SUITS[sex]
                },
            }
            for sex in SEXES
        ],
        "items": items,
    }
    WARDROBE_JSON.parent.mkdir(parents=True, exist_ok=True)
    WARDROBE_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _log(f"Wrote {WARDROBE_JSON.name} ({len(items)} pieces)")


def main() -> None:
    _log("Starting Character Studio modular export")
    for required in (MPFB_SRC, ASSETS_DIR, TARGETS_ROOT):
        if not required.is_dir():
            raise FileNotFoundError(f"City vendor path missing: {required}")

    configure_targets_root(TARGETS_ROOT)
    _ensure_mpfb_enabled()
    _install_system_assets()

    LocationService = _mpfb_import("services.locationservice").LocationService
    _log(f"MPFB user data: {LocationService.get_user_data()}")

    specs = _selected_specs(build_specs())
    for index, spec in enumerate(specs, start=1):
        _log(f"--- [{index}/{len(specs)}] {spec['id']} ({spec['kind']})")
        _create_and_export(spec)
    _write_wardrobe_json()
    _log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
