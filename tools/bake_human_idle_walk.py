# -*- coding: utf-8 -*-
"""Bake UAL Idle_Loop / Walk_Loop onto MPFB dressed humans (Orrun + Asset Lab).

Retarget is rest-relative in world space (do NOT copy raw Euler/quat):
    dest_pose = dest_rest_world * inverse(src_rest_world) * src_pose_world
then convert to dest bone local (parent-relative) and key.

Run:
  blender.exe --background --factory-startup --python
    C:\\Projekte\\AssetGenerator\\tools\\bake_human_idle_walk.py
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
from mathutils import Matrix, Vector

SRC_ANIM = Path(
    r"C:\Projekte\City\assets\humans\animations\quaternius\AnimationLibrary_Godot_Standard.gltf"
)
ORRUN_HUMANS = Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans")
AG_HUMANS = Path(r"C:\Projekte\AssetGenerator\assets\humans")
SCRATCH = Path(r"C:\Projekte\AssetGenerator\tools\_human_bake")

MALE_NAME = "male_dressed_male_worksuit01.glb"
FEMALE_NAME = "female_dressed_female_casualsuit01.glb"

# Bake each file onto itself so clothes / mesh sets are not dropped.
TARGETS = [
    ORRUN_HUMANS / MALE_NAME,
    ORRUN_HUMANS / FEMALE_NAME,
    AG_HUMANS / MALE_NAME,
    AG_HUMANS / FEMALE_NAME,
]

BONE_MAP = {
    "root": "Root",
    "DEF-hips": "pelvis",
    "DEF-spine.001": "spine_01",
    "DEF-spine.002": "spine_02",
    "DEF-spine.003": "spine_03",
    "DEF-neck": "neck_01",
    "DEF-head": "head",
    "DEF-shoulder.L": "clavicle_l",
    "DEF-upper_arm.L": "upperarm_l",
    "DEF-forearm.L": "lowerarm_l",
    "DEF-hand.L": "hand_l",
    "DEF-thumb.01.L": "thumb_01_l",
    "DEF-thumb.02.L": "thumb_02_l",
    "DEF-thumb.03.L": "thumb_03_l",
    "DEF-f_index.01.L": "index_01_l",
    "DEF-f_index.02.L": "index_02_l",
    "DEF-f_index.03.L": "index_03_l",
    "DEF-f_middle.01.L": "middle_01_l",
    "DEF-f_middle.02.L": "middle_02_l",
    "DEF-f_middle.03.L": "middle_03_l",
    "DEF-f_ring.01.L": "ring_01_l",
    "DEF-f_ring.02.L": "ring_02_l",
    "DEF-f_ring.03.L": "ring_03_l",
    "DEF-f_pinky.01.L": "pinky_01_l",
    "DEF-f_pinky.02.L": "pinky_02_l",
    "DEF-f_pinky.03.L": "pinky_03_l",
    "DEF-shoulder.R": "clavicle_r",
    "DEF-upper_arm.R": "upperarm_r",
    "DEF-forearm.R": "lowerarm_r",
    "DEF-hand.R": "hand_r",
    "DEF-thumb.01.R": "thumb_01_r",
    "DEF-thumb.02.R": "thumb_02_r",
    "DEF-thumb.03.R": "thumb_03_r",
    "DEF-f_index.01.R": "index_01_r",
    "DEF-f_index.02.R": "index_02_r",
    "DEF-f_index.03.R": "index_03_r",
    "DEF-f_middle.01.R": "middle_01_r",
    "DEF-f_middle.02.R": "middle_02_r",
    "DEF-f_middle.03.R": "middle_03_r",
    "DEF-f_ring.01.R": "ring_01_r",
    "DEF-f_ring.02.R": "ring_02_r",
    "DEF-f_ring.03.R": "ring_03_r",
    "DEF-f_pinky.01.R": "pinky_01_r",
    "DEF-f_pinky.02.R": "pinky_02_r",
    "DEF-f_pinky.03.R": "pinky_03_r",
    "DEF-thigh.L": "thigh_l",
    "DEF-shin.L": "calf_l",
    "DEF-foot.L": "foot_l",
    "DEF-toe.L": "ball_l",
    "DEF-thigh.R": "thigh_r",
    "DEF-shin.R": "calf_r",
    "DEF-foot.R": "foot_r",
    "DEF-toe.R": "ball_r",
}

TRANSLATION_BONES = {"Root", "pelvis"}
CLIPS = [
    ("Idle_Loop", ("Idle", "Idle_Loop"), False),
    ("Walk_Loop", ("Walk", "Walk_Loop"), True),
]
VERIFY_BONES = ("pelvis", "spine_01", "thigh_l", "thigh_r", "upperarm_l", "upperarm_r")
REQUIRED_CLIPS = ("Idle", "Walk")


def log(msg: str) -> None:
    print(f"[human-bake] {msg}", flush=True)


def ensure_scratch() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)


def backup_targets() -> None:
    for path in TARGETS:
        if not path.is_file():
            raise FileNotFoundError(f"missing target: {path}")
        bak = path.with_suffix(".glb.bak")
        if not bak.is_file():
            shutil.copy2(path, bak)
            log(f"backup created {bak} ({bak.stat().st_size} bytes)")
        else:
            log(f"backup exists {bak} ({bak.stat().st_size} bytes)")


def restore_from_bak(path: Path) -> None:
    bak = path.with_suffix(".glb.bak")
    if bak.is_file():
        shutil.copy2(bak, path)
        log(f"RESTORED {path.name} from .bak")
    else:
        log(f"WARNING no .bak to restore for {path}")


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    if bpy.context.selected_objects:
        bpy.ops.object.delete()
    for coll in (
        bpy.data.actions,
        bpy.data.armatures,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.objects,
    ):
        for block in list(coll):
            try:
                coll.remove(block)
            except Exception:
                pass


def import_gltf(path: Path) -> None:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(
        filepath=str(path),
        bone_heuristic="BLENDER",
        guess_original_bind_pose=True,
    )
    after = set(bpy.data.objects)
    log(f"imported {path.name}: +{len(after - before)} objects")


def find_armature(*, has_bone: str):
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE" and has_bone in obj.data.bones:
            return obj
    raise RuntimeError(f"no armature with bone {has_bone!r}")


def rest_world(arm, bone_name: str) -> Matrix:
    return arm.matrix_world @ arm.data.bones[bone_name].matrix_local


def pose_world(arm, bone_name: str) -> Matrix:
    return arm.matrix_world @ arm.pose.bones[bone_name].matrix


def hip_height_z(arm, bone_name: str) -> float:
    return rest_world(arm, bone_name).to_translation().z


def dest_order(dest, dest_names: set[str]) -> list[str]:
    ordered: list[str] = []

    def walk(bone):
        if bone.name in dest_names:
            ordered.append(bone.name)
        for child in bone.children:
            walk(child)

    for bone in dest.data.bones:
        if bone.parent is None:
            walk(bone)
    for name in dest_names:
        if name not in ordered:
            ordered.append(name)
    return ordered


def compose_mat(loc, rot) -> Matrix:
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def set_basis_from_arm_matrix(pb, dest_pose_arm: Matrix, parent_pose_arm) -> None:
    bone = pb.bone
    if pb.parent is not None and parent_pose_arm is not None:
        basis = (
            bone.matrix_local.inverted()
            @ pb.parent.bone.matrix_local
            @ parent_pose_arm.inverted()
            @ dest_pose_arm
        )
    else:
        basis = bone.matrix_local.inverted() @ dest_pose_arm
    pb.matrix_basis = basis


def assign_action(obj, action) -> None:
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots is not None:
        slot = None
        for s in slots:
            slot = s
            break
        if slot is None and hasattr(slots, "new"):
            try:
                slot = slots.new(id_type="OBJECT")
            except TypeError:
                try:
                    slot = slots.new()
                except Exception:
                    slot = None
        if slot is not None and hasattr(obj.animation_data, "action_slot"):
            try:
                obj.animation_data.action_slot = slot
            except Exception:
                pass


def ensure_quat_mode(arm) -> None:
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"


def reset_pose(arm) -> None:
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def copy_action(action, new_name: str):
    clone = action.copy()
    clone.name = new_name
    clone.use_fake_user = True
    return clone


def push_nla(arm, action, name: str) -> None:
    ad = arm.animation_data
    if ad is None:
        ad = arm.animation_data_create()
    track = ad.nla_tracks.new()
    track.name = name
    start = int(round(action.frame_range[0]))
    track.strips.new(name, start, action)


def bake_clip(src, dest, src_action, dest_action, *, in_place: bool, hip_scale: float,
              src_rest: dict, dest_rest: dict, order: list[str], reverse_map: dict) -> None:
    assign_action(src, src_action)
    assign_action(dest, dest_action)
    ensure_quat_mode(dest)
    reset_pose(dest)

    f0 = int(round(src_action.frame_range[0]))
    f1 = int(round(src_action.frame_range[1]))
    log(f"  bake {src_action.name} -> {dest_action.name} frames {f0}..{f1} "
        f"in_place={in_place} hip_scale={hip_scale:.4f}")

    scene = bpy.context.scene
    first_local: dict[str, tuple] = {}
    dest_inv = dest.matrix_world.inverted()

    for frame in range(f0, f1 + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        posed_arm: dict[str, Matrix] = {}

        for dest_name in order:
            src_name = reverse_map[dest_name]
            rel = src_rest[src_name].inverted() @ pose_world(src, src_name)
            if dest_name in TRANSLATION_BONES:
                rel = rel.copy()
                rel.translation = rel.to_translation() * hip_scale
            dest_pose_world = dest_rest[dest_name] @ rel
            if dest_name not in TRANSLATION_BONES:
                # rotation only: keep dest rest translation / scale
                _loc, rot, _sca = dest_pose_world.decompose()
                rest_loc = dest_rest[dest_name].to_translation()
                dest_pose_world = compose_mat(rest_loc, rot)
            if in_place and dest_name in TRANSLATION_BONES:
                rest_loc = dest_rest[dest_name].to_translation()
                loc = dest_pose_world.to_translation()
                loc.x = rest_loc.x
                loc.y = rest_loc.y
                dest_pose_world = dest_pose_world.copy()
                dest_pose_world.translation = loc
            dest_pose_arm = dest_inv @ dest_pose_world
            # drop non-uniform scale from the retarget
            loc, rot, _sca = dest_pose_arm.decompose()
            dest_pose_arm = compose_mat(loc, rot)
            posed_arm[dest_name] = dest_pose_arm
            pb = dest.pose.bones[dest_name]
            parent_pose = None
            if pb.parent is not None:
                parent_pose = posed_arm.get(pb.parent.name)
            set_basis_from_arm_matrix(pb, dest_pose_arm, parent_pose)

        for dest_name in order:
            pb = dest.pose.bones[dest_name]
            pb.rotation_mode = "QUATERNION"
            pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            if dest_name in TRANSLATION_BONES:
                pb.keyframe_insert(data_path="location", frame=frame)
            if frame == f0:
                first_local[dest_name] = (pb.location.copy(), pb.rotation_quaternion.copy())

    for dest_name, (loc, rot) in first_local.items():
        pb = dest.pose.bones[dest_name]
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = rot
        pb.keyframe_insert(data_path="rotation_quaternion", frame=f1)
        if dest_name in TRANSLATION_BONES:
            pb.location = loc
            pb.keyframe_insert(data_path="location", frame=f1)

    for fc in dest_action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    dest_action.use_fake_user = True


def export_dest(out_path: Path, dest, dest_objects: list) -> None:
    if dest.animation_data:
        dest.animation_data.action = None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in dest_objects:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    dest.select_set(True)
    bpy.context.view_layer.objects.active = dest
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scratch_out = SCRATCH / (out_path.stem + "_baked.glb")
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
        export_reset_pose_bones=True,
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
        # blender may append .glb
        alt = Path(str(scratch_out) + ".glb")
        if alt.is_file():
            scratch_out = alt
        else:
            raise RuntimeError(f"export produced no file: {scratch_out}")
    bak = out_path.with_suffix(".glb.bak")
    if not bak.is_file():
        raise RuntimeError(f"refusing overwrite, missing backup {bak}")
    shutil.copy2(scratch_out, out_path)
    log(f"exported {out_path} ({out_path.stat().st_size} bytes)")


def glb_chunks(path: Path):
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError(f"{path} is not a GLB")
    off = 12
    json_doc = None
    bin_blob = b""
    while off + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, off)
        off += 8
        chunk = data[off: off + chunk_len]
        off += chunk_len
        if chunk_type == 0x4E4F534A:
            json_doc = json.loads(chunk)
        elif chunk_type == 0x004E4942:
            bin_blob = chunk
    if json_doc is None:
        raise RuntimeError(f"{path}: no JSON chunk")
    return json_doc, bin_blob


COMPONENT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_accessor(doc, blob, acc_i):
    acc = doc["accessors"][acc_i]
    bv = doc["bufferViews"][acc["bufferView"]]
    fmt = COMPONENT[acc["componentType"]]
    n = NCOMP[acc["type"]]
    count = acc["count"]
    off = (bv.get("byteOffset", 0) + acc.get("byteOffset", 0))
    stride = bv.get("byteStride") or struct.calcsize(fmt) * n
    out = []
    for i in range(count):
        vals = struct.unpack_from("<" + fmt * n, blob, off + i * stride)
        out.append(vals[0] if n == 1 else vals)
    return out, acc


def node_name_map(doc):
    return {i: (n.get("name") or f"node_{i}") for i, n in enumerate(doc.get("nodes", []))}


def quat_angle(a, b) -> float:
    dot = abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3])
    dot = min(1.0, max(0.0, dot))
    return 2.0 * math.acos(dot)


def verify_glb(path: Path) -> dict:
    doc, blob = glb_chunks(path)
    names = node_name_map(doc)
    anims = {a.get("name"): a for a in doc.get("animations", [])}
    result = {"path": str(path), "clips": sorted(anims), "ok": True, "notes": []}
    for need in REQUIRED_CLIPS:
        if need not in anims:
            result["ok"] = False
            result["notes"].append(f"MISSING clip {need}")
    mid_rots = {}
    rest_rots = {}
    for node in doc.get("nodes", []):
        rest_rots[node.get("name")] = tuple(node.get("rotation") or (0, 0, 0, 1))
    channel_report = {}
    spans = {}
    for clip_name in REQUIRED_CLIPS:
        anim = anims.get(clip_name)
        if not anim:
            continue
        bones = {}
        for ch in anim.get("channels", []):
            tgt = ch.get("target", {})
            ni = tgt.get("node")
            bname = names.get(ni, "?")
            pathk = tgt.get("path")
            bones.setdefault(bname, set()).add(pathk)
            if pathk == "rotation" and bname in ("thigh_l", "calf_l", "upperarm_l", "foot_l"):
                samp = anim["samplers"][ch["sampler"]]
                times, _ = read_accessor(doc, blob, samp["input"])
                rots, _ = read_accessor(doc, blob, samp["output"])
                if times:
                    t0, t1 = times[0], times[-1]
                    mid_t = t0 + 0.5 * (t1 - t0)
                    best_i = min(range(len(times)), key=lambda i: abs(times[i] - mid_t))
                    mid_rots[(clip_name, bname)] = rots[best_i]
                    span = 0.0
                    for r in rots:
                        span = max(span, math.degrees(quat_angle(r, rots[0])))
                    spans[(clip_name, bname)] = span
        channel_report[clip_name] = {k: sorted(v) for k, v in bones.items()}
        missing = [b for b in VERIFY_BONES if b not in bones]
        if missing:
            result["ok"] = False
            result["notes"].append(f"{clip_name} missing channels on {missing}")
        if len(bones) < 6:
            result["ok"] = False
            result["notes"].append(f"{clip_name} only {len(bones)} bones (frozen?)")

    idle_th = mid_rots.get(("Idle", "thigh_l"))
    walk_th = mid_rots.get(("Walk", "thigh_l"))
    if idle_th and walk_th:
        ang = math.degrees(quat_angle(idle_th, walk_th))
        result["idle_vs_walk_thigh_deg"] = round(ang, 3)
        if ang < 2.0:
            result["ok"] = False
            result["notes"].append(f"Idle and Walk mid thigh_l almost identical ({ang:.3f} deg)")
    else:
        result["ok"] = False
        result["notes"].append("could not compare mid-clip thigh_l rotations")

    if walk_th:
        rest = rest_rots.get("thigh_l", (0, 0, 0, 1))
        ang = math.degrees(quat_angle(walk_th, rest))
        result["walk_vs_rest_thigh_deg"] = round(ang, 3)
        if ang < 2.0:
            result["ok"] = False
            result["notes"].append(f"Walk mid thigh_l is T-pose-ish vs rest ({ang:.3f} deg)")

    idle_arm = spans.get(("Idle", "upperarm_l"))
    idle_foot = spans.get(("Idle", "foot_l"))
    result["idle_arm_span"] = idle_arm
    result["idle_foot_span"] = idle_foot
    if idle_arm is not None and idle_arm > 25.0:
        result["ok"] = False
        result["notes"].append(f"Idle upperarm_l span {idle_arm:.1f} deg (source is ~6)")
    if idle_foot is not None and idle_foot > 20.0:
        result["ok"] = False
        result["notes"].append(f"Idle foot_l span {idle_foot:.1f} deg (source is ~3)")

    result["channel_counts"] = {clip: len(channel_report.get(clip, {})) for clip in REQUIRED_CLIPS}
    result["meshes"] = [m.get("name") for m in doc.get("meshes", [])]
    line = (
        f"{path.name}: clips={result['clips']} "
        f"ch={result.get('channel_counts')} "
        f"idle_vs_walk={result.get('idle_vs_walk_thigh_deg')}deg "
        f"walk_vs_rest={result.get('walk_vs_rest_thigh_deg')}deg "
        f"idle_arm_span={idle_arm} idle_foot_span={idle_foot} "
        f"{'PASS' if result['ok'] else 'FAIL'}"
    )
    if result["notes"]:
        line += " | " + "; ".join(result["notes"])
    result["line"] = line
    return result


def bake_one(dest_path: Path) -> None:
    log(f"==== bake {dest_path}")
    bak = dest_path.with_suffix(".glb.bak")
    src_glb = bak if bak.is_file() else dest_path

    clear_scene()
    import_gltf(src_glb)
    dest_objects = [o for o in bpy.data.objects]
    dest = find_armature(has_bone="pelvis")
    log(f"dest armature {dest.name} bones={len(dest.data.bones)} "
        f"meshes={[o.name for o in dest_objects if o.type == 'MESH']}")

    for act in list(bpy.data.actions):
        if not act.name.startswith("DST_"):
            act.name = "DST_" + act.name

    import_gltf(SRC_ANIM)
    src = find_armature(has_bone="DEF-hips")
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

    missing = [c[0] for c in CLIPS if c[0] not in src_actions]
    if missing:
        raise RuntimeError(f"source clips missing: {missing}; have {sorted(src_actions)}")

    reset_pose(src)
    reset_pose(dest)
    src_rest = {s: rest_world(src, s).copy() for s in BONE_MAP if s in src.data.bones}
    dest_rest = {d: rest_world(dest, d).copy() for d in BONE_MAP.values() if d in dest.data.bones}
    reverse_map = {d: s for s, d in BONE_MAP.items() if s in src_rest and d in dest_rest}
    order = dest_order(dest, set(reverse_map))

    src_hip = hip_height_z(src, "DEF-hips")
    dest_hip = hip_height_z(dest, "pelvis")
    hip_scale = dest_hip / src_hip if abs(src_hip) > 1e-6 else 1.0
    log(f"hip height src={src_hip:.4f} dest={dest_hip:.4f} scale={hip_scale:.4f}")
    log(f"mapped bones {len(reverse_map)}")

    scene = bpy.context.scene
    scene.render.fps = 24
    scene.render.fps_base = 1.0

    made = []
    for src_name, dest_names, in_place in CLIPS:
        primary = dest_names[0]
        action = bpy.data.actions.new(name=primary)
        bake_clip(
            src, dest, src_actions[src_name], action,
            in_place=in_place, hip_scale=hip_scale,
            src_rest=src_rest, dest_rest=dest_rest,
            order=order, reverse_map=reverse_map,
        )
        made.append(action)
        for extra in dest_names[1:]:
            clone = copy_action(action, extra)
            made.append(clone)
            log(f"  alias {extra}")

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
        push_nla(dest, act, act.name)

    export_dest(dest_path, dest, dest_objects)


def write_report(results: list[dict]) -> None:
    report = SCRATCH / "verify_report.json"
    report.write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = [r["line"] for r in results]
    (SCRATCH / "verify_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("verify report " + str(report))


def main() -> int:
    ensure_scratch()
    log(f"blender {bpy.app.version_string}")
    if not SRC_ANIM.is_file():
        raise FileNotFoundError(SRC_ANIM)
    backup_targets()

    results = []
    failed = []
    for path in TARGETS:
        try:
            bake_one(path)
            res = verify_glb(path)
            log(res["line"])
            results.append(res)
            if not res["ok"]:
                failed.append(path)
                restore_from_bak(path)
        except Exception:
            traceback.print_exc()
            failed.append(path)
            restore_from_bak(path)

    write_report(results)
    if failed:
        log("FAILED: " + ", ".join(p.name for p in failed))
        return 1
    log("ALL PASS")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
