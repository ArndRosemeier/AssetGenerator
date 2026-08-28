# -*- coding: utf-8 -*-
"""Ambitious orc restyle on the MakeHuman 53-bone UAL-baked worksuit path.

Art / Asset Lab only. Does not write Orrun or Origin, does not author clips,
does not add bones, does not use Quaternius Orc.glb as a donor.

Donor (read-only, already UAL-baked):
  C:\\Projekte\\AssetGenerator\\assets\\humans\\male_dressed_male_worksuit01.glb

Dest (NEW file only — never overwrite the donor):
  C:\\Projekte\\AssetGenerator\\assets\\humans\\male_orc_01.glb

Scratch (gitignored):
  C:\\Projekte\\AssetGenerator\\tools\\_human_orc_bake\\

Required UAL clip names kept from the worksuit donor (not authored here):
  Idle, Walk, Death (or Death01), Punch

Look-dev (silhouette + material target only — NOT a UV map):
  tools/_human_orc_bake/orc_lookdev_threequarter.png
  Project onto existing dest MH UVs; never bpy.ops.uv.smart_project.
  Placeholder olive albedo is OK until look-dev is painted onto dest UVs.
  Call blender/lib/bake.py only after look-dev lives on those dest UVs.

Run (Arnd, AG blenderctl 4.5 / Blender 4.5):
  <AG blender> --background --factory-startup --python
    C:\\Projekte\\AssetGenerator\\tools\\bake_human_orc.py

Ship the UV template before a full restyle (first flag):
  <AG blender> --background --factory-startup --python
    C:\\Projekte\\AssetGenerator\\tools\\bake_human_orc.py -- --uv-only

--uv-only writes:
  tools/_human_orc_bake/male_orc_01_uv_layout.png
from existing dest UVs via bpy.ops.uv.export_layout (fails loud if no UV).

Restyle rules:
  - MESH only on the existing 53-bone bind (BONE_MAP from bake_human_quaternius).
  - Conservative bulk via vertex displace; jaw on head-weighted verts.
  - Tusks as extra meshes bound to bone ``head`` via bind_mesh.
  - Do NOT scale thigh / calf / pelvis bones. No ogre hunch, no invented gait.
  - Keep worksuit clothes. Drop cleaver/shield if present (look-dev gear only).
  - Log hip_height_z before/after; fail if pelvis rest Z moves more than ~1 cm.
  - Guards snapshot worksuit / male_base / casualsuit / Quaternius Orc.glb.
"""
from __future__ import annotations

import json
import math
import shutil
import struct
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

TOOLS = Path(r"C:\Projekte\AssetGenerator\tools")
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import bake_human_quaternius as HQ  # noqa: E402

AG = Path(r"C:\Projekte\AssetGenerator")
AG_HUMANS = AG / "assets" / "humans"
DONOR = AG_HUMANS / "male_dressed_male_worksuit01.glb"
DEST = AG_HUMANS / "male_orc_01.glb"
SCRATCH = AG / "tools" / "_human_orc_bake"
UV_LAYOUT = SCRATCH / "male_orc_01_uv_layout.png"
LOOKDEV = SCRATCH / "orc_lookdev_threequarter.png"
PREVIEW_DIR = SCRATCH / "previews"

QUATERNIUS_ORC = AG / "assets" / "monsters" / "quaternius" / "big" / "Orc.glb"
FORBIDDEN_ORC_MARKERS = (
    "monsters/quaternius/big/Orc.glb",
    "monsters\\quaternius\\big\\Orc.glb",
    "/Orc.glb",
    "\\Orc.glb",
)

GUARD_PATHS = [
    DONOR,
    AG_HUMANS / "male_base.glb",
    AG_HUMANS / "male_dressed_male_casualsuit01.glb",
    AG_HUMANS / "female_dressed_female_casualsuit01.glb",
    QUATERNIUS_ORC,
]

# Required playback names. Death may appear as Death or Death01 on the donor.
REQUIRED_CLIP_GROUPS = (
    ("Idle", ("Idle", "Idle_Loop")),
    ("Walk", ("Walk", "Walk_Loop")),
    ("Punch", ("Punch",)),
    ("Death", ("Death", "Death01")),
)

PREVIEW_CLIPS = ("Idle", "Walk", "Death", "Punch")
PELVIS_MAX_DELTA_M = 0.011  # ~1 cm
TEX_SIZE = 1024
OLIVE = (0.28, 0.34, 0.18)
OLIVE_DARK = (0.18, 0.24, 0.12)
TUSK = (0.92, 0.88, 0.78)
JSON_FOURCC = 0x4E4F534A
BIN_FOURCC = 0x004E4942

# Never scale these bones (keep MH gait / hip height).
NO_SCALE_BONES = ("pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r")


def log(msg: str) -> None:
    print(f"[human-orc] {msg}", flush=True)


def want_uv_only() -> bool:
    return "--uv-only" in sys.argv


def refuse_quaternius_orc(*paths: Path) -> None:
    for path in paths:
        text = str(path).replace("/", "\\")
        low = text.lower()
        for marker in FORBIDDEN_ORC_MARKERS:
            if marker.lower().replace("/", "\\") in low:
                raise RuntimeError(
                    f"refusing Quaternius Orc path as donor/dest: {path}"
                )
        if path.name.lower() == "orc.glb" and "quaternius" in low:
            raise RuntimeError(f"refusing Quaternius Orc path: {path}")


def ensure_not_protected_dest(path: Path) -> None:
    refuse_quaternius_orc(path)
    resolved = path.resolve()
    protected = {
        DONOR.resolve(),
        (AG_HUMANS / "male_base.glb").resolve(),
        (AG_HUMANS / "male_dressed_male_casualsuit01.glb").resolve(),
        (AG_HUMANS / "female_dressed_female_casualsuit01.glb").resolve(),
        QUATERNIUS_ORC.resolve(),
    }
    if resolved in protected:
        raise RuntimeError(f"refusing to write protected path: {path}")
    if path.name == DONOR.name:
        raise RuntimeError("refusing to overwrite worksuit donor")
    if "worksuit" in path.name.lower() and path.name != DEST.name:
        raise RuntimeError(f"refusing worksuit-like dest name: {path.name}")


def snapshot(paths):
    out = {}
    for p in paths:
        if p.is_file():
            st = p.stat()
            out[str(p)] = (st.st_size, int(st.st_mtime_ns))
        else:
            out[str(p)] = None
    return out


def assert_untouched(before, label: str) -> None:
    after = snapshot([Path(k) for k in before])
    dirty = []
    for k, v in before.items():
        if after.get(k) != v:
            dirty.append((k, v, after.get(k)))
    if dirty:
        raise RuntimeError(f"{label} files changed: {dirty}")
    log(f"{label} untouched ({len(before)} paths)")


def ensure_scratch() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def clear_scene() -> None:
    HQ.clear_scene()


def import_gltf(path: Path) -> None:
    refuse_quaternius_orc(path)
    HQ.import_gltf(path)


def find_armature():
    return HQ.find_armature(has_bone="pelvis")


def hip_height_z(arm) -> float:
    return HQ.hip_height_z(arm, "pelvis")


def copy_donor_to_dest(*, force: bool) -> None:
    refuse_quaternius_orc(DONOR, DEST)
    ensure_not_protected_dest(DEST)
    if not DONOR.is_file():
        raise FileNotFoundError(f"missing UAL-baked worksuit donor: {DONOR}")
    if DEST.resolve() == DONOR.resolve():
        raise RuntimeError("dest must not be the worksuit donor")
    if DEST.is_file() and not force:
        log(f"dest exists, reusing {DEST} ({DEST.stat().st_size} bytes)")
        return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DONOR, DEST)
    log(f"copied donor -> dest {DEST} ({DEST.stat().st_size} bytes)")


def glb_anim_names(path: Path) -> list[str]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError(f"{path} is not a GLB")
    offset = 12
    doc = None
    length = struct.unpack_from("<I", data, 8)[0]
    while offset + 8 <= min(length, len(data)):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == JSON_FOURCC:
            doc = json.loads(chunk)
    if doc is None:
        raise RuntimeError(f"{path}: no JSON chunk")
    return [a.get("name") or "" for a in doc.get("animations", [])]


def resolve_clip(names: set[str], label: str, candidates: tuple[str, ...]) -> str:
    for c in candidates:
        if c in names:
            return c
    raise RuntimeError(
        f"cannot resolve required clip {label!r}; tried {candidates}; have={sorted(names)}"
    )


def assert_required_clips(path: Path) -> dict[str, str]:
    anims = set(glb_anim_names(path))
    resolved = {}
    for label, candidates in REQUIRED_CLIP_GROUPS:
        resolved[label] = resolve_clip(anims, label, candidates)
    log(f"required clips resolved: {resolved} (total anims={len(anims)})")
    return resolved


def mesh_objects():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def skinned_meshes(arm):
    out = []
    for obj in mesh_objects():
        if obj.parent == arm:
            out.append(obj)
            continue
        for mod in obj.modifiers:
            if mod.type == "ARMATURE" and mod.object == arm:
                out.append(obj)
                break
    return out


def drop_cleaver_shield() -> list[str]:
    """Remove look-dev weapons if somehow present; worksuit should have none."""
    removed = []
    keys = ("cleaver", "shield", "axe", "sword", "weapon")
    for obj in list(mesh_objects()):
        low = obj.name.lower()
        if any(k in low for k in keys):
            name = obj.name
            log(f"dropping gear mesh {name!r}")
            bpy.data.objects.remove(obj, do_unlink=True)
            removed.append(name)
    return removed


def vg_index(obj, name: str):
    vg = obj.vertex_groups.get(name)
    return vg.index if vg is not None else None


def vg_weight(vert, group_index) -> float:
    if group_index is None:
        return 0.0
    for g in vert.groups:
        if g.group == group_index:
            return float(g.weight)
    return 0.0


def assert_no_leg_bone_scale(arm) -> None:
    for name in NO_SCALE_BONES:
        if name not in arm.pose.bones:
            raise RuntimeError(f"missing bone {name!r} on 53-bone bind")
        pb = arm.pose.bones[name]
        sx, sy, sz = pb.scale
        if abs(sx - 1.0) > 1e-4 or abs(sy - 1.0) > 1e-4 or abs(sz - 1.0) > 1e-4:
            raise RuntimeError(
                f"refusing non-identity scale on {name}: {(sx, sy, sz)}"
            )
        bone = arm.data.bones[name]
        # Rest bones should not have been length-hacked via head/tail edits here.
        if bone.use_inherit_rotation is False:
            log(f"note: {name} use_inherit_rotation=False")


def restyle_bulk_and_jaw(arm) -> None:
    """Conservative vertex displace on skinned meshes; jaw on head-weighted verts."""
    assert_no_leg_bone_scale(arm)
    for obj in skinned_meshes(arm):
        me = obj.data
        if not me.vertices:
            continue
        head_i = vg_index(obj, "head")
        spine_i = vg_index(obj, "spine_03") or vg_index(obj, "spine_02")
        upper_l = vg_index(obj, "upperarm_l")
        upper_r = vg_index(obj, "upperarm_r")
        lower_l = vg_index(obj, "lowerarm_l")
        lower_r = vg_index(obj, "lowerarm_r")
        hand_l = vg_index(obj, "hand_l")
        hand_r = vg_index(obj, "hand_r")
        torso_groups = [
            vg_index(obj, "spine_01"),
            vg_index(obj, "spine_02"),
            vg_index(obj, "spine_03"),
            vg_index(obj, "pelvis"),
        ]

        # Object-space bbox for radial bulk.
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        z0, z1 = min(zs), max(zs)
        height = max(z1 - z0, 1e-3)

        for v in me.vertices:
            hw = vg_weight(v, head_i)
            tw = max(vg_weight(v, gi) for gi in torso_groups)
            arm_w = max(
                vg_weight(v, upper_l),
                vg_weight(v, upper_r),
                vg_weight(v, lower_l),
                vg_weight(v, lower_r),
                vg_weight(v, hand_l),
                vg_weight(v, hand_r),
            )
            # Radial bulk in XY — conservative, no vertical hunch.
            radial = Vector((v.co.x - cx, v.co.y - cy, 0.0))
            if radial.length < 1e-6:
                radial = Vector((0.0, -1.0, 0.0))
            else:
                radial.normalize()

            bulk = 0.0
            bulk += 0.028 * tw  # torso
            bulk += 0.022 * arm_w  # delts / forearms
            # Mild overall stockiness on clothed body pieces.
            bulk += 0.008 * max(0.0, 1.0 - hw)

            # Jaw: head-weighted verts in the lower-front face region.
            jaw = 0.0
            if hw >= 0.25:
                z_rel = (v.co.z - z0) / height
                # Lower face band; push jaw forward (-Y in MH rest) and slightly out.
                if 0.72 < z_rel < 0.92 and v.co.y < cy + 0.02:
                    jaw = (hw - 0.20) * 0.045
                    v.co.y -= jaw * 0.85
                    v.co.z -= jaw * 0.15
                    # Widen mandible.
                    v.co.x += math.copysign(jaw * 0.55, v.co.x - cx)

            if bulk > 0.0:
                v.co.x += radial.x * bulk
                v.co.y += radial.y * bulk

        me.update()
        log(f"restyled mesh {obj.name!r} verts={len(me.vertices)}")


def bind_mesh(obj, arm, bone_fn) -> None:
    """Bind extra mesh to armature via vertex groups (from tribal veteran)."""
    obj.parent = arm
    obj.parent_type = "OBJECT"
    needed = set()
    weights = []
    for v in obj.data.vertices:
        wmap = bone_fn(v)
        weights.append((v.index, wmap))
        needed.update(wmap)
    for name in needed:
        if name not in arm.data.bones:
            raise RuntimeError(f"bind_mesh: armature missing bone {name!r}")
        if name not in obj.vertex_groups:
            obj.vertex_groups.new(name=name)
    for vi, wmap in weights:
        for bname, w in wmap.items():
            obj.vertex_groups[bname].add([vi], float(w), "REPLACE")
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True


def make_opaque_mat(name: str, color, roughness: float = 0.9):
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
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = "OPAQUE"
        except Exception:
            pass
    return mat


def add_tusks(arm) -> list:
    """Tusks as extra meshes bound to ``head`` (no new bones)."""
    if "head" not in arm.data.bones:
        raise RuntimeError("53-bone bind missing head bone")
    head_rest = HQ.rest_world(arm, "head").to_translation()
    mat = make_opaque_mat("OrcTusk", TUSK, 0.55)
    created = []
    # Approximate mouth corners in front of the head bone.
    specs = [
        ("OrcTusk_L", -0.045, -0.095, -0.060, 12.0),
        ("OrcTusk_R", 0.045, -0.095, -0.060, -12.0),
    ]
    for name, dx, dy, dz, yaw_deg in specs:
        bm = bmesh.new()
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=True,
            segments=10,
            radius1=0.014,
            radius2=0.0035,
            depth=0.055,
        )
        # Point tip upward / slightly forward.
        for v in bm.verts:
            v.co.z += 0.028
            a = math.radians(-35.0)
            cy = v.co.y * math.cos(a) - v.co.z * math.sin(a)
            cz = v.co.y * math.sin(a) + v.co.z * math.cos(a)
            v.co.y = cy
            v.co.z = cz
            ca = math.cos(math.radians(yaw_deg))
            sa = math.sin(math.radians(yaw_deg))
            rx = v.co.x * ca - v.co.y * sa
            ry = v.co.x * sa + v.co.y * ca
            v.co.x = rx + head_rest.x + dx
            v.co.y = ry + head_rest.y + dy
            v.co.z += head_rest.z + dz
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append(mat)
        bind_mesh(obj, arm, lambda _v: {"head": 1.0})
        created.append(obj)
    log(f"tusks: {[o.name for o in created]} bound to head")
    return created


def body_like_meshes(arm):
    """Prefer basemesh / skin meshes for albedo restyle; keep clothes materials."""
    skins = []
    for obj in skinned_meshes(arm):
        low = obj.name.lower()
        if any(k in low for k in ("work", "suit", "shoe", "boot", "hair", "brow", "eye")):
            continue
        if "body" in low or "male" in low or "basemesh" in low or "human" in low:
            skins.append(obj)
    if not skins:
        # Fallback: largest skinned mesh that has UVs + head weights.
        candidates = []
        for obj in skinned_meshes(arm):
            if not obj.data.uv_layers:
                continue
            if vg_index(obj, "head") is None:
                continue
            candidates.append(obj)
        if not candidates:
            raise RuntimeError("no skinned UV body mesh found for orc albedo")
        candidates.sort(key=lambda o: len(o.data.vertices), reverse=True)
        skins = [candidates[0]]
    return skins


def apply_olive_albedo_on_dest_uvs(arm) -> None:
    """Template-then-project placeholder olive onto existing dest UVs.

    Does NOT call uv.smart_project. Does NOT use blender/lib/bake.py yet —
    that helper is only appropriate after look-dev is painted onto dest UVs.
    """
    if LOOKDEV.is_file():
        log(f"look-dev present (silhouette/material target only): {LOOKDEV}")
    else:
        log(f"look-dev not on disk yet (optional): {LOOKDEV}")

    for obj in body_like_meshes(arm):
        me = obj.data
        if not me.uv_layers:
            raise RuntimeError(f"{obj.name!r} has no UV; refusing smart_project")
        uv_layer = me.uv_layers.active or me.uv_layers[0]
        img = bpy.data.images.new(
            f"OrcOlive_{obj.name}", width=TEX_SIZE, height=TEX_SIZE, alpha=True
        )
        img.colorspace_settings.name = "sRGB"
        w = h = TEX_SIZE
        px = [0.0] * (w * h * 4)
        # Soft vertical variation so the placeholder is not a flat fill.
        for y in range(h):
            t = y / max(h - 1, 1)
            r = OLIVE_DARK[0] * (1.0 - t) + OLIVE[0] * t
            g = OLIVE_DARK[1] * (1.0 - t) + OLIVE[1] * t
            b = OLIVE_DARK[2] * (1.0 - t) + OLIVE[2] * t
            for x in range(w):
                i = (y * w + x) * 4
                # Mild leather-ish noise from UV index.
                n = 0.04 * math.sin(x * 0.17) * math.cos(y * 0.13)
                px[i] = max(0.0, min(1.0, r + n))
                px[i + 1] = max(0.0, min(1.0, g + n * 0.8))
                px[i + 2] = max(0.0, min(1.0, b + n * 0.5))
                px[i + 3] = 1.0

        # Stamp coverage from existing UV islands (project onto dest UVs).
        covered = 0
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv = uv_layer.data[li].uv
                x = int(max(0, min(w - 1, uv.x * w)))
                y = int(max(0, min(h - 1, uv.y * h)))
                i = (y * w + x) * 4
                if px[i + 3] > 0.5:
                    covered += 1
        if covered < 16:
            raise RuntimeError(
                f"{obj.name!r} UV stamp covered {covered} texels; UV map looks empty"
            )

        img.pixels = px
        img.update()
        debug = SCRATCH / f"orc_olive_{obj.name}.png"
        img.filepath_raw = str(debug)
        img.file_format = "PNG"
        img.save()
        log(f"wrote olive template {debug} (dest UVs, no smart_project)")

        mat = make_opaque_mat(f"OrcSkin_{obj.name}", OLIVE, 0.92)
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = uv_layer.name
        nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        me.materials.clear()
        me.materials.append(mat)
        log(f"skin material -> olive on existing UV {uv_layer.name!r} for {obj.name!r}")


def export_uv_layout(path: Path) -> None:
    ensure_scratch()
    meshes = [o for o in mesh_objects() if o.data.uv_layers]
    if not meshes:
        raise RuntimeError("no mesh with UV layers; refusing export_layout / smart_project")
    # Prefer body-like; else all UV meshes.
    arm = find_armature()
    try:
        targets = body_like_meshes(arm)
    except RuntimeError:
        targets = meshes
    bpy.ops.object.select_all(action="DESELECT")
    for obj in targets:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if path.exists():
        path.unlink()
    # Blender 4.x uv.export_layout writes the active object's UV layout.
    result = bpy.ops.uv.export_layout(
        filepath=str(path),
        export_all=False,
        modified=False,
        mode="PNG",
        size=(TEX_SIZE, TEX_SIZE),
        opacity=1.0,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    if result != {"FINISHED"} and not path.is_file():
        # Retry exporting all selected islands.
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.export_layout(
            filepath=str(path),
            export_all=True,
            modified=False,
            mode="PNG",
            size=(TEX_SIZE, TEX_SIZE),
            opacity=1.0,
        )
        bpy.ops.object.mode_set(mode="OBJECT")
    if not path.is_file():
        raise RuntimeError(f"uv.export_layout did not write {path}")
    log(f"UV layout {path} ({path.stat().st_size} bytes) from {[o.name for o in targets]}")


def export_glb(path: Path, arm, objects: list) -> None:
    ensure_not_protected_dest(path)
    refuse_quaternius_orc(path)
    if arm.animation_data:
        arm.animation_data.action = None
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch_out = SCRATCH / (path.stem + "_restyle.glb")
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
            export_animations=True,
            export_skins=True,
            export_yup=True,
            export_draco_mesh_compression_enable=False,
        )
    if not scratch_out.is_file():
        alt = Path(str(scratch_out) + ".glb")
        if alt.is_file():
            scratch_out = alt
        else:
            raise RuntimeError(f"export produced no file: {scratch_out}")
    shutil.copy2(scratch_out, path)
    log(f"exported {path} ({path.stat().st_size} bytes)")


def action_frame(name: str, kind: str) -> int:
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing in scene")
    frames = [kp.co.x for fc in act.fcurves for kp in fc.keyframe_points]
    if not frames:
        return 1
    lo, hi = int(min(frames)), int(max(frames))
    if kind == "idle":
        return lo + max(1, (hi - lo) // 4)
    if kind == "walk":
        return lo + max(1, (hi - lo) // 2)
    if kind == "punch":
        return lo + max(1, int((hi - lo) * 0.55))
    if kind == "death":
        return hi
    return lo


def apply_action(arm, name: str, frame: int) -> None:
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing")
    if arm.animation_data is None:
        arm.animation_data_create()
    # Mute NLA so the single action drives the pose.
    for track in arm.animation_data.nla_tracks:
        track.mute = True
    HQ.assign_action(arm, act)
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()


def posed_bbox(meshes):
    deps = bpy.context.evaluated_depsgraph_get()
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    hit = False
    for o in meshes:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(deps)
        mesh = ev.to_mesh()
        try:
            for v in mesh.vertices:
                w = ev.matrix_world @ v.co
                mins.x = min(mins.x, w.x)
                mins.y = min(mins.y, w.y)
                mins.z = min(mins.z, w.z)
                maxs.x = max(maxs.x, w.x)
                maxs.y = max(maxs.y, w.y)
                maxs.z = max(maxs.z, w.z)
                hit = True
        finally:
            ev.to_mesh_clear()
    if not hit:
        return Vector((0, 0, 0.9)), Vector((0.8, 0.8, 1.8))
    return (mins + maxs) * 0.5, (maxs - mins)


def setup_standing_preview(center, extent) -> None:
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    ground_mat = make_opaque_mat("PreviewGround", (0.18, 0.175, 0.165), 1.0)
    bpy.ops.mesh.primitive_plane_add(size=12.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "PreviewGround"
    ground.data.materials.append(ground_mat)

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
    cam.location = Vector(
        (
            center.x + span * 1.35,
            center.y - span * 1.85,
            max(center.z + span * 0.35, 1.55),
        )
    )
    target = Vector((center.x, center.y, max(center.z, 0.9)))
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

    add_light(
        "Key",
        "SUN",
        (3.0, -2.5, 6.0),
        3.4,
        rot=(math.radians(50), math.radians(15), math.radians(35)),
    )
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0, size=1.6)

    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 800
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue


def setup_death_preview(center, extent) -> None:
    """Camera framing from preview_bandit_death / bake_bandit_death."""
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    ground_mat = make_opaque_mat("PreviewGround", (0.18, 0.175, 0.165), 1.0)
    bpy.ops.mesh.primitive_plane_add(size=12.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "PreviewGround"
    ground.data.materials.append(ground_mat)

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
    cam.location = Vector(
        (
            center.x + span * 1.55,
            center.y - span * 2.05,
            max(center.z + span * 1.15, 1.35),
        )
    )
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

    add_light(
        "Key",
        "SUN",
        (3.0, -2.5, 6.0),
        3.4,
        rot=(math.radians(50), math.radians(15), math.radians(35)),
    )
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0, size=1.6)

    scene = bpy.context.scene
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1000
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    log(
        f"death cam={tuple(round(c, 3) for c in cam.location)} "
        f"look={tuple(round(c, 3) for c in target)}"
    )


def render_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"preview not written: {path}")
    log(f"preview {path} ({path.stat().st_size} bytes)")


def clip_kind(label: str) -> str:
    return {
        "Idle": "idle",
        "Walk": "walk",
        "Punch": "punch",
        "Death": "death",
    }[label]


def render_clip_stills(arm, resolved: dict[str, str], tag: str) -> dict[str, str]:
    meshes = mesh_objects()
    out = {}
    for label in PREVIEW_CLIPS:
        clip = resolved[label]
        frame = action_frame(clip, clip_kind(label))
        apply_action(arm, clip, frame)
        center, extent = posed_bbox(meshes)
        if label == "Death":
            setup_death_preview(center, extent)
        else:
            setup_standing_preview(center, extent)
        path = PREVIEW_DIR / f"male_orc_01_{tag}_{label.lower()}.png"
        render_png(path)
        out[label] = str(path)
    return out


def run_uv_only() -> dict:
    ensure_scratch()
    copy_donor_to_dest(force=False)
    assert_required_clips(DEST)
    clear_scene()
    import_gltf(DEST)
    arm = find_armature()
    bone_count = len(arm.data.bones)
    log(f"arm={arm.name!r} bones={bone_count} (expect ~53 mapped MH set)")
    if bone_count < 50:
        raise RuntimeError(f"expected ~53-bone MH bind, got {bone_count}")
    export_uv_layout(UV_LAYOUT)
    return {
        "mode": "uv-only",
        "dest": str(DEST),
        "uv_layout": str(UV_LAYOUT),
        "bones": bone_count,
    }


def run_restyle() -> dict:
    ensure_scratch()
    copy_donor_to_dest(force=True)
    resolved_bytes = assert_required_clips(DEST)

    # Before stills from a fresh donor import (worksuit).
    clear_scene()
    import_gltf(DONOR)
    arm_before = find_armature()
    before_hip = hip_height_z(arm_before)
    log(f"hip_height_z BEFORE (donor rest)={before_hip:.4f}")
    before_previews = render_clip_stills(arm_before, resolved_bytes, "before")

    # Restyle on dest copy.
    clear_scene()
    import_gltf(DEST)
    arm = find_armature()
    dest_objects = list(bpy.data.objects)
    hip_before = hip_height_z(arm)
    log(f"hip_height_z BEFORE (dest rest)={hip_before:.4f}")
    assert_no_leg_bone_scale(arm)

    drop_cleaver_shield()
    restyle_bulk_and_jaw(arm)
    tusks = add_tusks(arm)
    apply_olive_albedo_on_dest_uvs(arm)

    # Explicitly never scale gait bones after edits.
    for name in NO_SCALE_BONES:
        arm.pose.bones[name].scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    assert_no_leg_bone_scale(arm)

    hip_after = hip_height_z(arm)
    log(f"hip_height_z AFTER (dest rest)={hip_after:.4f}")
    delta = abs(hip_after - hip_before)
    if delta > PELVIS_MAX_DELTA_M:
        raise RuntimeError(
            f"pelvis rest Z moved {delta:.4f} m (> {PELVIS_MAX_DELTA_M}); "
            f"before={hip_before:.4f} after={hip_after:.4f}"
        )

    # Scene actions must still resolve Punch / Death after restyle (not authored).
    have = {a.name for a in bpy.data.actions}
    resolved_scene = {}
    for label, candidates in REQUIRED_CLIP_GROUPS:
        resolved_scene[label] = resolve_clip(have, label, candidates)

    export_objects = [o for o in dest_objects if o.name in bpy.data.objects] + tusks
    export_glb(DEST, arm, export_objects)
    resolved_out = assert_required_clips(DEST)

    after_previews = render_clip_stills(arm, resolved_scene, "after")

    return {
        "mode": "restyle",
        "donor": str(DONOR),
        "dest": str(DEST),
        "size": DEST.stat().st_size,
        "clips_resolved": resolved_out,
        "hip_before": hip_before,
        "hip_after": hip_after,
        "hip_delta_m": delta,
        "tusks": [o.name for o in tusks],
        "previews_before": before_previews,
        "previews_after": after_previews,
        "uv_layout_hint": str(UV_LAYOUT),
        "lookdev": str(LOOKDEV),
        "note": (
            "placeholder olive albedo on dest UVs; "
            "use blender/lib/bake.py only after look-dev is on dest UVs"
        ),
    }


def main() -> int:
    log(f"blender {bpy.app.version_string}")
    refuse_quaternius_orc(DONOR, DEST)
    ensure_not_protected_dest(DEST)
    # Import-time sanity: BONE_MAP is the 53-bone MH share map — do not mutate HQ.TARGETS.
    if len(HQ.BONE_MAP) < 50:
        raise RuntimeError(f"HQ.BONE_MAP unexpected size {len(HQ.BONE_MAP)}")
    log(f"reusing HQ.BONE_MAP entries={len(HQ.BONE_MAP)}; HQ.TARGETS left unchanged")

    guard = snapshot(GUARD_PATHS)
    log(f"guard snapshot: { {k: v[0] if v else None for k, v in guard.items()} }")
    try:
        if want_uv_only():
            res = run_uv_only()
        else:
            res = run_restyle()
        assert_untouched(guard, "protected humans/base/casualsuit/Quaternius Orc")
        print(json.dumps(res, indent=2), flush=True)
        log(f"DONE mode={res.get('mode')} dest={DEST}")
        return 0
    except Exception:
        traceback.print_exc()
        try:
            assert_untouched(guard, "protected humans/base/casualsuit/Quaternius Orc")
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
