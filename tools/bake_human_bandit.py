# -*- coding: utf-8 -*-
"""Bake UAL Idle_Loop / Walk_Loop / Sword_Attack onto the copied City bandit.

Reuses rest-relative world retarget from bake_human_idle_walk.py.
Does NOT touch civilian worksuit/casualsuit files or City originals.

Run:
  blender.exe --background --factory-startup --python
    C:\\Projekte\\AssetGenerator\\tools\\bake_human_bandit.py
"""
from __future__ import annotations

import json
import math
import shutil
import struct
import sys
import traceback
from pathlib import Path

import bpy

TOOLS = Path(r"C:\Projekte\AssetGenerator\tools")
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import bake_human_idle_walk as hb

DEST = Path(r"C:\Projekte\AssetGenerator\assets\humans\outfits\male_bandit_01.glb")
CITY_SRC = Path(r"C:\Projekte\City\assets\humans\outfits\male_bandit_01.glb")
FORBIDDEN_SUBSTR = ("worksuit", "casualsuit")

REQUIRED_CLIPS = ("Idle", "Walk")
OPTIONAL_ATTACK = ("Attack", "Sword_Attack")
CLIPS_CORE = [
    ("Idle_Loop", ("Idle", "Idle_Loop"), False),
    ("Walk_Loop", ("Walk", "Walk_Loop"), True),
]
CLIP_ATTACK = ("Sword_Attack", ("Attack", "Sword_Attack"), True)
VERIFY_BONES = hb.VERIFY_BONES
SWORD_MESH = "crudesword"
SWORD_NODE_SUB = "joepal_crude_sword"


def log(msg: str) -> None:
    print(f"[bandit-bake] {msg}", flush=True)


def assert_safe_path(path: Path) -> None:
    low = str(path).lower()
    for bad in FORBIDDEN_SUBSTR:
        if bad in low:
            raise RuntimeError(f"refusing to write forbidden path: {path}")
    if "\\city\\" in low or "/city/" in low:
        raise RuntimeError(f"refusing to write City path: {path}")


def backup_dest() -> Path:
    assert_safe_path(DEST)
    if not DEST.is_file():
        raise FileNotFoundError(DEST)
    bak = DEST.with_suffix(".glb.bak")
    if not bak.is_file():
        shutil.copy2(DEST, bak)
        log(f"backup created {bak} ({bak.stat().st_size} bytes)")
    else:
        log(f"backup exists {bak} ({bak.stat().st_size} bytes)")
    return bak


def action_motion_ok(action, dest, min_arm_span_deg: float = 8.0) -> tuple[bool, str]:
    """True if dest_action has real upperarm/spine rotation, not frozen/T-pose."""
    if action is None or len(action.fcurves) < 6:
        return False, f"too few fcurves ({0 if action is None else len(action.fcurves)})"
    spans = {}
    for fc in action.fcurves:
        dp = fc.data_path or ""
        if "rotation_quaternion" not in dp:
            continue
        bone = None
        if 'pose.bones["' in dp:
            bone = dp.split('pose.bones["', 1)[1].split('"]', 1)[0]
        if bone not in ("upperarm_l", "upperarm_r", "spine_01", "spine_03"):
            continue
        vals = [kp.co[1] for kp in fc.keyframe_points]
        if not vals:
            continue
        spans.setdefault(bone, []).append(max(vals) - min(vals))
    # quaternion component span is a cheap freeze check
    arm_span = max(spans.get("upperarm_l", [0]) + spans.get("upperarm_r", [0]))
    # convert rough quat-component delta to a "has motion" flag
    if arm_span < 0.02 and max(spans.get("spine_01", [0]) + spans.get("spine_03", [0])) < 0.02:
        return False, f"frozen channels arm/spine quat-span={spans}"
    return True, f"arm/spine quat-spans={ {k: round(max(v), 4) for k, v in spans.items()} }"


def bake_one(dest_path: Path) -> dict:
    log(f"==== bake {dest_path}")
    assert_safe_path(dest_path)
    bak = dest_path.with_suffix(".glb.bak")
    src_glb = bak if bak.is_file() else dest_path

    hb.clear_scene()
    hb.import_gltf(src_glb)
    dest_objects = [o for o in bpy.data.objects]
    dest = hb.find_armature(has_bone="pelvis")
    mesh_names = [o.name for o in dest_objects if o.type == "MESH"]
    log(f"dest armature {dest.name} bones={len(dest.data.bones)} meshes={mesh_names}")
    if not any("crude" in n.lower() or "sword" in n.lower() for n in mesh_names):
        log("WARNING: no obvious sword mesh name after import (will still keep all dest objects)")

    for act in list(bpy.data.actions):
        if not act.name.startswith("DST_"):
            act.name = "DST_" + act.name

    hb.import_gltf(hb.SRC_ANIM)
    src = hb.find_armature(has_bone="DEF-hips")
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
    log(f"src clips ({len(src_actions)}): {sorted(src_actions)[:40]}")

    missing_core = [c[0] for c in CLIPS_CORE if c[0] not in src_actions]
    if missing_core:
        raise RuntimeError(f"source clips missing: {missing_core}; have {sorted(src_actions)}")

    hb.reset_pose(src)
    hb.reset_pose(dest)
    src_rest = {s: hb.rest_world(src, s).copy() for s in hb.BONE_MAP if s in src.data.bones}
    dest_rest = {d: hb.rest_world(dest, d).copy() for d in hb.BONE_MAP.values() if d in dest.data.bones}
    reverse_map = {d: s for s, d in hb.BONE_MAP.items() if s in src_rest and d in dest_rest}
    order = hb.dest_order(dest, set(reverse_map))

    src_hip = hb.hip_height_z(src, "DEF-hips")
    dest_hip = hb.hip_height_z(dest, "pelvis")
    hip_scale = dest_hip / src_hip if abs(src_hip) > 1e-6 else 1.0
    log(f"hip height src={src_hip:.4f} dest={dest_hip:.4f} scale={hip_scale:.4f}")
    log(f"mapped bones {len(reverse_map)}")

    scene = bpy.context.scene
    scene.render.fps = 24
    scene.render.fps_base = 1.0

    made = []
    notes = []
    attack_kept = False

    for src_name, dest_names, in_place in CLIPS_CORE:
        primary = dest_names[0]
        action = bpy.data.actions.new(name=primary)
        hb.bake_clip(
            src, dest, src_actions[src_name], action,
            in_place=in_place, hip_scale=hip_scale,
            src_rest=src_rest, dest_rest=dest_rest,
            order=order, reverse_map=reverse_map,
        )
        made.append(action)
        for extra in dest_names[1:]:
            clone = hb.copy_action(action, extra)
            made.append(clone)
            log(f"  alias {extra}")

    src_atk = CLIP_ATTACK[0]
    if src_atk not in src_actions:
        notes.append(f"{src_atk} missing from UAL import; Attack skipped")
        log(notes[-1])
    else:
        try:
            primary = CLIP_ATTACK[1][0]
            action = bpy.data.actions.new(name=primary)
            hb.bake_clip(
                src, dest, src_actions[src_atk], action,
                in_place=CLIP_ATTACK[2], hip_scale=hip_scale,
                src_rest=src_rest, dest_rest=dest_rest,
                order=order, reverse_map=reverse_map,
            )
            ok, why = action_motion_ok(action, dest)
            log(f"  Attack motion check: ok={ok} {why}")
            if not ok:
                notes.append(f"Sword_Attack retarget empty/frozen: {why}")
                bpy.data.actions.remove(action)
            else:
                made.append(action)
                for extra in CLIP_ATTACK[1][1:]:
                    clone = hb.copy_action(action, extra)
                    made.append(clone)
                    log(f"  alias {extra}")
                attack_kept = True
        except Exception as exc:
            notes.append(f"Sword_Attack did not retarget: {exc}")
            log(notes[-1])
            traceback.print_exc()
            # drop any partial Attack actions
            for act in list(bpy.data.actions):
                if act.name in OPTIONAL_ATTACK:
                    try:
                        bpy.data.actions.remove(act)
                    except Exception:
                        pass

    src_objs = [o for o in bpy.data.objects if o not in dest_objects]
    bpy.ops.object.select_all(action="DESELECT")
    for o in src_objs:
        o.select_set(True)
    if src_objs:
        bpy.ops.object.delete()

    keep = {a.name for a in made}
    for act in list(bpy.data.actions):
        if act.name not in keep:
            bpy.data.actions.remove(act)
    for act in made:
        act.use_fake_user = True
        hb.push_nla(dest, act, act.name)

    hb.export_dest(dest_path, dest, dest_objects)
    return {"attack_kept": attack_kept, "notes": notes, "made": [a.name for a in made]}


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


def strip_anims(path: Path, drop: set[str]) -> None:
    doc, blob = hb.glb_chunks(path)
    before = [a.get("name") for a in doc.get("animations", [])]
    doc["animations"] = [a for a in doc.get("animations", []) if a.get("name") not in drop]
    after = [a.get("name") for a in doc.get("animations", [])]
    write_glb(path, doc, blob)
    log(f"stripped {sorted(set(before) - set(after))} from {path.name}; now {after}")


def mid_rot(doc, blob, names, anim, bone: str):
    for ch in anim.get("channels", []):
        tgt = ch.get("target", {})
        if tgt.get("path") != "rotation":
            continue
        if names.get(tgt.get("node")) != bone:
            continue
        samp = anim["samplers"][ch["sampler"]]
        times, _ = hb.read_accessor(doc, blob, samp["input"])
        rots, _ = hb.read_accessor(doc, blob, samp["output"])
        if not times:
            return None
        mid_t = times[0] + 0.5 * (times[-1] - times[0])
        best_i = min(range(len(times)), key=lambda i: abs(times[i] - mid_t))
        return rots[best_i]
    return None


def rot_span(doc, blob, names, anim, bone: str) -> float | None:
    for ch in anim.get("channels", []):
        tgt = ch.get("target", {})
        if tgt.get("path") != "rotation":
            continue
        if names.get(tgt.get("node")) != bone:
            continue
        samp = anim["samplers"][ch["sampler"]]
        rots, _ = hb.read_accessor(doc, blob, samp["output"])
        if not rots:
            return 0.0
        span = 0.0
        for r in rots:
            span = max(span, math.degrees(hb.quat_angle(r, rots[0])))
        return span
    return None


def verify_bandit(path: Path) -> dict:
    doc, blob = hb.glb_chunks(path)
    names = hb.node_name_map(doc)
    anims = {a.get("name"): a for a in doc.get("animations", [])}
    result = {"path": str(path), "clips": sorted(anims), "ok": True, "notes": [], "attack_ok": False}

    # reuse core Idle/Walk checks
    core = hb.verify_glb(path)
    result["core"] = core
    if not core.get("ok"):
        result["ok"] = False
        result["notes"].extend(core.get("notes") or [])

    meshes = [m.get("name") for m in doc.get("meshes", [])]
    node_names = [n.get("name") or "" for n in doc.get("nodes", [])]
    result["meshes"] = meshes
    result["has_crudesword"] = SWORD_MESH in meshes
    result["has_sword_node"] = any(SWORD_NODE_SUB in n for n in node_names)
    if not result["has_crudesword"]:
        result["ok"] = False
        result["notes"].append(f"missing mesh {SWORD_MESH}; have {meshes}")
    if not result["has_sword_node"]:
        result["ok"] = False
        result["notes"].append(f"missing node containing {SWORD_NODE_SUB}; have {node_names[-10:]}")

    city_ok = CITY_SRC.is_file()
    result["city_source_exists"] = city_ok
    result["city_source_bytes"] = CITY_SRC.stat().st_size if city_ok else 0
    if not city_ok:
        result["ok"] = False
        result["notes"].append("City source bandit missing")

    images = [(im.get("name"), im.get("uri"), "bufferView" in im) for im in doc.get("images", [])]
    result["images"] = images

    # Attack quality
    attack = anims.get("Attack") or anims.get("Sword_Attack")
    idle = anims.get("Idle")
    walk = anims.get("Walk")
    if attack and idle:
        bones = set()
        for ch in attack.get("channels", []):
            bones.add(names.get(ch.get("target", {}).get("node"), "?"))
        result["attack_channels"] = len(bones)
        deltas = {}
        drop = False
        reason = None
        for bone in ("upperarm_l", "upperarm_r", "spine_01", "spine_03"):
            ar = mid_rot(doc, blob, names, attack, bone)
            ir = mid_rot(doc, blob, names, idle, bone)
            wr = mid_rot(doc, blob, names, walk, bone) if walk else None
            rest = None
            for node in doc.get("nodes", []):
                if node.get("name") == bone:
                    rest = tuple(node.get("rotation") or (0, 0, 0, 1))
                    break
            if ar and ir:
                d_idle = math.degrees(hb.quat_angle(ar, ir))
                deltas[f"{bone}_vs_idle"] = round(d_idle, 3)
            if ar and wr:
                deltas[f"{bone}_vs_walk"] = round(math.degrees(hb.quat_angle(ar, wr)), 3)
            if ar and rest:
                deltas[f"{bone}_vs_rest"] = round(math.degrees(hb.quat_angle(ar, rest)), 3)
            sp = rot_span(doc, blob, names, attack, bone)
            if sp is not None:
                deltas[f"{bone}_span"] = round(sp, 3)
        result["attack_deltas"] = deltas
        arm_vs_idle = max(deltas.get("upperarm_l_vs_idle", 0), deltas.get("upperarm_r_vs_idle", 0))
        spine_vs_idle = max(deltas.get("spine_01_vs_idle", 0), deltas.get("spine_03_vs_idle", 0))
        arm_vs_walk = max(deltas.get("upperarm_l_vs_walk", 0), deltas.get("upperarm_r_vs_walk", 0))
        arm_vs_rest = max(deltas.get("upperarm_l_vs_rest", 0), deltas.get("upperarm_r_vs_rest", 0))
        arm_span = max(deltas.get("upperarm_l_span", 0), deltas.get("upperarm_r_span", 0))
        if arm_vs_rest < 2.0 and arm_span < 2.0:
            drop = True
            reason = "Attack is T-pose / rest-like"
        elif arm_vs_idle < 3.0 and spine_vs_idle < 3.0 and arm_span < 5.0:
            drop = True
            reason = f"Attack identical to Idle (arm {arm_vs_idle:.2f} spine {spine_vs_idle:.2f})"
        elif arm_vs_idle < 3.0 and arm_vs_walk < 3.0 and arm_span < 5.0:
            drop = True
            reason = "Attack identical to Idle and Walk"
        if drop:
            result["attack_ok"] = False
            result["drop_attack"] = True
            result["notes"].append(f"Sword_Attack did not retarget: {reason}")
        else:
            result["attack_ok"] = True
    elif "Attack" in anims or "Sword_Attack" in anims:
        result["notes"].append("Attack clip present but Idle missing; cannot compare")
    else:
        result["notes"].append("Attack not present")

    line = (
        f"{path.name}: clips={result['clips']} "
        f"core={'PASS' if core.get('ok') else 'FAIL'} "
        f"sword_mesh={result['has_crudesword']} sword_node={result['has_sword_node']} "
        f"attack={'OK' if result['attack_ok'] else 'NO'} "
        f"city={city_ok} "
        f"{'PASS' if result['ok'] else 'FAIL'}"
    )
    if result["notes"]:
        line += " | " + "; ".join(result["notes"])
    result["line"] = line
    return result


def main() -> int:
    hb.ensure_scratch()
    log(f"blender {bpy.app.version_string}")
    if not hb.SRC_ANIM.is_file():
        raise FileNotFoundError(hb.SRC_ANIM)
    if not CITY_SRC.is_file():
        raise FileNotFoundError(f"City source missing: {CITY_SRC}")
    backup_dest()

    bake_info = {"notes": []}
    try:
        bake_info = bake_one(DEST)
    except Exception:
        traceback.print_exc()
        hb.restore_from_bak(DEST)
        return 1

    res = verify_bandit(DEST)
    log(res["line"])
    if res.get("drop_attack"):
        strip_anims(DEST, set(OPTIONAL_ATTACK))
        res = verify_bandit(DEST)
        log("after strip: " + res["line"])

    report = {
        "bake": bake_info,
        "verify": res,
        "dest": str(DEST),
        "dest_bytes": DEST.stat().st_size if DEST.is_file() else 0,
        "bak": str(DEST.with_suffix(".glb.bak")),
        "city_still_exists": CITY_SRC.is_file(),
    }
    out = hb.SCRATCH / "bandit_verify.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (hb.SCRATCH / "bandit_verify.txt").write_text(res["line"] + "\n", encoding="utf-8")
    log("verify report " + str(out))

    if not res.get("ok"):
        log("FAILED core verify; restoring dest from .bak")
        hb.restore_from_bak(DEST)
        return 1
    log("BANDIT PASS")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
