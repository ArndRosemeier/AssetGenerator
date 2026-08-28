# -*- coding: utf-8 -*-
"""Ambitious orc restyle on the MakeHuman 53-bone UAL-baked path.

Art / Asset Lab only. Does not write Orrun or Origin, does not author clips,
does not add bones, does not use Quaternius Orc.glb as a donor.

Arnd nude lock (PR #1): same creature / same dest — not a new body plan.
  - Delete worksuit tee/dungarees; nude male_base on the same 53-bone bind.
  - Finished olive-grey skin on male_body MH UVs (no UV-grid / checker).
  - NO invented look-dev clothes: do not call add_lookdev_gear; no OrcGear_*,
    harness, spaulder, belt, loincloth, arm/ankle wraps, cubes/tori.
  - Widen mouth / open lips; tusks IN the mouth cavity (head-bound), not cheeks.
  - Brow spikes are male_body verts from an oversized face restyle band — NOT Eyes,
    NOT Icosphere, NOT an authored brow mesh. Flatten those verts. Hide Eyes
    separately if present as junk. Script never authors eyebrows.
  - AFTER stills: Idle, Walk, Punch_Cross, Death01 on nude dest (tusks visible).
  - Do NOT copy ANIM_DONOR onto dest as a first step. Live-import Orrun read-only;
    write dest only after AFTER stills succeed.
  - Do NOT overwrite tools/_human_orc_bake/male_orc_01_restyle.glb or
    male_orc_01_restyle_1635.glb (16:35 backups).
  - Death: dest-native Death01 on-back hold. Do not treat root_z=0 as lying
    (MH Root sits near origin — false positive). Do not invent clips.
  - Punch: Orrun Punch_Cross @ ~55% on dest. Idle/Walk restyle intent = nude +
    mouth/tusks + hide/flatten junk only.
  - Keep EEVEE_NEXT. No thigh/calf/pelvis scale. No ogre hunch.

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
  Protected restyle backups (never overwrite):
    tools/_human_orc_bake/male_orc_01_restyle.glb
    tools/_human_orc_bake/male_orc_01_restyle_1635.glb

Clip aliases (resolve existing names only — never invent Punch or Death):

  Idle  -> Idle, Idle_Loop
  Walk  -> Walk, Walk_Loop
  Death -> Death01 (preferred), Death
  Punch -> Punch_Cross (preferred), Punch_Jab, Punch_Enter
           (Orrun has no clip literally named Punch)

Full restyle path:
  1. Import Orrun worksuit READ-ONLY into the live Blender scene (UAL clips).
     Do NOT copy ANIM_DONOR onto dest. Scratch bake fallback never touches dest.
  2. Strip worksuit garments; attach nude male_base body on the same armature.
  3. Mesh-only restyle (bulk + mouth/jaw) + flatten brow-ridge spikes on male_body
     + mouth-cavity tusks. No gear.
  4. Hide junk Eyes mesh if present. Olive on male_body.
  5. AFTER stills on the live restyled scene (must succeed before any dest write).
  6. Only then export skinned dest (fake_user + NLA). Scratch export path must
     not clobber the protected restyle backups.
  7. Art Reviewer packet under tools/_human_orc_bake/previews/.

Restyle rules:
  - MESH only on the existing 53-bone bind (BONE_MAP from bake_human_quaternius).
  - Tusks BONE-parented to head (mouth cavity); no new bones.
  - Do NOT scale thigh / calf / pelvis bones. No invented clothes / gait.
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
from mathutils import Matrix, Vector

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
JSON_FOURCC = 0x4E4F534A
BIN_FOURCC = 0x004E4942

# Never scale these bones (keep MH gait / hip height).
NO_SCALE_BONES = ("pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r")

PELVIS_LYING_MAX_Z = 0.50  # standing MH pelvis ~0.95; lying hold is much lower
# Do NOT use absolute root_z/obj_z <= threshold as lying: MH Root sits near z=0
# at rest (root_z=0 is a false positive). Prefer posed bbox collapse / pelvis drop.
BBOX_LYING_MAX_Z = 0.70  # posed mesh AABB max Z when lying on ground
BBOX_LYING_MAX_HEIGHT = 0.90  # standing ~1.7–1.9; lying flattens
CHEST_ON_BACK_MIN_Z = 0.20  # chest forward world-Z; on-back faces sky
CHEST_FACEPLANT_MAX_Z = -0.05  # chest forward toward ground
# MH head bone origin is at the skull base, not the lips. Real mouth-corner
# distance in head-rest space is ~0.20 (local bake: 0.2053). Do not use a
# tight 0.08–0.14 cap — that rejects every real mouth vert.
HEAD_MOUTH_MAX_LOCAL = 0.28

# Scratch exports must never clobber the 16:35 restyle backups.
PROTECTED_RESTYLE_BACKUPS = (
    SCRATCH / "male_orc_01_restyle.glb",
    SCRATCH / "male_orc_01_restyle_1635.glb",
)

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


def seed_live_from_anim_donor() -> tuple[str, Path]:
    """Import UAL seed into the LIVE scene only. Never writes DEST or Orrun.

    Returns (seed_mode, clip_source_path) where clip_source_path is used only to
    read animation names (ANIM_DONOR or a scratch bake). DEST must stay untouched
    until AFTER stills succeed and export_glb runs.
    """
    refuse_quaternius_orc(ANIM_DONOR, DEST, AG_WORKSUIT)
    ensure_not_protected_dest(DEST)
    if DEST.resolve() == ANIM_DONOR.resolve():
        raise RuntimeError("dest must not be the Orrun worksuit")
    if DEST.resolve() == AG_WORKSUIT.resolve():
        raise RuntimeError("dest must not be the AG worksuit")

    if ANIM_DONOR.is_file():
        clear_scene()
        import_gltf(ANIM_DONOR)
        log(
            f"live-seed imported Orrun donor read-only "
            f"({ANIM_DONOR}; {ANIM_DONOR.stat().st_size} bytes); DEST not written yet"
        )
        return "orrun_live_import", ANIM_DONOR

    # Fallback: bake UAL onto a scratch GLB (not DEST), then import that.
    if not AG_WORKSUIT.is_file():
        raise FileNotFoundError(
            f"missing Orrun UAL worksuit animation donor: {ANIM_DONOR} "
            f"and missing AG worksuit mesh seed: {AG_WORKSUIT}. "
            f"Cannot live-seed; bake_human_orc.py does not author clips."
        )
    ensure_scratch()
    scratch_seed = SCRATCH / "male_orc_01_ual_seed.glb"
    log(
        f"Orrun donor missing ({ANIM_DONOR}); baking UAL into scratch "
        f"{scratch_seed} via bake_one (DEST untouched)"
    )
    shutil.copy2(AG_WORKSUIT, scratch_seed)
    refuse_quaternius_orc(scratch_seed)
    HQ.bake_one(scratch_seed)
    clear_scene()
    import_gltf(scratch_seed)
    log(f"live-seed imported scratch bake {scratch_seed}; DEST not written yet")
    return "bake_one_scratch", scratch_seed


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


def drop_orrun_still_action_clones() -> None:
    """ORRUN_STILL_* clones are pose-only helpers — never ship them on dest."""
    removed = []
    for act in list(bpy.data.actions):
        if act.name.startswith("ORRUN_STILL_"):
            removed.append(act.name)
            bpy.data.actions.remove(act)
    if removed:
        log(f"dropped still-only action clones before export: {removed}")


def preserve_all_actions_for_export(arm) -> list[str]:
    """Keep every imported UAL action alive for glTF ACTIONS+NLA export."""
    drop_orrun_still_action_clones()
    actions = [
        a
        for a in bpy.data.actions
        if a is not None and not a.name.startswith("ORRUN_STILL_")
    ]
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
            "DEST is written only after AFTER stills succeed (no early Orrun copy onto dest).",
            "Nude skin-only: no OrcGear_*, no invented look-dev clothes.",
            "Olive skin is painted on mesh male_body (mat OrcSkin_male_body).",
            "Tusks BONE-parented to head with Identity matrix_parent_inverse; "
            "mesh authored in Blender tip/BONE-parent space (not skull-base) — "
            "head-space+Identity was the 20:52 float-off.",
            "AFTER stills gate: tusk world vs posed male_body mouth verts before PNG "
            "(head-local length alone lied on 20:52).",
            "Mouth/jaw restyle skips neck_01 / heavy spine_03 (no Idle/Walk shred).",
            "male_base attach preserves bind transforms (no matrix_basis identity hack).",
            "Death AFTER: dest-native Death01 on-back; bbox/pelvis lying — not root_z=0.",
            "Punch AFTER uses Orrun Punch_Cross @ ~55% on dest with head camera.",
            "Idle/Walk AFTER = nude + mouth/tusks + junk hide/flatten only.",
            "ORRUN_STILL_* clones are still-only and are dropped before export.",
            "Protected scratch backups: male_orc_01_restyle.glb / _restyle_1635.glb.",
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
        # Keep imported bind transforms. Forcing matrix_basis=Identity here was
        # shredding neck/chest under Idle/Walk (verts no longer matched bone rest).
        mw = obj.matrix_world.copy()
        obj.parent = arm
        obj.parent_type = "OBJECT"
        obj.matrix_world = mw
        for mod in list(obj.modifiers):
            if mod.type == "ARMATURE":
                mod.object = arm
                mod.use_vertex_groups = True
                if hasattr(mod, "use_bone_envelopes"):
                    mod.use_bone_envelopes = False
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("Armature", "ARMATURE")
            mod.object = arm
            mod.use_vertex_groups = True
            if hasattr(mod, "use_bone_envelopes"):
                mod.use_bone_envelopes = False
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
    """Conservative bulk + orc mouth/jaw. Does NOT invent brow spikes.

    Neck/chest tear fix: mouth/jaw/widen only on head-dominant face verts —
    never on neck_01 / spine_03–heavy verts (those sat in the old dz band and
    shredded under Walk). Brow flatten stays face-only. No new neck mesh.
    """
    assert_no_leg_bone_scale(arm)
    for obj in skinned_meshes(arm):
        me = obj.data
        if not me.vertices:
            continue
        # Only restyle skin body — never Eyes / junk companions.
        if is_junk_companion_mesh(obj):
            continue
        if obj.name.startswith("OrcTusk_") or obj.name.startswith("OrcGear_"):
            continue
        head_i = vg_index(obj, "head")
        neck_i = vg_index(obj, "neck_01") or vg_index(obj, "neck")
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
        spine3_i = vg_index(obj, "spine_03")

        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        z0, z1 = min(zs), max(zs)
        height = max(z1 - z0, 1e-3)
        if "head" not in arm.data.bones:
            raise RuntimeError("53-bone bind missing head bone for mouth/jaw restyle")
        head_z = float(HQ.rest_world(arm, "head").to_translation().z)

        face_edits = 0
        neck_skipped = 0
        for v in me.vertices:
            hw = vg_weight(v, head_i)
            nw = vg_weight(v, neck_i)
            s3w = vg_weight(v, spine3_i)
            tw = max(vg_weight(v, gi) for gi in torso_groups)
            arm_w = max(
                vg_weight(v, upper_l),
                vg_weight(v, upper_r),
                vg_weight(v, lower_l),
                vg_weight(v, lower_r),
                vg_weight(v, hand_l),
                vg_weight(v, hand_r),
            )
            radial = Vector((v.co.x - cx, v.co.y - cy, 0.0))
            if radial.length < 1e-6:
                radial = Vector((0.0, -1.0, 0.0))
            else:
                radial.normalize()

            bulk = 0.0
            bulk += 0.038 * tw
            bulk += 0.030 * arm_w
            # Mild stockiness; skip head shell (avoids forehead radial spikes).
            if hw < 0.35:
                bulk += 0.012 * max(0.0, 1.0 - hw)

            # Idle/Walk neck/chest shred: never displace neck_01 or heavy spine_03.
            # Also skip any vert with meaningful neck weight — jaw/mouth on the
            # head/neck blend seam was still tearing under Walk.
            neck_zone = (
                nw >= 0.05
                or (s3w >= 0.22 and hw < 0.55 and arm_w < 0.30)
                or (s3w >= 0.40 and hw < 0.70)
            )
            if neck_zone:
                bulk = 0.0
                neck_skipped += 1
                continue

            dz = v.co.z - head_z
            # Face-only: strong head dominance; no neck blend seam.
            is_face = (
                hw >= 0.60
                and hw >= nw + 0.35
                and hw >= s3w + 0.30
                and nw < 0.12
                and s3w < 0.25
            )

            if is_face and -0.145 <= dz <= -0.055 and v.co.y < cy + 0.02:
                jaw = (hw - 0.18) * 0.070
                v.co.y -= jaw * 0.85
                v.co.z -= jaw * 0.18
                v.co.x += math.copysign(jaw * 0.85, v.co.x - cx)
                face_edits += 1

            if is_face and -0.110 <= dz <= -0.012 and v.co.y < cy:
                mouth_mid_z = head_z - 0.055
                widen = 0.018 * hw
                v.co.x += math.copysign(widen, v.co.x - cx)
                if v.co.z < mouth_mid_z:
                    v.co.z -= 0.012 * hw
                    v.co.y -= 0.010 * hw
                else:
                    v.co.z += 0.008 * hw
                    v.co.y -= 0.006 * hw
                face_edits += 1

            if bulk > 0.0:
                v.co.x += radial.x * bulk
                v.co.y += radial.y * bulk

        me.update()
        log(
            f"restyled mesh {obj.name!r} verts={len(me.vertices)} "
            f"head_z={head_z:.4f} face_edits={face_edits} "
            f"neck_bulk_damped={neck_skipped}"
        )

    flatten_male_body_brow_spikes(arm)


def flatten_male_body_brow_spikes(arm) -> int:
    """Flatten forward brow-ridge spikes on male_body (not Eyes, not a brow mesh).

    Dest GLB has Eyes + male_body (+ tusks/gear historically). Look-dev only painted
    a 2D heavy brow — the script never authors eyebrows. Spikes that remain after
    hiding Eyes are male_body verts (oversized prior face band / residual ridge).
    Pull those verts back toward the forehead plane.
    """
    bodies = [
        o
        for o in skinned_meshes(arm)
        if o.name == "male_body" or o.name.lower() == "male_body"
    ]
    if not bodies:
        raise RuntimeError(
            "flatten_male_body_brow_spikes: male_body missing — cannot hunt spikes"
        )
    flattened = 0
    for obj in bodies:
        me = obj.data
        head_i = vg_index(obj, "head")
        neck_i = vg_index(obj, "neck_01") or vg_index(obj, "neck")
        spine3_i = vg_index(obj, "spine_03")
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        z0, z1 = min(zs), max(zs)
        height = max(z1 - z0, 1e-3)
        # Forehead reference: median Y of head verts above brow band (less forward).
        forehead_ys = []
        for v in me.vertices:
            hw = vg_weight(v, head_i)
            nw = vg_weight(v, neck_i)
            if hw < 0.40 or nw >= 0.25:
                continue
            z_rel = (v.co.z - z0) / height
            if 0.92 < z_rel < 0.98 and abs(v.co.x - cx) < 0.06:
                forehead_ys.append(v.co.y)
        if not forehead_ys:
            forehead_ys = [cy - 0.04]
        forehead_ys.sort()
        forehead_y = forehead_ys[len(forehead_ys) // 2]
        # Brow band: high face, forward of forehead reference. Head-dominant only.
        for v in me.vertices:
            hw = vg_weight(v, head_i)
            nw = vg_weight(v, neck_i)
            s3w = vg_weight(v, spine3_i)
            if hw < 0.45 or nw >= 0.30 or hw < nw + 0.15:
                continue
            if hw < s3w + 0.10:
                continue
            z_rel = (v.co.z - z0) / height
            if not (0.875 <= z_rel <= 0.955):
                continue
            if abs(v.co.x - cx) > 0.090:
                continue  # temples / sides — leave
            # Spike = verts pushed forward of the forehead plane (-Y in MH rest).
            if v.co.y < forehead_y - 0.008:
                # Blend back toward forehead; keep a mild ridge, kill spikes.
                target_y = forehead_y - 0.004
                v.co.y = 0.25 * v.co.y + 0.75 * target_y
                # Slightly flatten upward protrusion.
                if z_rel > 0.93:
                    v.co.z -= 0.003 * hw
                flattened += 1
        me.update()
        log(
            f"brow-spike flatten mesh={obj.name!r} verts_adjusted={flattened} "
            f"forehead_y={forehead_y:.4f} (male_body face verts — not Eyes/neck)"
        )
    return flattened


def is_junk_companion_mesh(obj) -> bool:
    """True for leftover companion meshes that are not the nude orc identity.

    Eyes may exist as a separate MH export mesh — hide as junk. Icosphere may
    appear on some imports. These are NOT the brow spikes (spikes = male_body).
    """
    low = obj.name.lower()
    if low in ("eyes", "eye") or low.startswith("eyes"):
        return True
    if "icosphere" in low:
        return True
    return False


def hide_junk_companion_meshes(arm) -> list[str]:
    """Hide Eyes / Icosphere junk. Separate from brow-spike flatten on male_body."""
    hidden = []
    for obj in list(mesh_objects()):
        if not is_junk_companion_mesh(obj):
            continue
        obj.hide_render = True
        obj.hide_viewport = True
        try:
            obj.hide_set(True)
        except Exception:
            pass
        hidden.append(obj.name)
    if hidden:
        log(f"hidden junk companion meshes (not brow spikes): {hidden}")
    else:
        log("no Eyes/Icosphere junk companions to hide")
    return hidden


def assert_no_invented_gear() -> None:
    gear = [
        o.name
        for o in mesh_objects()
        if o.name.startswith("OrcGear_") or "orcgear" in o.name.lower()
    ]
    if gear:
        raise RuntimeError(
            f"invented look-dev gear present (forbidden on nude pass): {gear}"
        )


def male_body_mesh(arm):
    for obj in skinned_meshes(arm):
        if obj.name == "male_body" or obj.name.lower() == "male_body":
            return obj
    raise RuntimeError("male_body mesh required for mouth/tusk placement")


def _log_zrel_histogram(label: str, zrels: list[float], *, lo: float, hi: float, step: float) -> None:
    """Log a coarse histogram so empty mouth bands are diagnosable locally."""
    if not zrels:
        log(f"{label}: empty (no samples)")
        return
    bins = []
    edge = lo
    while edge < hi - 1e-9:
        bins.append((edge, edge + step, 0))
        edge += step
    for z in zrels:
        for i, (a, b, _) in enumerate(bins):
            if a <= z < b or (b >= hi - 1e-9 and a <= z <= b):
                a0, b0, c0 = bins[i]
                bins[i] = (a0, b0, c0 + 1)
                break
    parts = [f"[{a:.2f},{b:.2f})={c}" for a, b, c in bins if c]
    log(
        f"{label}: n={len(zrels)} min={min(zrels):.3f} max={max(zrels):.3f} "
        f"hist={parts or '(all outside range)'}"
    )


def collect_head_front_face_samples(arm) -> tuple[object, list[dict]]:
    """Head-weighted front-hemisphere samples on male_body for mouth hunting."""
    body = male_body_mesh(arm)
    me = body.data
    head_i = vg_index(body, "head")
    if head_i is None:
        raise RuntimeError("male_body missing head vertex group for mouth anchors")
    if "head" not in arm.data.bones:
        raise RuntimeError("53-bone bind missing head bone for mouth anchors")
    head_z = float(HQ.rest_world(arm, "head").to_translation().z)
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    cx = 0.5 * (min(xs) + max(xs))
    cy = 0.5 * (min(ys) + max(ys))
    z0, z1 = min(zs), max(zs)
    height = max(z1 - z0, 1e-3)
    samples = []
    for v in me.vertices:
        hw = vg_weight(v, head_i)
        if hw < 0.20:
            continue
        if v.co.y > cy:
            continue  # back half of bbox — not the face
        z_rel = (v.co.z - z0) / height
        dz = v.co.z - head_z
        samples.append(
            {
                "v": v,
                "hw": hw,
                "x": float(v.co.x),
                "y": float(v.co.y),
                "z": float(v.co.z),
                "z_rel": z_rel,
                "dz": dz,
                "cx": cx,
                "cy": cy,
                "z0": z0,
                "height": height,
                "head_z": head_z,
            }
        )
    _log_zrel_histogram(
        "head-front z_rel",
        [s["z_rel"] for s in samples],
        lo=0.70,
        hi=1.001,
        step=0.02,
    )
    _log_zrel_histogram(
        "head-front dz(head)",
        [s["dz"] for s in samples],
        lo=-0.20,
        hi=0.16,
        step=0.02,
    )
    return body, samples


def resolve_mouth_zrel_band(samples: list[dict]) -> tuple[float, float, float]:
    """Derive mouth z_rel band from forward head verts (not a fixed 0.80–0.87).

    Returns (mouth_lo, mouth_hi, brow_lo). Mouth is the lower portion of the
    forward face cluster; brow_lo is the refuse floor for cheek/brow.
    """
    if len(samples) < 20:
        raise RuntimeError(
            f"too few head-front samples for mouth band ({len(samples)})"
        )
    # Most-forward subset (MH faces -Y).
    ordered = sorted(samples, key=lambda s: s["y"])
    fwd = ordered[: max(40, len(ordered) * 45 // 100)]
    zrels = sorted(s["z_rel"] for s in fwd)

    def pct(p: float) -> float:
        i = int(round((len(zrels) - 1) * p))
        return zrels[max(0, min(len(zrels) - 1, i))]

    face_lo = pct(0.05)
    face_hi = pct(0.95)
    span = max(face_hi - face_lo, 1e-3)
    # Lower ~40% of forward face = mouth/lips; brow from ~55% up.
    mouth_lo = face_lo + 0.05 * span
    mouth_hi = face_lo + 0.45 * span
    brow_lo = face_lo + 0.55 * span
    log(
        f"mouth band from forward face: face_z_rel=[{face_lo:.3f},{face_hi:.3f}] "
        f"mouth=[{mouth_lo:.3f},{mouth_hi:.3f}] brow_lo={brow_lo:.3f} "
        f"(fwd_n={len(fwd)})"
    )
    return mouth_lo, mouth_hi, brow_lo


def find_mouth_corner_anchors(arm) -> tuple[Vector, Vector, int, int]:
    """Head-weighted lower-lip / mouth-corner verts on male_body (object space).

    Full-body z_rel 0.80–0.87 was empty on MH male_body (face lives ~0.88+).
    Logs a head-front histogram, derives an adaptive mouth band, then expands
    until real L/R corners exist. Still refuses cheek/brow. No head-bone offsets
    for the tusk bases — anchors are mesh verts (nudged into the cavity).

    Returns ``(left_pos, right_pos, left_vert_index, right_vert_index)``.
    """
    _body, samples = collect_head_front_face_samples(arm)
    if not samples:
        raise RuntimeError("no head-weighted front verts on male_body for mouth anchors")
    cx = samples[0]["cx"]
    cy = samples[0]["cy"]
    z0 = samples[0]["z0"]
    height = samples[0]["height"]
    head_z = samples[0]["head_z"]
    mouth_lo, mouth_hi, brow_lo = resolve_mouth_zrel_band(samples)

    # Parallel head-relative dz windows (expand if z_rel band is sparse).
    dz_windows = (
        (-0.110, -0.018),
        (-0.130, -0.012),
        (-0.150, -0.008),
        (-0.160, -0.005),
    )

    def pick_candidates(z_lo: float, z_hi: float, dz_lo: float, dz_hi: float, hw_min: float):
        out = []
        for s in samples:
            if s["hw"] < hw_min:
                continue
            if s["y"] > cy - 0.005:
                continue
            in_z = z_lo <= s["z_rel"] <= z_hi
            in_dz = dz_lo <= s["dz"] <= dz_hi
            if not (in_z or in_dz):
                continue
            if s["z_rel"] >= brow_lo:
                continue  # cheek/brow refuse
            if s["dz"] > -0.005:
                continue  # at/above head bone — brow/forehead
            if abs(s["x"] - cx) > 0.090:
                continue
            out.append(s)
        return out

    candidates = []
    used = None
    # Widen/shift mouth_hi toward brow_lo until we have corners.
    for expand in (0.0, 0.03, 0.06, 0.09, 0.12):
        z_hi = min(mouth_hi + expand, brow_lo - 0.005)
        z_lo = mouth_lo - 0.5 * expand
        for dz_lo, dz_hi in dz_windows:
            for hw_min in (0.35, 0.28, 0.22, 0.18):
                cand = pick_candidates(z_lo, z_hi, dz_lo, dz_hi, hw_min)
                if len(cand) >= 6:
                    left_side = [s for s in cand if s["x"] < cx]
                    right_side = [s for s in cand if s["x"] >= cx]
                    if left_side and right_side:
                        candidates = cand
                        used = (z_lo, z_hi, dz_lo, dz_hi, hw_min, len(cand))
                        break
            if candidates:
                break
        if candidates:
            break

    if len(candidates) < 6 or used is None:
        raise RuntimeError(
            f"too few mouth-band verts for tusk anchors ({len(candidates)}); "
            f"mouth_lo={mouth_lo:.3f} mouth_hi={mouth_hi:.3f} brow_lo={brow_lo:.3f} "
            f"head_z={head_z:.4f}. See head-front z_rel/dz histograms above."
        )
    log(
        f"mouth candidates n={used[5]} z_rel=[{used[0]:.3f},{used[1]:.3f}] "
        f"dz=[{used[2]:.3f},{used[3]:.3f}] hw_min={used[4]}"
    )

    # Prefer forward half of mouth band, then extreme X as corners.
    candidates.sort(key=lambda s: s["y"])
    front = candidates[: max(8, len(candidates) // 2)]
    left_side = [s for s in front if s["x"] < cx]
    right_side = [s for s in front if s["x"] >= cx]
    if not left_side or not right_side:
        # Fall back to full candidate set if forward half is one-sided.
        left_side = [s for s in candidates if s["x"] < cx]
        right_side = [s for s in candidates if s["x"] >= cx]
    if not left_side or not right_side:
        raise RuntimeError(
            f"mouth anchors missing L/R split "
            f"(L={len(left_side)} R={len(right_side)} cand={len(candidates)})"
        )

    # Among each side, prefer forward verts that still have some |x| (true corners).
    def pick_corner(side: list[dict], want_left: bool) -> dict:
        side_sorted = sorted(side, key=lambda s: s["y"])
        forward_side = side_sorted[: max(4, len(side_sorted) // 2)]
        if want_left:
            return min(forward_side, key=lambda s: s["x"])
        return max(forward_side, key=lambda s: s["x"])

    left = pick_corner(left_side, True)
    right = pick_corner(right_side, False)

    def into_mouth(s: dict, sign_x: float) -> Vector:
        # Nudge into cavity: toward center, deeper -Y, slightly down.
        return Vector(
            (
                s["x"] - sign_x * 0.006,
                s["y"] - 0.012,
                s["z"] - 0.006,
            )
        )

    left_p = into_mouth(left, -1.0)
    right_p = into_mouth(right, 1.0)

    for label, p, src in (("L", left_p, left), ("R", right_p, right)):
        z_rel = (p.z - z0) / height
        dz = p.z - head_z
        if z_rel >= brow_lo or dz > -0.005:
            raise RuntimeError(
                f"tusk anchor {label} looks like cheek/brow "
                f"(z_rel={z_rel:.3f} brow_lo={brow_lo:.3f} dz={dz:.3f} "
                f"src_z_rel={src['z_rel']:.3f})"
            )
        if abs(p.x - cx) > 0.085:
            raise RuntimeError(
                f"tusk anchor {label} |x|={abs(p.x - cx):.3f} looks like cheek, not mouth"
            )
        if abs(p.x - cx) < 0.012:
            raise RuntimeError(
                f"tusk anchor {label} |x|={abs(p.x - cx):.3f} too centered — not a corner"
            )
    left_idx = int(left["v"].index)
    right_idx = int(right["v"].index)
    log(
        f"mouth anchors L={tuple(round(c, 4) for c in left_p)} "
        f"R={tuple(round(c, 4) for c in right_p)} "
        f"verts=({left_idx},{right_idx}) "
        f"z_rel=({(left_p.z - z0) / height:.3f},{(right_p.z - z0) / height:.3f}) "
        f"dz=({left_p.z - head_z:.3f},{right_p.z - head_z:.3f}) "
        f"(male_body verts, not head-bone offsets)"
    )
    return left_p, right_p, left_idx, right_idx


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


def _evaluated_mesh_centroid_world(obj) -> Vector:
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        if not me.vertices:
            raise RuntimeError(f"evaluated mesh empty: {obj.name!r}")
        mw = ev.matrix_world
        acc = Vector((0.0, 0.0, 0.0))
        for v in me.vertices:
            acc += mw @ v.co
        return acc / float(len(me.vertices))
    finally:
        ev.to_mesh_clear()


def head_pose_world_matrix(arm) -> Matrix:
    """Posed head bone matrix in world space (follows Idle/Walk/Punch/Death)."""
    if "head" not in arm.pose.bones:
        raise RuntimeError("dest armature missing head pose bone")
    return arm.matrix_world @ arm.pose.bones["head"].matrix


def world_to_head_local(arm, world_p: Vector) -> Vector:
    return head_pose_world_matrix(arm).inverted() @ Vector(world_p)


def body_local_to_world(body, p: Vector) -> Vector:
    return body.matrix_world @ Vector(p)


def head_bone_length(arm) -> float:
    if "head" not in arm.data.bones:
        raise RuntimeError("dest armature missing head bone")
    return float(arm.data.bones["head"].length)


def head_local_to_bone_parent_local(arm, head_local: Vector) -> Vector:
    """Convert head ``matrix_local`` space → Blender BONE-parent object space.

    Default BONE parenting uses ``pose_mat`` then offsets by ``+Y * bone.length``
    (the tip). Mesh authored in skull-base / ``matrix_local`` space with Identity
    ``matrix_parent_inverse`` therefore sits a full head-bone length away from the
    mouth — numeric head-local checks still pass (rigid tip attach), but still
    cameras see floating cones (20:52 Reviewer HOLD).
    """
    return Vector(head_local) - Vector((0.0, head_bone_length(arm), 0.0))


def evaluated_vertex_world(obj, vert_index: int) -> Vector:
    """World position of a mesh vertex after modifiers (Armature deform)."""
    if obj.type != "MESH":
        raise RuntimeError(f"evaluated_vertex_world: {obj.name!r} is not a mesh")
    nverts = len(obj.data.vertices)
    if vert_index < 0 or vert_index >= nverts:
        raise RuntimeError(
            f"evaluated_vertex_world: {obj.name!r} vert {vert_index} "
            f"out of range n={nverts}"
        )
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        if vert_index >= len(me.vertices):
            raise RuntimeError(
                f"evaluated_vertex_world: {obj.name!r} eval mesh missing vert "
                f"{vert_index} (n={len(me.vertices)})"
            )
        return ev.matrix_world @ me.vertices[vert_index].co
    finally:
        ev.to_mesh_clear()


def _matrix_is_identity(m: Matrix, *, eps: float = 1e-5) -> bool:
    ident = Matrix.Identity(4)
    for i in range(4):
        for j in range(4):
            if abs(float(m[i][j]) - float(ident[i][j])) > eps:
                return False
    return True


def bind_tusk_to_head_bone(obj, arm) -> None:
    """Parent tusk to the head bone (no Armature modifier).

    Critical: assigning ``obj.parent`` makes Blender preserve world transform via
    ``matrix_parent_inverse``. Leaving that keep-transform inverse cancels bone
    motion — tusks stick at rest world. Mesh data must already be in **BONE
    parent / tip** space (see ``head_local_to_bone_parent_local``); then force
    Identity parent inverse so the head pose fully drives the object.
    """
    if "head" not in arm.data.bones:
        raise RuntimeError("bind_tusk_to_head_bone: missing head bone")
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    obj.parent = None
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    if hasattr(obj, "rotation_quaternion"):
        obj.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()

    # Order: parent object, then bone name, then bone type.
    obj.parent = arm
    obj.parent_bone = "head"
    obj.parent_type = "BONE"
    # Wipe the keep-transform inverse Blender just wrote — verts are already
    # tip-parent local; bone pose must apply unopposed.
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()

    if obj.parent != arm or obj.parent_type != "BONE" or obj.parent_bone != "head":
        raise RuntimeError(
            f"bind_tusk_to_head_bone failed on {obj.name!r}: "
            f"parent={obj.parent!r} type={obj.parent_type!r} bone={obj.parent_bone!r}"
        )
    # Parent inverse must stay Identity (keep-transform inverse = rest stick).
    if not _matrix_is_identity(obj.matrix_parent_inverse):
        raise RuntimeError(
            f"{obj.name!r} matrix_parent_inverse is not Identity after bone parent — "
            f"would stick tusks at rest world. pinv={obj.matrix_parent_inverse}"
        )
    if any(m.type == "ARMATURE" for m in obj.modifiers):
        raise RuntimeError(
            f"{obj.name!r} still has Armature modifier after bone parent "
            f"(would double-transform)"
        )
    log(
        f"tusk {obj.name!r} BONE-parented to head "
        f"(matrix_parent_inverse=Identity, tip-space mesh, no Armature modifier)"
    )


# Max world distance from tusk centroid to the posed mouth-corner vert on the
# still frame. Cone centroid sits ~2–3cm from the base; into_mouth nudge ~1cm.
# 20:52 float-off was ~head-bone-length (~15–25cm) — must fail that class.
TUSK_MOUTH_WORLD_MAX = 0.085


def force_armature_rest(arm) -> None:
    """Clear action/NLA drivers and snap every bone to rest bind.

    ``assert_tusks_follow_head`` ends on the Death still frame with an action
    assigned. A bare ``reset_pose`` + restoring the prior action/NLA mute state
    left the armature posed — ``rest_after_bind`` then compared head-parented
    tusks to weight-blended mouth verts and got dist≈0.11 while tip-space bind
    at true rest was 0.026. Always leave a quiet rest pose after follow tests.
    """
    if arm.animation_data is not None:
        arm.animation_data.action = None
        for track in arm.animation_data.nla_tracks:
            track.mute = True
    HQ.reset_pose(arm)
    # Death still leaves scene.frame at the hold frame; snap back so any stray
    # driver/NLA cannot re-pose on the next depsgraph update.
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()


def assert_tusks_in_mouth_for_current_pose(arm, tusks: list, label: str) -> None:
    """Gate the PNG the Reviewer sees — tusk world must meet posed mouth verts.

    Head-local length alone lied on 20:52: tip-space mis-authoring kept a fixed
    head-local offset that passed the budget while the camera saw rest-offset
    cones in front of the face. Compare evaluated tusk centroids to the skinned
    male_body mouth-corner verts at this exact pose.
    """
    if not tusks:
        raise RuntimeError(f"{label}: no tusks for in-mouth still gate")
    body = male_body_mesh(arm)
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()
    for tusk in tusks:
        if tusk.parent != arm or tusk.parent_type != "BONE" or tusk.parent_bone != "head":
            raise RuntimeError(
                f"{label} still: {tusk.name!r} lost head BONE parent "
                f"(parent={getattr(tusk.parent, 'name', None)!r} "
                f"type={tusk.parent_type!r} bone={tusk.parent_bone!r})"
            )
        pinv = tusk.matrix_parent_inverse
        if not _matrix_is_identity(pinv):
            raise RuntimeError(
                f"{label} still: {tusk.name!r} matrix_parent_inverse not Identity"
            )
        if "orc_mouth_vert" not in tusk:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} missing orc_mouth_vert custom prop "
                f"— cannot prove mouth coincidence"
            )
        mouth_idx = int(tusk["orc_mouth_vert"])
        mouth_w = evaluated_vertex_world(body, mouth_idx)
        # Bind target under current head pose (catches tip miss / rest-stick).
        if "orc_mouth_head_local" not in tusk:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} missing orc_mouth_head_local"
            )
        hl = tusk["orc_mouth_head_local"]
        expected = head_pose_world_matrix(arm) @ Vector(
            (float(hl[0]), float(hl[1]), float(hl[2]))
        )
        # into_mouth nudge lives in head-local; apply it on the posed mouth vert
        # so the gate compares tusk to the same cavity point we authored to —
        # not the raw lip vert (~1.5cm off) or a leftover Death pose (0.11).
        if "orc_mouth_raw_head_local" in tusk:
            raw_hl = tusk["orc_mouth_raw_head_local"]
            nudge = Vector(
                (
                    float(hl[0]) - float(raw_hl[0]),
                    float(hl[1]) - float(raw_hl[1]),
                    float(hl[2]) - float(raw_hl[2]),
                )
            )
            mouth_target_w = mouth_w + head_pose_world_matrix(arm).to_3x3() @ nudge
        else:
            mouth_target_w = mouth_w
        c = _evaluated_mesh_centroid_world(tusk)
        dist_vert = (c - mouth_target_w).length
        dist_bind = (c - expected).length
        if dist_bind > TUSK_MOUTH_WORLD_MAX:
            raise RuntimeError(
                f"{label} still: tusk {tusk.name!r} missed head-pose bind target "
                f"(dist_bind_target={dist_bind:.4f} > {TUSK_MOUTH_WORLD_MAX}) "
                f"tusk_w={tuple(round(x, 3) for x in c)} "
                f"bind_w={tuple(round(x, 3) for x in expected)} "
                f"mouth_w={tuple(round(x, 3) for x in mouth_target_w)} — "
                f"pixels would float; refusing PNG"
            )
        if dist_vert > TUSK_MOUTH_WORLD_MAX:
            raise RuntimeError(
                f"{label} still: tusk {tusk.name!r} not at posed mouth vert "
                f"(dist_mouth_vert={dist_vert:.4f} > {TUSK_MOUTH_WORLD_MAX}) "
                f"tusk_w={tuple(round(x, 3) for x in c)} "
                f"mouth_w={tuple(round(x, 3) for x in mouth_target_w)} "
                f"raw_vert_w={tuple(round(x, 3) for x in mouth_w)} "
                f"bind_w={tuple(round(x, 3) for x in expected)} — "
                f"pixels would float; refusing PNG"
            )
        log(
            f"{label} still gate: {tusk.name} mouth_vert_dist={dist_vert:.4f} "
            f"bind_dist={dist_bind:.4f}"
        )
    log(f"{label} still gate: tusks coincide with posed mouth verts")


def assert_tusks_follow_head(arm, tusks: list) -> None:
    """Fail unless tusks track the head under Idle, Walk, AND Death (large delta).

    20:14: Idle@15/Walk@16 head barely moves, so a 'head-local lock' can pass
    while tusks are stuck at rest world. Death (and a forced head rotate) must
    show a real head_delta; tusks must keep head-local mouth position there too.
    """
    if not tusks:
        raise RuntimeError("assert_tusks_follow_head: no tusks")
    for tusk in tusks:
        if tusk.parent != arm or tusk.parent_type != "BONE" or tusk.parent_bone != "head":
            raise RuntimeError(
                f"{tusk.name!r} must be BONE-parented to head before follow assert; "
                f"got parent={getattr(tusk.parent, 'name', None)!r} "
                f"type={tusk.parent_type!r} bone={tusk.parent_bone!r}"
            )
        if not _matrix_is_identity(tusk.matrix_parent_inverse):
            raise RuntimeError(
                f"{tusk.name!r} matrix_parent_inverse not Identity — rest-stick bind"
            )

    if arm.animation_data is not None:
        arm.animation_data.action = None
        for track in arm.animation_data.nla_tracks:
            track.mute = True

    try:
        HQ.reset_pose(arm)
        bpy.context.view_layer.update()
        rest_locals = [
            world_to_head_local(arm, _evaluated_mesh_centroid_world(t)) for t in tusks
        ]
        rest_worlds = [_evaluated_mesh_centroid_world(t) for t in tusks]
        rest_tip = head_motion_marker_world(arm)

        def _check_pose(label: str, *, require_head_delta: float) -> float:
            bpy.context.view_layer.update()
            bpy.context.evaluated_depsgraph_get().update()
            # Use bone.tail — bone.head is the rotation pivot and stays put.
            posed_tip = head_motion_marker_world(arm)
            head_delta = (posed_tip - rest_tip).length
            if head_delta < require_head_delta:
                raise RuntimeError(
                    f"{label}: head_tip_delta={head_delta:.4f} < {require_head_delta} "
                    f"— pose too close to rest to prove tusk follow "
                    f"(measuring bone.tail, not bone.head pivot)"
                )
            for tusk, rest_l, rest_w in zip(tusks, rest_locals, rest_worlds):
                posed_w = _evaluated_mesh_centroid_world(tusk)
                posed_l = world_to_head_local(arm, posed_w)
                local_drift = (posed_l - rest_l).length
                world_delta = (posed_w - rest_w).length
                if local_drift > 0.025:
                    raise RuntimeError(
                        f"tusk {tusk.name!r} not locked to head under {label}: "
                        f"head_local_drift={local_drift:.4f}"
                    )
                if world_delta < 0.5 * head_delta:
                    raise RuntimeError(
                        f"tusk {tusk.name!r} stuck near rest under {label} "
                        f"(tusk_world_delta={world_delta:.4f} "
                        f"head_tip_delta={head_delta:.4f}) — Reviewer float-off"
                    )
                if posed_l.length > HEAD_MOUTH_MAX_LOCAL:
                    raise RuntimeError(
                        f"tusk {tusk.name!r} head-local length={posed_l.length:.4f} "
                        f"> {HEAD_MOUTH_MAX_LOCAL} under {label}"
                    )
                if "orc_mouth_head_local" in tusk:
                    hl = tusk["orc_mouth_head_local"]
                    expected = head_pose_world_matrix(arm) @ Vector(
                        (float(hl[0]), float(hl[1]), float(hl[2]))
                    )
                    dist_bind = (posed_w - expected).length
                    if dist_bind > TUSK_MOUTH_WORLD_MAX:
                        raise RuntimeError(
                            f"tusk {tusk.name!r} off bind mouth under {label}: "
                            f"dist_bind_target={dist_bind:.4f} > {TUSK_MOUTH_WORLD_MAX}"
                        )
            return head_delta

        # 1) Forced head rotate via Euler on bone; delta from bone.tail.
        force_head_pose_for_tusk_assert(arm)
        d_rot = _check_pose("forced_head_rotate", require_head_delta=0.05)
        log(f"tusk follow OK forced_head_rotate head_tip_delta={d_rot:.4f}")

        # 2) Idle / Walk still frames (same as AFTER).
        clip_specs = (
            ("Idle", ("Idle", "Idle_Loop"), "idle"),
            ("Walk", ("Walk", "Walk_Loop"), "walk"),
        )
        tested = [f"forced_head_rotateΔ={d_rot:.3f}"]
        for label, names, kind in clip_specs:
            act = None
            for name in names:
                act = bpy.data.actions.get(name)
                if act is not None:
                    break
            if act is None:
                raise RuntimeError(
                    f"assert_tusks_follow_head: missing {label} action {names}"
                )
            frame = action_frame_for_action(act, kind)
            HQ.reset_pose(arm)
            HQ.assign_action(arm, act)
            bpy.context.scene.frame_set(int(frame))
            bpy.context.view_layer.update()
            bpy.context.evaluated_depsgraph_get().update()
            posed_tip = head_motion_marker_world(arm)
            head_delta = (posed_tip - rest_tip).length
            for tusk, rest_l, rest_w in zip(tusks, rest_locals, rest_worlds):
                posed_w = _evaluated_mesh_centroid_world(tusk)
                posed_l = world_to_head_local(arm, posed_w)
                local_drift = (posed_l - rest_l).length
                world_delta = (posed_w - rest_w).length
                if local_drift > 0.025:
                    raise RuntimeError(
                        f"tusk {tusk.name!r} not locked to head under {label}@{frame}: "
                        f"head_local_drift={local_drift:.4f}"
                    )
                if head_delta > 0.025 and world_delta < 0.5 * head_delta:
                    raise RuntimeError(
                        f"tusk {tusk.name!r} stuck near rest under {label}@{frame} "
                        f"(tusk_world_delta={world_delta:.4f} "
                        f"head_tip_delta={head_delta:.4f})"
                    )
                if posed_l.length > HEAD_MOUTH_MAX_LOCAL:
                    raise RuntimeError(
                        f"tusk {tusk.name!r} head-local length={posed_l.length:.4f} "
                        f"under {label}@{frame}"
                    )
                if "orc_mouth_head_local" in tusk:
                    hl = tusk["orc_mouth_head_local"]
                    expected = head_pose_world_matrix(arm) @ Vector(
                        (float(hl[0]), float(hl[1]), float(hl[2]))
                    )
                    dist_bind = (posed_w - expected).length
                    if dist_bind > TUSK_MOUTH_WORLD_MAX:
                        raise RuntimeError(
                            f"tusk {tusk.name!r} off bind mouth under {label}@{frame}: "
                            f"dist_bind_target={dist_bind:.4f} > {TUSK_MOUTH_WORLD_MAX}"
                        )
            tested.append(f"{label}:{act.name}@{frame}Δ={head_delta:.3f}")
            if arm.animation_data is not None:
                arm.animation_data.action = None

        # 3) Death last/hold frame — large head motion; must not float above face.
        death = None
        for name in ("Death01", "Death"):
            death = bpy.data.actions.get(name)
            if death is not None:
                break
        if death is None:
            raise RuntimeError(
                "assert_tusks_follow_head: missing Death01/Death — "
                "cannot prove follow on the Death still"
            )
        death_frame = action_frame_for_action(death, "death")
        HQ.reset_pose(arm)
        HQ.assign_action(arm, death)
        bpy.context.scene.frame_set(int(death_frame))
        d_death = _check_pose(
            f"Death:{death.name}@{death_frame}", require_head_delta=0.08
        )
        tested.append(f"Death:{death.name}@{death_frame}Δ={d_death:.3f}")
        log(f"tusk head-local lock OK on clips {tested}")
    finally:
        # Do NOT restore the prior action/NLA mute state here — that left the
        # Death hold frame driving the armature and made rest_after_bind lie.
        force_armature_rest(arm)


def add_tusks(arm) -> list:
    """Tusks in the mouth cavity, BONE-parented to head (follow all clips).

    Mouth anchors from male_body verts → world → head-rest (``matrix_local``)
    → **tip / BONE-parent object space** → parent_type=BONE / parent_bone=head
    with Identity ``matrix_parent_inverse``. No Armature modifier. No new bones.

    Blender's default BONE parent places the child relative to the bone tip
    (``pose_mat + Y*length``). Authoring in skull-base space with Identity
    inverse parks cones a head-length off the mouth while head-local locks
    still pass — that was the 20:52 pixel miss.
    """
    if "head" not in arm.data.bones:
        raise RuntimeError("53-bone bind missing head bone")
    HQ.reset_pose(arm)
    bpy.context.view_layer.update()

    body = male_body_mesh(arm)
    left_body, right_body, left_idx, right_idx = find_mouth_corner_anchors(arm)
    left_world = body_local_to_world(body, left_body)
    right_world = body_local_to_world(body, right_body)
    # Raw corner verts (pre into_mouth nudge) for the still-gate mouth target.
    left_raw_world = body_local_to_world(body, body.data.vertices[left_idx].co)
    right_raw_world = body_local_to_world(body, body.data.vertices[right_idx].co)
    head_rest = HQ.rest_world(arm, "head")
    head_rest_inv = head_rest.inverted()
    left_head = head_rest_inv @ left_world
    right_head = head_rest_inv @ right_world
    left_raw_head = head_rest_inv @ left_raw_world
    right_raw_head = head_rest_inv @ right_raw_world
    bone_len = head_bone_length(arm)
    left_local = head_local_to_bone_parent_local(arm, left_head)
    right_local = head_local_to_bone_parent_local(arm, right_head)
    log(
        f"tusk bases head-rest-local L={tuple(round(c, 4) for c in left_head)} "
        f"R={tuple(round(c, 4) for c in right_head)} "
        f"tip-parent-local L={tuple(round(c, 4) for c in left_local)} "
        f"R={tuple(round(c, 4) for c in right_local)} "
        f"head_bone_length={bone_len:.4f} "
        f"(mouth verts → head space → BONE tip parent space)"
    )
    # Mouth sits below/forward of the skull-base head origin (~0.20 on MH).
    for label, p in (("L", left_head), ("R", right_head)):
        if p.length > HEAD_MOUTH_MAX_LOCAL:
            raise RuntimeError(
                f"tusk anchor {label} head-local length={p.length:.4f} "
                f"> {HEAD_MOUTH_MAX_LOCAL} — beyond MH mouth (not inventing closer anchors)"
            )
        if p.length < 0.08:
            raise RuntimeError(
                f"tusk anchor {label} head-local length={p.length:.4f} too close to "
                f"head origin — likely cheek/skull, not mouth (MH mouth ~0.20)"
            )

    mat = make_opaque_mat("OrcTusk", TUSK, 0.55)
    created = []
    specs = [
        (
            "OrcTusk_L",
            left_local,
            left_head,
            left_raw_head,
            left_idx,
            left_world,
            14.0,
        ),
        (
            "OrcTusk_R",
            right_local,
            right_head,
            right_raw_head,
            right_idx,
            right_world,
            -14.0,
        ),
    ]
    for name, base, head_local, raw_head_local, mouth_idx, mouth_world, yaw_deg in specs:
        bm = bmesh.new()
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=True,
            segments=10,
            radius1=0.013,
            radius2=0.0030,
            depth=0.052,
        )
        # Tip up / slightly forward / slightly out of mouth (tip-parent local).
        for v in bm.verts:
            v.co.z += 0.026
            a = math.radians(-42.0)
            cy = v.co.y * math.cos(a) - v.co.z * math.sin(a)
            cz = v.co.y * math.sin(a) + v.co.z * math.cos(a)
            v.co.y = cy
            v.co.z = cz
            ca = math.cos(math.radians(yaw_deg))
            sa = math.sin(math.radians(yaw_deg))
            rx = v.co.x * ca - v.co.y * sa
            ry = v.co.x * sa + v.co.y * ca
            v.co.x = rx + base.x
            v.co.y = ry + base.y
            v.co.z += base.z
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append(mat)
        obj["orc_mouth_vert"] = int(mouth_idx)
        obj["orc_mouth_head_local"] = [
            float(head_local.x),
            float(head_local.y),
            float(head_local.z),
        ]
        obj["orc_mouth_raw_head_local"] = [
            float(raw_head_local.x),
            float(raw_head_local.y),
            float(raw_head_local.z),
        ]
        bind_tusk_to_head_bone(obj, arm)
        created.append(obj)

    # Rest-pose proof: tusk world must meet the mouth anchor world (tip miss → ~bone_len).
    force_armature_rest(arm)
    for obj, mouth_world in (
        (created[0], left_world),
        (created[1], right_world),
    ):
        c = _evaluated_mesh_centroid_world(obj)
        dist = (c - Vector(mouth_world)).length
        if dist > TUSK_MOUTH_WORLD_MAX:
            raise RuntimeError(
                f"rest bind: {obj.name!r} centroid world dist to mouth={dist:.4f} "
                f"> {TUSK_MOUTH_WORLD_MAX} (head_bone_length={bone_len:.4f}). "
                f"tusk={tuple(round(x, 3) for x in c)} "
                f"mouth={tuple(round(x, 3) for x in mouth_world)}. "
                f"Likely head-space authored into tip BONE parent."
            )
        log(
            f"rest bind OK {obj.name}: mouth_world_dist={dist:.4f} "
            f"(tip-parent space + Identity pinv)"
        )

    # Same gate stills use — must pass at true rest BEFORE follow posing.
    assert_tusks_in_mouth_for_current_pose(arm, created, "rest_before_follow")
    assert_tusks_follow_head(arm, created)
    # Follow assert leaves Death@hold unless force_armature_rest ran in finally.
    force_armature_rest(arm)
    assert_tusks_in_mouth_for_current_pose(arm, created, "rest_after_bind")
    log(f"tusks: {[o.name for o in created]} BONE-parented to head (mouth cavity, tip-space)")
    return created


def body_like_meshes(arm):
    """Skin / basemesh targets for finished olive albedo (no garments).

    After glTF the MH skin mesh is named ``male_body``. Eyes may exist as a
    separate junk companion (hidden — not an olive target). Brow spikes are
    male_body verts, not a separate mesh.
    """
    skins = []
    # Prefer exact male_body first (dest / male_base export name).
    for obj in skinned_meshes(arm):
        if obj.name == "male_body" or obj.name.lower() == "male_body":
            skins.append(obj)
    if skins:
        return skins
    for obj in skinned_meshes(arm):
        low = obj.name.lower()
        if is_garment_mesh_name(obj.name):
            continue
        if any(
            k in low
            for k in (
                "hair",
                "brow",
                "eye",
                "tusk",
                "orcgear",
                "strap",
                "belt",
                "loin",
                "spaulder",
                "wrap",
                "icosphere",
            )
        ):
            continue
        if "body" in low or "basemesh" in low or "human" in low:
            skins.append(obj)
    if not skins:
        candidates = []
        for obj in skinned_meshes(arm):
            if not obj.data.uv_layers:
                continue
            if vg_index(obj, "head") is None:
                continue
            low = obj.name.lower()
            if any(
                k in low
                for k in ("tusk", "orcgear", "strap", "belt", "loin", "spaulder", "eye")
            ):
                continue
            candidates.append(obj)
        if not candidates:
            raise RuntimeError(
                "no skinned UV body mesh found for orc albedo "
                "(expected male_body after glTF import)"
            )
        candidates.sort(key=lambda o: len(o.data.vertices), reverse=True)
        skins = [candidates[0]]
    return skins


def apply_finished_olive_skin(arm) -> None:
    """Finished olive-grey skin on male_body (existing MH UVs). No UV-grid/checker.

    Mesh name is male_body; material datablock may be named OrcSkin_male_body.
    Re-applying after dest GLB import is required — white proxy means olive was
    never bound to male_body.
    """
    if LOOKDEV.is_file():
        log(f"look-dev reference present (not a UV map): {LOOKDEV}")
    else:
        log(f"look-dev reference optional/missing: {LOOKDEV}")

    skins = body_like_meshes(arm)
    if not any(o.name.lower() == "male_body" for o in skins):
        log(
            f"warning: olive targets are {[o.name for o in skins]} "
            f"(expected male_body after glTF); still painting these"
        )
    for obj in skins:
        me = obj.data
        if not me.uv_layers:
            raise RuntimeError(f"{obj.name!r} has no UV; refusing smart_project")
        # Keep mesh name male_body; material id documents olive ownership.
        mat_name = f"OrcSkin_{obj.name}"
        mat = make_opaque_mat(mat_name, OLIVE, 0.88)
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
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
            f"finished olive-grey skin on mesh={obj.name!r} mat={mat_name!r} "
            f"(Principled+noise, no UV-grid, uv={me.uv_layers.active.name!r})"
        )



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
    # Never overwrite the protected 16:35 restyle backups.
    scratch_out = SCRATCH / f"{path.stem}_export_live.glb"
    protected = {p.resolve() for p in PROTECTED_RESTYLE_BACKUPS}
    if scratch_out.resolve() in protected:
        raise RuntimeError(f"refusing to write protected restyle backup path: {scratch_out}")
    if path.resolve() in protected:
        raise RuntimeError(f"refusing dest path that aliases a protected backup: {path}")
    for backup in PROTECTED_RESTYLE_BACKUPS:
        if backup.is_file():
            log(f"protected restyle backup intact: {backup} ({backup.stat().st_size} bytes)")
    before_backup_sizes = {
        str(p.resolve()): (p.stat().st_size if p.is_file() else None)
        for p in PROTECTED_RESTYLE_BACKUPS
    }
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
    # Re-check backups were not clobbered by a mis-aimed export.
    for backup in PROTECTED_RESTYLE_BACKUPS:
        if str(backup.resolve()) in before_backup_sizes:
            after = backup.stat().st_size if backup.is_file() else None
            if after != before_backup_sizes[str(backup.resolve())]:
                raise RuntimeError(
                    f"protected restyle backup changed during export: {backup} "
                    f"before={before_backup_sizes[str(backup.resolve())]} after={after}"
                )
    shutil.copy2(scratch_out, path)
    log(f"exported {path} ({path.stat().st_size} bytes) via scratch {scratch_out.name}")


def action_frame_for_action(act, kind: str) -> int:
    """Pick still frame from an Action datablock (donor or dest).

    Death = final keyed hold (UAL Death01 ends on its back — never frame 0).
    Punch = mid-late (~55%), matching the donor Punch_Cross still.
    """
    if act is None:
        raise RuntimeError("action_frame_for_action: act is None")
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
        return lo + max(1, int((hi - lo) * 0.55))
    if kind == "death":
        if hi <= lo:
            raise RuntimeError(
                f"death action {act.name!r} has empty frame range lo={lo} hi={hi}"
            )
        return int(hi)
    return lo


def action_frame(name: str, kind: str) -> int:
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing in scene")
    return action_frame_for_action(act, kind)


def log_action_motion_channels(act) -> list[str]:
    """Log Root/root/location fcurves — Death01 root motion often lives here."""
    interesting = []
    for fc in act.fcurves:
        p = fc.data_path or ""
        low = p.lower()
        if "root" in low or p == "location" or p.endswith(".location"):
            zs = []
            if fc.array_index == 2 and fc.keyframe_points:
                zs = [
                    round(float(kp.co.y), 3)
                    for kp in (
                        fc.keyframe_points[0],
                        fc.keyframe_points[len(fc.keyframe_points) // 2],
                        fc.keyframe_points[-1],
                    )
                ]
            interesting.append(
                f"{p}[{fc.array_index}] keys={len(fc.keyframe_points)}"
                + (f" z_samples={zs}" if zs else "")
            )
    log(f"action {act.name!r} root/location channels: {interesting or '(none)'}")
    return interesting


def root_bone_name(arm) -> str | None:
    for name in ("Root", "root"):
        if name in arm.pose.bones:
            return name
    return None


def root_world_z(arm) -> float | None:
    name = root_bone_name(arm)
    if name is None:
        return None
    return float((arm.matrix_world @ arm.pose.bones[name].head).z)


def pelvis_world_z(arm) -> float:
    return float((arm.matrix_world @ arm.pose.bones["pelvis"].head).z)


def posed_mesh_aabb_z(arm) -> tuple[float, float, float]:
    """Return (min_z, max_z, height) of dest-owned posed meshes."""
    meshes = dest_owned_meshes(arm)
    center, extent = posed_bbox(meshes)
    min_z = float(center.z - 0.5 * extent.z)
    max_z = float(center.z + 0.5 * extent.z)
    return min_z, max_z, float(extent.z)


def death_pose_metrics(arm) -> dict:
    """Height metrics for Death stills.

    Local facts: dest-native Death01 pelvis_z stayed ~0.954 (lean). MH Root sits
    near world z=0 at rest — root_z=0 is a FALSE POSITIVE for lying. Do not use
    absolute root_z/obj_z thresholds. Lying = pelvis drop and/or posed bbox
    collapse (not pelvis-only alone without height context when tall).
    """
    pz = pelvis_world_z(arm)
    hz = float(head_world_pos(arm).z)
    rz = root_world_z(arm)
    obj_z = float(arm.matrix_world.translation.z)
    z0, z1, height = posed_mesh_aabb_z(arm)
    forward = chest_forward_world(arm)
    # root_z / arm_obj_z logged only — never alone as lying (z≈0 at rest).
    bbox_lying = z1 <= BBOX_LYING_MAX_Z or height <= BBOX_LYING_MAX_HEIGHT
    pelvis_lying = pz <= PELVIS_LYING_MAX_Z
    # Require real collapse: bbox lying, or pelvis low AND not still standing-tall.
    lying = bbox_lying or (pelvis_lying and height <= 1.20)
    on_back = float(forward.z) >= CHEST_ON_BACK_MIN_Z
    faceplant = lying and float(forward.z) <= CHEST_FACEPLANT_MAX_Z
    return {
        "pelvis_z": round(pz, 3),
        "head_z": round(hz, 3),
        "root_z": None if rz is None else round(rz, 3),
        "arm_obj_z": round(obj_z, 3),
        "bbox_min_z": round(z0, 3),
        "bbox_max_z": round(z1, 3),
        "bbox_height": round(height, 3),
        "chest_fwd_z": round(float(forward.z), 3),
        "lying": lying,
        "on_back": on_back,
        "faceplant": faceplant,
    }


def apply_action_datablock(arm, act, frame: int) -> None:
    """Pose dest armature with an exact Action datablock at frame (active action)."""
    if act is None:
        raise RuntimeError("apply_action_datablock: act is None")
    HQ.reset_pose(arm)
    arm.location = (0.0, 0.0, 0.0)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    if arm.animation_data is None:
        arm.animation_data_create()
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
    if arm.animation_data is None or arm.animation_data.action != act:
        raise RuntimeError(
            f"failed to assign {act.name!r} onto dest armature {arm.name!r} for still"
        )
    log(f"pose arm={arm.name!r} action={act.name!r} frame={int(frame)} mode=active")


def apply_death_action_nla_solo(arm, act, frame: int) -> None:
    """Evaluate Death01 via a single unmuted NLA strip (root motion / slots).

    Active-action assign can miss Root location evaluation on Blender 4.4+ slotted
    actions; Punch_Cross worked with active assign, Death01 may need NLA solo.
    """
    if act is None:
        raise RuntimeError("apply_death_action_nla_solo: act is None")
    HQ.reset_pose(arm)
    # Clear object-level transform so location fcurves can drive from rest.
    arm.location = (0.0, 0.0, 0.0)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    ad.action = None
    for track in list(ad.nla_tracks):
        ad.nla_tracks.remove(track)
    # Mute every other armature's NLA so leftovers cannot drive the still.
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE" or obj is arm or obj.animation_data is None:
            continue
        for track in obj.animation_data.nla_tracks:
            track.mute = True
        obj.animation_data.action = None
    track = ad.nla_tracks.new()
    track.name = f"STILL_{act.name}"
    track.mute = False
    start = int(round(act.frame_range[0]))
    strip = track.strips.new(act.name, start, act)
    if hasattr(HQ, "bind_strip_action_slot"):
        HQ.bind_strip_action_slot(arm, strip, act)
    # bind_strip_action_slot may re-assign active action; NLA solo needs it clear.
    ad.action = None
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    log(
        f"pose arm={arm.name!r} action={act.name!r} frame={int(frame)} "
        f"mode=nla_solo strip={strip.name!r} "
        f"slot={getattr(strip, 'action_slot', None)!r}"
    )


def apply_death_action_nla_unmute(arm, act, frame: int) -> None:
    """Pose via existing NLA strips that already reference ``act`` (unmute only).

    glTF import often leaves Death01 on NLA; rebuilding strips can drop Root /
    object channels. Prefer unmute of the imported strip when present.
    """
    if act is None:
        raise RuntimeError("apply_death_action_nla_unmute: act is None")
    if arm.animation_data is None:
        raise RuntimeError(
            f"arm {arm.name!r} has no animation_data for NLA unmute of {act.name!r}"
        )
    HQ.reset_pose(arm)
    ad = arm.animation_data
    ad.action = None
    matched = []
    for track in ad.nla_tracks:
        track_hit = False
        for strip in track.strips:
            strip_act = getattr(strip, "action", None)
            if strip_act == act or (
                strip_act is not None and strip_act.name == act.name
            ):
                track.mute = False
                if hasattr(strip, "mute"):
                    strip.mute = False
                track_hit = True
                matched.append(f"{track.name}/{strip.name}")
        if not track_hit:
            track.mute = True
    if not matched:
        raise RuntimeError(
            f"no existing NLA strip for {act.name!r} on {arm.name!r}; "
            f"tracks={[(t.name, [s.name for s in t.strips]) for t in ad.nla_tracks]}"
        )
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    log(
        f"pose arm={arm.name!r} action={act.name!r} frame={int(frame)} "
        f"mode=nla_unmute strips={matched}"
    )


def apply_action(arm, name: str, frame: int) -> None:
    act = bpy.data.actions.get(name)
    if act is None:
        have = sorted(a.name for a in bpy.data.actions)
        raise RuntimeError(f"action {name!r} missing; have={have}")
    if act.name != name:
        raise RuntimeError(f"action lookup {name!r} resolved to {act.name!r}")
    apply_action_datablock(arm, act, frame)


def find_death_on_back_frame(arm, act, *, apply_fn) -> int:
    """Scan Death01 for lying + on-back using Root/bbox (not pelvis alone).

    Local 16:52: dest-native Death01 pelvis_z stayed 0.954 for frames 0–57 (lean,
    not lie-down). Root / posed AABB are the lying signals to verify.
    """
    if act is None:
        raise RuntimeError("find_death_on_back_frame: act is None")
    log_action_motion_channels(act)
    fr = tuple(act.frame_range)
    lo, hi = int(round(fr[0])), int(round(fr[1]))
    key_frames = sorted(
        {
            int(round(kp.co.x))
            for fc in act.fcurves
            for kp in fc.keyframe_points
        }
    )
    if hi < lo:
        raise RuntimeError(f"{act.name!r} has invalid frame_range {fr}")
    span = hi - lo
    step = 1 if span <= 180 else max(1, span // 90)
    candidates = sorted(set(key_frames) | set(range(lo, hi + 1, step)) | {hi, lo})
    samples = []
    best = None
    best_score = -1e9
    for f in candidates:
        apply_fn(arm, act, f)
        m = death_pose_metrics(arm)
        samples.append({"frame": f, **m})
        if m["lying"] and m["on_back"] and not m["faceplant"]:
            # Prefer flatter / lower holds with stronger on-back.
            score = (
                float(m["chest_fwd_z"]) * 2.0
                - float(m["bbox_max_z"])
                - float(m["bbox_height"]) * 0.5
            )
            if score > best_score:
                best_score = score
                best = f
    if best is None:
        raise RuntimeError(
            f"no on-back lying frame in {act.name!r} frame_range=({lo},{hi}). "
            f"Lying needs bbox_max_z<={BBOX_LYING_MAX_Z} OR bbox_height<={BBOX_LYING_MAX_HEIGHT} "
            f"OR (pelvis_z<={PELVIS_LYING_MAX_Z} and bbox_height<=1.20); "
            f"root_z=0 is NOT lying (MH Root rest false positive). "
            f"on-back needs chest_fwd_z>={CHEST_ON_BACK_MIN_Z}. "
            f"samples={samples}"
        )
    apply_fn(arm, act, best)
    m = death_pose_metrics(arm)
    log(
        f"death on-back frame chosen action={act.name!r} frame={best} "
        f"metrics={m} (scanned {len(candidates)} frames; last={hi})"
    )
    return int(best)


def assert_death_on_back(arm, act_name: str, frame: int) -> None:
    """Fail loud if Death still looks face-down / standing instead of on-back hold."""
    m = death_pose_metrics(arm)
    log(f"death on-back check action={act_name!r} frame={frame} metrics={m}")
    if not m["lying"]:
        raise RuntimeError(
            f"Death still not lying (metrics={m}) for {act_name!r}@{frame}"
        )
    if m["faceplant"]:
        raise RuntimeError(
            f"Death still is faceplant (metrics={m}) for {act_name!r}@{frame}"
        )
    if not m["on_back"]:
        raise RuntimeError(
            f"Death still is not on-back (metrics={m}) for {act_name!r}@{frame}"
        )


def fetch_orrun_still_actions(names: tuple[str, ...]) -> dict[str, object]:
    """Load exact Orrun worksuit actions for AFTER still posing (read-only).

    Punch_Cross: donor DOES pose dest (active action @ ~55%).
    Death01: investigate via HQ.copy_action + NLA solo; Root/bbox metrics (pelvis
    alone stays ~0.95 on this MH bind). Never writes the donor file.
    """
    if not ANIM_DONOR.is_file():
        raise FileNotFoundError(
            f"missing Orrun animation donor for still actions: {ANIM_DONOR}"
        )
    refuse_quaternius_orc(ANIM_DONOR)
    before_objs = set(bpy.data.objects)
    before_acts = set(bpy.data.actions)
    import_gltf(ANIM_DONOR)

    new_acts = [a for a in bpy.data.actions if a not in before_acts]
    by_name: dict[str, object] = {}
    for act in new_acts:
        # glTF may import as exact name or Name.001 when dest already has Name.
        raw = act.name
        stem = raw.rsplit(".", 1)[0] if raw.rsplit(".", 1)[-1].isdigit() else raw
        if stem in names and stem not in by_name:
            by_name[stem] = act
        if raw in names and raw not in by_name:
            by_name[raw] = act

    missing = [n for n in names if n not in by_name]
    if missing:
        have = sorted(a.name for a in new_acts)
        # Clean donor objects before failing.
        for o in list(bpy.data.objects):
            if o not in before_objs:
                bpy.data.objects.remove(o, do_unlink=True)
        raise RuntimeError(
            f"Orrun donor missing still action(s) {missing} after import; "
            f"new_actions={have}. Do not invent clips."
        )

    clones: dict[str, object] = {}
    for name in names:
        src = by_name[name]
        clone_name = f"ORRUN_STILL_{name}"
        # Drop prior clone from a previous still pass in the same Blender session.
        old = bpy.data.actions.get(clone_name)
        if old is not None:
            bpy.data.actions.remove(old)
        clone = HQ.copy_action(src, clone_name)
        clone.use_fake_user = True
        clones[name] = clone
        fr = tuple(clone.frame_range)
        log(
            f"orrun still action {name!r} -> {clone.name!r} "
            f"frame_range=({int(round(fr[0]))},{int(round(fr[1]))}) "
            f"from donor {ANIM_DONOR.name}"
        )

    # Remove donor armature + meshes (never keep leftover donor in the still scene).
    removed = []
    for o in list(bpy.data.objects):
        if o not in before_objs:
            removed.append(f"{o.type}:{o.name}")
            bpy.data.objects.remove(o, do_unlink=True)
    # Remove imported (non-clone) new actions so dest export is not polluted.
    keep = set(clones.values())
    for act in list(bpy.data.actions):
        if act not in before_acts and act not in keep:
            bpy.data.actions.remove(act)
    # Remove donor import leftovers tracking (dest arms were in before_objs).
    leftover_new = [o.name for o in bpy.data.objects if o not in before_objs]
    if leftover_new:
        raise RuntimeError(f"donor import leftovers remain: {leftover_new}")
    return clones


def head_world_pos(arm) -> Vector:
    """Skull-base end of the head bone (bone.head). Useful for mouth distance.

    Do NOT use this to prove the head rotated — bone.head is the rotation pivot,
    so a pure head-bone rotate leaves it fixed (forced_head_rotate head_delta=0).
    """
    if "head" not in arm.pose.bones:
        raise RuntimeError("dest armature missing head bone for still camera")
    pb = arm.pose.bones["head"]
    return arm.matrix_world @ pb.head


def head_motion_marker_world(arm) -> Vector:
    """A point that moves when the head bone rotates (bone.tail, not bone.head)."""
    if "head" not in arm.pose.bones:
        raise RuntimeError("dest armature missing head bone for motion marker")
    pb = arm.pose.bones["head"]
    return arm.matrix_world @ pb.tail


def force_head_pose_for_tusk_assert(arm) -> None:
    """Actually rotate the head bone (Euler XYZ). Prove tip moves (not bone.head)."""
    HQ.reset_pose(arm)
    if arm.animation_data is not None:
        arm.animation_data.action = None
        for track in arm.animation_data.nla_tracks:
            track.mute = True
    bpy.context.view_layer.update()
    tip_rest = head_motion_marker_world(arm)
    pb = arm.pose.bones["head"]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = (math.radians(55.0), 0.0, 0.0)
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()
    tip_posed = head_motion_marker_world(arm)
    delta = (tip_posed - tip_rest).length
    if delta < 0.05:
        raise RuntimeError(
            f"force_head_pose_for_tusk_assert failed: head tip delta={delta:.4f} "
            f"(rest={tuple(round(c, 4) for c in tip_rest)} "
            f"posed={tuple(round(c, 4) for c in tip_posed)}). "
            f"Head bone did not actually rotate."
        )
    log(f"forced head pose applied: tip_delta={delta:.4f}")


def chest_forward_world(arm) -> Vector:
    """Anatomical chest-forward in world space (rest MH faces armature -Y).

    Picks the bone-local axis that aligns with armature -Y in rest, then
    transforms it by the posed bone — so on-back => +Z, faceplant => -Z.
    Do NOT pick 'whichever axis points up' (that confuses back with chest).
    """
    bone_name = "spine_02" if "spine_02" in arm.pose.bones else "spine_03"
    if bone_name not in arm.pose.bones or bone_name not in arm.data.bones:
        raise RuntimeError("dest armature missing spine bone for death on-back check")
    rest_bone = arm.data.bones[bone_name]
    pb = arm.pose.bones[bone_name]
    rest_mat = rest_bone.matrix_local.to_3x3()
    armature_forward = Vector((0.0, -1.0, 0.0))
    local_axes = (
        Vector((1.0, 0.0, 0.0)),
        Vector((-1.0, 0.0, 0.0)),
        Vector((0.0, 0.0, 1.0)),
        Vector((0.0, 0.0, -1.0)),
    )
    best_local = max(local_axes, key=lambda v: float((rest_mat @ v).dot(armature_forward)))
    pose_mat = (arm.matrix_world @ pb.matrix).to_3x3()
    return (pose_mat @ best_local).normalized()


def dest_owned_meshes(arm) -> list:
    """Meshes skinned to / parented on the dest armature (nude body + tusks)."""
    out = []
    for obj in mesh_objects():
        if obj.name.startswith("Preview") or obj.name == "PreviewGround":
            continue
        if is_junk_companion_mesh(obj):
            continue
        if obj.parent == arm:
            out.append(obj)
            continue
        for mod in obj.modifiers:
            if mod.type == "ARMATURE" and mod.object == arm:
                out.append(obj)
                break
    return out


def is_dest_identity_mesh(obj) -> bool:
    """Nude body + tusks that must stay visible in AFTER stills.

    male_body is the skin. OrcTusk_* are mouth tusks. Eyes/Icosphere are junk
    (hidden separately). OrcGear_* is forbidden on this nude pass. Brow spikes
    are male_body verts — flattened in restyle, not a separate mesh.
    """
    n = obj.name
    low = n.lower()
    if is_junk_companion_mesh(obj):
        return False
    if n.startswith("OrcGear_") or "orcgear" in low:
        return False
    if n == "male_body" or low == "male_body":
        return True
    if n.startswith("OrcSkin_") or n.startswith("OrcTusk_"):
        return True
    if "tusk" in low:
        return True
    if any(k in low for k in ("body", "basemesh", "malehighpoly", "male_base", "human")):
        return True
    return False


def ensure_dest_identity_visible(arm) -> list:
    """Show nude body+tusks; keep junk hidden; refuse invented gear."""
    hide_junk_companion_meshes(arm)
    assert_no_invented_gear()
    owned = dest_owned_meshes(arm)
    for obj in owned:
        if is_junk_companion_mesh(obj):
            continue
        obj.hide_render = False
        obj.hide_viewport = False
        obj.hide_set(False)
    names = {o.name for o in owned}
    has_body = any(
        n == "male_body" or n.lower() == "male_body" or "body" in n.lower()
        for n in names
    )
    if not has_body:
        raise RuntimeError(
            f"dest still meshes missing male_body skin; have={sorted(names)}. "
            f"Olive must live on male_body (not an OrcSkin_* mesh name)."
        )
    if not any("tusk" in n.lower() or n.startswith("OrcTusk_") for n in names):
        raise RuntimeError(
            f"dest still meshes missing tusks; have={sorted(names)}. "
            f"Refusing AFTER stills that are not nude male_orc_01."
        )
    if any(n.startswith("OrcGear_") for n in names):
        raise RuntimeError(f"OrcGear_* must not appear on nude pass; have={sorted(names)}")
    # Ensure junk stays hidden even if parented on arm.
    for obj in mesh_objects():
        if is_junk_companion_mesh(obj):
            obj.hide_render = True
            obj.hide_viewport = True
            try:
                obj.hide_set(True)
            except Exception:
                pass
    if not any(is_dest_identity_mesh(o) for o in owned):
        raise RuntimeError(f"dest identity meshes missing; have={sorted(names)}")
    return [o for o in owned if is_dest_identity_mesh(o) and not o.hide_render]


def isolate_dest_for_stills(arm) -> list:
    """Remove leftover donor armatures; show nude body+tusks; hide junk."""
    removed_arms = []
    for obj in list(bpy.data.objects):
        if obj.type == "ARMATURE" and obj != arm:
            removed_arms.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed_arms:
        log(f"isolate: removed leftover armatures {removed_arms}")

    owned = ensure_dest_identity_visible(arm)
    owned_set = set(owned)
    hidden = []
    for obj in list(mesh_objects()):
        if obj.name.startswith("Preview") or obj.name == "PreviewGround":
            continue
        if is_junk_companion_mesh(obj):
            obj.hide_render = True
            obj.hide_viewport = True
            try:
                obj.hide_set(True)
            except Exception:
                pass
            hidden.append(obj.name)
            continue
        if obj in owned_set or is_dest_identity_mesh(obj):
            obj.hide_render = False
            obj.hide_viewport = False
            obj.hide_set(False)
            continue
        obj.hide_render = True
        obj.hide_viewport = True
        hidden.append(obj.name)
    if hidden:
        log(f"isolate: hidden non-identity/junk meshes {hidden}")
    extras = [o.name for o in bpy.data.objects if o.type == "ARMATURE" and o != arm]
    if extras:
        raise RuntimeError(f"isolate failed; extra armatures remain: {extras}")
    log(
        f"isolate: dest arm={arm.name!r} still_meshes="
        f"{sorted(o.name for o in owned)}"
    )
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


def setup_standing_preview(center, extent, *, look_at=None, show_head: bool = False) -> None:
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
    if look_at is None:
        target = Vector((center.x, center.y, max(center.z, 0.9)))
    else:
        target = Vector(look_at)

    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    if show_head:
        # Pull back / raise so Punch keeps dest head + tusks in frame.
        cam.location = Vector(
            (
                center.x + span * 1.55,
                center.y - span * 2.25,
                max(target.z + span * 0.20, center.z + span * 0.55, 1.75),
            )
        )
    else:
        cam.location = Vector(
            (
                center.x + span * 1.35,
                center.y - span * 1.85,
                max(center.z + span * 0.35, 1.55),
            )
        )
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
    if show_head:
        log(
            f"standing cam (head) loc={tuple(round(c, 3) for c in cam.location)} "
            f"look={tuple(round(c, 3) for c in target)}"
        )


def setup_death_preview(center, extent, *, look_at=None) -> None:
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
    if look_at is None:
        target = Vector((center.x, center.y, max(center.z, 0.15)))
    else:
        target = Vector(look_at)
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
    """Render AFTER stills on the live restyled nude scene (DEST not written yet).

    Idle/Walk: live actions (nude + mouth/tusks intent only).
    Punch: Orrun Punch_Cross on dest (~55%).
    Death: dest-native Death01 on-back; bbox/pelvis lying — never root_z=0 alone.
    """
    meshes = isolate_dest_for_stills(arm)
    apply_finished_olive_skin(arm)
    meshes = ensure_dest_identity_visible(arm)

    # Punch from Orrun (proven). Death prefers dest-native Death01.
    orrun_still = fetch_orrun_still_actions(("Punch_Cross", "Death01"))
    punch_act = orrun_still["Punch_Cross"]
    donor_death = orrun_still["Death01"]
    meshes = isolate_dest_for_stills(arm)
    apply_finished_olive_skin(arm)

    dest_death_name = resolved["Death"]
    if dest_death_name != "Death01" and "Death01" in {a.name for a in bpy.data.actions}:
        dest_death_name = "Death01"
    dest_death = bpy.data.actions.get(dest_death_name)

    death_act = None
    death_frame = None
    death_apply = None
    death_errors = []
    # Dest-native first (Arnd lock). Orrun copy_action only as fallback investigation.
    death_candidates = (
        ("dest_native_nla_unmute", dest_death, apply_death_action_nla_unmute),
        ("dest_native_nla_solo", dest_death, apply_death_action_nla_solo),
        ("dest_native_active", dest_death, apply_action_datablock),
        ("orrun_nla_solo", donor_death, apply_death_action_nla_solo),
        ("orrun_active", donor_death, apply_action_datablock),
    )
    for label_src, act, apply_fn in death_candidates:
        if act is None:
            death_errors.append(f"{label_src}: missing action")
            continue
        try:
            death_frame = find_death_on_back_frame(arm, act, apply_fn=apply_fn)
            death_act = act
            death_apply = apply_fn
            log(
                f"Death AFTER using {label_src} action={act.name!r} frame={death_frame}"
            )
            break
        except RuntimeError as exc:
            death_errors.append(f"{label_src}/{act.name}: {exc}")
            log(f"Death AFTER candidate failed ({label_src}): {exc}")
    if death_act is None or death_frame is None or death_apply is None:
        raise RuntimeError(
            "no Death01 on-back lying frame (dest-native preferred; "
            "bbox/pelvis lying — not root_z=0 FP); do not invent clips. failures="
            + " || ".join(death_errors)
        )

    frames = {
        "Idle": action_frame(resolved["Idle"], "idle"),
        "Walk": action_frame(resolved["Walk"], "walk"),
        "Punch": action_frame_for_action(punch_act, "punch"),
        "Death": death_frame,
    }
    action_for = {
        "Idle": resolved["Idle"],
        "Walk": resolved["Walk"],
        "Punch": punch_act.name,
        "Death": death_act.name,
    }
    log(
        f"still frames ({tag}): "
        + ", ".join(f"{lab}={action_for[lab]!r}@{frames[lab]}" for lab in PREVIEW_CLIPS)
    )

    out = {}
    for label in PREVIEW_CLIPS:
        frame = frames[label]
        if label == "Death":
            # Re-apply with the same method that found the lying frame.
            death_apply(arm, death_act, frame)
            assert_death_on_back(arm, death_act.name, frame)
            clip_label = death_act.name
        elif label == "Punch":
            apply_action_datablock(arm, punch_act, frame)
            clip_label = punch_act.name
        else:
            apply_action(arm, resolved[label], frame)
            clip_label = resolved[label]

        meshes = ensure_dest_identity_visible(arm)
        if not any(o.name.lower() == "male_body" for o in meshes):
            raise RuntimeError(
                f"AFTER {label} missing male_body in visible meshes; "
                f"have={sorted(o.name for o in meshes)}"
            )
        tusks_live = [
            o
            for o in meshes
            if o.name.startswith("OrcTusk_") or "tusk" in o.name.lower()
        ]
        if len(tusks_live) < 2:
            tusks_live = [
                o
                for o in bpy.data.objects
                if o.type == "MESH"
                and (o.name.startswith("OrcTusk_") or "tusk" in o.name.lower())
            ]
        # Gate the PNG Reviewer sees — numeric lock alone passed while stills floated.
        assert_tusks_in_mouth_for_current_pose(arm, tusks_live, label)

        center, extent = posed_bbox(meshes)
        if label == "Death":
            head = head_world_pos(arm)
            setup_death_preview(center, extent, look_at=head)
        elif label == "Punch":
            head = head_world_pos(arm)
            center = Vector((center.x, center.y, max(center.z, head.z * 0.55 + 0.35)))
            setup_standing_preview(center, extent, look_at=head, show_head=True)
        else:
            setup_standing_preview(center, extent)

        # Re-assert after camera setup (must not have broken bone parent).
        assert_tusks_in_mouth_for_current_pose(arm, tusks_live, f"{label}_pre_render")
        path = still_path(tag, label)
        render_png(path)
        out[label] = str(path)
        log(
            f"still {tag}/{label} arm={arm.name!r} action={clip_label!r} "
            f"frame={frame} meshes={sorted(o.name for o in meshes)} -> {path.name}"
        )
    out["_frames"] = {k: frames[k] for k in PREVIEW_CLIPS}
    out["_actions"] = {k: action_for[k] for k in PREVIEW_CLIPS}
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
    # Snapshot DEST before anything — must remain untouched until stills succeed.
    dest_before = snapshot([DEST])
    seed_mode, clip_source = seed_live_from_anim_donor()
    donor_clips = log_clip_list(clip_source)
    assert_required_clips(clip_source)
    # DEST must still be untouched after live seed (no Orrun copy onto dest).
    assert_untouched(dest_before, "DEST before restyle/stills (must not be pre-seeded)")

    arm = find_armature()
    hip_before = hip_height_z(arm)
    log(f"hip_height_z BEFORE (live seed rest)={hip_before:.4f}")
    assert_no_leg_bone_scale(arm)
    bone_count = len(arm.data.bones)
    if bone_count < 50:
        raise RuntimeError(
            f"expected ~53-bone MH bind, got {bone_count} bones on {arm.name!r}"
        )
    log(f"restyle bind bones={bone_count} arm={arm.name!r}")

    drop_weapons()
    _body_meshes, removed_garments = strip_dressed_meshes_attach_male_base(arm)
    restyle_bulk_and_jaw(arm)  # includes brow-spike flatten on male_body
    tusks = add_tusks(arm)
    hidden_junk = hide_junk_companion_meshes(arm)
    assert_no_invented_gear()
    apply_finished_olive_skin(arm)

    # Explicitly never scale gait bones after edits.
    for name in NO_SCALE_BONES:
        arm.pose.bones[name].scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    assert_no_leg_bone_scale(arm)

    hip_after = hip_height_z(arm)
    log(f"hip_height_z AFTER (live rest)={hip_after:.4f}")
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

    # AFTER stills MUST succeed before any DEST write.
    assert_untouched(dest_before, "DEST immediately before AFTER stills")
    after_previews = render_clip_stills(arm, resolved_scene, "after")
    still_frames = after_previews.pop("_frames", {})
    still_actions = after_previews.pop("_actions", {})
    assert_untouched(dest_before, "DEST after AFTER stills (export not started)")

    preserved = preserve_all_actions_for_export(arm)
    if len(preserved) < len([n for n in donor_clips if n]):
        raise RuntimeError(
            f"scene actions ({len(preserved)}) < donor clips ({len(donor_clips)}); "
            f"refusing export that would drop UAL. preserved={preserved}"
        )

    owned = dest_owned_meshes(arm)
    export_objects = [
        o
        for o in owned
        if not o.name.startswith("Preview")
        and o.name != "PreviewGround"
        and not is_junk_companion_mesh(o)
        and not o.name.startswith("OrcGear_")
    ]
    if not export_objects:
        raise RuntimeError("no mesh objects to export after nude restyle")
    # First write of DEST — only from the restyled live scene after stills passed.
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
        gear=[],  # nude pass — no invented clothes
        removed_garments=removed_garments,
    )
    packet["still_frames"] = still_frames
    packet["still_actions"] = still_actions
    packet["dest_write"] = "after_stills_only"
    packet["hidden_junk"] = hidden_junk
    packet["nude_pass"] = True
    ART_REVIEW_PACKET.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    return {
        "mode": "restyle",
        "seed_mode": seed_mode,
        "anim_donor": str(ANIM_DONOR),
        "clip_source": str(clip_source),
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
        "gear": [],
        "hidden_junk": hidden_junk,
        "removed_garments": removed_garments,
        "previews_after": after_previews,
        "still_frames": still_frames,
        "still_actions": still_actions,
        "art_review_packet": str(ART_REVIEW_PACKET),
        "clip_list_md": str(CLIP_LIST_MD),
        "uv_layout_hint": str(UV_LAYOUT),
        "lookdev": str(LOOKDEV),
        "note": (
            "Nude pass: DEST after stills; mouth tusks; male_body brow flatten; "
            "no OrcGear; Punch=Orrun Punch_Cross; Death=dest-native metrics "
            "(not root_z=0 FP); olive on male_body"
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
