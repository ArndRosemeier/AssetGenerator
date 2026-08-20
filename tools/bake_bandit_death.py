# -*- coding: utf-8 -*-
"""ADD UAL Death01 onto the live bandit without dropping Idle/Attack/Walk.

Rest-relative retarget is identical to bake_human_idle_walk.py.
Writes Orrun + AG dests only. Never writes City or civilian walkers.
"""
from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import sys
import traceback
from pathlib import Path

TOOLS = Path(r"C:\Projekte\AssetGenerator\tools")
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

LIVE = Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans\male_bandit_01.glb")
AG_DEST = Path(r"C:\Projekte\AssetGenerator\assets\humans\outfits\male_bandit_01.glb")
CITY_BANDIT = Path(r"C:\Projekte\City\assets\humans\outfits\male_bandit_01.glb")
CIVILIANS = (
    Path(r"C:\Projekte\AssetGenerator\assets\humans\male_dressed_male_worksuit01.glb"),
    Path(r"C:\Projekte\AssetGenerator\assets\humans\female_dressed_female_casualsuit01.glb"),
    Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans\male_dressed_male_worksuit01.glb"),
    Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans\female_dressed_female_casualsuit01.glb"),
)
PREVIEW_PNG = Path(r"C:\Users\windo\agent-previews\bandit_death.png")
KEEP_CLIPS = ("Idle", "Idle_Loop", "Walk", "Walk_Loop", "Attack", "Sword_Attack")
DEATH_SRC = "Death01"
DEATH_NAMES = ("Death", "Death01")


def log(msg: str) -> None:
    print(f"[bandit-death] {msg}", flush=True)


def snapshot(paths):
    out = {}
    for p in paths:
        if p.is_file():
            st = p.stat()
            out[str(p)] = (st.st_size, int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime))
        else:
            out[str(p)] = None
    return out


def assert_untouched(before, label):
    after = snapshot([Path(k) for k in before])
    dirty = []
    for k, v in before.items():
        if after.get(k) != v:
            dirty.append((k, v, after.get(k)))
    if dirty:
        raise RuntimeError(f"{label} files changed: {dirty}")
    log(f"{label} untouched ({len(before)} paths)")


def write_glb(path: Path, doc: dict, blob: bytes) -> None:
    json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    pad_j = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * pad_j
    bin_bytes = blob
    pad_b = (4 - (len(bin_bytes) % 4)) % 4
    bin_bytes = bin_bytes + (b"\x00" * pad_b)
    length = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    out = bytearray()
    out += b"glTF"
    out += struct.pack("<II", 2, length)
    out += struct.pack("<II", len(json_bytes), 0x4E4F534A)
    out += json_bytes
    out += struct.pack("<II", len(bin_bytes), 0x004E4942)
    out += bin_bytes
    path.write_bytes(bytes(out))


def glb_fourcc(path: Path) -> list[str]:
    data = path.read_bytes()
    off = 12
    tags = []
    while off + 8 <= len(data):
        cl, ct = struct.unpack_from("<II", data, off)
        off += 8
        tags.append(bytes([ct & 0xFF, (ct >> 8) & 0xFF, (ct >> 16) & 0xFF, (ct >> 24) & 0xFF]).decode("latin1"))
        off += cl
    return tags


def force_opaque_json(path: Path) -> dict:
    import bake_human_idle_walk as B
    doc, blob = B.glb_chunks(path)
    for mat in doc.get("materials", []):
        mat["alphaMode"] = "OPAQUE"
        mat.pop("alphaCutoff", None)
        pbr = mat.get("pbrMetallicRoughness") or {}
        if "baseColorFactor" in pbr and len(pbr["baseColorFactor"]) == 4:
            pbr["baseColorFactor"][3] = 1.0
    write_glb(path, doc, blob)
    tags = glb_fourcc(path)
    anims = [a.get("name") for a in doc.get("animations", [])]
    mats = [(m.get("name"), m.get("alphaMode", "OPAQUE")) for m in doc.get("materials", [])]
    return {
        "clips": anims,
        "materials": mats,
        "fourcc": tags,
        "size": path.stat().st_size,
        "meshes": [m.get("name") for m in doc.get("meshes", [])],
    }


def force_opaque_mats():
    import bpy
    for mat in bpy.data.materials:
        if hasattr(mat, "blend_method"):
            try:
                mat.blend_method = "OPAQUE"
            except Exception:
                pass
        if hasattr(mat, "surface_render_method"):
            try:
                mat.surface_render_method = "OPAQUE"
            except Exception:
                pass
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED" and "Alpha" in node.inputs:
                    node.inputs["Alpha"].default_value = 1.0


def dest_bbox(objs):
    from mathutils import Vector
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    hit = False
    for o in objs:
        if o.type != "MESH" or o.name not in __import__("bpy").data.objects:
            continue
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            mins.x, mins.y, mins.z = min(mins.x, w.x), min(mins.y, w.y), min(mins.z, w.z)
            maxs.x, maxs.y, maxs.z = max(maxs.x, w.x), max(maxs.y, w.y), max(maxs.z, w.z)
            hit = True
    if not hit:
        return Vector((0, 0, 0.4)), Vector((1, 1, 1))
    return (mins + maxs) * 0.5, (maxs - mins)


def setup_death_preview(center, extent):
    import bpy
    from mathutils import Vector
    import math as _m

    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    mat = bpy.data.materials.new("PreviewGround")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.18, 0.175, 0.165, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = "OPAQUE"
        except Exception:
            pass
    bpy.ops.mesh.primitive_plane_add(size=12.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "PreviewGround"
    ground.data.materials.append(mat)

    world = bpy.data.worlds.new("PreviewWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.14, 0.145, 0.155, 1.0)
        bg.inputs[1].default_value = 1.0

    span = max(float(extent.x), float(extent.y), float(extent.z), 0.8)
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    # 3/4 hero, slightly high so a finished-on-ground pose reads
    cam.location = Vector((
        center.x + span * 1.55,
        center.y - span * 2.05,
        max(center.z + span * 1.15, 1.35),
    ))
    target = Vector((center.x, center.y, max(center.z, 0.15)))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    def add_light(name, ltype, loc, energy, size=0.6, rot=None):
        data = bpy.data.lights.new(name, ltype)
        data.energy = energy
        if ltype == "AREA":
            data.size = size
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        if rot:
            obj.rotation_euler = rot
        bpy.context.scene.collection.objects.link(obj)

    add_light("Key", "SUN", (3.0, -2.5, 6.0), 3.4, rot=(_m.radians(50), _m.radians(15), _m.radians(35)))
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0, size=1.6)

    scene = bpy.context.scene
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    log(f"preview engine={scene.render.engine} cam={tuple(round(c, 3) for c in cam.location)} look={tuple(round(c, 3) for c in target)}")


def apply_action(arm, name: str, frame: int):
    import bpy
    import bake_human_idle_walk as B
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing")
    B.assign_action(arm, act)
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()


def export_dest_hold(out_path, dest, dest_objects):
    """Same as bake_human_idle_walk.export_dest but do not reset pose bones.

    export_reset_pose_bones=True appends a rest/T-pose key on the last sample,
    which stands the corpse back up. Death must hold the finished down pose.
    """
    import bpy
    import bake_human_idle_walk as B
    if dest.animation_data:
        dest.animation_data.action = None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in dest_objects:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    dest.select_set(True)
    bpy.context.view_layer.objects.active = dest
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scratch_out = B.SCRATCH / (out_path.stem + "_baked.glb")
    if scratch_out.exists():
        scratch_out.unlink()
    kwargs = dict(
        filepath=str(scratch_out),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_skins=True,
        export_morph=True,
        export_yup=True,
        export_draco_mesh_compression_enable=False,
        export_nla_strips=True,
        export_anim_single_armature=True,
        export_optimize_animation_size=False,
        export_force_sampling=True,
        export_reset_pose_bones=False,
        export_rest_position_armature=True,
        export_current_frame=False,
        export_extras=False,
        export_cameras=False,
        export_lights=False,
        export_def_bones=False,
    )
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(
            filepath=str(scratch_out),
            export_format="GLB",
            use_selection=True,
            export_apply=False,
            export_animations=True,
            export_skins=True,
            export_morph=True,
            export_yup=True,
            export_draco_mesh_compression_enable=False,
        )
    if not scratch_out.is_file():
        alt = Path(str(scratch_out) + ".glb")
        if alt.is_file():
            scratch_out = alt
        else:
            raise RuntimeError(f"export produced no file: {scratch_out}")
    bak = out_path.with_suffix(".glb.bak")
    if not bak.is_file():
        raise RuntimeError(f"refusing overwrite, missing backup {bak}")
    shutil.copy2(scratch_out, out_path)
    log(f"exported {out_path} ({out_path.stat().st_size} bytes) reset_pose_bones=False")


def hold_death_last_key(path: Path) -> dict:
    """If exporter snapped the last Death sample back to rest, hold the previous key."""
    import bake_human_idle_walk as B
    doc, blob = B.glb_chunks(path)
    blob = bytearray(blob)
    names = B.node_name_map(doc)
    notes = []
    for anim in doc.get("animations", []):
        if anim.get("name") not in DEATH_NAMES:
            continue
        pelvis_ch = None
        for ch in anim.get("channels", []):
            tgt = ch.get("target", {})
            if names.get(tgt.get("node")) == "pelvis" and tgt.get("path") == "translation":
                pelvis_ch = ch
                break
        if pelvis_ch is None:
            notes.append(f"{anim.get('name')} no pelvis translation")
            continue
        samp = anim["samplers"][pelvis_ch["sampler"]]
        locs, _ = B.read_accessor(doc, bytes(blob), samp["output"])
        if len(locs) < 3:
            continue
        first_z, last_z, prev_z = locs[0][2], locs[-1][2], locs[-2][2]
        min_z = min(l[2] for l in locs)
        notes.append(f"{anim.get('name')} pelvis z first={first_z:.3f} last={last_z:.3f} prev={prev_z:.3f} min={min_z:.3f}")
        if last_z > 0.4 and prev_z < 0.25:
            # rewrite last sample of every sampler in this clip to the previous sample
            for samp in anim.get("samplers", []):
                acc = doc["accessors"][samp["output"]]
                bv = doc["bufferViews"][acc["bufferView"]]
                n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
                sz = {5126: 4, 5125: 4, 5123: 2, 5121: 1}[acc["componentType"]]
                off = (bv.get("byteOffset", 0) + acc.get("byteOffset", 0))
                stride = bv.get("byteStride") or (sz * n)
                if acc["count"] < 2:
                    continue
                prev = blob[off + (acc["count"] - 2) * stride: off + (acc["count"] - 1) * stride]
                last_off = off + (acc["count"] - 1) * stride
                blob[last_off: last_off + len(prev)] = prev
            notes.append(f"{anim.get('name')} held previous key onto last sample")
    write_glb(path, doc, bytes(blob))
    return {"notes": notes}


def action_last_frame(name: str) -> int:
    import bpy
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing")
    frames = [kp.co.x for fc in act.fcurves for kp in fc.keyframe_points]
    if not frames:
        return int(round(act.frame_range[1]))
    return int(round(max(frames)))


def pelvis_world_z(arm) -> float:
    pb = arm.pose.bones.get("pelvis")
    if pb is None:
        return 0.0
    return (arm.matrix_world @ pb.matrix).to_translation().z


def bake_add_death(dest_path: Path) -> dict:
    import bpy
    import bake_human_idle_walk as B

    log(f"==== add Death onto {dest_path}")
    B.clear_scene()
    B.import_gltf(dest_path)
    dest_objects = [o for o in bpy.data.objects]
    dest = B.find_armature(has_bone="pelvis")
    mesh_names = [o.name for o in dest_objects if o.type == "MESH"]
    log(f"dest armature {dest.name} bones={len(dest.data.bones)} meshes={mesh_names}")

    dest_actions = {}
    for act in list(bpy.data.actions):
        raw = act.name
        if raw.startswith("DST_"):
            raw = raw[4:]
        else:
            act.name = "DST_" + act.name
            raw = act.name[4:]
        dest_actions[raw] = act
    log(f"kept dest clips: {sorted(dest_actions)}")
    missing_keep = [c for c in KEEP_CLIPS if c not in dest_actions]
    if missing_keep:
        raise RuntimeError(f"live dest missing clips {missing_keep}; have {sorted(dest_actions)}")

    B.import_gltf(B.SRC_ANIM)
    src = B.find_armature(has_bone="DEF-hips")
    log(f"src armature {src.name} bones={len(src.data.bones)}")

    src_actions = {}
    for act in list(bpy.data.actions):
        if act.name.startswith("DST_"):
            continue
        raw = act.name
        if raw.startswith("SRC_"):
            raw = raw[4:]
        else:
            act.name = "SRC_" + act.name
            raw = act.name[4:]
        src_actions[raw] = act
    if DEATH_SRC not in src_actions:
        raise RuntimeError(f"{DEATH_SRC} missing from UAL; have {sorted(src_actions)}")
    log(f"UAL has {DEATH_SRC} frames={tuple(src_actions[DEATH_SRC].frame_range)}")

    B.reset_pose(src)
    B.reset_pose(dest)
    src_rest = {s: B.rest_world(src, s).copy() for s in B.BONE_MAP if s in src.data.bones}
    dest_rest = {d: B.rest_world(dest, d).copy() for d in B.BONE_MAP.values() if d in dest.data.bones}
    reverse_map = {d: s for s, d in B.BONE_MAP.items() if s in src_rest and d in dest_rest}
    order = B.dest_order(dest, set(reverse_map))
    src_hip = B.hip_height_z(src, "DEF-hips")
    dest_hip = B.hip_height_z(dest, "pelvis")
    hip_scale = dest_hip / src_hip if abs(src_hip) > 1e-6 else 1.0
    log(f"hip height src={src_hip:.4f} dest={dest_hip:.4f} scale={hip_scale:.4f} mapped={len(reverse_map)}")

    scene = bpy.context.scene
    scene.render.fps = 24
    scene.render.fps_base = 1.0

    # Death is a real UAL fall: keep root/pelvis translation (NOT in_place).
    death = bpy.data.actions.new(name="Death")
    B.bake_clip(
        src, dest, src_actions[DEATH_SRC], death,
        in_place=False, hip_scale=hip_scale,
        src_rest=src_rest, dest_rest=dest_rest,
        order=order, reverse_map=reverse_map,
    )
    death01 = B.copy_action(death, "Death01")
    log("  alias Death01")

    src_objs = [o for o in bpy.data.objects if o not in dest_objects]
    bpy.ops.object.select_all(action="DESELECT")
    for o in src_objs:
        o.select_set(True)
    if src_objs:
        bpy.ops.object.delete()

    # Restore dest clip names and keep them + Death/Death01.
    made = []
    for raw, act in dest_actions.items():
        if act.name != raw:
            act.name = raw
        act.use_fake_user = True
        made.append(act)
    death.use_fake_user = True
    death01.use_fake_user = True
    made.extend([death, death01])

    keep = {a.name for a in made}
    for act in list(bpy.data.actions):
        if act.name not in keep:
            bpy.data.actions.remove(act)

    if dest.animation_data:
        dest.animation_data.action = None
        while dest.animation_data.nla_tracks:
            dest.animation_data.nla_tracks.remove(dest.animation_data.nla_tracks[0])
    for act in made:
        B.push_nla(dest, act, act.name)

    force_opaque_mats()
    bak = dest_path.with_suffix(".glb.bak")
    if not bak.is_file():
        shutil.copy2(dest_path, bak)
        log(f"backup created {bak} ({bak.stat().st_size} bytes)")
    export_dest_hold(dest_path, dest, dest_objects)
    hold_info = hold_death_last_key(dest_path)
    log(f"hold_death {hold_info}")
    info = force_opaque_json(dest_path)
    log(f"exported clips={info['clips']} fourcc={info['fourcc']} size={info['size']}")
    need = {"Death", "Idle", "Attack"}
    have = set(info["clips"])
    if not need.issubset(have):
        raise RuntimeError(f"dest missing {need - have}; have {info['clips']}")
    if info["fourcc"] != ["JSON", "BIN\x00"]:
        raise RuntimeError(f"bad fourcc {info['fourcc']!r}")

    last = action_last_frame("Death")
    apply_action(dest, "Death", last)
    z_death2 = pelvis_world_z(dest)
    apply_action(dest, "Idle", action_last_frame("Idle"))
    z_idle = pelvis_world_z(dest)
    apply_action(dest, "Death", last)
    z_death2 = pelvis_world_z(dest)
    log(f"scene pelvis z idle={z_idle:.3f} death_last={z_death2:.3f} drop={z_idle - z_death2:.3f}")

    # Authoritative: GLB last pelvis sample must stay down (UAL Death01 hips z 0.88 -> 0.06).
    import bake_human_idle_walk as B2
    doc, blob = B2.glb_chunks(dest_path)
    names = B2.node_name_map(doc)
    anims = {a.get("name"): a for a in doc.get("animations", [])}
    death_anim = anims.get("Death")
    if not death_anim:
        raise RuntimeError("Death clip missing after export")
    last_z = None
    first_z = None
    min_z = None
    for ch in death_anim.get("channels", []):
        tgt = ch.get("target", {})
        if names.get(tgt.get("node")) != "pelvis" or tgt.get("path") != "translation":
            continue
        locs, _ = B2.read_accessor(doc, blob, death_anim["samplers"][ch["sampler"]]["output"])
        first_z, last_z = locs[0][2], locs[-1][2]
        min_z = min(l[2] for l in locs)
        break
    log(f"GLB Death pelvis z first={first_z} last={last_z} min={min_z}")
    if last_z is None or last_z > 0.35 or (first_z is not None and (first_z - last_z) < 0.35):
        raise RuntimeError(
            f"Death last pelvis z {last_z} not down (first={first_z} min={min_z}); refusing standing death"
        )
    z_idle = first_z if z_idle > 10 else z_idle
    if last_z > 0.35:
        raise RuntimeError("Death last frame still standing")

    center, extent = dest_bbox(dest_objects)
    log(f"death bbox center={tuple(round(c, 3) for c in center)} extent={tuple(round(c, 3) for c in extent)}")
    setup_death_preview(center, extent)
    PREVIEW_PNG.parent.mkdir(parents=True, exist_ok=True)
    scratch_png = B.SCRATCH / "bandit_death.png"
    scratch_png.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(scratch_png)
    bpy.ops.render.render(write_still=True)
    if not scratch_png.is_file():
        raise RuntimeError("preview not written")
    shutil.copy2(scratch_png, PREVIEW_PNG)
    log(f"preview {PREVIEW_PNG} ({PREVIEW_PNG.stat().st_size} bytes)")

    info["pelvis_idle_z"] = round(z_idle, 4)
    info["pelvis_death_z"] = round(z_death2, 4)
    info["preview"] = str(PREVIEW_PNG)
    info["preview_bytes"] = PREVIEW_PNG.stat().st_size
    return info


def main() -> int:
    import bake_human_idle_walk as B

    B.ensure_scratch()
    import bpy
    log(f"blender {bpy.app.version_string}")
    if not B.SRC_ANIM.is_file():
        raise FileNotFoundError(B.SRC_ANIM)
    if not LIVE.is_file():
        raise FileNotFoundError(LIVE)
    if LIVE.resolve() == CITY_BANDIT.resolve() or AG_DEST.resolve() == CITY_BANDIT.resolve():
        raise RuntimeError("refusing to write City bandit")
    for p in (LIVE, AG_DEST):
        low = str(p).lower()
        if "worksuit" in low or "casualsuit" in low:
            raise RuntimeError(f"refusing forbidden path {p}")
        if "\\city\\" in low or "/city/" in low:
            raise RuntimeError(f"refusing City path {p}")

    guard = snapshot(list(CIVILIANS) + [CITY_BANDIT])
    log(f"civilian/City snapshot: {guard}")

    live_bak = LIVE.with_suffix(".glb.bak")
    if not live_bak.is_file():
        shutil.copy2(LIVE, live_bak)
        log(f"live backup {live_bak} ({live_bak.stat().st_size})")
    # AG dest may have a stale City-sized .bak; ignore it. We write AG from LIVE after success.

    try:
        info = bake_add_death(LIVE)
        shutil.copy2(LIVE, AG_DEST)
        log(f"copied live -> AG {AG_DEST} ({AG_DEST.stat().st_size})")
        ag_info = force_opaque_json(AG_DEST)
        if set(ag_info["clips"]) != set(info["clips"]):
            raise RuntimeError(f"AG clips mismatch {ag_info['clips']} vs {info['clips']}")
        assert_untouched(guard, "civilian/City")
        report = {
            "dest": str(LIVE),
            "dest_bytes": LIVE.stat().st_size,
            "ag_dest": str(AG_DEST),
            "ag_bytes": AG_DEST.stat().st_size,
            "city_bytes": CITY_BANDIT.stat().st_size if CITY_BANDIT.is_file() else None,
            "clips": info["clips"],
            "fourcc": info["fourcc"],
            "materials": info["materials"],
            "preview": info["preview"],
            "preview_bytes": info["preview_bytes"],
            "pelvis_idle_z": info["pelvis_idle_z"],
            "pelvis_death_z": info["pelvis_death_z"],
        }
        out = B.SCRATCH / "bandit_death_verify.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        (B.SCRATCH / "bandit_death_verify.txt").write_text(
            f"dest={LIVE} bytes={LIVE.stat().st_size}\n"
            f"ag={AG_DEST} bytes={AG_DEST.stat().st_size}\n"
            f"clips={info['clips']}\n"
            f"fourcc={info['fourcc']}\n"
            f"preview={PREVIEW_PNG}\n",
            encoding="utf-8",
        )
        log(f"DONE dest={LIVE} bytes={LIVE.stat().st_size} clips={info['clips']} preview={PREVIEW_PNG}")
        return 0
    except Exception:
        traceback.print_exc()
        if live_bak.is_file() and live_bak.stat().st_size > 4000000:
            shutil.copy2(live_bak, LIVE)
            log(f"RESTORED live from bak ({live_bak.stat().st_size})")
        # never restore AG from a City-sized stale bak
        assert_untouched(guard, "civilian/City")
        return 1


def launch_via_blenderctl() -> int:
    sys.path.insert(0, str(TOOLS))
    import blenderctl
    install = blenderctl.require_blender()
    log(f"blenderctl {install.executable} v{install.version_str} via {install.source}")
    cmd = [
        str(install.executable),
        "--background",
        "--factory-startup",
        "-noaudio",
        "--addons",
        "io_scene_gltf2",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).resolve()),
    ]
    log("exec " + " ".join(cmd))
    completed = subprocess.run(cmd)
    return completed.returncode


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        in_blender = True
    except ImportError:
        in_blender = False
    if not in_blender:
        sys.exit(launch_via_blenderctl())
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
