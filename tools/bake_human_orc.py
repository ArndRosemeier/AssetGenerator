# -*- coding: utf-8 -*-
"""Ambitious orc restyle on the MakeHuman 53-bone UAL-baked path.

Art / Asset Lab only. Does not write Orrun or Origin, does not author clips,
does not add bones, does not use Quaternius Orc.glb as a donor.

Art Reviewer HOLD fix: dest must NOT read as a painted human in overalls.
  - Delete worksuit tee/dungarees (and other garment meshes) on dest.
  - Swap holey dressed body for nude male_base meshes (same 53-bone weights).
  - Finished olive-grey skin on existing MH body UVs (no UV-grid / checker /
    island-wire diagnostic albedo).
  - Look-dev harness + loincloth as extra meshes (tribal bind_mesh pattern):
    chest straps, left spaulder, belt, ragged loincloth. No cleaver/shield.
  - Tusks stay on head. No thigh/calf/pelvis scale. No ogre hunch.
  - Reshoot AFTER stills only: Idle, Walk, Death01, Punch_Cross.
  - Punch/Death AFTER must pose the same dest armature/meshes as Idle/Walk
    (olive + tusks + harness). Leftover donor/extra armatures are removed/hidden.
  - Death still frame = final Death01 hold (on back, same as donor Death still).
  - Punch still frame = same mid-late formula as the donor Punch still.

Exact local invoke (Arnd, AG blenderctl 4.5 / Blender 4.5):

  Full restyle + Art Reviewer AFTER stills + clip list::

    <AG blender> --background --factory-startup --python ^
      C:\\Projekte\\AssetGenerator\\tools\\bake_human_orc.py

  UV template only (no Punch/Death gate; CPU raster, not uv.export_layout)::

    <AG blender> --background --factory-startup --python ^
      C:\\Projekte\\AssetGenerator\\tools\\bake_human_orc.py -- --uv-only

Paths (donor / dest — never overwrite donors):

  Animation donor (read-only, ~45 UAL clips):
    C:\\Projekte\\OrrunWithEngine\\orrun\\assets\\humans\\male_dressed_male_worksuit01.glb
  AG worksuit (read-only, often Idle/Walk only — never the UAL donor):
    C:\\Projekte\\AssetGenerator\\assets\\humans\\male_dressed_male_worksuit01.glb
  Nude body swap (read-only; full MH body, no clothes delete-mask):
    C:\\Projekte\\AssetGenerator\\assets\\humans\\male_base.glb
  Dest (NEW file only under AG humans):
    C:\\Projekte\\AssetGenerator\\assets\\humans\\male_orc_01.glb
  Scratch (gitignored):
    C:\\Projekte\\AssetGenerator\\tools\\_human_orc_bake\\
  Optional look-dev reference (silhouette / color target, not a UV map):
    C:\\Projekte\\AssetGenerator\\tools\\_human_orc_bake\\orc_lookdev_threequarter.png

Clip aliases (resolve existing names only — never invent Punch or Death):

  Idle  -> Idle, Idle_Loop
  Walk  -> Walk, Walk_Loop
  Death -> Death01 (preferred), Death
  Punch -> Punch_Cross (preferred), Punch_Jab, Punch_Enter
           (Orrun has no clip literally named Punch)

Full restyle path:
  1. Seed dest from Orrun worksuit copy (UAL clips), OR if Orrun is missing
     seed AG worksuit mesh then bake_human_quaternius.bake_one(dest) —
     never invent clips.
  2. Strip worksuit garments; attach nude male_base body on the same armature.
  3. Mesh-only restyle (bulk/jaw) + tusks + look-dev harness/loincloth.
  4. Finished olive-grey skin on MH UVs (Principled; no diagnostic grid).
  5. Re-export skinned dest with every donor action preserved (fake_user + NLA).
  6. Write Art Reviewer packet under tools/_human_orc_bake/previews/:
       male_orc_01_after_{idle,walk,death,punch}.png
       CLIP_LIST.md          (actual names + resolved aliases)
       art_review_packet.json

--uv-only writes tools/_human_orc_bake/male_base_uv_layout.png from existing
male_base UV islands (CPU PNG; bpy.ops.uv.export_layout needs GPU and fails
under --background). Does NOT call assert_required_clips.

Restyle rules:
  - MESH only on the existing 53-bone bind (BONE_MAP from bake_human_quaternius).
  - Conservative bulk via vertex displace; jaw on head-weighted verts.
  - Tusks + harness/loincloth bound via bind_mesh; no new bones.
  - Do NOT scale thigh / calf / pelvis bones. No ogre hunch, no invented gait.
  - Do NOT keep worksuit clothes. Drop cleaver/shield if present.
  - Log hip_height_z before/after; fail if pelvis rest Z moves more than ~1 cm.
  - After export, every donor clip name must still exist on dest (loud fail).
  - Guards snapshot AG worksuit / Orrun worksuit / male_base / casualsuit /
    Quaternius Orc.glb.
"""
from __future__ import annotations

import json
import math
import shutil
import struct
import sys
import traceback
import zlib
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
ORRUN_HUMANS = Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans")

# AG 4-clip Idle/Walk copy — guarded, never used as the full UAL animation donor.
AG_WORKSUIT = AG_HUMANS / "male_dressed_male_worksuit01.glb"
# Orrun full UAL worksuit (~45 clips) — animation + mesh seed for dest. Read-only.
ANIM_DONOR = ORRUN_HUMANS / "male_dressed_male_worksuit01.glb"
# Clean full-body MH UVs for --uv-only (may have zero clips).
MALE_BASE = AG_HUMANS / "male_base.glb"

DEST = AG_HUMANS / "male_orc_01.glb"
SCRATCH = AG / "tools" / "_human_orc_bake"
UV_LAYOUT = SCRATCH / "male_base_uv_layout.png"
LOOKDEV = SCRATCH / "orc_lookdev_threequarter.png"
PREVIEW_DIR = SCRATCH / "previews"
ART_REVIEW_PACKET = PREVIEW_DIR / "art_review_packet.json"
CLIP_LIST_MD = PREVIEW_DIR / "CLIP_LIST.md"

QUATERNIUS_ORC = AG / "assets" / "monsters" / "quaternius" / "big" / "Orc.glb"
FORBIDDEN_ORC_MARKERS = (
    "monsters/quaternius/big/Orc.glb",
    "monsters\\quaternius\\big\\Orc.glb",
    "/Orc.glb",
    "\\Orc.glb",
)

GUARD_PATHS = [
    AG_WORKSUIT,
    ANIM_DONOR,
    MALE_BASE,
    AG_HUMANS / "male_dressed_male_casualsuit01.glb",
    AG_HUMANS / "female_dressed_female_casualsuit01.glb",
    QUATERNIUS_ORC,
]

# Required playback names from Orrun UAL worksuit (~45 clips).
# There is no clip literally named "Punch" or inventable "Death" —
# resolve Death01 / Punch_Cross (etc.) only. Never invent actions.
REQUIRED_CLIP_GROUPS = (
    ("Idle", ("Idle", "Idle_Loop")),
    ("Walk", ("Walk", "Walk_Loop")),
    ("Punch", ("Punch_Cross", "Punch_Jab", "Punch_Enter")),
    ("Death", ("Death01", "Death")),
)

PREVIEW_CLIPS = ("Idle", "Walk", "Death", "Punch")
PELVIS_MAX_DELTA_M = 0.011  # ~1 cm
TEX_SIZE = 1024
# Finished olive-grey skin (look-dev target). Not a UV-grid / checker.
OLIVE = (0.34, 0.38, 0.28)
OLIVE_SHADOW = (0.22, 0.26, 0.18)
OLIVE_WARM = (0.40, 0.36, 0.26)
TUSK = (0.92, 0.88, 0.78)
LEATHER = (0.16, 0.10, 0.07)
LEATHER_DARK = (0.10, 0.07, 0.05)
LEATHER_RED = (0.28, 0.14, 0.09)
RAG_TAN = (0.42, 0.32, 0.22)
METAL = (0.55, 0.50, 0.42)
JSON_FOURCC = 0x4E4F534A
BIN_FOURCC = 0x004E4942

# Never scale these bones (keep MH gait / hip height).
NO_SCALE_BONES = ("pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r")

# Garment / worksuit mesh name markers (tee, dungarees, shoes, …).
GARMENT_NAME_KEYS = (
    "work",
    "suit",
    "shoe",
    "boot",
    "cloth",
    "garment",
    "pants",
    "shirt",
    "tee",
    "tshirt",
    "dungaree",
    "overall",
    "jean",
    "sock",
    "glove",
)
WEAPON_NAME_KEYS = ("cleaver", "shield", "axe", "sword", "weapon")


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
    protected = {p.resolve() for p in GUARD_PATHS}
    if resolved in protected:
        raise RuntimeError(f"refusing to write protected path: {path}")
    if path.name == AG_WORKSUIT.name or path.name == ANIM_DONOR.name:
        if resolved != DEST.resolve():
            raise RuntimeError(f"refusing to overwrite worksuit donor: {path}")
    if path.name == MALE_BASE.name:
        raise RuntimeError("refusing to overwrite male_base.glb")
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


def seed_dest_from_anim_donor(*, force: bool) -> str:
    """Copy Orrun full-UAL worksuit onto AG dest. Never writes Orrun or AG worksuit.

    Returns seed mode: ``orrun_copy`` or ``bake_one``.
    """
    refuse_quaternius_orc(ANIM_DONOR, DEST, AG_WORKSUIT)
    ensure_not_protected_dest(DEST)
    if DEST.resolve() == ANIM_DONOR.resolve():
        raise RuntimeError("dest must not be the Orrun worksuit")
    if DEST.resolve() == AG_WORKSUIT.resolve():
        raise RuntimeError("dest must not be the AG worksuit")
    if DEST.is_file() and not force:
        log(f"dest exists, reusing {DEST} ({DEST.stat().st_size} bytes)")
        return "reuse"

    DEST.parent.mkdir(parents=True, exist_ok=True)

    if ANIM_DONOR.is_file():
        shutil.copy2(ANIM_DONOR, DEST)
        log(
            f"copied anim donor (Orrun worksuit) -> dest {DEST} "
            f"({DEST.stat().st_size} bytes)"
        )
        return "orrun_copy"

    # Fallback: seed mesh from AG worksuit, then UAL-bake onto dest only.
    if not AG_WORKSUIT.is_file():
        raise FileNotFoundError(
            f"missing Orrun UAL worksuit animation donor: {ANIM_DONOR} "
            f"and missing AG worksuit mesh seed: {AG_WORKSUIT}. "
            f"Cannot seed {DEST.name}; bake_human_orc.py does not author clips."
        )
    log(
        f"Orrun donor missing ({ANIM_DONOR}); seeding mesh from AG worksuit "
        f"then bake_human_quaternius.bake_one({DEST.name})"
    )
    shutil.copy2(AG_WORKSUIT, DEST)
    # bake_one writes only dest_path (and its .bak). Never pass Orrun/Quaternius Orc.
    refuse_quaternius_orc(DEST)
    ensure_not_protected_dest(DEST)
    HQ.bake_one(DEST)
    log(f"bake_one complete -> {DEST} ({DEST.stat().st_size} bytes)")
    return "bake_one"


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


def missing_clip_labels(names: set[str]) -> list[str]:
    missing = []
    for label, candidates in REQUIRED_CLIP_GROUPS:
        if not any(c in names for c in candidates):
            missing.append(label)
    return missing


def _punch_death_hint(have: list[str] | set[str]) -> str:
    return (
        f"have={sorted(have)}. "
        f"Use Orrun animation donor {ANIM_DONOR} (copy onto dest), or run "
        f"tools/bake_human_quaternius.py / bake_one({DEST.name}) first — "
        f"bake_human_orc.py does not author Punch/Death. "
        f"Do not use AG {AG_WORKSUIT.name} alone when it only has Idle/Walk."
    )


def assert_required_clips(path: Path) -> dict[str, str]:
    """Full restyle gate only. Never invent clips."""
    anims = set(glb_anim_names(path))
    missing = missing_clip_labels(anims)
    combat = [m for m in missing if m in ("Punch", "Death")]
    if combat:
        raise RuntimeError(
            f"missing required clip(s) {combat} on {path.name}; {_punch_death_hint(anims)}"
        )
    if missing:
        raise RuntimeError(
            f"missing required clip(s) {missing} on {path.name}; have={sorted(anims)}. "
            f"Do not invent clips; fix the donor bake."
        )
    resolved = {}
    for label, candidates in REQUIRED_CLIP_GROUPS:
        resolved[label] = resolve_clip(anims, label, candidates)
    log(f"required clips resolved: {resolved} (total anims={len(anims)})")
    return resolved


def log_clip_list(path: Path) -> list[str]:
    anims = glb_anim_names(path)
    log(f"clips on {path.name} ({len(anims)}): {anims}")
    return anims


def assert_donor_clips_preserved(donor_clips: list[str], dest_path: Path) -> list[str]:
    """Every donor animation name must survive on dest. Never invent replacements."""
    dest_clips = glb_anim_names(dest_path)
    dest_set = set(dest_clips)
    missing = [n for n in donor_clips if n and n not in dest_set]
    if missing:
        raise RuntimeError(
            f"dest {dest_path.name} lost {len(missing)} donor clip(s) after restyle "
            f"export: {missing}. Donor had {len(donor_clips)}, dest has {len(dest_clips)}. "
            f"Refusing to ship a skinned mesh that dropped UAL actions."
        )
    log(
        f"donor clips preserved on dest: {len(donor_clips)}/{len(donor_clips)} "
        f"(dest total={len(dest_clips)})"
    )
    return dest_clips


def preserve_all_actions_for_export(arm) -> list[str]:
    """Keep every imported UAL action alive for glTF ACTIONS+NLA export."""
    actions = [a for a in bpy.data.actions if a is not None]
    if not actions:
        raise RuntimeError(
            "no bpy.data.actions after dest import; cannot export skinned UAL clips"
        )
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = None
    for track in list(arm.animation_data.nla_tracks):
        arm.animation_data.nla_tracks.remove(track)
    names: list[str] = []
    for act in actions:
        act.use_fake_user = True
        HQ.push_nla(arm, act, act.name)
        names.append(act.name)
    # Clear active action so export reads NLA strips / ACTIONS cleanly.
    arm.animation_data.action = None
    log(f"preserved {len(names)} actions on NLA for export: {sorted(names)}")
    return sorted(names)


def still_path(tag: str, label: str) -> Path:
    return PREVIEW_DIR / f"male_orc_01_{tag}_{label.lower()}.png"


def write_art_review_packet(
    *,
    seed_mode: str,
    donor_clips: list[str],
    dest_clips: list[str],
    resolved: dict[str, str],
    after_previews: dict[str, str],
    hip_before: float,
    hip_after: float,
    tusks: list[str],
    gear: list[str],
    removed_garments: list[str],
    before_previews: dict[str, str] | None = None,
) -> dict:
    """Art Reviewer packet: AFTER stills + actual clip names (never invented)."""
    ensure_scratch()
    alias_rows = []
    for label, candidates in REQUIRED_CLIP_GROUPS:
        alias_rows.append(
            {
                "label": label,
                "resolved": resolved[label],
                "candidates": list(candidates),
            }
        )

    for label in PREVIEW_CLIPS:
        p = Path(after_previews[label])
        if not p.is_file():
            raise RuntimeError(f"Art Reviewer AFTER still missing ({label}): {p}")

    stills = {
        "after": {k: after_previews[k] for k in PREVIEW_CLIPS},
        "expected_filenames": {
            "after": [still_path("after", lab).name for lab in PREVIEW_CLIPS],
        },
        "note": (
            "AFTER stills only (HOLD reshoot). Poses: Idle, Walk, Death01, Punch_Cross "
            "via resolved aliases — never invent clips."
        ),
    }
    if before_previews:
        stills["before"] = {k: before_previews[k] for k in PREVIEW_CLIPS}

    packet = {
        "title": "male_orc_01 Art Reviewer packet (skinned mesh, HOLD fix)",
        "dest": str(DEST),
        "anim_donor": str(ANIM_DONOR),
        "ag_worksuit_guarded": str(AG_WORKSUIT),
        "male_base_body": str(MALE_BASE),
        "seed_mode": seed_mode,
        "clip_count_donor": len(donor_clips),
        "clip_count_dest": len(dest_clips),
        "clips_donor": donor_clips,
        "clips_dest": dest_clips,
        "aliases_resolved": resolved,
        "alias_rows": alias_rows,
        "stills": stills,
        "hip_before": hip_before,
        "hip_after": hip_after,
        "hip_delta_m": abs(hip_after - hip_before),
        "tusks": tusks,
        "gear": gear,
        "removed_garments": removed_garments,
        "notes": [
            "HOLD: no worksuit tee/dungarees; nude male_base body + look-dev harness.",
            "Finished olive-grey Principled skin on MH UVs (no UV-grid / checker).",
            "Punch resolves to Punch_Cross (preferred); there is no clip named Punch.",
            "Death resolves to Death01 (preferred); do not invent Death.",
            "AFTER stills isolate dest armature only (tusks+gear required); no leftover donor.",
            "Death still uses final on-back frame of Death01 (same as donor Death still).",
            "Punch still uses same mid-late frame formula as donor Punch still on dest arm.",
        ],
    }
    ART_REVIEW_PACKET.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# male_orc_01 Art Reviewer — clip list (HOLD fix)",
        "",
        f"- Dest: `{DEST}`",
        f"- Animation donor: `{ANIM_DONOR}`",
        f"- Body: nude `{MALE_BASE.name}` (worksuit garments removed)",
        f"- Seed mode: `{seed_mode}`",
        f"- Donor clips: **{len(donor_clips)}**",
        f"- Dest clips after restyle: **{len(dest_clips)}**",
        "",
        "## Resolved playback aliases",
        "",
        "| Label | Resolved (actual name) | Candidates |",
        "| --- | --- | --- |",
    ]
    for row in alias_rows:
        lines.append(
            f"| {row['label']} | `{row['resolved']}` | "
            f"{', '.join(f'`{c}`' for c in row['candidates'])} |"
        )
    lines.extend(
        [
            "",
            "## Full dest clip list (actual names)",
            "",
        ]
    )
    for name in dest_clips:
        lines.append(f"- `{name}`")
    lines.extend(
        [
            "",
            "## AFTER stills (HOLD reshoot)",
            "",
            "Under `tools/_human_orc_bake/previews/`",
            "",
        ]
    )
    for label in PREVIEW_CLIPS:
        actual = resolved[label]
        lines.append(
            f"- **{label}** (`{actual}`): `{still_path('after', label).name}`"
        )
    lines.append("")
    CLIP_LIST_MD.write_text("\n".join(lines), encoding="utf-8")
    log(f"Art Reviewer packet: {ART_REVIEW_PACKET}")
    log(f"clip list doc: {CLIP_LIST_MD}")
    return packet


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


def drop_weapons() -> list[str]:
    """Remove look-dev weapons if somehow present (no cleaver/shield)."""
    removed = []
    for obj in list(mesh_objects()):
        low = obj.name.lower()
        if any(k in low for k in WEAPON_NAME_KEYS):
            name = obj.name
            log(f"dropping weapon mesh {name!r}")
            bpy.data.objects.remove(obj, do_unlink=True)
            removed.append(name)
    return removed


def is_garment_mesh_name(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in GARMENT_NAME_KEYS)


def drop_worksuit_garments() -> list[str]:
    """Delete tee/dungarees/shoes and other worksuit garment meshes. Reviewer: no worksuit."""
    removed = []
    for obj in list(mesh_objects()):
        if is_garment_mesh_name(obj.name):
            name = obj.name
            log(f"dropping worksuit garment {name!r}")
            bpy.data.objects.remove(obj, do_unlink=True)
            removed.append(name)
    if not removed:
        log(
            "no garment-named meshes found; dressed body may still be delete-masked — "
            "male_base body swap is required"
        )
    else:
        log(f"removed {len(removed)} worksuit garment mesh(es): {removed}")
    return removed


def strip_dressed_meshes_attach_male_base(arm) -> tuple[list, list[str]]:
    """Replace holey dressed body with nude male_base meshes on the same armature.

    Dressed worksuit GLBs stamp clothes delete-masks into the body. After dropping
    tee/dungarees the remaining body has holes — swap in male_base (full MH body,
    same 53-bone weight names). Keeps dest armature + Orrun UAL actions.
    """
    if not MALE_BASE.is_file():
        raise FileNotFoundError(
            f"missing nude body {MALE_BASE}; required after stripping worksuit clothes "
            f"(dressed body is delete-masked under garments)"
        )
    refuse_quaternius_orc(MALE_BASE)

    removed = drop_worksuit_garments()
    # Also remove remaining dest meshes (holey body / old eyes) — male_base replaces them.
    for obj in list(mesh_objects()):
        name = obj.name
        log(f"dropping dest mesh before male_base attach: {name!r}")
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(name)

    before_objs = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    import_gltf(MALE_BASE)
    new_objs = [o for o in bpy.data.objects if o not in before_objs]
    base_arm = None
    base_meshes = []
    for o in new_objs:
        if o.type == "ARMATURE" and "pelvis" in getattr(o.data, "bones", {}):
            base_arm = o
        elif o.type == "MESH":
            base_meshes.append(o)
    if base_arm is None:
        raise RuntimeError("male_base import missing pelvis armature")
    if not base_meshes:
        raise RuntimeError("male_base import produced no meshes")

    attached = []
    for obj in base_meshes:
        obj.parent = arm
        obj.parent_type = "OBJECT"
        for mod in list(obj.modifiers):
            if mod.type == "ARMATURE":
                mod.object = arm
                mod.use_vertex_groups = True
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("Armature", "ARMATURE")
            mod.object = arm
            mod.use_vertex_groups = True
        # Fail loud if weights do not reference MH bones on dest.
        missing_bones = [
            vg.name
            for vg in obj.vertex_groups
            if vg.name not in arm.data.bones and vg.name.lower() not in ("root",)
        ]
        # Root may exist as bone "root" on MH — tolerate unknown empty groups lightly.
        hard_missing = [n for n in missing_bones if n in ("pelvis", "head", "spine_01")]
        if hard_missing:
            raise RuntimeError(
                f"male_base mesh {obj.name!r} missing dest bones {hard_missing}"
            )
        attached.append(obj)
        log(f"attached male_base mesh {obj.name!r} -> {arm.name!r}")

    # Drop every imported male_base armature (dest keeps Orrun clips).
    leftover_arms = [
        o
        for o in list(bpy.data.objects)
        if o.type == "ARMATURE" and o != arm
    ]
    for extra in leftover_arms:
        log(f"removing leftover armature after male_base attach: {extra.name!r}")
        bpy.data.objects.remove(extra, do_unlink=True)
    # Drop any actions that arrived with male_base (usually none / empty).
    for act in list(bpy.data.actions):
        if act not in before_actions:
            log(f"removing male_base-imported action {act.name!r}")
            bpy.data.actions.remove(act)

    if not attached:
        raise RuntimeError("male_base attach produced no skinned meshes")
    extras = [o.name for o in bpy.data.objects if o.type == "ARMATURE" and o != arm]
    if extras:
        raise RuntimeError(f"extra armatures remain after male_base attach: {extras}")
    log(f"male_base body attached ({len(attached)}); removed_dest_meshes={len(removed)}")
    return attached, removed


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
            bulk += 0.038 * tw  # torso — nude creature read
            bulk += 0.030 * arm_w  # delts / forearms
            # Mild overall stockiness; skip pure head shell.
            bulk += 0.012 * max(0.0, 1.0 - hw)

            # Jaw: head-weighted verts in the lower-front face region.
            jaw = 0.0
            if hw >= 0.25:
                z_rel = (v.co.z - z0) / height
                # Lower face band; push jaw forward (-Y in MH rest) and slightly out.
                if 0.72 < z_rel < 0.92 and v.co.y < cy + 0.02:
                    jaw = (hw - 0.20) * 0.055
                    v.co.y -= jaw * 0.85
                    v.co.z -= jaw * 0.15
                    # Widen mandible.
                    v.co.x += math.copysign(jaw * 0.65, v.co.x - cx)

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
    """Skin / basemesh targets for finished olive albedo (no garments)."""
    skins = []
    for obj in skinned_meshes(arm):
        low = obj.name.lower()
        if is_garment_mesh_name(obj.name):
            continue
        if any(k in low for k in ("hair", "brow", "eye", "tusk", "orcgear", "strap", "belt", "loin", "spaulder", "wrap")):
            continue
        if "body" in low or "male" in low or "basemesh" in low or "human" in low:
            skins.append(obj)
    if not skins:
        candidates = []
        for obj in skinned_meshes(arm):
            if not obj.data.uv_layers:
                continue
            if vg_index(obj, "head") is None:
                continue
            low = obj.name.lower()
            if any(k in low for k in ("tusk", "orcgear", "strap", "belt", "loin", "spaulder")):
                continue
            candidates.append(obj)
        if not candidates:
            raise RuntimeError("no skinned UV body mesh found for orc albedo")
        candidates.sort(key=lambda o: len(o.data.vertices), reverse=True)
        skins = [candidates[0]]
    return skins


def apply_finished_olive_skin(arm) -> None:
    """Finished olive-grey skin on existing MH body UVs. No UV-grid / checker / wire.

    Uses Principled Base Color (solid finished look). Optional LOOKDEV file is
    logged as a silhouette/color reference only — never applied as a UV layout.
    Does NOT call uv.smart_project. Does NOT draw island outlines into albedo.
    """
    if LOOKDEV.is_file():
        log(f"look-dev reference present (not a UV map): {LOOKDEV}")
    else:
        log(f"look-dev reference optional/missing: {LOOKDEV}")

    for obj in body_like_meshes(arm):
        me = obj.data
        if not me.uv_layers:
            raise RuntimeError(f"{obj.name!r} has no UV; refusing smart_project")
        # Solid finished olive-grey — reads as skin, not diagnostic layout.
        mat = make_opaque_mat(f"OrcSkin_{obj.name}", OLIVE, 0.88)
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        # Mild procedural mottling in object space (not UV-island wire).
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 12.0
        noise.inputs["Detail"].default_value = 6.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[0].color = (*OLIVE_SHADOW, 1.0)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = (*OLIVE_WARM, 1.0)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if "Subsurface Weight" in bsdf.inputs:
            bsdf.inputs["Subsurface Weight"].default_value = 0.05
        elif "Subsurface" in bsdf.inputs:
            try:
                bsdf.inputs["Subsurface"].default_value = 0.04
            except Exception:
                pass
        me.materials.clear()
        me.materials.append(mat)
        log(
            f"finished olive-grey skin on {obj.name!r} "
            f"(Principled+noise, no UV-grid, uv={me.uv_layers.active.name!r})"
        )


def mesh_from_bmesh(name: str, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def append_transformed(dst_bm, src_bm) -> None:
    vert_map = {}
    for v in src_bm.verts:
        vert_map[v] = dst_bm.verts.new(v.co)
    dst_bm.verts.ensure_lookup_table()
    for f in src_bm.faces:
        try:
            dst_bm.faces.new([vert_map[v] for v in f.verts])
        except ValueError:
            pass


def _bone_t(arm, name: str) -> Vector:
    if name not in arm.data.bones:
        raise RuntimeError(f"53-bone bind missing {name!r} for look-dev gear")
    return HQ.rest_world(arm, name).to_translation()


def add_lookdev_gear(arm) -> list:
    """Look-dev harness + loincloth as extra meshes (tribal add_gear / bind_mesh).

    Shoulder spaulder (L), chest X-straps, wide belt, ragged loincloth.
    Optional arm/ankle wraps. No cleaver/shield. No new bones.
    """
    created = []
    leather = make_opaque_mat("OrcLeather", LEATHER, 0.92)
    leather_dark = make_opaque_mat("OrcLeatherDark", LEATHER_DARK, 0.95)
    metal = make_opaque_mat("OrcMetal", METAL, 0.45)

    chest = _bone_t(arm, "spine_03")
    mid = _bone_t(arm, "spine_02")
    pelvis = _bone_t(arm, "pelvis")
    sh_l = _bone_t(arm, "upperarm_l")
    sh_r = _bone_t(arm, "upperarm_r")
    low_l = _bone_t(arm, "lowerarm_l")
    low_r = _bone_t(arm, "lowerarm_r")
    calf_l = _bone_t(arm, "calf_l")
    calf_r = _bone_t(arm, "calf_r")

    # --- Chest X-straps (two diagonal bands) ---
    bm = bmesh.new()
    strap_specs = [
        # (x0,y0,z0) -> (x1,y1,z1), half-width
        (sh_r.x * 0.55, -0.08, chest.z + 0.02, pelvis.x - 0.08, -0.10, pelvis.z + 0.06, 0.018),
        (sh_l.x * 0.55, -0.08, chest.z + 0.02, pelvis.x + 0.08, -0.10, pelvis.z + 0.06, 0.018),
    ]
    for x0, y0, z0, x1, y1, z1, hw in strap_specs:
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        direction = Vector((x1 - x0, y1 - y0, z1 - z0))
        length = max(direction.length, 1e-3)
        midp = Vector((0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)))
        for v in tmp.verts:
            v.co.x *= hw * 2.0
            v.co.y *= 0.012
            v.co.z *= length
        # Orient cube local Z along strap direction.
        z_axis = direction.normalized()
        x_axis = z_axis.cross(Vector((0.0, 1.0, 0.0)))
        if x_axis.length < 1e-4:
            x_axis = z_axis.cross(Vector((1.0, 0.0, 0.0)))
        x_axis.normalize()
        y_axis = z_axis.cross(x_axis).normalized()
        for v in tmp.verts:
            local = Vector(v.co)
            v.co = midp + x_axis * local.x + y_axis * local.y + z_axis * local.z
        append_transformed(bm, tmp)
        tmp.free()
    straps = mesh_from_bmesh("OrcGear_ChestStraps", bm, leather)
    def strap_w(v):
        t = max(0.0, min(1.0, (v.co.z - pelvis.z) / max(chest.z - pelvis.z, 1e-3)))
        return {"spine_03": 0.15 + 0.55 * t, "spine_02": 0.45, "spine_01": 0.40 - 0.25 * t}
    bind_mesh(straps, arm, strap_w)
    created.append(straps)

    # Strap rivets (small metal discs on the X crossing)
    bm = bmesh.new()
    for dx in (-0.03, 0.03, 0.0):
        tmp = bmesh.new()
        bmesh.ops.create_uvsphere(tmp, u_segments=8, v_segments=6, radius=0.012)
        for v in tmp.verts:
            v.co.x += mid.x + dx
            v.co.y += -0.11
            v.co.z += mid.z + 0.02
        append_transformed(bm, tmp)
        tmp.free()
    rivets = mesh_from_bmesh("OrcGear_StrapRivets", bm, metal)
    bind_mesh(rivets, arm, lambda _v: {"spine_02": 1.0})
    created.append(rivets)

    # --- Left spaulder (two overlapping plates on upperarm_l) ---
    bm = bmesh.new()
    for i, (sx, sy, sz, ox, oy, oz) in enumerate(
        (
            (0.11, 0.08, 0.06, 0.02, -0.02, 0.02),
            (0.09, 0.07, 0.05, 0.05, -0.01, -0.02),
        )
    ):
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            v.co.x = v.co.x * sx + sh_l.x + ox
            v.co.y = v.co.y * sy + sh_l.y + oy
            v.co.z = v.co.z * sz + sh_l.z + oz
            # Soften outer edge
            if v.co.x < sh_l.x - 0.02:
                v.co.x = sh_l.x - 0.02 + (v.co.x - (sh_l.x - 0.02)) * 0.35
        append_transformed(bm, tmp)
        tmp.free()
    spaulder = mesh_from_bmesh("OrcGear_Spaulder_L", bm, leather_dark)
    def spaulder_w(v):
        return {"upperarm_l": 0.75, "spine_03": 0.25}
    bind_mesh(spaulder, arm, spaulder_w)
    created.append(spaulder)

    # --- Wide buckled belt ---
    bpy.ops.mesh.primitive_torus_add(
        align="WORLD",
        location=(pelvis.x, pelvis.y - 0.02, pelvis.z + 0.05),
        rotation=(math.radians(90.0), 0.0, 0.0),
        major_radius=0.16,
        minor_radius=0.028,
        major_segments=24,
        minor_segments=10,
    )
    belt = bpy.context.active_object
    belt.name = "OrcGear_Belt"
    belt.data.materials.clear()
    belt.data.materials.append(leather_dark)
    # Flatten slightly into a wide belt band.
    for v in belt.data.vertices:
        v.co.z *= 0.55
        v.co.z += 0.01
    bind_mesh(belt, arm, lambda _v: {"pelvis": 1.0})
    created.append(belt)

    # Belt buckles (two metal boxes on front)
    bm = bmesh.new()
    for dx in (-0.035, 0.035):
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            v.co.x = v.co.x * 0.028 + pelvis.x + dx
            v.co.y = v.co.y * 0.012 + pelvis.y - 0.14
            v.co.z = v.co.z * 0.035 + pelvis.z + 0.05
        append_transformed(bm, tmp)
        tmp.free()
    buckles = mesh_from_bmesh("OrcGear_BeltBuckles", bm, metal)
    bind_mesh(buckles, arm, lambda _v: {"pelvis": 1.0})
    created.append(buckles)

    # --- Ragged loincloth (layered front flaps) ---
    flap_specs = [
        (0.0, -0.12, 0.10, 0.14, 0.012, 0.28, LEATHER_RED),
        (-0.06, -0.10, 0.08, 0.09, 0.010, 0.22, LEATHER),
        (0.06, -0.10, 0.08, 0.09, 0.010, 0.20, RAG_TAN),
        (0.0, -0.08, 0.06, 0.07, 0.008, 0.16, LEATHER_DARK),
    ]
    for i, (dx, dy, dz, sx, sy, sz, col) in enumerate(flap_specs):
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            # Taper toward bottom + ragged edge via x jitter on lower verts
            v.co.x *= sx * (0.55 + 0.45 * max(0.0, v.co.z + 0.5))
            v.co.y *= sy
            v.co.z = (v.co.z * 0.5 - 0.5) * sz  # hang downward
            if v.co.z < -sz * 0.35:
                v.co.x += 0.015 * math.sin(i * 2.1 + v.co.x * 40.0)
            v.co.x += pelvis.x + dx
            v.co.y += pelvis.y + dy
            v.co.z += pelvis.z + dz
        flap = mesh_from_bmesh(
            f"OrcGear_Loin_{i}",
            tmp,
            make_opaque_mat(f"OrcLoinMat_{i}", col, 0.95),
        )
        bind_mesh(flap, arm, lambda _v: {"pelvis": 0.85, "spine_01": 0.15})
        created.append(flap)

    # --- Arm wraps ---
    for side, low, bone in (("L", low_l, "lowerarm_l"), ("R", low_r, "lowerarm_r")):
        bpy.ops.mesh.primitive_torus_add(
            align="WORLD",
            location=(low.x, low.y, low.z),
            rotation=(0.0, math.radians(90.0), 0.0),
            major_radius=0.045,
            minor_radius=0.012,
            major_segments=16,
            minor_segments=8,
        )
        wrap = bpy.context.active_object
        wrap.name = f"OrcGear_ArmWrap_{side}"
        wrap.data.materials.clear()
        wrap.data.materials.append(leather)
        # Stretch along forearm
        for v in wrap.data.vertices:
            v.co.z *= 2.2
        bind_mesh(wrap, arm, lambda _v, b=bone: {b: 1.0})
        created.append(wrap)

    # --- Ankle wraps ---
    for side, cpos, bone in (("L", calf_l, "calf_l"), ("R", calf_r, "calf_r")):
        bpy.ops.mesh.primitive_torus_add(
            align="WORLD",
            location=(cpos.x, cpos.y, cpos.z - 0.08),
            rotation=(math.radians(90.0), 0.0, 0.0),
            major_radius=0.055,
            minor_radius=0.014,
            major_segments=16,
            minor_segments=8,
        )
        wrap = bpy.context.active_object
        wrap.name = f"OrcGear_AnkleWrap_{side}"
        wrap.data.materials.clear()
        wrap.data.materials.append(leather)
        for v in wrap.data.vertices:
            v.co.z *= 1.6
        bind_mesh(wrap, arm, lambda _v, b=bone: {b: 1.0})
        created.append(wrap)

    log(f"look-dev gear: {[o.name for o in created]}")
    return created


def _uv_to_px(u: float, v: float, w: int, h: int) -> tuple[int, int]:
    """Map Blender UV (V up) to PNG pixel (Y down)."""
    x = int(max(0, min(w - 1, math.floor(u * w))))
    y = int(max(0, min(h - 1, math.floor((1.0 - v) * h))))
    return x, y


def rasterize_uv_tri(px: bytearray, w: int, h: int, uv0, uv1, uv2, rgba) -> None:
    """CPU fill of one UV triangle (tribal-veteran raster idea; no re-unwrap)."""
    pts = [
        (uv0[0] * w, (1.0 - uv0[1]) * h),
        (uv1[0] * w, (1.0 - uv1[1]) * h),
        (uv2[0] * w, (1.0 - uv2[1]) * h),
    ]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx = max(0, int(math.floor(min(xs) - 1)))
    maxx = min(w - 1, int(math.ceil(max(xs) + 1)))
    miny = max(0, int(math.floor(min(ys) - 1)))
    maxy = min(h - 1, int(math.ceil(max(ys) + 1)))

    def edge(a, b, c):
        return (c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])

    area = edge(pts[0], pts[1], pts[2])
    if abs(area) < 1e-6:
        cx = int(sum(xs) / 3.0)
        cy = int(sum(ys) / 3.0)
        if 0 <= cx < w and 0 <= cy < h:
            i = (cy * w + cx) * 4
            px[i : i + 4] = bytes(rgba)
        return
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            p = (x + 0.5, y + 0.5)
            w0 = edge(pts[1], pts[2], p)
            w1 = edge(pts[2], pts[0], p)
            w2 = edge(pts[0], pts[1], p)
            if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                i = (y * w + x) * 4
                px[i : i + 4] = bytes(rgba)


def draw_uv_line(px: bytearray, w: int, h: int, uv_a, uv_b, rgba) -> None:
    x0, y0 = _uv_to_px(uv_a[0], uv_a[1], w, h)
    x1, y1 = _uv_to_px(uv_b[0], uv_b[1], w, h)
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= x0 < w and 0 <= y0 < h:
            i = (y0 * w + x0) * 4
            px[i : i + 4] = bytes(rgba)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def write_png_rgba(path: Path, w: int, h: int, px: bytearray) -> None:
    """Pure-Python RGBA PNG (stdlib zlib). No Pillow, no GPU."""
    if len(px) != w * h * 4:
        raise RuntimeError(f"RGBA buffer size {len(px)} != {w * h * 4}")
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)  # filter None
        raw.extend(px[y * stride : (y + 1) * stride])
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    out = bytearray()
    out.extend(b"\x89PNG\r\n\x1a\n")
    out.extend(chunk(b"IHDR", ihdr))
    out.extend(chunk(b"IDAT", compressed))
    out.extend(chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    if not path.is_file() or path.stat().st_size < 33:
        raise RuntimeError(f"PNG write failed: {path}")


def cpu_export_uv_layout_png(obj, path: Path, size: int = TEX_SIZE) -> Path:
    """Raster existing UV islands to PNG. Does not smart_project or touch UVs."""
    me = obj.data
    if not me.uv_layers:
        raise RuntimeError(f"{obj.name!r} has no UV layer")
    uv_layer = me.uv_layers.active or me.uv_layers[0]
    w = h = int(size)
    # Dark board + light filled islands + white outlines (UV editor style).
    bg = (28, 28, 32, 255)
    fill = (70, 110, 160, 255)
    edge = (230, 230, 235, 255)
    px = bytearray(bg * (w * h))

    filled = 0
    stroked = 0
    for poly in me.polygons:
        loops = list(poly.loop_indices)
        if len(loops) < 3:
            continue
        uvs = [(uv_layer.data[li].uv.x, uv_layer.data[li].uv.y) for li in loops]
        for i in range(1, len(uvs) - 1):
            rasterize_uv_tri(px, w, h, uvs[0], uvs[i], uvs[i + 1], fill)
            filled += 1
        for i in range(len(uvs)):
            draw_uv_line(px, w, h, uvs[i], uvs[(i + 1) % len(uvs)], edge)
            stroked += 1

    if filled < 1:
        raise RuntimeError(
            f"{obj.name!r} UV layer {uv_layer.name!r} produced no triangles; "
            f"refusing empty layout"
        )
    write_png_rgba(path, w, h, px)
    log(
        f"CPU UV layout {path.name} from {obj.name!r}/{uv_layer.name!r} "
        f"tris={filled} edges={stroked} bytes={path.stat().st_size}"
    )
    return path


def export_uv_layout(path: Path) -> None:
    """CPU UV island layout for --background. Never call bpy.ops.uv.export_layout.

    PNG mode of export_layout uses GPUOffScreen and raises:
      SystemError: GPU functions for drawing are not available in background mode
    """
    ensure_scratch()
    meshes = [o for o in mesh_objects() if o.data.uv_layers]
    if not meshes:
        raise RuntimeError(
            "no mesh with UV layers; refusing CPU UV layout / smart_project"
        )
    targets = meshes
    try:
        arm = find_armature()
        try:
            targets = body_like_meshes(arm)
        except RuntimeError:
            targets = sorted(meshes, key=lambda o: len(o.data.vertices), reverse=True)
    except RuntimeError:
        targets = sorted(meshes, key=lambda o: len(o.data.vertices), reverse=True)
        log("no pelvis armature on UV source; using largest UV mesh")
    if not targets:
        raise RuntimeError("no UV mesh targets for layout export")

    primary = targets[0]
    if not primary.data.uv_layers:
        raise RuntimeError(f"{primary.name!r} has no UV layer")
    written = [cpu_export_uv_layout_png(primary, path)]
    # Per-mesh dumps when several UV meshes exist (clothes etc.).
    if len(targets) > 1:
        for obj in targets[1:]:
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in obj.name)
            per = SCRATCH / f"male_base_uv_layout_{safe}.png"
            written.append(cpu_export_uv_layout_png(obj, per))
    log(f"CPU UV layouts: {[str(p) for p in written]}")


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
    """Pick the same still frame used for donor Idle/Walk/Punch/Death reviews.

    Death uses the action's last frame (UAL Death01 ends on its back — not
    frame 0 / falling). Punch uses mid-late (~55%), matching the donor Punch still.
    """
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing in scene")
    # Prefer native frame_range (matches bake_bandit_death hold) over scanning
    # every fcurve key — empty/invalid ranges fall back to key scan.
    fr = tuple(act.frame_range)
    lo_r, hi_r = int(round(fr[0])), int(round(fr[1]))
    frames = [kp.co.x for fc in act.fcurves for kp in fc.keyframe_points]
    if frames:
        lo_k, hi_k = int(min(frames)), int(max(frames))
        lo = min(lo_r, lo_k) if hi_r > lo_r else lo_k
        hi = max(hi_r, hi_k) if hi_r > lo_r else hi_k
    elif hi_r > lo_r:
        lo, hi = lo_r, hi_r
    else:
        return 1
    if kind == "idle":
        return lo + max(1, (hi - lo) // 4)
    if kind == "walk":
        return lo + max(1, (hi - lo) // 2)
    if kind == "punch":
        # Same formula as the donor Punch still (~mid-late impact).
        return lo + max(1, int((hi - lo) * 0.55))
    if kind == "death":
        # Donor Death01 still is the final on-back hold — never frame 0.
        if hi <= lo:
            raise RuntimeError(
                f"death action {name!r} has empty frame range lo={lo} hi={hi}"
            )
        return int(hi)
    return lo


def apply_action(arm, name: str, frame: int) -> None:
    act = bpy.data.actions.get(name)
    if act is None:
        # Exact name only — never silently fall back to Punch_Cross.001 / Death.001.
        have = sorted(a.name for a in bpy.data.actions)
        raise RuntimeError(f"action {name!r} missing; have={have}")
    if act.name != name:
        raise RuntimeError(f"action lookup {name!r} resolved to {act.name!r}")
    HQ.reset_pose(arm)
    if arm.animation_data is None:
        arm.animation_data_create()
    # Mute NLA on EVERY armature so leftover strips cannot drive another rig.
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE" or obj.animation_data is None:
            continue
        for track in obj.animation_data.nla_tracks:
            track.mute = True
        if obj != arm:
            obj.animation_data.action = None
    HQ.assign_action(arm, act)
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    # Loud confirm: dest arm must own the active action.
    if arm.animation_data is None or arm.animation_data.action != act:
        raise RuntimeError(
            f"failed to assign {name!r} onto dest armature {arm.name!r} for still"
        )
    log(f"pose arm={arm.name!r} action={name!r} frame={int(frame)}")


def dest_owned_meshes(arm) -> list:
    """Meshes skinned to / parented on the dest armature only (orc body+tusks+gear)."""
    out = []
    for obj in mesh_objects():
        if obj.name.startswith("Preview") or obj.name == "PreviewGround":
            continue
        if obj.parent == arm:
            out.append(obj)
            continue
        for mod in obj.modifiers:
            if mod.type == "ARMATURE" and mod.object == arm:
                out.append(obj)
                break
    return out


def isolate_dest_for_stills(arm) -> list:
    """Hide/delete leftover donor armatures and non-dest meshes before Punch/Death stills.

    Idle/Walk were accepted; Punch previously framed a different leftover mesh.
    AFTER stills must show the same male_orc_01 dest (olive, tusks, harness).
    """
    removed_arms = []
    for obj in list(bpy.data.objects):
        if obj.type == "ARMATURE" and obj != arm:
            removed_arms.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed_arms:
        log(f"isolate: removed leftover armatures {removed_arms}")

    owned = dest_owned_meshes(arm)
    owned_set = set(owned)
    hidden = []
    for obj in list(mesh_objects()):
        if obj.name.startswith("Preview") or obj.name == "PreviewGround":
            continue
        if obj in owned_set:
            obj.hide_render = False
            obj.hide_viewport = False
            continue
        obj.hide_render = True
        obj.hide_viewport = True
        hidden.append(obj.name)
    if hidden:
        log(f"isolate: hid non-dest meshes {hidden}")

    names = {o.name for o in owned}
    if not any("tusk" in n.lower() for n in names):
        raise RuntimeError(
            f"dest still meshes missing tusks; have={sorted(names)}. "
            f"Refusing Punch/Death AFTER that is not male_orc_01."
        )
    if not any(n.startswith("OrcGear_") for n in names):
        raise RuntimeError(
            f"dest still meshes missing look-dev gear; have={sorted(names)}"
        )
    extras = [o.name for o in bpy.data.objects if o.type == "ARMATURE" and o != arm]
    if extras:
        raise RuntimeError(f"isolate failed; extra armatures remain: {extras}")
    log(f"isolate: dest arm={arm.name!r} still_meshes={sorted(names)}")
    return owned


def clear_preview_helpers() -> None:
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        if obj.name.startswith("Preview") or obj.name == "PreviewGround":
            bpy.data.objects.remove(obj, do_unlink=True)


def posed_bbox(meshes):
    deps = bpy.context.evaluated_depsgraph_get()
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    hit = False
    for o in meshes:
        if o.type != "MESH":
            continue
        if getattr(o, "hide_render", False):
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
    clear_preview_helpers()

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
    clear_preview_helpers()

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
    """Render stills on the dest armature only (same male_orc_01 for all clips)."""
    meshes = isolate_dest_for_stills(arm)
    # Canonical still frames — same formulas as donor Idle/Walk/Punch/Death stills.
    frames = {
        label: action_frame(resolved[label], clip_kind(label)) for label in PREVIEW_CLIPS
    }
    log(
        f"still frames ({tag}): "
        + ", ".join(f"{lab}={resolved[lab]!r}@{frames[lab]}" for lab in PREVIEW_CLIPS)
    )
    if resolved.get("Punch") != "Punch_Cross":
        log(f"note: Punch resolved to {resolved.get('Punch')!r} (Punch_Cross preferred)")
    if resolved.get("Death") != "Death01":
        log(f"note: Death resolved to {resolved.get('Death')!r} (Death01 preferred)")
    # Death must not be frame 0 / start of fall.
    if frames["Death"] <= 1:
        raise RuntimeError(
            f"Death still frame {frames['Death']} looks like start/rest; "
            f"expected final on-back hold of {resolved['Death']!r}"
        )

    out = {}
    for label in PREVIEW_CLIPS:
        clip = resolved[label]
        frame = frames[label]
        apply_action(arm, clip, frame)
        # Re-affirm isolation each clip (preview helpers must not become subjects).
        meshes = dest_owned_meshes(arm)
        for obj in meshes:
            obj.hide_render = False
            obj.hide_viewport = False
        center, extent = posed_bbox(meshes)
        if label == "Death":
            setup_death_preview(center, extent)
        else:
            setup_standing_preview(center, extent)
        path = still_path(tag, label)
        render_png(path)
        out[label] = str(path)
        log(
            f"still {tag}/{label} arm={arm.name!r} action={clip!r} "
            f"frame={frame} meshes={len(meshes)} -> {path.name}"
        )
    out["_frames"] = {k: frames[k] for k in PREVIEW_CLIPS}
    return out


def run_uv_only() -> dict:
    """Export UV layout from male_base (default). Does not require Punch/Death."""
    ensure_scratch()
    uv_src = MALE_BASE
    if not uv_src.is_file():
        raise FileNotFoundError(
            f"missing UV source {uv_src}. --uv-only needs male_base.glb "
            f"(clean full-body MH UVs; clips may be empty)."
        )
    # Read-only: never write male_base / worksuit / Orrun.
    ensure_not_protected_dest(DEST)  # dest path sanity only; we do not write dest here
    clips = log_clip_list(uv_src)
    clear_scene()
    import_gltf(uv_src)
    arm = find_armature()
    bone_count = len(arm.data.bones)
    log(f"uv source={uv_src.name!r} arm={arm.name!r} bones={bone_count}")
    export_uv_layout(UV_LAYOUT)
    return {
        "mode": "uv-only",
        "uv_source": str(uv_src),
        "uv_layout": str(UV_LAYOUT),
        "bones": bone_count,
        "clips": clips,
        "note": "UV template only; Punch/Death not required for --uv-only",
    }


def run_restyle() -> dict:
    ensure_scratch()
    seed_mode = seed_dest_from_anim_donor(force=True)
    # Capture donor clip list before mesh restyle / re-export.
    if seed_mode == "orrun_copy":
        donor_clips = log_clip_list(ANIM_DONOR)
    else:
        # bake_one / reuse: dest already holds the UAL set we must preserve.
        donor_clips = log_clip_list(DEST)
    assert_required_clips(DEST)

    # Restyle on dest (Orrun clips on armature; strip worksuit; male_base body).
    clear_scene()
    import_gltf(DEST)
    arm = find_armature()
    hip_before = hip_height_z(arm)
    log(f"hip_height_z BEFORE (dest rest)={hip_before:.4f}")
    assert_no_leg_bone_scale(arm)
    bone_count = len(arm.data.bones)
    if bone_count < 50:
        raise RuntimeError(
            f"expected ~53-bone MH bind, got {bone_count} bones on {arm.name!r}"
        )
    log(f"restyle bind bones={bone_count} arm={arm.name!r}")

    drop_weapons()
    _body_meshes, removed_garments = strip_dressed_meshes_attach_male_base(arm)
    restyle_bulk_and_jaw(arm)
    tusks = add_tusks(arm)
    gear = add_lookdev_gear(arm)
    apply_finished_olive_skin(arm)

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
    missing_scene = missing_clip_labels(have)
    combat_scene = [m for m in missing_scene if m in ("Punch", "Death")]
    if combat_scene:
        raise RuntimeError(
            f"scene missing required clip(s) {combat_scene}; {_punch_death_hint(have)}"
        )
    resolved_scene = {}
    for label, candidates in REQUIRED_CLIP_GROUPS:
        resolved_scene[label] = resolve_clip(have, label, candidates)
    # HOLD reshoot targets: Death01 + Punch_Cross when present.
    log(
        f"AFTER still actions: Idle={resolved_scene['Idle']!r} "
        f"Walk={resolved_scene['Walk']!r} "
        f"Death={resolved_scene['Death']!r} "
        f"Punch={resolved_scene['Punch']!r}"
    )
    if resolved_scene["Punch"] not in ("Punch_Cross", "Punch_Jab", "Punch_Enter"):
        raise RuntimeError(
            f"Punch must resolve to Punch_Cross/Jab/Enter, got {resolved_scene['Punch']!r}"
        )
    if resolved_scene["Death"] not in ("Death01", "Death"):
        raise RuntimeError(
            f"Death must resolve to Death01/Death, got {resolved_scene['Death']!r}"
        )

    # AFTER stills on the LIVE restyled dest (before export) so Punch/Death cannot
    # frame a leftover donor armature. Idle/Walk restyle unchanged.
    after_previews = render_clip_stills(arm, resolved_scene, "after")
    still_frames = after_previews.pop("_frames", {})

    preserved = preserve_all_actions_for_export(arm)
    if len(preserved) < len([n for n in donor_clips if n]):
        raise RuntimeError(
            f"scene actions ({len(preserved)}) < donor clips ({len(donor_clips)}); "
            f"refusing export that would drop UAL. preserved={preserved}"
        )

    export_objects = [
        o
        for o in bpy.data.objects
        if o.type == "MESH"
        and not o.name.startswith("Preview")
        and o.name != "PreviewGround"
        and not getattr(o, "hide_render", False)
    ]
    # Prefer dest-owned meshes only (tusks + gear + body).
    owned = dest_owned_meshes(arm)
    if owned:
        export_objects = owned
    if not export_objects:
        raise RuntimeError("no mesh objects to export after restyle/gear")
    export_glb(DEST, arm, export_objects)
    dest_clips = assert_donor_clips_preserved(donor_clips, DEST)
    resolved_out = assert_required_clips(DEST)

    packet = write_art_review_packet(
        seed_mode=seed_mode,
        donor_clips=donor_clips,
        dest_clips=dest_clips,
        resolved=resolved_out,
        after_previews=after_previews,
        hip_before=hip_before,
        hip_after=hip_after,
        tusks=[o.name for o in tusks],
        gear=[o.name for o in gear],
        removed_garments=removed_garments,
    )
    packet["still_frames"] = still_frames
    ART_REVIEW_PACKET.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    return {
        "mode": "restyle",
        "seed_mode": seed_mode,
        "anim_donor": str(ANIM_DONOR),
        "ag_worksuit_guarded": str(AG_WORKSUIT),
        "male_base_body": str(MALE_BASE),
        "dest": str(DEST),
        "size": DEST.stat().st_size,
        "bones": bone_count,
        "clips_donor": donor_clips,
        "clips_dest": dest_clips,
        "clips_resolved": resolved_out,
        "hip_before": hip_before,
        "hip_after": hip_after,
        "hip_delta_m": delta,
        "tusks": [o.name for o in tusks],
        "gear": [o.name for o in gear],
        "removed_garments": removed_garments,
        "previews_after": after_previews,
        "art_review_packet": str(ART_REVIEW_PACKET),
        "clip_list_md": str(CLIP_LIST_MD),
        "uv_layout_hint": str(UV_LAYOUT),
        "lookdev": str(LOOKDEV),
        "note": (
            "HOLD fix: no worksuit clothes; finished olive-grey skin; "
            "look-dev harness/loincloth; AFTER stills only"
        ),
        "packet_notes": packet.get("notes"),
    }


def main() -> int:
    log(f"blender {bpy.app.version_string}")
    refuse_quaternius_orc(DEST, AG_WORKSUIT, ANIM_DONOR, MALE_BASE)
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
        assert_untouched(
            guard,
            "protected AG/Orrun worksuit, male_base, casualsuit, Quaternius Orc",
        )
        print(json.dumps(res, indent=2), flush=True)
        log(f"DONE mode={res.get('mode')} dest={DEST}")
        return 0
    except Exception:
        traceback.print_exc()
        try:
            assert_untouched(
                guard,
                "protected AG/Orrun worksuit, male_base, casualsuit, Quaternius Orc",
            )
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
