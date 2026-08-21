# -*- coding: utf-8 -*-
"""Legacy arm repair for hamlet walkers (neutralize / rebind).

Prefer tools/bake_human_quaternius.py — full UAL via world Copy Rotation (City-style).

Does NOT re-run bake_human_idle_walk.py. That retarget (guess_original_bind_pose=True
on an already-baked dest, T-pose UAL → A-pose MPFB) is how the live files got here.

Strategy:
  1. Diagnose live + backups + CS piece + base (weights, deformed arm islands, materials).
  2. Prefer neutralizing compounded arm channels back to A-pose bind (keep spine/legs).
  3. Optionally clamp clothing sleeve weights that leak onto spine/hips.
  4. Export JSON+BIN (fourcc BIN\\0), force OPAQUE, copy Orrun + AG, render previews.

Blender 4.5 note: NLA strips need action slots; export rebuilds slotted strips and the
vendored glTF exporter skips strips that still lack a slot.
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

ORRUN_HUMANS = Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans")
AG_HUMANS = Path(r"C:\Projekte\AssetGenerator\assets\humans")
CS_HUMANS = Path(r"C:\Projekte\AssetGenerator\character_studio\assets\humans")
CS_PIECES = CS_HUMANS / "pieces"
SRC_ANIM = Path(
    r"C:\Projekte\City\assets\humans\animations\quaternius\AnimationLibrary_Godot_Standard.gltf"
)
SCRATCH = Path(r"C:\Projekte\AssetGenerator\tools\_human_bake\arm_skin")
PREVIEW_DIR = Path(r"C:\Projekte\AssetGenerator\tools\_human_bake\arm_skin\previews")
BLENDER_BIN = Path(
    r"C:\Projekte\AssetGenerator\tools\blender-bin\blender-4.5.12-windows-x64\blender.exe"
)

FEMALE_NAME = "female_dressed_female_casualsuit01.glb"
MALE_NAME = "male_dressed_male_worksuit01.glb"
FEMALE_PIECE = "female_female_casualsuit01.glb"
MALE_PIECE = "male_male_worksuit01.glb"

JSON_FOURCC = 0x4E4F534A
BIN_FOURCC = 0x004E4942

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
REQUIRED_CLIPS = ("Idle", "Walk")

ARM_L = {
    "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l",
    "thumb_01_l", "thumb_02_l", "thumb_03_l",
    "index_01_l", "index_02_l", "index_03_l",
    "middle_01_l", "middle_02_l", "middle_03_l",
    "ring_01_l", "ring_02_l", "ring_03_l",
    "pinky_01_l", "pinky_02_l", "pinky_03_l",
}
ARM_R = {
    "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
    "thumb_01_r", "thumb_02_r", "thumb_03_r",
    "index_01_r", "index_02_r", "index_03_r",
    "middle_01_r", "middle_02_r", "middle_03_r",
    "ring_01_r", "ring_02_r", "ring_03_r",
    "pinky_01_r", "pinky_02_r", "pinky_03_r",
}
ARM_ALL = ARM_L | ARM_R
TORSO = {"Root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head"}
LEGS = {"thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r"}


def neutralize_arm_clip_channels(dest) -> dict:
    """Force arm bones to bind (identity basis) on Idle/Walk.

    Live clips were compounded by a T-pose→A-pose world retarget, which folds
    forearms through the torso. Legs/spine keys stay; arms return to A-pose.
    """
    ensure_quat_mode(dest)
    arm_bones = [b.name for b in dest.pose.bones if b.name in ARM_ALL]
    clips = []
    for name in ("Idle", "Walk", "Idle_Loop", "Walk_Loop"):
        act = bpy.data.actions.get(name)
        if act is None:
            continue
        clips.append(name)
        assign_action(dest, act)
        f0 = int(round(act.frame_range[0]))
        f1 = int(round(act.frame_range[1]))
        for frame in range(f0, f1 + 1):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            for bname in arm_bones:
                pb = dest.pose.bones[bname]
                pb.rotation_mode = "QUATERNION"
                pb.matrix_basis = Matrix.Identity(4)
                pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                pb.location = Vector((0.0, 0.0, 0.0))
                pb.keyframe_insert(data_path="location", frame=frame)
        for fc in act.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        for slot in getattr(act, "slots", []) or []:
            try:
                for layer in act.layers:
                    for strip in layer.strips:
                        cb = strip.channelbag(slot, ensure=False)
                        if cb is None:
                            continue
                        for fc in cb.fcurves:
                            for kp in fc.keyframe_points:
                                kp.interpolation = "LINEAR"
            except Exception:
                pass
        act.use_fake_user = True
    if dest.animation_data:
        dest.animation_data.action = None
    log(f"neutralized arm channels on {clips} bones={len(arm_bones)}")
    return {"clips": clips, "arm_bones": arm_bones}

PROTECTED = (
    "tent_canvas_small", "campfire_ring", "Tribal", "Tribal_Veteran", "kaykit",
)


def log(msg: str) -> None:
    print(f"[arm-skin] {msg}", flush=True)


def ensure_scratch() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    if bpy.context.selected_objects:
        bpy.ops.object.delete()
    for coll in (
        bpy.data.actions, bpy.data.armatures, bpy.data.meshes,
        bpy.data.materials, bpy.data.images, bpy.data.objects,
        bpy.data.cameras, bpy.data.lights, bpy.data.worlds,
    ):
        for block in list(coll):
            try:
                coll.remove(block)
            except Exception:
                pass


def import_gltf(path: Path, *, guess_bind: bool) -> None:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(
        filepath=str(path),
        bone_heuristic="BLENDER",
        guess_original_bind_pose=guess_bind,
    )
    after = set(bpy.data.objects)
    log(f"imported {path.name} guess_bind={guess_bind} +{len(after - before)} objects")


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


def build_retarget_dest_rest(src_rest: dict, dest_rest_a: dict, reverse_map: dict) -> dict:
    """Build a T-pose-homologous dest rest for retarget.

    UAL rests in a T-pose; MPFB villagers rest in an A-pose. Feeding A-pose
    dest_rest into rest-relative retarget applies the T→Idle world delta on top
    of already-lowered arms and folds them through the torso. Use dest joint
    translations (proportions) with hip-aligned source T-pose rotations instead.
    """
    if "DEF-hips" not in src_rest or "pelvis" not in dest_rest_a:
        return {k: v.copy() for k, v in dest_rest_a.items()}
    align = dest_rest_a["pelvis"].to_quaternion() @ src_rest["DEF-hips"].to_quaternion().inverted()
    out = {}
    for dest_name, src_name in reverse_map.items():
        loc = dest_rest_a[dest_name].to_translation()
        rot = align @ src_rest[src_name].to_quaternion()
        out[dest_name] = compose_mat(loc, rot)
    return out


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
    if slots is None:
        return
    slot = None
    for s in slots:
        slot = s
        break
    # Do NOT slots.new() here: an empty pre-created slot prevents keyframe_insert
    # from binding the OBarmature slot that glTF/NLA export need.
    if slot is not None and hasattr(obj.animation_data, "action_slot"):
        try:
            obj.animation_data.action_slot = slot
        except Exception:
            pass


def ensure_quat_mode(arm) -> None:
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"


def reset_pose(arm) -> None:
    # Keep the active action (and its slot); only zero pose channels.
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def copy_action(action, new_name: str):
    clone = action.copy()
    clone.name = new_name
    clone.use_fake_user = True
    return clone


def ensure_action_object_slot(action):
    """Return an existing action slot; never invent an empty one."""
    slots = getattr(action, "slots", None)
    if slots is None:
        return None
    for s in slots:
        return s
    return None


def bind_strip_action_slot(arm, strip, action) -> bool:
    """Make sure an NLA strip has a usable action_slot for glTF export."""
    if strip is None or action is None:
        return False
    if getattr(strip, "action_slot", None) is not None:
        return True
    # Prefer the slot Blender assigned when the action was active on this armature.
    assign_action(arm, action)
    ad = arm.animation_data
    slot = getattr(ad, "action_slot", None) if ad is not None else None
    if slot is None:
        slot = ensure_action_object_slot(action)
    if slot is None:
        return False
    try:
        strip.action = action
        strip.action_slot = slot
        return getattr(strip, "action_slot", None) is not None
    except Exception:
        return False


def push_nla(arm, action, name: str) -> None:
    ad = arm.animation_data
    if ad is None:
        ad = arm.animation_data_create()
    track = ad.nla_tracks.new()
    track.name = name
    start = int(round(action.frame_range[0]))
    strip = track.strips.new(name, start, action)
    if not bind_strip_action_slot(arm, strip, action):
        log(f"WARNING: NLA strip {name!r} has no action_slot after bind")


def repair_nla_action_slots(arm) -> int:
    """Assign missing action slots on NLA strips so glTF export does not crash."""
    ad = arm.animation_data
    if ad is None:
        return 0
    fixed = 0
    for track in ad.nla_tracks:
        for strip in track.strips:
            if strip.action is None:
                continue
            if getattr(strip, "action_slot", None) is not None:
                continue
            if bind_strip_action_slot(arm, strip, strip.action):
                fixed += 1
            else:
                log(f"WARNING: could not slot strip {track.name}/{strip.name} action={strip.action.name}")
    return fixed


def clear_unslottable_nla(arm) -> int:
    """Drop NLA strips that still lack action_slot (export would crash on them)."""
    ad = arm.animation_data
    if ad is None:
        return 0
    removed = 0
    for track in list(ad.nla_tracks):
        for strip in list(track.strips):
            if strip.action is not None and getattr(strip, "action_slot", None) is None:
                track.strips.remove(strip)
                removed += 1
        if len(track.strips) == 0:
            ad.nla_tracks.remove(track)
    return removed


def force_opaque(mat) -> None:
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


def force_all_opaque() -> list[str]:
    names = []
    for mat in bpy.data.materials:
        force_opaque(mat)
        names.append(mat.name)
    return names


def make_opaque_mat(name: str, color, roughness: float = 0.85):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 1.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    force_opaque(mat)
    return mat


def mesh_objects():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def vg_weight(mesh, vert_index: int, group_index: int) -> float:
    for g in mesh.data.vertices[vert_index].groups:
        if g.group == group_index:
            return g.weight
    return 0.0


def group_index_map(mesh) -> dict[str, int]:
    return {g.name: g.index for g in mesh.vertex_groups}


def classify_groups(names) -> dict[str, set[str]]:
    arm_l, arm_r, torso, legs, other = set(), set(), set(), set(), set()
    for n in names:
        if n in ARM_L:
            arm_l.add(n)
        elif n in ARM_R:
            arm_r.add(n)
        elif n in TORSO:
            torso.add(n)
        elif n in LEGS:
            legs.add(n)
        else:
            other.add(n)
    return {"arm_l": arm_l, "arm_r": arm_r, "torso": torso, "legs": legs, "other": other}


def vert_bucket_weights(mesh, vi: int, gmap: dict[str, int], buckets: dict[str, set[str]]) -> dict[str, float]:
    out = {k: 0.0 for k in buckets}
    for g in mesh.data.vertices[vi].groups:
        name = None
        for n, idx in gmap.items():
            if idx == g.group:
                name = n
                break
        if name is None:
            continue
        for key, names in buckets.items():
            if name in names:
                out[key] += g.weight
                break
    return out


def sample_mesh_weights(mesh) -> dict:
    gmap = group_index_map(mesh)
    buckets = classify_groups(gmap)
    n = len(mesh.data.vertices)
    leak_l = leak_r = arm_l_n = arm_r_n = 0
    leak_examples = []
    # spatial: verts that sit in an arm-like rest location
    spatial_arm = 0
    spatial_torso_on_arm = 0
    mw = mesh.matrix_world
    xs_l, xs_r = [], []
    for vi, v in enumerate(mesh.data.vertices):
        w = vert_bucket_weights(mesh, vi, gmap, buckets)
        world = mw @ v.co
        if w["arm_l"] >= 0.35:
            arm_l_n += 1
            xs_l.append(world.x)
            if w["torso"] + w["legs"] >= 0.20:
                leak_l += 1
                if len(leak_examples) < 6:
                    leak_examples.append({
                        "mesh": mesh.name, "side": "L", "vi": vi,
                        "co": [round(world.x, 3), round(world.y, 3), round(world.z, 3)],
                        "arm": round(w["arm_l"], 3), "torso": round(w["torso"], 3),
                        "legs": round(w["legs"], 3),
                    })
        if w["arm_r"] >= 0.35:
            arm_r_n += 1
            xs_r.append(world.x)
            if w["torso"] + w["legs"] >= 0.20:
                leak_r += 1
                if len(leak_examples) < 6:
                    leak_examples.append({
                        "mesh": mesh.name, "side": "R", "vi": vi,
                        "co": [round(world.x, 3), round(world.y, 3), round(world.z, 3)],
                        "arm": round(w["arm_r"], 3), "torso": round(w["torso"], 3),
                        "legs": round(w["legs"], 3),
                    })
        # spatial arm band (T-pose-ish: |x| large, mid height)
        if abs(world.x) > 0.22 and 0.85 < world.z < 1.55:
            spatial_arm += 1
            if w["torso"] >= 0.40 and w["arm_l"] + w["arm_r"] < 0.30:
                spatial_torso_on_arm += 1
    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else None
    return {
        "name": mesh.name,
        "verts": n,
        "groups": sorted(gmap),
        "arm_l_verts": arm_l_n,
        "arm_r_verts": arm_r_n,
        "leak_l": leak_l,
        "leak_r": leak_r,
        "leak_l_frac": round(leak_l / arm_l_n, 4) if arm_l_n else 0.0,
        "leak_r_frac": round(leak_r / arm_r_n, 4) if arm_r_n else 0.0,
        "arm_l_mean_x": mean(xs_l),
        "arm_r_mean_x": mean(xs_r),
        "spatial_arm_band": spatial_arm,
        "spatial_torso_on_arm": spatial_torso_on_arm,
        "leak_examples": leak_examples,
    }


def depsgraph_eval_positions(obj) -> list[Vector]:
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    mw = ev.matrix_world
    out = [mw @ v.co.copy() for v in me.vertices]
    ev.to_mesh_clear()
    return out


def deformed_arm_metrics(mesh, pose_label: str) -> dict:
    gmap = group_index_map(mesh)
    buckets = classify_groups(gmap)
    try:
        pos = depsgraph_eval_positions(mesh)
    except Exception as exc:
        return {"name": mesh.name, "pose": pose_label, "error": str(exc)}
    chest_l = chest_r = waist = 0
    arm_l_n = arm_r_n = 0
    xs_l, xs_r, zs_l, zs_r = [], [], [], []
    for vi, v in enumerate(mesh.data.vertices):
        if vi >= len(pos):
            break
        w = vert_bucket_weights(mesh, vi, gmap, buckets)
        p = pos[vi]
        if w["arm_l"] >= 0.45:
            arm_l_n += 1
            xs_l.append(p.x)
            zs_l.append(p.z)
            # through chest: near midline, torso height
            if abs(p.x) < 0.12 and 0.95 < p.z < 1.45:
                chest_l += 1
            if abs(p.x) < 0.18 and 0.70 < p.z < 1.00:
                waist += 1
        if w["arm_r"] >= 0.45:
            arm_r_n += 1
            xs_r.append(p.x)
            zs_r.append(p.z)
            if abs(p.x) < 0.12 and 0.95 < p.z < 1.45:
                chest_r += 1
            if abs(p.x) < 0.18 and 0.70 < p.z < 1.00:
                waist += 1
    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else None
    chest = chest_l + chest_r
    arm_n = arm_l_n + arm_r_n
    return {
        "name": mesh.name,
        "pose": pose_label,
        "arm_l": arm_l_n,
        "arm_r": arm_r_n,
        "chest_through": chest,
        "chest_frac": round(chest / arm_n, 4) if arm_n else 0.0,
        "waist_blobs": waist,
        "arm_l_mean_x": mean(xs_l),
        "arm_r_mean_x": mean(xs_r),
        "arm_l_mean_z": mean(zs_l),
        "arm_r_mean_z": mean(zs_r),
        "arms_separated": bool(
            mean(xs_l) is not None and mean(xs_r) is not None
            and abs(mean(xs_l) - mean(xs_r)) >= 0.20
        ),
    }


def play_clip(arm, name: str, mid: bool = True) -> int | None:
    act = bpy.data.actions.get(name)
    if act is None:
        for a in bpy.data.actions:
            if a.name == name or a.name.endswith(name):
                act = a
                break
    if act is None:
        return None
    assign_action(arm, act)
    f0 = int(round(act.frame_range[0]))
    f1 = int(round(act.frame_range[1]))
    frame = f0 + (f1 - f0) // 2 if mid else f0
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return frame


def glb_chunks(path: Path):
    data = Path(path).read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError(f"{path} is not a GLB")
    _magic, _version, length = struct.unpack_from("<III", data, 0)
    offset = 12
    doc = None
    blob = b""
    unknown = []
    found = []
    while offset + 8 <= min(length, len(data)):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        fourcc = data[offset + 4 : offset + 8]
        found.append(fourcc)
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == JSON_FOURCC or fourcc == b"JSON":
            doc = json.loads(chunk)
        elif chunk_type == BIN_FOURCC or fourcc[:3] == b"BIN":
            blob = chunk
            if fourcc != b"BIN\x00":
                unknown.append(fourcc)
        else:
            unknown.append(fourcc)
    if doc is None:
        raise RuntimeError(f"{path}: no JSON chunk")
    return doc, blob, unknown, found


def write_glb(path: Path, doc: dict, blob: bytes) -> None:
    json_bytes = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_pad = (4 - (len(json_bytes) % 4)) % 4
    json_bytes = json_bytes + (b" " * json_pad)
    bin_pad = (4 - (len(blob) % 4)) % 4
    blob_padded = blob + (b"\x00" * bin_pad)
    total = 12 + 8 + len(json_bytes) + 8 + len(blob_padded)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(json_bytes), JSON_FOURCC)
    out += json_bytes
    out += struct.pack("<II", len(blob_padded), BIN_FOURCC)
    out += blob_padded
    path.write_bytes(bytes(out))


def patch_fourcc_and_opaque(path: Path) -> dict:
    doc, blob, unknown, found = glb_chunks(path)
    blends = []
    dirty = False
    for mat in doc.get("materials", []):
        mode = mat.get("alphaMode", "OPAQUE")
        blends.append((mat.get("name"), mode))
        if mode != "OPAQUE":
            mat["alphaMode"] = "OPAQUE"
            dirty = True
        extra = mat.get("extras") or {}
        if extra.get("alphaMode") and extra.get("alphaMode") != "OPAQUE":
            extra["alphaMode"] = "OPAQUE"
            dirty = True
    if unknown or dirty or found != [b"JSON", b"BIN\x00"]:
        write_glb(path, doc, blob)
        doc, blob, unknown, found = glb_chunks(path)
        log(f"rewrote {path.name} fourcc={[c.decode('latin1') for c in found]} opaque")
    anims = [a.get("name") for a in doc.get("animations", [])]
    meshes = [m.get("name") for m in doc.get("meshes", [])]
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "fourcc": [c.decode("latin1") for c in found],
        "clips": anims,
        "meshes": meshes,
        "materials": [(m.get("name"), m.get("alphaMode", "OPAQUE")) for m in doc.get("materials", [])],
        "skins": len(doc.get("skins", [])),
    }


def setup_preview_scene(height: float = 1.65):
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    if "PreviewGround" not in bpy.data.objects:
        ground_mat = make_opaque_mat("PreviewGround", (0.18, 0.175, 0.165), 1.0)
        bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.0))
        ground = bpy.context.active_object
        ground.name = "PreviewGround"
        ground.data.materials.append(ground_mat)
    world = bpy.data.worlds.get("PreviewWorld") or bpy.data.worlds.new("PreviewWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.14, 0.145, 0.155, 1.0)
        bg.inputs[1].default_value = 1.0
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    look_z = height * 0.52
    target = Vector((0.00, 0.00, look_z))
    cam.location = Vector((2.15, -2.85, look_z + 0.35))
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

    add_light("Key", "SUN", (3.0, -2.5, 6.0), 3.4, rot=(math.radians(50), math.radians(15), math.radians(35)))
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0, size=1.6)
    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 800
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
    return cam


def render_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"preview not written: {path}")
    log(f"preview {path} ({path.stat().st_size} bytes)")


def scene_overview() -> dict:
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = mesh_objects()
    info = {
        "armatures": [],
        "meshes": [],
        "actions": [a.name for a in bpy.data.actions],
        "materials": [],
    }
    for arm in arms:
        info["armatures"].append({
            "name": arm.name,
            "bones": len(arm.data.bones),
            "bone_sample": [b.name for b in list(arm.data.bones)[:12]],
            "has_pelvis": "pelvis" in arm.data.bones,
        })
    for mesh in meshes:
        mats = []
        for slot in mesh.material_slots:
            if slot.material:
                mats.append({
                    "name": slot.material.name,
                    "blend": getattr(slot.material, "blend_method", None),
                })
        info["meshes"].append({
            "name": mesh.name,
            "verts": len(mesh.data.vertices),
            "parent": mesh.parent.name if mesh.parent else None,
            "vgroups": [g.name for g in mesh.vertex_groups],
            "mods": [m.type for m in mesh.modifiers],
            "materials": mats,
        })
    for mat in bpy.data.materials:
        info["materials"].append({
            "name": mat.name,
            "blend": getattr(mat, "blend_method", None),
        })
    return info


def diagnose_file(path: Path, tag: str, *, guess_bind: bool, render: bool) -> dict:
    log(f"==== diagnose {tag} {path}")
    report = {
        "tag": tag,
        "path": str(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "guess_bind": guess_bind,
    }
    if not path.is_file():
        report["error"] = "missing"
        return report
    try:
        doc, blob, unknown, found = glb_chunks(path)
        report["fourcc"] = [c.decode("latin1") for c in found]
        report["glb_clips"] = [a.get("name") for a in doc.get("animations", [])]
        report["glb_meshes"] = [m.get("name") for m in doc.get("meshes", [])]
        report["glb_materials"] = [
            (m.get("name"), m.get("alphaMode", "OPAQUE")) for m in doc.get("materials", [])
        ]
        report["glb_skins"] = len(doc.get("skins", []))
    except Exception as exc:
        report["glb_error"] = str(exc)

    clear_scene()
    import_gltf(path, guess_bind=guess_bind)
    report["scene"] = scene_overview()
    try:
        arm = find_armature(has_bone="pelvis")
    except RuntimeError as exc:
        report["error"] = str(exc)
        return report
    report["armature"] = arm.name
    reset_pose(arm)
    weights = [sample_mesh_weights(m) for m in mesh_objects() if m.name != "PreviewGround"]
    report["weights_rest"] = weights
    rest_def = [deformed_arm_metrics(m, "rest") for m in mesh_objects() if m.name != "PreviewGround"]
    report["deform_rest"] = rest_def

    idle_frame = play_clip(arm, "Idle", mid=True)
    report["idle_frame"] = idle_frame
    if idle_frame is not None:
        report["deform_idle"] = [
            deformed_arm_metrics(m, "Idle") for m in mesh_objects() if m.name != "PreviewGround"
        ]
    walk_frame = play_clip(arm, "Walk", mid=True)
    report["walk_frame"] = walk_frame
    if walk_frame is not None:
        report["deform_walk"] = [
            deformed_arm_metrics(m, "Walk") for m in mesh_objects() if m.name != "PreviewGround"
        ]

    report["verdict"] = verdict_from_report(report)
    if render:
        height = 1.55 if "female" in tag else 1.75
        setup_preview_scene(height)
        force_all_opaque()
        reset_pose(arm)
        render_png(SCRATCH / f"diag_{tag}_rest.png")
        if idle_frame is not None:
            play_clip(arm, "Idle", mid=True)
            render_png(SCRATCH / f"diag_{tag}_idle.png")
        if walk_frame is not None:
            play_clip(arm, "Walk", mid=True)
            render_png(SCRATCH / f"diag_{tag}_walk.png")
    log(f"verdict {tag}: {report['verdict']}")
    return report


def _chest_frac(deforms) -> float:
    if not deforms:
        return 0.0
    # Prefer body meshes; clothing sleeve weights inflate chest_frac even when
    # the skinned body arms are fine.
    body = []
    clothes = []
    for d in deforms:
        if not isinstance(d, dict) or "chest_frac" not in d:
            continue
        name = (d.get("name") or "").lower()
        if any(s in name for s in ("suit", "casual", "work", "cloth")):
            clothes.append(d)
        else:
            body.append(d)
    use = body or clothes
    worst = 0.0
    for d in use:
        worst = max(worst, float(d["chest_frac"]))
    return worst


def _arms_separated(deforms) -> bool:
    if not deforms:
        return False
    for d in deforms:
        if not isinstance(d, dict):
            continue
        xl, xr = d.get("arm_l_mean_x"), d.get("arm_r_mean_x")
        if xl is None or xr is None:
            continue
        # MPFB left is +X, right is -X; only the split magnitude matters.
        if abs(xl - xr) >= 0.20:
            return True
    return False


def _leak_frac(weights) -> float:
    worst = 0.0
    for w in weights or []:
        worst = max(worst, w.get("leak_l_frac", 0.0), w.get("leak_r_frac", 0.0))
    return worst


def verdict_from_report(report: dict) -> dict:
    leak = _leak_frac(report.get("weights_rest"))
    idle_chest = _chest_frac(report.get("deform_idle"))
    walk_chest = _chest_frac(report.get("deform_walk"))
    rest_sep = _arms_separated(report.get("deform_rest"))
    idle_sep = _arms_separated(report.get("deform_idle"))
    walk_sep = _arms_separated(report.get("deform_walk"))
    has_clothes = any(
        "suit" in (m or "").lower() or "casual" in (m or "").lower() or "work" in (m or "").lower()
        for m in report.get("glb_meshes") or []
    )
    has_clips = all(c in (report.get("glb_clips") or []) for c in REQUIRED_CLIPS)
    # Clothing sleeves stuck on the torso show up as high chest_frac on the suit mesh.
    # Crossed / folded Idle/Walk arms also fail separation even when chest_frac is mild.
    posed_bad = False
    if report.get("deform_idle") is not None:
        posed_bad = posed_bad or idle_chest >= 0.12 or not idle_sep
    if report.get("deform_walk") is not None:
        posed_bad = posed_bad or walk_chest >= 0.12 or not walk_sep
    weights_bad = leak >= 0.12
    clean = (not posed_bad) and (not weights_bad)
    return {
        "clean": bool(clean),
        "posed_bad": bool(posed_bad),
        "weights_bad": bool(weights_bad),
        "leak_frac": leak,
        "idle_chest_frac": idle_chest,
        "walk_chest_frac": walk_chest,
        "rest_separated": rest_sep,
        "idle_separated": idle_sep,
        "walk_separated": walk_sep,
        "has_clothes": has_clothes,
        "has_clips": has_clips,
    }


def clamp_arm_island_weights(mesh) -> dict:
    """Zero spine/hips/leg influence on verts that belong to an arm island."""
    gmap = group_index_map(mesh)
    buckets = classify_groups(gmap)
    n = len(mesh.data.vertices)
    if n == 0:
        return {"mesh": mesh.name, "changed": 0}

    # adjacency via edges
    adj = [[] for _ in range(n)]
    for e in mesh.data.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)

    def arm_side(vi):
        w = vert_bucket_weights(mesh, vi, gmap, buckets)
        if w["arm_l"] >= 0.35 and w["arm_l"] >= w["arm_r"]:
            return "l"
        if w["arm_r"] >= 0.35:
            return "r"
        return None

    seen = [False] * n
    changed = 0
    islands = 0
    for seed in range(n):
        if seen[seed] or arm_side(seed) is None:
            continue
        side = arm_side(seed)
        stack = [seed]
        seen[seed] = True
        comp = []
        while stack:
            vi = stack.pop()
            comp.append(vi)
            for nb in adj[vi]:
                if not seen[nb] and arm_side(nb) == side:
                    seen[nb] = True
                    stack.append(nb)
        islands += 1
        keep = ARM_L if side == "l" else ARM_R
        drop = TORSO | LEGS | (ARM_R if side == "l" else ARM_L)
        for vi in comp:
            groups = mesh.data.vertices[vi].groups
            # read current
            weights = {g.group: g.weight for g in groups}
            keep_sum = 0.0
            for name in keep:
                idx = gmap.get(name)
                if idx is not None:
                    keep_sum += weights.get(idx, 0.0)
            if keep_sum <= 1e-6:
                continue
            # zero dropped groups
            did = False
            for name in drop:
                idx = gmap.get(name)
                if idx is None or weights.get(idx, 0.0) <= 1e-8:
                    continue
                mesh.vertex_groups[name].remove([vi])
                did = True
            if not did:
                continue
            # renormalize remaining arm weights
            leftover = []
            for name in keep:
                idx = gmap.get(name)
                if idx is None:
                    continue
                w = vg_weight(mesh, vi, idx)
                if w > 1e-8:
                    leftover.append((name, w))
            total = sum(w for _, w in leftover)
            if total <= 1e-8:
                continue
            for name, w in leftover:
                mesh.vertex_groups[name].add([vi], w / total, "REPLACE")
            changed += 1
    log(f"clamped {mesh.name}: islands={islands} verts_changed={changed}")
    return {"mesh": mesh.name, "islands": islands, "changed": changed}





def dist_point_segment(p: Vector, head: Vector, tail: Vector) -> float:
    d = tail - head
    l2 = d.length_squared
    if l2 < 1e-12:
        return (p - head).length
    t = max(0.0, min(1.0, (p - head).dot(d) / l2))
    return (p - (head + d * t)).length



def copy_vert_weights(src_mesh, src_vi, dst_mesh, dst_vi) -> None:
    src_gmap = group_index_map(src_mesh)
    dst_names = {g.name for g in dst_mesh.vertex_groups}
    src_w = {g.group: g.weight for g in src_mesh.data.vertices[src_vi].groups}
    for g in list(dst_mesh.data.vertices[dst_vi].groups):
        dst_mesh.vertex_groups[g.group].remove([dst_vi])
    for gidx, weight in src_w.items():
        name = None
        for n, i in src_gmap.items():
            if i == gidx:
                name = n
                break
        if name is None:
            continue
        if name not in dst_names:
            dst_mesh.vertex_groups.new(name=name)
            dst_names.add(name)
        dst_mesh.vertex_groups[name].add([dst_vi], weight, "REPLACE")


def sleeve_vertex_indices(mesh) -> list[int]:
    """Grow from existing arm-weighted verts, stop at the torso midline."""
    gmap = group_index_map(mesh)
    buckets = classify_groups(gmap)
    n = len(mesh.data.vertices)
    adj = [[] for _ in range(n)]
    for e in mesh.data.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    mw = mesh.matrix_world
    seeds = []
    for vi, v in enumerate(mesh.data.vertices):
        w = vert_bucket_weights(mesh, vi, gmap, buckets)
        if w["arm_l"] + w["arm_r"] >= 0.28:
            seeds.append(vi)
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        vi = stack.pop()
        for nb in adj[vi]:
            if nb in seen:
                continue
            q = mw @ mesh.data.vertices[nb].co
            if abs(q.x) < 0.13:
                continue
            if q.z < 0.85 or q.z > 1.55:
                continue
            seen.add(nb)
            stack.append(nb)
    return sorted(seen)


def auto_weight_sleeves(clothes, arm) -> dict:
    """Bone-heat the clothing duplicate, copy weights back onto sleeve islands only."""
    reset_pose(arm)
    bpy.context.view_layer.update()
    vis = sleeve_vertex_indices(clothes)
    log(f"sleeve island {clothes.name}: {len(vis)} verts")
    if not vis:
        return {"mesh": clothes.name, "changed": 0}
    dup = clothes.copy()
    dup.data = clothes.data.copy()
    dup.name = clothes.name + "_autow"
    bpy.context.scene.collection.objects.link(dup)
    for mod in list(dup.modifiers):
        if mod.type == "ARMATURE":
            dup.modifiers.remove(mod)
    bpy.ops.object.select_all(action="DESELECT")
    dup.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    bpy.context.view_layer.update()
    changed = 0
    for vi in vis:
        copy_vert_weights(dup, vi, clothes, vi)
        changed += 1
    bpy.data.objects.remove(dup, do_unlink=True)
    # leftover mesh datablock
    for me in list(bpy.data.meshes):
        if me.name.endswith("_autow") or me.users == 0:
            try:
                bpy.data.meshes.remove(me)
            except Exception:
                pass
    log(f"auto-weight sleeves {clothes.name}: copied={changed}")
    return {"mesh": clothes.name, "changed": changed, "island": len(vis)}


def fix_clothing_sleeve_weights() -> list[dict]:
    arm = find_armature(has_bone="pelvis")
    meshes = [m for m in mesh_objects() if m.name != "PreviewGround"]
    clothes = [m for m in meshes if any(s in m.name.lower() for s in ("suit", "casual", "work"))]
    out = []
    log(f"sleeve auto-weight clothes={[c.name for c in clothes]}")
    for cloth in clothes:
        out.append(auto_weight_sleeves(cloth, arm))
    return out


def clamp_all_arm_weights() -> list[dict]:
    out = []
    for mesh in mesh_objects():
        if mesh.name == "PreviewGround":
            continue
        if not mesh.vertex_groups:
            continue
        sample = sample_mesh_weights(mesh)
        is_clothes = any(s in mesh.name.lower() for s in ("suit", "casual", "work", "cloth"))
        leak = max(sample.get("leak_l_frac", 0.0), sample.get("leak_r_frac", 0.0))
        if not is_clothes and leak < 0.10:
            log(f"skip clamp {mesh.name} leak={leak}")
            continue
        log(f"clamp {mesh.name} leak={leak} clothes={is_clothes}")
        out.append(clamp_arm_island_weights(mesh))
    return out


def bake_clip(src, dest, src_action, dest_action, *, in_place: bool, hip_scale: float,
              src_rest: dict, dest_rest: dict, order: list[str], reverse_map: dict) -> None:
    """Retarget by copying parent-local matrix_basis (UAL T-pose ↔ MPFB A-pose safe).

    World rest-relative retarget folds A-pose arms through the torso because UAL
    rests in a T-pose. Local basis deltas are the motion away from each skeleton's
    own rest, so Idle stays near the villager A-pose instead of applying T→down
    on top of already-lowered arms.
    """
    assign_action(src, src_action)
    assign_action(dest, dest_action)
    ensure_quat_mode(dest)
    reset_pose(dest)

    f0 = int(round(src_action.frame_range[0]))
    f1 = int(round(src_action.frame_range[1]))
    log(f"  bake {src_action.name} -> {dest_action.name} frames {f0}..{f1} "
        f"in_place={in_place} hip_scale={hip_scale:.4f} mode=matrix_basis")
    scene = bpy.context.scene
    first_local: dict[str, tuple] = {}
    pelvis = "pelvis"

    for frame in range(f0, f1 + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for dest_name in order:
            src_name = reverse_map[dest_name]
            if src_name not in src.pose.bones or dest_name not in dest.pose.bones:
                continue
            sp = src.pose.bones[src_name]
            dp = dest.pose.bones[dest_name]
            dp.rotation_mode = "QUATERNION"
            basis = sp.matrix_basis.copy()
            if in_place and dest_name == pelvis:
                # Keep villager rooted: drop planar translation from hips.
                basis = basis.copy()
                basis.translation.x = 0.0
                basis.translation.y = 0.0
                basis.translation.z *= hip_scale
            elif dest_name in TRANSLATION_BONES:
                basis = basis.copy()
                basis.translation *= hip_scale
            elif dest_name not in TRANSLATION_BONES:
                # Rotation-only on non-root bones (match prior bake behaviour).
                loc, rot, sca = basis.decompose()
                basis = rot.to_matrix().to_4x4()
                basis.translation = Vector((0.0, 0.0, 0.0))
            dp.matrix_basis = basis
        bpy.context.view_layer.update()
        for dest_name in order:
            if dest_name not in dest.pose.bones:
                continue
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
    for slot in getattr(dest_action, "slots", []) or []:
        try:
            for layer in dest_action.layers:
                for strip in layer.strips:
                    cb = strip.channelbag(slot, ensure=False)
                    if cb is None:
                        continue
                    for fc in cb.fcurves:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception:
            pass
    dest_action.use_fake_user = True
    n_slots = len(list(getattr(dest_action, "slots", []) or []))
    log(f"  baked {dest_action.name} slots={n_slots} legacy_fcurves={len(dest_action.fcurves)}")


def retarget_idle_walk(dest, dest_objects: list) -> None:
    """Apply UAL Idle/Walk onto dest rest. Does not touch vertex groups."""
    dest_set = set(dest_objects)
    for act in list(bpy.data.actions):
        if not act.name.startswith("DST_"):
            act.name = "DST_" + act.name
    import_gltf(SRC_ANIM, guess_bind=False)
    src = find_armature(has_bone="DEF-hips")
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
    # Clear any leftover dest clip so keyframing does not fight an old Idle.
    if dest.animation_data:
        dest.animation_data.action = None
        for track in list(dest.animation_data.nla_tracks):
            dest.animation_data.nla_tracks.remove(track)
    src_rest = {s: rest_world(src, s).copy() for s in BONE_MAP if s in src.data.bones}
    dest_rest = {d: rest_world(dest, d).copy() for d in BONE_MAP.values() if d in dest.data.bones}
    reverse_map = {d: s for s, d in BONE_MAP.items() if s in src_rest and d in dest_rest}
    order = dest_order(dest, set(reverse_map))
    src_hip = hip_height_z(src, "DEF-hips")
    dest_hip = hip_height_z(dest, "pelvis")
    hip_scale = dest_hip / src_hip if abs(src_hip) > 1e-6 else 1.0
    log(f"retarget mapped={len(reverse_map)} hip_scale={hip_scale:.4f} (matrix_basis copy)")
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
    src_objs = [o for o in bpy.data.objects if o not in dest_set and o.name != "PreviewGround"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in src_objs:
        if o.name in bpy.data.objects:
            o.select_set(True)
    if src_objs:
        bpy.ops.object.delete()
    keep = {a.name for a in made}
    for act in list(bpy.data.actions):
        if act.name not in keep:
            bpy.data.actions.remove(act)
    if dest.animation_data:
        dest.animation_data.action = None
        for track in list(dest.animation_data.nla_tracks):
            dest.animation_data.nla_tracks.remove(track)
    for act in made:
        act.use_fake_user = True
        push_nla(dest, act, act.name)



def ensure_clip_actions(dest) -> list[str]:
    """Keep loader clip names Idle / Walk (and Loop aliases) on the dest armature."""
    by_name = {a.name: a for a in bpy.data.actions}
    # importer sometimes prefixes
    def find_clip(want: str):
        if want in by_name:
            return by_name[want]
        for a in bpy.data.actions:
            if a.name == want or a.name.endswith(want) or a.name.replace("DST_", "") == want:
                return a
        return None
    idle = find_clip("Idle")
    walk = find_clip("Walk")
    if idle is None:
        idle = find_clip("Idle_Loop")
        if idle is not None and idle.name != "Idle":
            idle = copy_action(idle, "Idle")
    if walk is None:
        walk = find_clip("Walk_Loop")
        if walk is not None and walk.name != "Walk":
            walk = copy_action(walk, "Walk")
    if idle is None or walk is None:
        raise RuntimeError(f"missing Idle/Walk after import; have {[a.name for a in bpy.data.actions]}")
    idle.name = "Idle"
    walk.name = "Walk"
    aliases = []
    if find_clip("Idle_Loop") is None:
        aliases.append(copy_action(idle, "Idle_Loop"))
    if find_clip("Walk_Loop") is None:
        aliases.append(copy_action(walk, "Walk_Loop"))
    keep = []
    for name in ("Idle", "Idle_Loop", "Walk", "Walk_Loop"):
        act = find_clip(name)
        if act is None:
            raise RuntimeError(f"clip {name} missing after aliasing")
        act.use_fake_user = True
        keep.append(act.name)
    if dest.animation_data is None:
        dest.animation_data_create()
    dest.animation_data.action = None
    for track in list(dest.animation_data.nla_tracks):
        dest.animation_data.nla_tracks.remove(track)
    for name in ("Idle", "Idle_Loop", "Walk", "Walk_Loop"):
        push_nla(dest, find_clip(name), name)
    log(f"clips ready {keep}")
    return keep


def assemble_dressed(base_path: Path, piece_path: Path):
    """Load base + clothing piece onto the base armature. Keep existing piece weights."""
    clear_scene()
    import_gltf(base_path, guess_bind=False)
    dest = find_armature(has_bone="pelvis")
    dest_objects = [o for o in bpy.data.objects]
    log(f"base armature {dest.name} meshes={[o.name for o in dest_objects if o.type == 'MESH']}")
    import_gltf(piece_path, guess_bind=False)
    piece_objs = [o for o in bpy.data.objects if o not in dest_objects]
    piece_meshes = [o for o in piece_objs if o.type == "MESH"]
    piece_arms = [o for o in piece_objs if o.type == "ARMATURE"]
    log(f"piece meshes={[o.name for o in piece_meshes]} arms={[o.name for o in piece_arms]}")
    dest_names = {b.name for b in dest.data.bones}
    for mesh in piece_meshes:
        vg_names = {g.name for g in mesh.vertex_groups}
        mapped = vg_names & dest_names
        log(f"  {mesh.name} vgroups={len(vg_names)} mapped_to_dest={len(mapped)} verts={len(mesh.data.vertices)}")
        for mod in list(mesh.modifiers):
            if mod.type == "ARMATURE":
                mesh.modifiers.remove(mod)
        mod = mesh.modifiers.new("Armature", "ARMATURE")
        mod.object = dest
        mesh.parent = dest
    for arm in piece_arms:
        bpy.data.objects.remove(arm, do_unlink=True)
    # drop leftover empty objects from the piece
    for o in list(bpy.data.objects):
        if o not in dest_objects and o.type not in {"MESH", "ARMATURE"}:
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass
    keep = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"}]
    return dest, keep


def load_clean_bind(path: Path):
    clear_scene()
    import_gltf(path, guess_bind=False)
    dest = find_armature(has_bone="pelvis")
    dest_objects = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"}]
    reset_pose(dest)
    log(f"clean bind {path.name} arm={dest.name} meshes={[o.name for o in dest_objects if o.type == 'MESH']}")
    return dest, dest_objects


def scrub_foreign_nla(keep_arm) -> int:
    """Remove NLA on non-dest objects. Imported strips often lack action_slot."""
    removed_tracks = 0
    for obj in bpy.data.objects:
        if obj == keep_arm:
            continue
        ad = obj.animation_data
        if ad is None:
            continue
        if ad.nla_tracks:
            for track in list(ad.nla_tracks):
                ad.nla_tracks.remove(track)
                removed_tracks += 1
        ad.action = None
    return removed_tracks


def export_dest(out_path: Path, dest, dest_objects: list) -> Path:
    force_all_opaque()
    n_scrub = scrub_foreign_nla(dest)
    if n_scrub:
        log(f"scrubbed {n_scrub} foreign NLA tracks before export")
    if dest.animation_data is None:
        dest.animation_data_create()
    keep_actions = []
    for name in ("Idle", "Idle_Loop", "Walk", "Walk_Loop"):
        act = bpy.data.actions.get(name)
        if act is not None:
            keep_actions.append(act)
    for track in list(dest.animation_data.nla_tracks):
        dest.animation_data.nla_tracks.remove(track)
    for act in keep_actions:
        assign_action(dest, act)
        push_nla(dest, act, act.name)
    n_fixed = repair_nla_action_slots(dest)
    log(
        f"export NLA rebuilt actions={[a.name for a in keep_actions]} fixed={n_fixed} "
        + "strips="
        + ",".join(
            f"{t.name}:{getattr(t.strips[0], 'action_slot', None) is not None}"
            for t in dest.animation_data.nla_tracks
            if t.strips
        )
    )
    dest.animation_data.action = None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in dest_objects:
        if obj.name in bpy.data.objects and obj.name != "PreviewGround":
            obj.select_set(True)
    dest.select_set(True)
    bpy.context.view_layer.objects.active = dest
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scratch_out = SCRATCH / (out_path.stem + "_fixed.glb")
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
        alt = Path(str(scratch_out) + ".glb")
        if alt.is_file():
            scratch_out = alt
        else:
            raise RuntimeError(f"export produced no file: {scratch_out}")
    info = patch_fourcc_and_opaque(scratch_out)
    log(f"exported scratch {scratch_out} {info}")
    return scratch_out


def backup_live(path: Path) -> Path:
    bak = Path(str(path) + ".skin.bak")
    if not bak.is_file():
        shutil.copy2(path, bak)
        log(f"skin.bak created {bak} ({bak.stat().st_size} bytes)")
    else:
        log(f"skin.bak exists {bak} ({bak.stat().st_size} bytes)")
    return bak


def install_fixed(scratch: Path, dests: list[Path]) -> None:
    for dest in dests:
        if not dest.parent.is_dir():
            raise RuntimeError(f"refusing write, missing dir {dest.parent}")
        # never touch protected names
        for bad in PROTECTED:
            if bad.lower() in dest.name.lower():
                raise RuntimeError(f"refusing to overwrite protected {dest}")
        if dest.is_file():
            backup_live(dest)
        else:
            log(f"install target missing, creating {dest}")
        shutil.copy2(scratch, dest)
        patch_fourcc_and_opaque(dest)
        log(f"installed {dest} ({dest.stat().st_size} bytes)")


def render_final_previews(arm, prefix: str, copy_names: dict[str, str]) -> dict:
    height = 1.55 if "female" in prefix else 1.75
    setup_preview_scene(height)
    force_all_opaque()
    paths = {}
    play_clip(arm, "Idle", mid=True)
    idle_path = SCRATCH / f"{prefix}_idle.png"
    render_png(idle_path)
    paths["idle"] = idle_path
    play_clip(arm, "Walk", mid=True)
    walk_path = SCRATCH / f"{prefix}_walk.png"
    render_png(walk_path)
    paths["walk"] = walk_path
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for key, dest_name in copy_names.items():
        src = paths[key]
        dest = PREVIEW_DIR / dest_name
        shutil.copy2(src, dest)
        log(f"copied preview -> {dest} ({dest.stat().st_size} bytes)")
        paths[f"copy_{key}"] = dest
    return paths


def candidate_paths(kind: str) -> dict[str, Path]:
    name = FEMALE_NAME if kind == "female" else MALE_NAME
    piece = FEMALE_PIECE if kind == "female" else MALE_PIECE
    base = "female_base.glb" if kind == "female" else "male_base.glb"
    return {
        "orrun_live": ORRUN_HUMANS / name,
        "ag_live": AG_HUMANS / name,
        "orrun_bak": ORRUN_HUMANS / (name + ".bak") if False else Path(str(ORRUN_HUMANS / name) + ".bak"),
        "ag_bak": Path(str(AG_HUMANS / name) + ".bak"),
        "cs": CS_HUMANS / name,
        "base": AG_HUMANS / base,
        "piece": CS_PIECES / piece,
        "cs_base": CS_HUMANS / base,
    }


def pick_bind_source(kind: str, reports: dict) -> dict:
    """Choose how to rebuild this character."""
    live = reports.get("orrun_live") or {}
    live_v = (live.get("verdict") or {})
    ag_bak = reports.get("ag_bak") or {}
    ag_v = (ag_bak.get("verdict") or {})
    orrun_bak = reports.get("orrun_bak") or {}
    orrun_v = (orrun_bak.get("verdict") or {})

    if live_v.get("clean") and live_v.get("has_clips") and live_v.get("has_clothes"):
        return {"action": "leave", "reason": "live already clean"}

    # First-bake AG bak: clothes + clips, no second retarget
    if ag_v.get("clean") and ag_v.get("has_clips") and ag_v.get("has_clothes"):
        return {"action": "restore_file", "src": "ag_bak", "reason": "AG first-bake is clean"}

    # Orrun pre-anim bak if it actually has clothes (it usually does not)
    if orrun_v.get("clean") and orrun_v.get("has_clothes"):
        return {
            "action": "rebind_retarget",
            "src": "orrun_bak",
            "clamp": orrun_v.get("weights_bad", False),
            "reason": "Orrun bak clean bind with clothes",
        }

    # Live rest bind OK but Idle/Walk fold arms through the torso. Neutralize
    # arm channels back to A-pose bind; keep spine/leg motion from the live clips.
    # (Full UAL re-retarget is unsafe: world rest-relative assumes matching T-pose
    # rests, and matrix_basis copy fails across UAL↔MPFB bone axes.)
    if live_v.get("rest_separated") and live_v.get("has_clothes") and live_v.get("posed_bad"):
        return {
            "action": "neutralize_arms",
            "src": "orrun_live",
            "clamp": live_v.get("weights_bad", False),
            "reason": "live rest bind OK; neutralize compounded arm channels",
        }

    # Rest + clips look fine enough, but clothing arm islands leak to spine/hips.
    # Clamp sleeve weights and keep existing Idle/Walk.
    if (
        live_v.get("has_clips")
        and live_v.get("has_clothes")
        and live_v.get("posed_bad")
        and live_v.get("weights_bad")
        and live_v.get("idle_separated")
        and live_v.get("walk_separated")
    ):
        return {
            "action": "clamp_keep_clips",
            "src": "orrun_live",
            "reason": "live clips OK; clothing arm islands leak to torso",
        }

    # Live imported without bind-guess: if rest arms are separated, weights/IBM are OK
    # and we only need to replace the compounded Idle/Walk.
    if live_v.get("rest_separated") and live_v.get("has_clothes"):
        return {
            "action": "rebind_retarget",
            "src": "orrun_live",
            "clamp": live_v.get("weights_bad", False),
            "reason": "live rest bind OK; replace compounded clips",
        }

    # AG bak rest OK even if posed_bad (same double-bake may not apply to bak)
    if ag_v.get("rest_separated") and ag_v.get("has_clothes"):
        return {
            "action": "rebind_retarget",
            "src": "ag_bak",
            "clamp": ag_v.get("weights_bad", False),
            "reason": "AG bak rest bind OK; retarget once",
        }

    # Reconstruct from base + clothing piece (clean T-pose weights)
    return {
        "action": "assemble_retarget",
        "src": "base+piece",
        "clamp": True,
        "reason": "no clean dressed bind; assemble base + piece",
    }


def apply_plan(kind: str, plan: dict, paths: dict) -> dict:
    log(f"==== apply {kind} {plan}")
    result = {"kind": kind, "plan": plan}
    if plan["action"] == "leave":
        result["fixed"] = False
        result["left"] = True
        return result

    dests = [paths["orrun_live"], paths["ag_live"]]
    copy_names = {
        "idle": f"{kind}_casual_idle.png" if kind == "female" else f"{kind}_work_idle.png",
        "walk": f"{kind}_casual_walk.png" if kind == "female" else f"{kind}_work_walk.png",
    }
    # requested names
    if kind == "female":
        copy_names = {"idle": "female_casual_idle.png", "walk": "female_casual_walk.png"}
    else:
        copy_names = {"idle": "male_work_idle.png", "walk": "male_work_walk.png"}

    if plan["action"] == "clamp_keep_clips":
        dest, dest_objects = load_clean_bind(paths[plan["src"]])
        result["clamp"] = fix_clothing_sleeve_weights()
        result["clips"] = ensure_clip_actions(dest)
        dest_objects = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"} and o.name != "PreviewGround"]
        scratch = export_dest(paths["orrun_live"], dest, dest_objects)
        install_fixed(scratch, dests)
        dest, dest_objects = load_clean_bind(paths["orrun_live"])
        previews = render_final_previews(dest, f"{kind}_final", copy_names)
        play_clip(dest, "Idle", mid=True)
        post = {
            "deform_idle": [deformed_arm_metrics(m, "Idle") for m in mesh_objects() if m.name != "PreviewGround"],
        }
        play_clip(dest, "Walk", mid=True)
        post["deform_walk"] = [deformed_arm_metrics(m, "Walk") for m in mesh_objects() if m.name != "PreviewGround"]
        post["weights"] = [sample_mesh_weights(m) for m in mesh_objects() if m.name != "PreviewGround"]
        info = patch_fourcc_and_opaque(paths["orrun_live"])
        result.update({"fixed": True, "export": info, "previews": {k: str(v) for k, v in previews.items()}, "post": post})
        return result

    if plan["action"] == "neutralize_arms":
        dest, dest_objects = load_clean_bind(paths[plan["src"]])
        if plan.get("clamp"):
            result["clamp"] = clamp_all_arm_weights()
        result["neutralize"] = neutralize_arm_clip_channels(dest)
        result["clips"] = ensure_clip_actions(dest)
        dest_objects = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"} and o.name != "PreviewGround"]
        scratch = export_dest(paths["orrun_live"], dest, dest_objects)
        install_fixed(scratch, dests)
        dest, dest_objects = load_clean_bind(paths["orrun_live"])
        previews = render_final_previews(dest, f"{kind}_final", copy_names)
        play_clip(dest, "Idle", mid=True)
        post = {
            "deform_idle": [deformed_arm_metrics(m, "Idle") for m in mesh_objects() if m.name != "PreviewGround"],
        }
        play_clip(dest, "Walk", mid=True)
        post["deform_walk"] = [deformed_arm_metrics(m, "Walk") for m in mesh_objects() if m.name != "PreviewGround"]
        post["weights"] = [sample_mesh_weights(m) for m in mesh_objects() if m.name != "PreviewGround"]
        info = patch_fourcc_and_opaque(paths["orrun_live"])
        result.update({"fixed": True, "export": info, "previews": {k: str(v) for k, v in previews.items()}, "post": post})
        return result

    if plan["action"] == "restore_file":
        src = paths[plan["src"]]
        scratch = SCRATCH / (paths["orrun_live"].stem + "_restored.glb")
        shutil.copy2(src, scratch)
        info = patch_fourcc_and_opaque(scratch)
        install_fixed(scratch, dests)
        # preview from restored
        dest, dest_objects = load_clean_bind(paths["orrun_live"])
        previews = render_final_previews(dest, f"{kind}_final", copy_names)
        # post metrics
        reset_pose(dest)
        post = {
            "weights": [sample_mesh_weights(m) for m in mesh_objects() if m.name != "PreviewGround"],
        }
        play_clip(dest, "Idle", mid=True)
        post["deform_idle"] = [deformed_arm_metrics(m, "Idle") for m in mesh_objects() if m.name != "PreviewGround"]
        play_clip(dest, "Walk", mid=True)
        post["deform_walk"] = [deformed_arm_metrics(m, "Walk") for m in mesh_objects() if m.name != "PreviewGround"]
        result.update({"fixed": True, "export": info, "previews": {k: str(v) for k, v in previews.items()}, "post": post})
        return result

    if plan["action"] == "rebind_retarget":
        dest, dest_objects = load_clean_bind(paths[plan["src"]])
        if plan.get("clamp"):
            result["clamp"] = clamp_all_arm_weights()
        retarget_idle_walk(dest, dest_objects)
        dest_objects = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"} and o.name != "PreviewGround"]
        scratch = export_dest(paths["orrun_live"], dest, dest_objects)
        install_fixed(scratch, dests)
        dest, dest_objects = load_clean_bind(paths["orrun_live"])
        previews = render_final_previews(dest, f"{kind}_final", copy_names)
        play_clip(dest, "Idle", mid=True)
        post = {
            "deform_idle": [deformed_arm_metrics(m, "Idle") for m in mesh_objects() if m.name != "PreviewGround"],
        }
        play_clip(dest, "Walk", mid=True)
        post["deform_walk"] = [deformed_arm_metrics(m, "Walk") for m in mesh_objects() if m.name != "PreviewGround"]
        info = patch_fourcc_and_opaque(paths["orrun_live"])
        result.update({"fixed": True, "export": info, "previews": {k: str(v) for k, v in previews.items()}, "post": post})
        return result

    if plan["action"] == "assemble_retarget":
        base = paths["base"] if paths["base"].is_file() else paths["cs_base"]
        dest, dest_objects = assemble_dressed(base, paths["piece"])
        if plan.get("clamp"):
            result["clamp"] = clamp_all_arm_weights()
        retarget_idle_walk(dest, dest_objects)
        dest_objects = [o for o in bpy.data.objects if o.type in {"MESH", "ARMATURE"} and o.name != "PreviewGround"]
        scratch = export_dest(paths["orrun_live"], dest, dest_objects)
        install_fixed(scratch, dests)
        dest, dest_objects = load_clean_bind(paths["orrun_live"])
        previews = render_final_previews(dest, f"{kind}_final", copy_names)
        play_clip(dest, "Idle", mid=True)
        post = {
            "deform_idle": [deformed_arm_metrics(m, "Idle") for m in mesh_objects() if m.name != "PreviewGround"],
        }
        play_clip(dest, "Walk", mid=True)
        post["deform_walk"] = [deformed_arm_metrics(m, "Walk") for m in mesh_objects() if m.name != "PreviewGround"]
        info = patch_fourcc_and_opaque(paths["orrun_live"])
        result.update({"fixed": True, "export": info, "previews": {k: str(v) for k, v in previews.items()}, "post": post})
        return result

    raise RuntimeError(f"unknown plan {plan}")


def diagnose_kind(kind: str, *, render: bool) -> tuple[dict, dict]:
    paths = candidate_paths(kind)
    reports = {}
    # Always diagnose live + both baks. Piece/base only if we may assemble.
    for key in ("orrun_live", "ag_bak", "orrun_bak"):
        p = paths[key]
        if p.is_file():
            reports[key] = diagnose_file(p, f"{kind}_{key}", guess_bind=False, render=render)
        else:
            reports[key] = {"tag": f"{kind}_{key}", "path": str(p), "exists": False}
    # If live looks broken and baks are not clean, also look at piece/base rest
    live_v = (reports.get("orrun_live") or {}).get("verdict") or {}
    ag_v = (reports.get("ag_bak") or {}).get("verdict") or {}
    need_assemble = (not live_v.get("clean")) and (not ag_v.get("clean"))
    if need_assemble or not live_v.get("has_clothes"):
        for key in ("piece", "base"):
            p = paths[key]
            if p.is_file():
                reports[key] = diagnose_file(p, f"{kind}_{key}", guess_bind=False, render=False)
    return paths, reports


def post_is_worse(before: dict, after_deform_idle, after_deform_walk) -> bool:
    bv = before.get("verdict") or {}
    after_idle = _chest_frac(after_deform_idle)
    after_walk = _chest_frac(after_deform_walk)
    after_sep = _arms_separated(after_deform_idle) and _arms_separated(after_deform_walk)
    before_idle = bv.get("idle_chest_frac", 1.0)
    before_walk = bv.get("walk_chest_frac", 1.0)
    before_sep = bv.get("idle_separated") and bv.get("walk_separated")
    # Body-mesh gate: refuse folded arms through the chest.
    if after_idle >= 0.20 or after_walk >= 0.20:
        log(f"post-check reject chest idle={after_idle:.3f} walk={after_walk:.3f}")
        return True
    if not after_sep:
        log("post-check reject arms not separated")
        return True
    if after_idle > before_idle + 0.05 or after_walk > before_walk + 0.05:
        return True
    if before_sep and not after_sep:
        return True
    return False


def main() -> int:
    ensure_scratch()
    log(f"blender {bpy.app.version_string}")
    diagnose_only = "--diagnose-only" in sys.argv
    skip_diag = "--skip-diagnose" in sys.argv
    skip_male_if_clean = True

    summary = {
        "blender": bpy.app.version_string,
        "female": {},
        "male": {},
    }

    for kind in ("female", "male"):
        log(f"######## {kind}")
        paths = candidate_paths(kind)
        if skip_diag:
            reports = {
                "orrun_live": {
                    "verdict": {
                        "clean": False,
                        "posed_bad": True,
                        "weights_bad": True,
                        "has_clips": True,
                        "has_clothes": True,
                        "rest_separated": True,
                        "idle_separated": False,
                        "walk_separated": False,
                    }
                }
            }
        else:
            paths, reports = diagnose_kind(kind, render=True)
        plan = pick_bind_source(kind, reports)
        summary[kind]["paths"] = {k: str(v) for k, v in paths.items()}
        summary[kind]["verdicts"] = {k: (r.get("verdict") if isinstance(r, dict) else None) for k, r in reports.items()}
        summary[kind]["plan"] = plan
        (SCRATCH / f"diag_{kind}.json").write_text(
            json.dumps({"plan": plan, "reports": reports}, indent=2, default=str),
            encoding="utf-8",
        )
        log(f"{kind} plan={plan}")
        if diagnose_only:
            continue
        if kind == "male" and skip_male_if_clean and plan.get("action") == "leave":
            log("male live is clean; leaving him")
            summary[kind]["fixed"] = False
            continue
        # Female is always processed if not clean; if plan is leave, skip
        if plan.get("action") == "leave":
            summary[kind]["fixed"] = False
            continue
        try:
            applied = apply_plan(kind, plan, paths)
            summary[kind]["applied"] = {
                k: applied[k] for k in applied if k != "post"
            }
            summary[kind]["post"] = applied.get("post")
            # refuse to ship a worse mesh
            before = reports.get("orrun_live") or {}
            post = applied.get("post") or {}
            if applied.get("fixed") and post_is_worse(before, post.get("deform_idle"), post.get("deform_walk")):
                log(f"{kind} post-check WORSE than live — restoring .skin.bak")
                for dest in (paths["orrun_live"], paths["ag_live"]):
                    skin = Path(str(dest) + ".skin.bak")
                    if skin.is_file():
                        try:
                            if dest.is_file():
                                dest.unlink()
                            shutil.copy2(skin, dest)
                            log(f"restored {dest} from {skin}")
                        except OSError as exc:
                            log(f"WARNING: restore failed for {dest}: {exc}")
                summary[kind]["shipped"] = False
                summary[kind]["reason"] = "post metrics worse; did not ship"
            else:
                summary[kind]["shipped"] = bool(applied.get("fixed"))
        except Exception:
            traceback.print_exc()
            summary[kind]["error"] = traceback.format_exc()
            summary[kind]["shipped"] = False

    out = SCRATCH / "arm_skin_report.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log(f"report {out}")
    # also a short txt
    lines = [f"blender {summary.get('blender')}"]
    for kind in ("female", "male"):
        block = summary[kind]
        lines.append(f"{kind}: plan={block.get('plan')} shipped={block.get('shipped')}")
        if block.get("applied") and block["applied"].get("export"):
            exp = block["applied"]["export"]
            lines.append(f"  dest={exp.get('path')} bytes={exp.get('bytes')} clips={exp.get('clips')} fourcc={exp.get('fourcc')}")
            lines.append(f"  materials={exp.get('materials')}")
    (SCRATCH / "arm_skin_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
