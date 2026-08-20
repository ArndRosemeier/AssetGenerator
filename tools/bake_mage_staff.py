# -*- coding: utf-8 -*-
"""Parent KayKit Skeleton_Staff under Mage handslot.r into one GLB.

Art only. Does not retarget or edit Mage animation clips.
Writes characters/Skeleton_Mage_Staff.glb and leaves Skeleton_Mage.glb
and City copies untouched.
"""
from __future__ import annotations

import json
import struct
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix

AG = Path(r"C:\Projekte\AssetGenerator\assets\monsters\kaykit_skeletons")
CITY = Path(r"C:\Projekte\City\assets\monsters\kaykit_skeletons")
MAGE = AG / "characters" / "Skeleton_Mage.glb"
STAFF = AG / "props" / "Skeleton_Staff.gltf"
DEST = AG / "characters" / "Skeleton_Mage_Staff.glb"

REQUIRED_CLIPS = (
    "Unarmed_Melee_Attack_Punch_A",
    "Spellcast_Shoot",
    "Spellcast_Raise",
    "Walking_A",
    "Idle",
)

GUARD_PATHS = [
    MAGE,
    CITY / "characters" / "Skeleton_Mage.glb",
    CITY / "props" / "Skeleton_Staff.gltf",
    CITY / "props" / "Skeleton_Staff.bin",
    CITY / "props" / "skeleton_texture.png",
]


def log(msg: str) -> None:
    print(f"[mage-staff] {msg}", flush=True)


def snapshot(paths):
    out = {}
    for p in paths:
        if p.is_file():
            st = p.stat()
            out[str(p)] = (st.st_size, int(st.st_mtime_ns))
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


def glb_chunks(path: Path):
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"not a glb: {path}")
    offset = 12
    doc = None
    blob = b""
    while offset + 8 <= length:
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif chunk_type == 0x004E4942:
            blob = chunk
    if doc is None:
        raise ValueError(f"no JSON chunk: {path}")
    return doc, blob


def write_glb(path: Path, doc: dict, blob: bytes) -> None:
    json_bytes = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_pad = (4 - (len(json_bytes) % 4)) % 4
    json_bytes = json_bytes + (b" " * json_pad)
    bin_pad = (4 - (len(blob) % 4)) % 4
    blob_padded = blob + (b"\x00" * bin_pad)
    total = 12 + 8 + len(json_bytes) + 8 + len(blob_padded)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(json_bytes), 0x4E4F534A)
    out += json_bytes
    out += struct.pack("<II", len(blob_padded), 0x004E4942)
    out += blob_padded
    path.write_bytes(bytes(out))


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)
    for img in list(bpy.data.images):
        bpy.data.images.remove(img)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)


def import_gltf(path: Path) -> None:
    bpy.ops.import_scene.gltf(filepath=str(path))


def find_rig():
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not arms:
        raise RuntimeError("no armature after Mage import")
    for o in arms:
        if o.name == "Rig" or "Rig" in o.name:
            return o
    return arms[0]


def find_staff(pre_names: set[str]):
    candidates = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name in pre_names:
            continue
        if "Staff" in obj.name or obj.name.startswith("Cylinder"):
            candidates.append(obj)
    if not candidates:
        for obj in bpy.data.objects:
            if obj.type == "MESH" and obj.name not in pre_names:
                candidates.append(obj)
    if not candidates:
        raise RuntimeError("staff mesh not found after import")
    return candidates[0]


def clean_unskinned(obj) -> None:
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    if obj.vertex_groups:
        obj.vertex_groups.clear()
    obj.parent = None
    obj.parent_type = "OBJECT"
    obj.parent_bone = ""


def parent_staff_identity(staff, rig) -> None:
    bone_name = "handslot.r"
    if bone_name not in rig.data.bones:
        raise RuntimeError(f"bone {bone_name!r} missing on {rig.name}")
    bone = rig.data.bones[bone_name]
    staff.name = "Skeleton_Staff"
    staff.parent = None
    staff.location = (0.0, 0.0, 0.0)
    staff.rotation_mode = "QUATERNION"
    staff.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    staff.rotation_euler = (0.0, 0.0, 0.0)
    staff.scale = (1.0, 1.0, 1.0)
    staff.matrix_parent_inverse = Matrix.Identity(4)
    staff.parent = rig
    staff.parent_type = "BONE"
    staff.parent_bone = bone_name
    staff.matrix_parent_inverse = Matrix.Identity(4)
    # Blender bone-parent space is the bone TAIL. glTF node origin is the bone
    # HEAD. Offset by -length on local Y so exported local TRS is identity
    # (matches City hang-off-handslot with no extra offset).
    staff.location = (0.0, -float(bone.length), 0.0)
    staff.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    staff.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    log(
        f"parented {staff.name} -> {rig.name}/{bone_name} "
        f"blender_loc={tuple(staff.location)} bone_len={bone.length:.6f}"
    )


def export_glb(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_nla_strips=True,
        export_force_sampling=False,
        export_bake_animation=False,
        export_optimize_animation_size=False,
        export_anim_slide_to_zero=False,
        export_apply=False,
        export_skins=True,
        export_rest_position_armature=True,
        export_def_bones=False,
        export_anim_single_armature=True,
        export_current_frame=False,
        export_draco_mesh_compression_enable=False,
        export_extras=False,
        export_cameras=False,
        export_lights=False,
    )


def force_staff_identity(path: Path) -> None:
    """Strip leftover local TRS on Skeleton_Staff so it hangs at handslot.r identity."""
    doc, blob = glb_chunks(path)
    nodes = doc.get("nodes", [])
    staff_i = None
    slot_i = None
    for i, n in enumerate(nodes):
        if n.get("name") == "Skeleton_Staff":
            staff_i = i
        if n.get("name") == "handslot.r":
            slot_i = i
    if staff_i is None or slot_i is None:
        raise RuntimeError("post: missing Skeleton_Staff or handslot.r")
    slot = nodes[slot_i]
    kids = list(slot.get("children") or [])
    if staff_i not in kids:
        kids.append(staff_i)
        slot["children"] = kids
        log("post: added Skeleton_Staff to handslot.r.children")
    staff = nodes[staff_i]
    changed = False
    for key in ("translation", "rotation", "scale", "matrix"):
        if key in staff:
            del staff[key]
            changed = True
    if changed:
        log("post: stripped staff local TRS -> identity")
    write_glb(path, doc, blob)


def verify_dest(path: Path) -> dict:
    doc, _ = glb_chunks(path)
    nodes = doc.get("nodes", [])
    names = {i: n.get("name") for i, n in enumerate(nodes)}
    inv = {n.get("name"): i for i, n in enumerate(nodes)}
    staff_i = inv.get("Skeleton_Staff")
    slot_i = inv.get("handslot.r")
    notes = []
    parent_ok = False
    if staff_i is None:
        notes.append("no Skeleton_Staff node")
    if slot_i is None:
        notes.append("no handslot.r node")
    if staff_i is not None and slot_i is not None:
        kids = nodes[slot_i].get("children") or []
        parent_ok = staff_i in kids
        if not parent_ok:
            notes.append(f"handslot.r.children={kids} missing staff {staff_i}")
        parents = [names[i] for i, n in enumerate(nodes) if staff_i in (n.get("children") or [])]
        notes.append(f"staff parents={parents}")
    unskinned = False
    if staff_i is not None:
        mesh_i = nodes[staff_i].get("mesh")
        if mesh_i is None:
            notes.append("staff node has no mesh")
        else:
            mesh = doc["meshes"][mesh_i]
            attrs = []
            skinned = False
            for prim in mesh.get("primitives", []):
                a = list((prim.get("attributes") or {}).keys())
                attrs.append(a)
                if "JOINTS_0" in a or "WEIGHTS_0" in a or "JOINTS" in a or "WEIGHTS" in a:
                    skinned = True
            unskinned = not skinned
            notes.append(f"staff mesh={mesh.get('name')!r} attrs={attrs}")
            if nodes[staff_i].get("skin") is not None:
                unskinned = False
                notes.append("staff node has skin")
    anims = [a.get("name") for a in doc.get("animations", [])]
    missing = [c for c in REQUIRED_CLIPS if c not in anims]
    if missing:
        notes.append(f"missing clips {missing}")
    staff_trs = None
    if staff_i is not None:
        n = nodes[staff_i]
        staff_trs = {
            "translation": n.get("translation"),
            "rotation": n.get("rotation"),
            "scale": n.get("scale"),
            "matrix": n.get("matrix"),
        }
    return {
        "dest": str(path),
        "parent_ok": parent_ok,
        "unskinned": unskinned,
        "clip_count": len(anims),
        "required_ok": not missing,
        "staff_trs": staff_trs,
        "notes": notes,
        "ok": parent_ok and unskinned and len(anims) >= 95 and not missing,
    }


def verify_original_mage_has_no_staff() -> None:
    doc, _ = glb_chunks(MAGE)
    names = [n.get("name") for n in doc.get("nodes", [])]
    if "Skeleton_Staff" in names:
        raise RuntimeError("original Skeleton_Mage.glb now has Skeleton_Staff")
    log(f"original Mage has no staff ({len(doc.get('animations', []))} clips, {len(names)} nodes)")


def bake() -> dict:
    if not MAGE.is_file():
        raise FileNotFoundError(MAGE)
    if not STAFF.is_file():
        raise FileNotFoundError(STAFF)
    if DEST.resolve() == MAGE.resolve():
        raise RuntimeError("refusing to overwrite Skeleton_Mage.glb")

    reset_scene()
    log(f"import mage {MAGE}")
    import_gltf(MAGE)
    pre = {o.name for o in bpy.data.objects}
    actions_before = sorted(a.name for a in bpy.data.actions)
    log(f"mage objects={len(pre)} actions={len(actions_before)}")

    log(f"import staff {STAFF}")
    import_gltf(STAFF)
    staff = find_staff(pre)
    log(f"staff obj={staff.name!r} mesh={staff.data.name if staff.data else None!r}")
    clean_unskinned(staff)

    rig = find_rig()
    parent_staff_identity(staff, rig)

    keep = set()
    keep.add(rig.name)
    keep.add(staff.name)
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and (obj.parent == rig or obj.name.startswith("Skeleton_Mage")):
            keep.add(obj.name)
    for obj in list(bpy.data.objects):
        if obj.name not in keep and obj.type != "ARMATURE":
            log(f"remove leftover {obj.name!r} type={obj.type}")
            bpy.data.objects.remove(obj, do_unlink=True)

    if DEST.exists():
        DEST.unlink()
    log(f"export {DEST}")
    export_glb(DEST)
    if not DEST.is_file():
        raise RuntimeError("export produced no file")

    force_staff_identity(DEST)
    res = verify_dest(DEST)
    log(
        f"verify parent_ok={res['parent_ok']} unskinned={res['unskinned']} "
        f"clips={res['clip_count']} required_ok={res['required_ok']}"
    )
    for n in res["notes"]:
        log(f"  note: {n}")
    if not res["ok"]:
        raise RuntimeError(f"verify failed: {res}")
    return res


def main() -> int:
    log(f"blender {bpy.app.version_string}")
    guard = snapshot(GUARD_PATHS)
    try:
        res = bake()
        verify_original_mage_has_no_staff()
        for p in GUARD_PATHS:
            if not p.is_file():
                raise RuntimeError(f"guard missing after bake: {p}")
        assert_untouched(guard, "Mage original + City")
        log(f"DONE dest={DEST} size={DEST.stat().st_size}")
        print(
            json.dumps(
                {
                    "dest": str(DEST),
                    "parent": "handslot.r",
                    "parent_ok": res["parent_ok"],
                    "unskinned": res["unskinned"],
                    "clip_count": res["clip_count"],
                    "city_left_alone": True,
                    "original_mage_unchanged": True,
                },
                indent=2,
            ),
            flush=True,
        )
        return 0
    except Exception:
        traceback.print_exc()
        try:
            assert_untouched(guard, "Mage original + City")
        except Exception:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
