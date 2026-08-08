"""
Blender headless script: MPFB humans with MakeHuman eyes for Character Studio.

Produces the four GLBs Character Studio loads (male/female nude base and one
casual outfit each). Every export carries the 28 curated face morphs plus a
fitted, head-weighted `Eyes` mesh, so faces have real eyeballs instead of empty
sockets.

Asset Lab owns this pipeline but does not vendor MPFB: Blender 4.2, the MPFB
plugin and the MakeHuman CC0 system assets are read from the City checkout.
Nothing under the City tree is written to.

Run via:
  tools\\character_studio\\export_humans.bat
  (or) <city>\\tools\\vendor\\blender\\...\\blender.exe --background \\
       --python tools/character_studio/blender_export_humans.py

Environment:
  CITY_ROOT     override the City checkout (default: <AssetGenerator>/../City)
  STUDIO_ONLY   comma-separated subset of ids from HUMAN_MATRIX
"""
from __future__ import annotations

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

# MPFB writes into its user data dir; keep that inside Asset Lab so an export
# never mutates the City checkout.
USER_DATA_OVERRIDE = SCRIPT_DIR / ".mpfb_user_data"
OUT_DIR = ROOT / "character_studio" / "assets" / "humans"

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

# "garments" is the mhclo equip order; an empty list is a nude base.
HUMAN_MATRIX: list[dict] = [
    {"id": "male_base", "sex": "male", "garments": [], "out": "male_base.glb"},
    {"id": "female_base", "sex": "female", "garments": [], "out": "female_base.glb"},
    {
        "id": "male_casual_01",
        "sex": "male",
        "garments": ["male_casualsuit01", "shoes01"],
        "out": "outfits/male_casual_01.glb",
    },
    {
        "id": "female_casual_01",
        "sex": "female",
        "garments": ["female_casualsuit01", "shoes01"],
        "out": "outfits/female_casual_01.glb",
    },
]


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
    candidates = [
        Path(os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\4.2\extensions\.user\user_default\mpfb")),
        Path(os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\4.2\extensions\user_default\mpfb")),
        Path(bpy.utils.user_resource("EXTENSIONS")) / "user_default" / "mpfb",
    ]
    try:
        candidates.insert(0, Path(bpy.utils.extension_path_user("bl_ext.user_default")) / "mpfb")
    except Exception:  # noqa: BLE001
        pass

    installed = False
    for target in candidates:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(MPFB_SRC, target)
            _log(f"Installed MPFB to {target}")
            installed = True
            break
        except Exception as exc:  # noqa: BLE001
            _log(f"Install candidate failed {target}: {exc}")
    if not installed:
        raise RuntimeError("Could not install MPFB into any Blender extension path")

    for mod in ("bl_ext.user_default.mpfb", "mpfb"):
        try:
            bpy.ops.preferences.addon_enable(module=mod)
            _log(f"Enabled addon module: {mod}")
            bpy.ops.wm.save_userpref()
            return
        except Exception as exc:  # noqa: BLE001
            _log(f"Could not enable {mod}: {exc}")
    raise RuntimeError("Failed to enable MPFB addon/extension")


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


def _mhclo_path(folder_name: str) -> Path:
    folder = ASSETS_DIR / "clothes" / folder_name
    matches = sorted(folder.glob("*.mhclo"))
    if not matches:
        raise FileNotFoundError(f"No .mhclo in {folder}")
    return matches[0]


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


def _create_and_export(spec: dict) -> Path:
    HumanService = _mpfb_import("services.humanservice").HumanService
    ObjectService = _mpfb_import("services.objectservice").ObjectService
    sex = spec["sex"]

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

    # Eyes and clothes both fit against the macro-shaped basemesh, so equip them
    # before the shape keys are collapsed.
    eyes = _equip_eyes(basemesh)
    for garment in spec["garments"]:
        garment_path = _mhclo_path(garment)
        _log(f"Equipping {garment_path.name}")
        HumanService.add_mhclo_asset(
            str(garment_path),
            basemesh,
            asset_type="Clothes",
            subdiv_levels=0,
            material_type="GAMEENGINE",
            set_up_rigging=True,
            interpolate_weights=True,
            import_subrig=False,
            import_weights=True,
        )
    clothes_objs = list(
        ObjectService.find_all_objects_of_type_amongst_nearest_relatives(basemesh, "Clothes")
    )
    if len(clothes_objs) != len(spec["garments"]):
        raise RuntimeError(
            f"{spec['id']}: equipped {len(clothes_objs)} garments, expected {len(spec['garments'])}"
        )

    # Bake macros into Basis, then face morphs while MH vertex indices still match
    # the target files, then strip helpers.
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
        _apply_non_armature_modifiers(clothes)
        _assign_unweighted_verts(clothes, ("spine_03", "pelvis", "foot_l", "foot_r", "head"))
        _limit_weights_to_four(clothes)

    _log_rig_alignment(basemesh, armature, require_pelvis_in_mesh=not spec["garments"])

    bpy.ops.object.select_all(action="DESELECT")
    basemesh.select_set(True)
    armature.select_set(True)
    eyes.select_set(True)
    for clothes in clothes_objs:
        clothes.select_set(True)
    bpy.context.view_layer.objects.active = armature

    out_glb = OUT_DIR / spec["out"]
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
        export_morph=True,
        export_yup=True,
    )
    _log(f"Exported {out_glb} ({out_glb.stat().st_size} bytes)")
    return out_glb


def _selected_specs() -> list[dict]:
    only = os.environ.get("STUDIO_ONLY", "").strip()
    if not only:
        return HUMAN_MATRIX
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    known = {s["id"] for s in HUMAN_MATRIX}
    missing = wanted - known
    if missing:
        raise RuntimeError(f"STUDIO_ONLY unknown ids: {sorted(missing)} (known: {sorted(known)})")
    return [s for s in HUMAN_MATRIX if s["id"] in wanted]


def main() -> None:
    _log("Starting Character Studio human export (with eyes)")
    for required in (MPFB_SRC, ASSETS_DIR, TARGETS_ROOT):
        if not required.is_dir():
            raise FileNotFoundError(f"City vendor path missing: {required}")

    configure_targets_root(TARGETS_ROOT)
    _ensure_mpfb_enabled()
    _install_system_assets()

    LocationService = _mpfb_import("services.locationservice").LocationService
    _log(f"MPFB user data: {LocationService.get_user_data()}")

    for spec in _selected_specs():
        _create_and_export(spec)
    _log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
