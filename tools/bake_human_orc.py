# -*- coding: utf-8 -*-
"""Ambitious orc restyle on the MakeHuman 53-bone UAL-baked path.

Art / Asset Lab only. Does not write Orrun or Origin, does not author clips,
does not add bones, does not use Quaternius Orc.glb as a donor.

Arnd nude lock (PR #1): same creature / same dest — not a new body plan.
  - Delete worksuit tee/dungarees; nude male_base on the same 53-bone bind.
  - Finished olive-grey skin on male_body MH UVs (no UV-grid / checker).
  - NO invented look-dev clothes: do not call add_lookdev_gear; no OrcGear_*,
    harness, spaulder, belt, loincloth, arm/ankle wraps, cubes/tori.
  - A widened mouth with tusks IN it (head-bound), visible on
    Idle/Walk/Punch_Cross/Death01 — not cheeks, not through the chest.
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
  3. Measure the mouth aperture ONCE on the untouched face, then jaw/brow/chest
     restyle, then carve the oral cavity, then seat tusks in it. No gear.
  4. Hide junk Eyes mesh if present. Olive on male_body.
  5. AFTER stills on the live restyled scene (must succeed before any dest write).
     Two stills per clip: body framing plus a mouth close-up.
  6. Only then export skinned dest (fake_user + NLA). Scratch export path must
     not clobber the protected restyle backups.
  7. Art Reviewer packet under tools/_human_orc_bake/previews/.

Mouth / tusk approach (this pass; read before changing anything below):

  The mouth is measured, not hunted. ``tools/orc_mouth_geometry.py`` finds the
  nose tip and the chin on the mid-sagittal forward profile and places one
  aperture (centre, half-width, half-height, depth) as fractions of the
  measured head width. That aperture is the single authority for the carve, the
  tusks, the still gate and the close-up camera; nothing re-derives the mouth.

  Three root causes this replaces, all of them from the same family of mistake:

  1. The mouth was defined as a box in Y anchored on the mouth corners, but the
     corner hunt returned jaw-side verts at |x-cx| ~ 82 mm (a 164 mm wide
     "mouth"), and the mid-sagittal lips protrude ~30 mm in front of the jaw
     sides. The box therefore could only ever contain lateral verts
     (``pool=36 min_|x-cx|=0.0649``) and the lip part refused a mouth it was
     measuring in the wrong place. Tusks authored off those anchors sat near
     the jaw angle, which is why "no visible tusks" survived EXIT 0 twice.
  2. Parting lip verts cannot open a mouth: the outer rim moves and the inner
     loop seals the hole, and there is nothing behind it but more face. This
     pass bores a real concave cavity (subdividing the region first when the
     mesh is too coarse to represent one) and paints it with a dark interior
     material, so there is somewhere for a tusk to be.
  3. The restyle authored its artefacts on purpose: every offset was a step
     function of a hard selection box (jaw dz band, pec box, "dy > 10 mm"
     outlier test), so two adjacent verts straddling a boundary were torn apart
     by the full amplitude -- the chin needle, the pec spike, the torso strand.
     Every offset now runs through a smooth falloff. Separately, clearing a
     pec vert's only vertex group left it unweighted, frozen at rest while the
     mesh deformed: weights are now transferred, never deleted, and
     ``assert_all_skin_verts_bound`` enforces that centrally.
  4. The Punch torso edge (1876, 1891) at 0.2129 is NOT a restyle artefact. It
     measured the same on b4d8e69 and on af0e428, restyles sharing almost no
     torso code, because neither touches that pair: it is the donor bind with
     no blend across a seam, and adjacent verts driven by disjoint bones
     separate by whatever those bones do. Flattening or skipping restyle on the
     pair, which earlier passes tried, cannot move the number.
     ``repair_bind_seams`` fixes it at the bind — measure the posed edges over
     the poses the stills will use, blend the weights across the seams that
     tear, re-measure — and the gate now names the bones on both ends instead
     of reporting only spine and head, which are 1.00 and 0.00 on that pair and
     say nothing about what drives it.
  5. Three separate bakes each got the torso tear gate wrong in a different
     way, and the criterion now carries one condition from each. A trunk edge
     is flagged when it exceeds the absolute cap, or when ALL of:
       * ``stretch > TORSO_EDGE_MAX_STRETCH`` -- much further than it should
         have, relative. f4d2059 had none of this: ``worst_torso=0.0911``
         passed a 0.14 m cap while a ~10 mm chest edge had reached 91 mm, and
         the Punch still showed it as a jagged band.
       * ``grown > TORSO_EDGE_MIN_EXCESS_M`` -- far enough to see, absolute.
         46fc7b0 had only the ratio and refused on a 2.8 mm toe seam at 3.88x
         that had moved 8 mm.
       * ``weight gap > TORSO_EDGE_MAX_GAP`` -- driven by disjoint bones, i.e.
         actually a tear rather than deformation. 9ce780d had only the geometry
         and refused on a spine_03/upperarm_r seam whose weights differed by
         0.127. Nothing was wrong with it; smoothing had nothing to remove,
         which is why three passes could not move its 22 mm of growth. This is
         also the ONLY one of the three that smoothing can change, so it is
         what lets the repair converge -- a closed loop whose sensor and
         actuator measure different quantities does not.
     Scope is the trunk, selected positively: spine, pelvis, neck and clavicle,
     with the limb set derived from the armature. 46fc7b0 defined it as "not a
     limb" with a blacklist of twelve bone names against a bind of fifty-three,
     missing both toes, both clavicles and all thirty finger joints. Every probe
     and every still logs the trunk stretch percentiles and the biggest trunk
     edges by growth with their weight gaps, flagged or not, so a passing bake
     still says what the chest is doing.

  6. A still cannot prove tusks it cannot see. f4d2059's Punch still is a
     picture of the character's own guard hand, and its Death still is an
     overhead view of the top of a supine head. Both are correct renders of
     correct geometry. So the close-up camera direction is now chosen by
     measuring occlusion (``orc_still_visibility``, exact segment-triangle, not
     a vertex-radius test that sees through a mesh's gaps), the Punch still
     frame moves within Punch_Cross only if no angle can see past the hand, and
     a still that cannot show the tusks fails instead of shipping.

  Do not reintroduce absolute millimetre windows for the mouth. If a number
  needs to change, change the fraction and re-run the offline checks -- they
  need no Blender and take about a second each::

    python tools/orc_mouth_geometry.py     # the mouth solver's own self-test
    python tools/orc_mouth_selfcheck.py    # maw carve + tusk containment
    python tools/orc_bind_repair.py        # seam repair on modelled skinning
    python tools/orc_still_visibility.py   # projection + occlusion for stills

  The second one reads the tusk and cavity constants straight out of this file
  and replays the carve and the still gate against synthetic heads over a range
  of proportions and mesh densities. It is the cheapest way to find out that a
  tusk would be buried in the cavity wall.

Restyle rules:
  - MESH only on the existing 53-bone bind (BONE_MAP from bake_human_quaternius).
  - Tusks BONE-parented to head, seated in the carved cavity; no new bones.
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
import orc_bind_repair as BR  # noqa: E402
import orc_mouth_geometry as MG  # noqa: E402
import orc_still_visibility as SV  # noqa: E402

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
# Oral cavity interior. Dark enough that the carved maw reads as an opening in
# a still and ivory tusks separate from it.
MOUTH_INTERIOR = (0.10, 0.055, 0.055)
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
# MH head bone origin is at the skull base, not the lips. Real mouth distance
# in head-rest space is ~0.20 (local bake: 0.2053). Do not use a tight
# 0.08–0.14 cap — that rejects every real mouth vert.
HEAD_MOUTH_MAX_LOCAL = 0.28

# --- oral cavity + tusks ----------------------------------------------------
# Every number below is a fraction of the aperture that
# ``orc_mouth_geometry.solve_mouth_aperture`` measured on this head, never an
# absolute millimetre. That is the point: the failed bakes hunted the mouth
# with absolute windows (a 24 mm forward allowance anchored on the jaw sides,
# a 48 mm cap on |x-cx|, a 28 mm minimum lip gap) and the windows, not the
# mesh, decided the answer.
#
# Skull-vert selection for the head cloud and the carve. Mouth skin on the MH
# 53-bone bind is pure head; anything with neck/spine influence is jaw seam.
SKULL_HEAD_W_MIN = 0.55
SKULL_NECK_W_MAX = 0.20
SKULL_SPINE_W_MAX = 0.15
# The carve must actually open the maw: this fraction of the measured cavity
# depth has to be reached by real geometry, over at least this many verts.
# A rim that moves while the middle stays put is the 15:26 "reads closed"
# failure, and it is caught here rather than in the Reviewer's eyes.
CAVITY_MIN_ACHIEVED_DEPTH_FRAC = 0.60
CAVITY_MIN_CARVED_VERTS = 24
# Refine the mouth neighbourhood until the aperture half-width is sampled this
# many times, so the bore is a cavity rather than a triangular dent.
CAVITY_SUBDIV_TARGET_SAMPLES = 5
CAVITY_SUBDIV_REGION_R = 1.6  # normalised aperture radius gathered for cutting
CAVITY_SUBDIV_MAX_PASSES = 3
# The mouth neighbourhood is a small part of the body, so an absolute floor
# matters more than a percentage; the percentage only caps very dense meshes.
CAVITY_SUBDIV_MIN_BUDGET = 600
CAVITY_SUBDIV_MAX_ADDED_FRAC = 0.25  # of the male_body vert count
# Polygons at or above this mean falloff are painted with the interior
# material, so the bore reads dark and the lip rim stays skin.
CAVITY_INTERIOR_POLY_FALLOFF = 0.35

# Tusk seat, in aperture coordinates (u along +X, w along +Z, d into the head).
TUSK_SEAT_U_FRAC = 0.38  # canine line, not the commissure
TUSK_SEAT_W_FRAC = -0.55  # lower gum, inside the rim ellipse
# Shallow on purpose. The cavity wall ramps back out toward the rim, so depth
# off the centre line is limited; a deep seat buries the tusk in the wall
# instead of standing it in open air. TUSK_BORE_CLEARANCE_M is what enforces
# that, and this is the value that satisfies it with room to spare.
TUSK_SEAT_D_FRAC = 0.24
TUSK_AXIS_MEDIAL = 0.18  # dental-arch convergence toward the midline
TUSK_AXIS_OUTWARD = 0.15  # slight outward lean; more and the tip leaves the maw
TUSK_LENGTH_HH_FRAC = 1.30  # multiples of the aperture half-height
TUSK_RADIUS_BASE_HH_FRAC = 0.28
TUSK_RADIUS_TIP_HH_FRAC = 0.08
TUSK_SEGMENTS = 12

# Still gate, in posed aperture coordinates. One containment test replaces the
# seven overlapping distance caps that each encoded a different guess about
# where the mouth was. The pixel-failure classes those caps defended against
# are all still refused, by construction:
#   cheek float (21:10)        -> ellipse radius > 1
#   chin needle (0706a32)      -> w < -half_height
#   tip past the lip (21:56)   -> d < 0
#   buried / invisible (1116245) -> front-fraction below TUSK_MIN_FRONT_FRAC
#   Death chest spike (ac21975)  -> d > depth
TUSK_APERTURE_MARGIN = 0.0015  # ~1.5 mm of numeric slack, not a new knob
# Rigid-bind proof: an authored centroid must land where the head pose puts it.
TUSK_BIND_MAX_M = 0.004
# Fraction of tusk verts that must sit in the camera-facing front of the bore.
TUSK_FRONT_D_FRAC = 0.70  # "front" = d <= 0.70 * depth
TUSK_MIN_FRONT_FRAC = 0.50
# The tusk must span a real part of the aperture height, or it is a stub the
# still cannot show.
TUSK_MIN_W_SPAN_HH_FRAC = 0.80
# The axis must still rise through the maw rather than down the throat. With
# TUSK_AXIS_MEDIAL/OUTWARD as authored the up component is ~0.97.
TUSK_MIN_AXIS_RISE_DOT = 0.75
# Every tusk vert must stand this far in front of the cavity wall at its own
# (u, w). Without it a tusk can satisfy "inside the aperture volume" while
# being embedded in the wall: the wall ramps back out toward the rim, so depth
# available on the canine line is a fraction of the depth on the centre line.
# This is the check that separates "in the maw" from "in the flesh".
TUSK_BORE_CLEARANCE_M = 0.003
# Posed rim-tracking: the mouth rim anchor vert must keep following the head
# bone rigidly, proving the maw and the tusks have not parted company. Measured
# as deviation from its own head-rest-local position, so it is 0 at rest.
MOUTH_RIM_TRACK_MAX_M = 0.012
# Rim anchors must be near-pure head verts, or neck bleed alone would trip the
# tracking check under Death.
MOUTH_RIM_HEAD_W_MIN = 0.90

# --- jaw muzzle -------------------------------------------------------------
# Heavy-jaw offset band, measured from the head bone origin (skull base).
JAW_BAND_DZ = (-0.145, -0.055)
# Eased in/out over this much dz. Without it the band edge is a 1-vert cliff
# with the full amplitude across it, which is exactly how a needle is authored.
JAW_BAND_EDGE = 0.030
# 48 mm of forward push on a 100 mm deep face was a caricature and it also
# out-projected the nose, which destroys every landmark the mouth solver needs.
JAW_FORWARD_M = 0.012
JAW_DROP_RATIO = 0.20
# Jaw offset fades to zero inside this normalised aperture radius.
JAW_APERTURE_KEEPOUT = 1.35

# --- brow-ridge flatten -----------------------------------------------------
BROW_BAND_EDGE = 0.020  # z_rel easing at the band ends
BROW_X_EDGE = 0.018
# A vert this far forward of the forehead plane gets the full pull; nearer
# verts get a proportional share, so the "is a spike" test is not a step.
BROW_SPIKE_FULL_M = 0.012

# --- torso / bind seam ------------------------------------------------------
# Posed torso-vert outlier (Idle pec pinch / Death through-torso spike).
TORSO_SPIKE_MAX_M = 0.36
# Longest non-limb posed edge the still gate will accept. Do not raise it.
TORSO_EDGE_MAX_M = 0.14
# ...and how far a non-limb edge may stretch relative to its REST length. This
# is the criterion that matters and the absolute cap above cannot express.
# f4d2059 passed with worst_torso=0.0911: comfortably under 0.14 m, but chest
# edges on this mesh are ~10 mm at rest, so that edge was stretched ~9x and the
# Punch still showed it as a jagged band across the chest. Stretch is scale-free
# and catches a 40 mm edge that was 4 mm at rest, which no metre value can.
# Normal skin deformation stretches a well-blended edge by well under 2x; a
# weight discontinuity is what produces the rest.
TORSO_EDGE_MAX_STRETCH = 2.6
# ...and it must also have GROWN by this much. Stretch alone was 46fc7b0's
# refusal: a 2.8 mm toe seam reaching 10.8 mm is 3.88x while having moved 8 mm,
# which nobody can see. Absolute length alone was f4d2059's miss: a ~10 mm chest
# edge reaching 91 mm passed a 0.14 m cap and read as a jagged band. That one is
# 9x with 81 mm of growth, so it fails both halves and is still caught. Together
# the two say "moved far, and much further than it should have".
TORSO_EDGE_MIN_EXCESS_M = 0.015
# ...and its two verts must be driven by substantially DIFFERENT bones. This is
# the mechanism test, and the only one of the three that smoothing can change.
# 9ce780d refused on a spine_03/upperarm_r seam whose weights differed by 0.127
# -- already smooth, nothing to repair, so three smoothing passes could not move
# its 22 mm of growth. A closed loop whose sensor and actuator measure different
# things does not converge. Both measure this now.
TORSO_EDGE_MAX_GAP = 0.25
# How many of the biggest trunk edges by growth to name in the log, flagged or
# not. A passing bake should still say what the chest is doing.
TORSO_TOP_GROWTH_REPORTED = 3
# Rest edges shorter than this are treated as this long, so a degenerate edge
# cannot report an enormous ratio.
TORSO_REST_EDGE_FLOOR_M = 0.002
# Bones that count as trunk. Clavicle is included on purpose: the shoulder cap
# is body surface, not a joint that opens, and the chest band f4d2059 showed ran
# out of the pec toward it. The limb set is then everything else the armature
# drives except the head, derived from the armature rather than hand-kept — see
# ``trunk_and_limb_groups`` for why that direction matters.
TRUNK_BONE_NAMES = frozenset(
    {
        "spine_01",
        "spine_02",
        "spine_03",
        "pelvis",
        "neck_01",
        "neck",
        "clavicle_l",
        "clavicle_r",
    }
)
NON_LIMB_BONE_NAMES = TRUNK_BONE_NAMES | frozenset({"head", "Root", "root"})
# Both ends of an edge need at least this much trunk weight...
TRUNK_EDGE_MIN_W = 0.30
# ...and neither end may be this limb-driven. That is what keeps the armpit and
# the hip out: joints that legitimately open under Punch_Cross (~20 cm).
TRUNK_EDGE_MAX_LIMB_W = 0.40

# --- donor bind seam repair -------------------------------------------------
# The Punch edge (1876, 1891) at 0.2129 with spine=(1.00, 0.00) is a bind with
# no blend across a seam: adjacent verts driven by disjoint bones separate by
# whatever those bones do. It measured the same on b4d8e69 and af0e428, two
# restyles sharing almost no torso code, which is how we know the restyle never
# touched it. Repair the bind, and verify by measurement.
#
# Repair targets, inside the gate's limits so the gate has margin.
BIND_SEAM_TARGET_M = 0.12
BIND_SEAM_TARGET_STRETCH = 2.2
BIND_SEAM_TARGET_EXCESS_M = 0.012
BIND_SEAM_TARGET_GAP = 0.20
# Frames sampled per clip. The Death still chooses its on-back frame at render
# time, so one frame per clip does not prove the bind survives the still.
BIND_SEAM_PROBE_FRAMES = 6
# (dilation rings, Laplacian iterations) per attempt. Spreading the weight
# transition over 2*rings edges divides the worst posed edge by about the same
# factor, so 2 rings should already take 0.2129 well under target; the later
# attempts exist so a worse seam still converges rather than refusing.
BIND_SEAM_ATTEMPTS = ((2, 10), (3, 16), (4, 24), (6, 32))
BIND_SMOOTH_LAMBDA = 0.5
# Beyond this share of male_body the "seam" is a broken bind, not a seam, and
# re-weighting that much of the character is not a repair. Sized for a whole
# seam RING rather than a single pair: the stretch criterion is expected to
# flag the clavicle-to-spine transition around the axilla, which is a loop of
# verts and is also where the "pec/axilla pinch" keeps being reported.
BIND_SEAM_MAX_SEED_FRAC = 0.20
REHOME_MAX_PASSES = 8

# --- still visibility -------------------------------------------------------
# The one thing a reviewer asks of a still: can I see the tusks? f4d2059 passed
# every numeric gate and was reported "tusks not readable" on Punch and Death,
# because Punch_Cross holds the guard hand in front of the mouth and the Death
# camera looks at the top of a supine head. No tusk-placement gate can see
# that; only measuring the camera can.
STILL_LENS_MM = 50.0
STILL_SENSOR_MM = 36.0  # Blender's default sensor width
# Tusk samples per tusk for the visibility sweep. Occlusion is exact
# segment-triangle work, so the whole cone is not needed to know whether a
# reviewer can see it.
STILL_TUSK_SAMPLES_PER_TUSK = 6
# Occluder triangles are gathered within this many measured head widths of the
# mouth: the head, the shoulders, and in Punch the hands.
STILL_OCCLUDER_RADIUS_HEAD_WIDTHS = 3.0
# The close-up must clear both of these or the bake refuses.
STILL_MIN_VISIBLE_FRAC = 0.30
# Screen extent of the visible tusks, measured on the LARGER axis so the answer
# does not depend on camera roll — Death looks straight down the mouth axis,
# where roll is arbitrary for both the render and the measurement.
STILL_MIN_TUSK_PX = 24.0
# Blender's to_track_quat("-Z", "Y") rolls the camera to keep world +Z up, so
# the measurement has to use the same hint or its pixel extents would be
# rotated relative to the render.
STILL_CAMERA_UP = (0.0, 0.0, 1.0)

# --- mouth close-up still ---------------------------------------------------
MOUTH_CLOSEUP_RES = 720
# View directions swept around the mouth axis, straight-on first. The sweep
# exists for the poses where something is in front of the mouth.
MOUTH_CLOSEUP_AZIMUTHS = (0, 20, -20, 40, -40, 60, -60, 80, -80, 100, -100)
# Negative elevation looks up into the mouth from below, which is the natural
# way to see past a tucked chin — and Punch tucks the chin.
MOUTH_CLOSEUP_ELEVATIONS = (0, -18, 18, -36, 36)
# Fractions of Punch_Cross tried for the Punch still, nearest the canonical 55 %
# first. Only used when no camera angle at the current frame can see the maw.
PUNCH_STILL_FRAME_FRACS = (0.55, 0.50, 0.60, 0.45, 0.65, 0.40, 0.70, 0.35, 0.75)
# Camera standoff as a multiple of the measured head width. At 1.8 with a 50 mm
# lens on a 720x720 frame the shot covers ~1.35 head widths, so brow to chin is
# in frame and a 26 mm tusk is ~90 px tall. The body still, for comparison, is
# ~4.4 mm per pixel: about ten pixels of tusk.
MOUTH_CLOSEUP_REACH_HEAD_WIDTHS = 1.8
# Keep the close-up camera above the preview ground plane (Death puts the head
# on the floor, and a camera under the plane renders the plane).
MOUTH_CLOSEUP_MIN_CAM_Z = 0.10
# Mouth key placement and target irradiance at the maw, in W/m^2. The body
# rig's sun delivers ~3.4, so this lifts the cavity a little above the face
# without blowing out the ivory. Energy is computed from the standoff so it
# stays correct whatever the head scale.
MOUTH_CLOSEUP_KEY_STANDOFF = 1.1  # multiples of the camera reach
MOUTH_CLOSEUP_KEY_IRRADIANCE = 7.0

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


def still_path(tag: str, label: str, view: str = "body") -> Path:
    if view == "body":
        return PREVIEW_DIR / f"male_orc_01_{tag}_{label.lower()}.png"
    if view == "mouth":
        return PREVIEW_DIR / f"male_orc_01_{tag}_{label.lower()}_mouth.png"
    raise RuntimeError(f"still_path: unknown view {view!r}")


def write_art_review_packet(
    *,
    seed_mode: str,
    donor_clips: list[str],
    dest_clips: list[str],
    resolved: dict[str, str],
    after_previews: dict[str, str],
    mouth_previews: dict[str, str],
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
        m = Path(mouth_previews[label])
        if not m.is_file():
            raise RuntimeError(
                f"Art Reviewer AFTER mouth close-up missing ({label}): {m} — "
                f"the body still is too wide to show a tusk"
            )

    stills = {
        "after": {k: after_previews[k] for k in PREVIEW_CLIPS},
        "after_mouth": {k: mouth_previews[k] for k in PREVIEW_CLIPS},
        "expected_filenames": {
            "after": [still_path("after", lab).name for lab in PREVIEW_CLIPS],
            "after_mouth": [
                still_path("after", lab, view="mouth").name for lab in PREVIEW_CLIPS
            ],
        },
        "note": (
            "Two stills per clip: the body still for silhouette, the *_mouth "
            "close-up for the maw. Poses: Idle, Walk, Death01, Punch_Cross via "
            "resolved aliases — never invent clips. Judge tusks on the close-up: "
            "at body framing a 30 mm tusk is about ten pixels."
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
            "Mouth is measured once by tools/orc_mouth_geometry.py (nose tip + "
            "chin on the mid-sagittal profile, sizes as fractions of the "
            "measured head width) and that aperture is the only authority for "
            "the carve, the tusks, the still gate and the close-up camera.",
            "The maw is a real bored cavity with a dark interior material, not "
            "parted lip verts: parting moves the outer rim while the inner loop "
            "seals the hole, and skin behind the 'opening' hid the tusks in "
            "0706a32 and 0240d6e. The mouth neighbourhood is subdivided first "
            "when it is too coarse to represent a cavity.",
            "Tusks BONE-parented to head with Identity matrix_parent_inverse, "
            "seated and scaled entirely in aperture coordinates, and required to "
            "stand clear of the cavity wall (the wall ramps back out toward the "
            "rim, so a deep seat on the canine line is in the flesh, not the "
            "maw). Zero torso/arm radial bulk. Do NOT seat unbind edges. "
            "Stretched-edge gate 0.14.",
            "Offline checks, no Blender needed: python tools/orc_mouth_geometry.py, "
            "tools/orc_mouth_selfcheck.py, tools/orc_bind_repair.py and "
            "tools/orc_still_visibility.py. Run them after changing any mouth, "
            "tusk, bind-repair or still-framing constant.",
            "Every restyle offset runs through a smooth falloff. Hard selection "
            "boxes with step displacement authored the chin needle, the pec "
            "spike and the torso strand; the box boundary itself was the tear.",
            "Pec head/neck weight is transferred to spine_02/spine_03, never "
            "deleted: deleting a pec vert's only group left it unweighted and "
            "frozen at rest, which draws the strand. "
            "assert_all_skin_verts_bound enforces this after every weight edit, "
            "counting only weight on groups that match an actual bone — weight "
            "on a group no bone drives is inert and the vert is frozen.",
            "The Punch edge (1876,1891) at 0.2129 is the donor bind, not the "
            "restyle: identical on b4d8e69 and af0e428, which share almost no "
            "torso code. repair_bind_seams measures the posed edges over the "
            "still poses, Laplacian-blends the weights across seams that tear, "
            "and re-measures against the pre-repair edge classification so it "
            "cannot pass by reclassifying a torso edge as a limb edge.",
            "Trunk edges are flagged on the absolute cap, or on stretch AND "
            "absolute growth AND weight gap together. One condition per failed "
            "bake: f4d2059 passed 0.0911 m (9x, +81 mm) on a metre cap alone; "
            "46fc7b0 refused on 3.88x from a toe seam that moved 8 mm; 9ce780d "
            "refused on a spine_03/upperarm_r seam whose weights differed by "
            "0.127, where there was no discontinuity to repair. The gap is also "
            "the only one smoothing can change, so the repair converges. The log "
            "names the biggest trunk edges by growth with their gaps whether or "
            "not anything is flagged.",
            "Scope is the trunk, selected positively: spine, pelvis, neck and "
            "clavicle, with the limb set derived from the armature rather than "
            "hand-kept. 46fc7b0's blacklist covered twelve of fifty-three "
            "bones and classified toes and fingers as torso.",
            "No chest mesh or weight edits. flatten_chest_pinch and "
            "reassign_chest_head_weights both existed to chase that Punch edge; "
            "they reshaped the pec region, every bake carrying them was reported "
            "with a pec pinch, and their purpose is now served at the bind.",
            "Close-up camera direction is chosen by measuring occlusion, and the "
            "Punch still frame moves inside Punch_Cross only when no angle can "
            "see past the guard hand. A still that cannot show the tusks fails "
            "rather than shipping: f4d2059's Punch still was a picture of the "
            "character's own hand and its Death still was the top of a head.",
            "AFTER stills gate: aperture containment (radius, depth, front "
            "fraction, height span) + rigid-bind proof + mouth-rim tracking + "
            "torso-spike refuse; junk Eyes unlinked from collections.",
            "TWO STILLS PER CLIP — judge the maw on the *_mouth close-up, not "
            "on the body still. The body still frames a 1.8 m figure from ~5 m "
            "on a 50 mm lens at 640x800, about 4.4 mm per pixel, and on Punch "
            "the guard hand covers the mouth while on Death the camera sees the "
            "top of a supine head. body_still_tusk_visibility records what each "
            "body still actually shows; mouth_cameras records the close-up "
            "angle and the measured tusk pixel size.",
            "Jaw restyle skips neck_01 / heavy spine_03 (no Idle/Walk shred) and "
            "fades out across the mouth aperture so the carve still sees the "
            "face the aperture was solved on.",
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
            f"- **{label}** (`{actual}`): body `{still_path('after', label).name}`, "
            f"maw `{still_path('after', label, view='mouth').name}`"
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
        # Root may exist as bone "root" on MH — tolerate unknown empty groups lightly,
        # but name them: a vert weighted only to one of these is inert under the
        # Armature modifier, and that is the frozen-vert strand class.
        if missing_bones:
            log(
                f"male_base mesh {obj.name!r} vertex groups with no dest bone: "
                f"{sorted(set(missing_bones))}"
            )
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


def _clear_vg(obj, vert_index: int, group_index) -> bool:
    if group_index is None:
        return False
    vg = None
    for g in obj.vertex_groups:
        if g.index == group_index:
            vg = g
            break
    if vg is None:
        return False
    try:
        vg.remove([int(vert_index)])
        return True
    except RuntimeError:
        return False


def _arm_weight(vert, upper_l, upper_r, lower_l, lower_r, hand_l, hand_r) -> float:
    return max(
        vg_weight(vert, upper_l),
        vg_weight(vert, upper_r),
        vg_weight(vert, lower_l),
        vg_weight(vert, lower_r),
        vg_weight(vert, hand_l),
        vg_weight(vert, hand_r),
    )


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


def restyle_face(arm, aperture) -> None:
    """Heavy jaw + brow flatten. No bulk, no chest edits, no invented gear.

    Radial torso/arm bulk is gone rather than multiplied by zero: it drew the
    0706a32 pec-armpit spike and the Walk neck tear, and the orc read comes
    from the maw, the tusks and the skin. The chest edits are gone too (see
    below), so what remains is the jaw offset and the brow flatten.

    Neck/chest tear guard: jaw edits only on head-dominant face verts, never on
    neck_01 / spine_03-heavy verts. Those sat in the old dz band and shredded
    under Walk.

    Chin-needle fix: the jaw offset used to be a step function of ``dz`` over a
    hard [-0.145, -0.055] band with amplitude up to 48 mm, so two adjacent verts
    straddling the band edge were torn 48 mm apart. That is the 0706a32 Idle
    "chin needle" -- authored on purpose by the selection box. The offset is now
    eased in over ``JAW_BAND_EDGE``, its amplitude is a sane muzzle, and it
    fades out across the measured mouth aperture so the carve that follows still
    sees the face the aperture was solved on. A 48 mm muzzle also out-projected
    the nose, which destroys the landmarks the aperture is measured from.
    """
    assert_no_leg_bone_scale(arm)
    if "head" not in arm.data.bones:
        raise RuntimeError("53-bone bind missing head bone for jaw restyle")
    head_z = float(HQ.rest_world(arm, "head").to_translation().z)
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
        spine3_i = vg_index(obj, "spine_03")
        arm_groups = (
            vg_index(obj, "upperarm_l"),
            vg_index(obj, "upperarm_r"),
            vg_index(obj, "lowerarm_l"),
            vg_index(obj, "lowerarm_r"),
            vg_index(obj, "hand_l"),
            vg_index(obj, "hand_r"),
        )
        ys = [v.co.y for v in me.vertices]
        cy = 0.5 * (min(ys) + max(ys))

        face_edits = 0
        seam_skipped = 0
        worst_offset = 0.0
        for v in me.vertices:
            hw = vg_weight(v, head_i)
            nw = vg_weight(v, neck_i)
            s3w = vg_weight(v, spine3_i)
            arm_w = _arm_weight(v, *arm_groups)
            # Idle/Walk neck shred: never jaw-edit the neck seam or the upper
            # chest. A cliff between spine_03 pecs and spine_02 pinched the
            # sternum on Idle and Death stretched it into a through-torso spike.
            if nw >= 0.05 or (
                (s3w >= 0.22 and hw < 0.55 and arm_w < 0.30)
                or (s3w >= 0.40 and hw < 0.70)
            ):
                seam_skipped += 1
                continue
            is_face = (
                hw >= 0.60
                and hw >= nw + 0.35
                and hw >= s3w + 0.30
                and nw < 0.12
                and s3w < 0.25
            )
            if not is_face or v.co.y >= cy + 0.02:
                continue
            band = MG.band_falloff(
                float(v.co.z) - head_z, JAW_BAND_DZ[0], JAW_BAND_DZ[1], JAW_BAND_EDGE
            )
            if band <= 0.0:
                continue
            u, w, _d = aperture.aperture_coords(
                (float(v.co.x), float(v.co.y), float(v.co.z))
            )
            keep_out = MG.smoothstep(
                min(1.0, aperture.radial(u, w) / JAW_APERTURE_KEEPOUT)
            )
            amp = JAW_FORWARD_M * band * keep_out * min(1.0, hw)
            if amp <= 0.0:
                continue
            # Do NOT copysign-X the midline. d1f412a shoved every mouth vert
            # ~50 mm out, the commissure pool bottomed out at |x-cx|=65 mm, and
            # the mid-mouth hunt then found nothing.
            v.co.y -= amp
            v.co.z -= amp * JAW_DROP_RATIO
            worst_offset = max(worst_offset, amp)
            face_edits += 1

        me.update()
        log(
            f"restyled mesh {obj.name!r} verts={len(me.vertices)} "
            f"head_z={head_z:.4f} jaw_edits={face_edits} "
            f"worst_jaw_offset={worst_offset:.4f} seam_skipped={seam_skipped}"
        )

    flatten_male_body_brow_spikes(arm, aperture)
    # No chest edits. flatten_chest_pinch and reassign_chest_head_weights both
    # existed to chase the Punch edge (1876, 1891), which f4d2059 established is
    # a donor bind seam and repair_bind_seams now fixes at its actual root. What
    # they left behind was a reshaped pec region: the flatten pulled the pec
    # apex back toward a box median and pushed the sternum forward, and every
    # bake carrying it was reported with a "pec pinch". They are the only code
    # deliberately deforming the area the artefact keeps appearing in, and their
    # stated purpose is now served by a measured repair, so they are gone.
    # One invariant covering every weight edit above: a skin vert with no
    # remaining bone influence is frozen at rest object space while the rest of
    # the mesh deforms, which draws exactly the 0240d6e "torso/pec strand".
    # Seam repair is not done here — it needs the final mesh and the still
    # poses, so ``repair_bind_seams`` runs after the carve.
    assert_all_skin_verts_bound(arm, "after restyle weight edits")


def flatten_male_body_brow_spikes(arm, aperture) -> int:
    """Flatten forward brow-ridge spikes on male_body (not Eyes, not a brow mesh).

    Dest GLB has Eyes + male_body (+ tusks/gear historically). Look-dev only painted
    a 2D heavy brow — the script never authors eyebrows. Spikes that remain after
    hiding Eyes are male_body verts (oversized prior face band / residual ridge).
    Pull those verts back toward the forehead plane.

    Like the jaw and the pec plate, the pull is eased across the band and across
    the "is this a spike" threshold, so flattening a ridge cannot itself tear a
    new one at the band edge. ``aperture`` is only used to keep the flatten off
    the mouth.
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
            band = MG.band_falloff(z_rel, 0.875, 0.955, BROW_BAND_EDGE)
            if band <= 0.0:
                continue
            side = MG.band_falloff(abs(v.co.x - cx), -0.090, 0.090, BROW_X_EDGE)
            if side <= 0.0:
                continue  # temples / sides — leave
            u, w, _d = aperture.aperture_coords(
                (float(v.co.x), float(v.co.y), float(v.co.z))
            )
            if aperture.radial(u, w) <= 1.0:
                continue  # the mouth aperture is not a brow ridge
            # Spike = verts pushed forward of the forehead plane (-Y in MH rest).
            protrusion = (forehead_y - 0.008) - float(v.co.y)
            if protrusion <= 0.0:
                continue
            ramp = MG.smoothstep(min(1.0, protrusion / BROW_SPIKE_FULL_M))
            weight = 0.75 * band * side * ramp
            if weight <= 0.0:
                continue
            target_y = forehead_y - 0.004
            v.co.y = (1.0 - weight) * float(v.co.y) + weight * target_y
            v.co.z -= 0.003 * hw * band * ramp
            flattened += 1
        me.update()
        log(
            f"brow-spike flatten mesh={obj.name!r} verts_adjusted={flattened} "
            f"forehead_y={forehead_y:.4f} (male_body face verts — not Eyes/neck)"
        )
    return flattened


def vg_by_index(obj, group_index):
    if group_index is None:
        return None
    for g in obj.vertex_groups:
        if g.index == group_index:
            return g
    return None


def vertex_group_name(obj, group_index) -> str:
    vg = vg_by_index(obj, group_index)
    return vg.name if vg is not None else f"<gone:{group_index}>"


def armature_bone_groups(obj, arm) -> dict:
    """Vertex group index -> bone name, for groups the armature can actually drive.

    A vertex group whose name is not a bone on the dest armature is inert: the
    Armature modifier ignores it. A vert weighted ONLY to such groups is
    frozen at its rest object-space position while the rest of the mesh
    deforms, even though ``vert.groups`` makes it look bound -- and in the
    pixels that is indistinguishable from an unweighted vert.

    This is the distinction the 1876/1891 Punch edge needed. It measured
    exactly 0.2129 on b4d8e69 and again on af0e428, two restyles that share
    almost no torso code, which means the restyle was never involved: one end
    of that edge barely moves, so the length is a function of the donor bind and
    the Punch pose alone. A weight total that counts every group, bone or not,
    cannot see a frozen vert, which is why the earlier bound-vert invariant
    passed on one.
    """
    bones = arm.data.bones
    return {
        int(vg.index): vg.name for vg in obj.vertex_groups if vg.name in bones
    }


def bone_weight_map(vert, bone_groups: dict) -> dict:
    """Weights of ``vert`` on groups the armature drives, pruned of zeros."""
    out = {}
    for g in vert.groups:
        gi = int(g.group)
        w = float(g.weight)
        if gi in bone_groups and w > 0.0:
            out[gi] = w
    return out


def effective_bind_weight(vert, bone_groups: dict) -> float:
    return sum(bone_weight_map(vert, bone_groups).values())


def log_inert_vertex_groups(obj, arm) -> list[str]:
    """Name the vertex groups on ``obj`` that no bone will ever drive."""
    bones = arm.data.bones
    inert = sorted(vg.name for vg in obj.vertex_groups if vg.name not in bones)
    log(
        f"{obj.name!r} vertex groups with no matching bone (inert under the "
        f"Armature modifier): {inert or '(none)'}"
    )
    return inert


def write_bone_weights(obj, index: int, weights: dict, bone_groups: dict) -> None:
    """Replace a vert's bone weights with ``weights``, transactionally.

    Validated before anything is written, so a vert is never left mid-edit with
    part of its influence removed.
    """
    if not weights:
        raise RuntimeError(
            f"{obj.name!r} vert {index}: refusing to write an empty bone weight "
            f"set — that is the frozen-vert strand class"
        )
    for gi in weights:
        if gi not in bone_groups:
            raise RuntimeError(
                f"{obj.name!r} vert {index}: weight on group "
                f"{vertex_group_name(obj, gi)!r} which is not an armature bone"
            )
        if vg_by_index(obj, gi) is None:
            raise RuntimeError(
                f"{obj.name!r} vert {index}: vertex group index {gi} vanished"
            )
    old = {
        int(g.group)
        for g in obj.data.vertices[index].groups
        if int(g.group) in bone_groups
    }
    for gi, w in weights.items():
        vg_by_index(obj, gi).add([int(index)], float(w), "REPLACE")
    for gi in old - set(weights):
        _clear_vg(obj, index, gi)


def _mesh_adjacency(me) -> list:
    adj = [[] for _ in me.vertices]
    for e in me.edges:
        a, b = int(e.vertices[0]), int(e.vertices[1])
        adj[a].append(b)
        adj[b].append(a)
    return adj


def rehome_unbound_verts(arm, label: str) -> int:
    """Give every skin vert real bone influence, averaged from its neighbours.

    Runs before any weight edit or gate, because everything downstream assumes
    the bind is complete. The averaging itself lives in ``orc_bind_repair``,
    which is tested offline.
    """
    total = 0
    for obj in skinned_meshes(arm):
        if is_junk_companion_mesh(obj) or obj.name.startswith("OrcTusk_"):
            continue
        bone_groups = armature_bone_groups(obj, arm)
        log_inert_vertex_groups(obj, arm)
        if not bone_groups:
            raise RuntimeError(
                f"{label}: {obj.name!r} has no vertex group matching any bone on "
                f"{arm.name!r} — the mesh is not bound to this armature at all"
            )
        me = obj.data
        cur = [bone_weight_map(v, bone_groups) for v in me.vertices]
        unbound = {i for i, w in enumerate(cur) if sum(w.values()) <= 1e-6}
        if not unbound:
            log(f"{label}: {obj.name!r} every vert has bone influence already")
            continue
        sample = sorted(unbound)[:8]
        log(
            f"{label}: {obj.name!r} {len(unbound)} vert(s) have no bone influence "
            f"(e.g. {sample}); their groups: "
            + "; ".join(
                f"{i}:"
                + str(
                    {
                        vertex_group_name(obj, int(g.group)): round(float(g.weight), 3)
                        for g in me.vertices[i].groups
                    }
                )
                for i in sample
            )
        )
        adj = _mesh_adjacency(me)
        try:
            fixed = BR.rehome_from_neighbours(
                adj, cur, unbound, max_passes=REHOME_MAX_PASSES
            )
        except BR.BindRepairError as exc:
            raise RuntimeError(f"{label}: {obj.name!r} {exc}") from exc
        for i, w in sorted(fixed.items()):
            write_bone_weights(obj, i, w, bone_groups)
        total += len(fixed)
        log(
            f"{label}: {obj.name!r} re-homed {len(fixed)} vert(s) onto their "
            f"neighbours' averaged bone weights"
        )
    return total


def assert_all_skin_verts_bound(arm, label: str) -> None:
    """Every skin vert must have weight on a bone the armature actually drives.

    This is the single invariant behind the strand artefacts. A vert the
    armature cannot move does not follow the pose at all: it sits at rest
    object space while its neighbours move, and the edges to those neighbours
    render as a spike from the body to nowhere. Weight edits are allowed to
    move influence around; they are never allowed to remove all of it.

    Note "a bone the armature actually drives" — weight on a vertex group with
    no matching bone counts for nothing, and reporting such a vert as bound is
    what let a frozen one reach the Punch still.
    """
    for obj in skinned_meshes(arm):
        if is_junk_companion_mesh(obj) or obj.name.startswith("OrcTusk_"):
            continue
        bone_groups = armature_bone_groups(obj, arm)
        if not bone_groups:
            raise RuntimeError(
                f"{label}: {obj.name!r} has no vertex group matching a bone on "
                f"{arm.name!r}"
            )
        unbound = [
            int(v.index)
            for v in obj.data.vertices
            if effective_bind_weight(v, bone_groups) <= 1e-6
        ]
        if unbound:
            detail = "; ".join(
                f"{i}:"
                + str(
                    {
                        vertex_group_name(obj, int(g.group)): round(float(g.weight), 3)
                        for g in obj.data.vertices[i].groups
                    }
                )
                for i in unbound[:6]
            )
            raise RuntimeError(
                f"{label}: {obj.name!r} has {len(unbound)} vert(s) with no bone "
                f"influence {unbound[:12]}{'...' if len(unbound) > 12 else ''} — "
                f"their groups are [{detail}]. Such a vert stays at rest while "
                f"the mesh deforms and draws the pec/torso strand; refusing to "
                f"continue"
            )
        log(
            f"{label}: {obj.name!r} all {len(obj.data.vertices)} verts driven by "
            f"{len(bone_groups)} bone group(s)"
        )


def spine_weight(vert, spine_groups) -> float:
    """Trunk-core weight: the spine chain only."""
    return max(vg_weight(vert, gi) for gi in spine_groups)


def group_max_weight(vert, group_indices) -> float:
    if not group_indices:
        return 0.0
    return max(vg_weight(vert, gi) for gi in group_indices)


def trunk_and_limb_groups(body, arm) -> tuple:
    """Split male_body's bone groups into trunk, limb, and neither.

    Single owner of "is this vert part of the body a tear would read on".

    The trunk set is written out; the limb set is everything else the armature
    drives, minus the head. That direction matters. 46fc7b0 defined the scope as
    "not a limb" using a blacklist of twelve bone names against a bind of
    fifty-three: it missed ``ball_l``/``ball_r``, ``clavicle_l``/``clavicle_r``
    and all thirty finger joints, so a 2.8 mm toe seam between ``ball_l`` and
    ``foot_l`` was classified as a torso edge and refused the bake. A hand-kept
    list of limbs can always be incomplete; a list derived from the armature
    cannot.

    ``clavicle`` counts as trunk on purpose: the shoulder cap is body surface,
    not a joint that opens, and the chest band f4d2059 showed ran out of the pec
    toward it. What must stay out of scope is the armpit — clavicle blended with
    ``upperarm`` — because Punch_Cross legitimately opens that ~20 cm.
    """
    bone_groups = armature_bone_groups(body, arm)
    trunk = [gi for gi, name in bone_groups.items() if name in TRUNK_BONE_NAMES]
    limb = [
        gi for gi, name in bone_groups.items() if name not in NON_LIMB_BONE_NAMES
    ]
    if not trunk:
        raise RuntimeError(
            f"{body.name!r} has no vertex group among {sorted(TRUNK_BONE_NAMES)} — "
            f"cannot tell the trunk from the limbs"
        )
    log(
        f"trunk/limb split on {body.name!r}: trunk="
        f"{sorted(bone_groups[gi] for gi in trunk)} "
        f"limb={len(limb)} group(s) "
        f"{sorted(bone_groups[gi] for gi in limb)[:8]}"
        f"{'...' if len(limb) > 8 else ''}"
    )
    return trunk, limb


def stretch_gate_context(body, arm) -> dict:
    """Per-vert trunk/limb weights, the edge list, and REST edge lengths.

    Built once and shared by ``assert_no_torso_spike`` and the bind repair, so
    the repair cannot disagree with the gate about which edges are trunk edges
    or about how far they have stretched.
    """
    me = body.data
    trunk_gis, limb_gis = trunk_and_limb_groups(body, arm)
    trunk = [group_max_weight(v, trunk_gis) for v in me.vertices]
    limb = [group_max_weight(v, limb_gis) for v in me.vertices]
    scale = body_world_scale(body)
    edges = []
    rest = []
    for e in me.edges:
        a, b = int(e.vertices[0]), int(e.vertices[1])
        edges.append((a, b))
        rest.append(
            max(
                (me.vertices[a].co - me.vertices[b].co).length * scale,
                TORSO_REST_EDGE_FLOOR_M,
            )
        )
    ctx = {"trunk": trunk, "limb": limb, "edges": edges, "rest": rest}
    in_scope = sum(1 for a, b in edges if is_trunk_edge(ctx, a, b))
    log(
        f"trunk scope: {in_scope} of {len(edges)} male_body edges have both ends "
        f"on the trunk (trunk weight >= {TRUNK_EDGE_MIN_W}, limb weight < "
        f"{TRUNK_EDGE_MAX_LIMB_W})"
    )
    return ctx


def is_trunk_edge(ctx: dict, a: int, b: int) -> bool:
    """True when BOTH ends sit on the trunk and neither is limb-driven.

    Out of scope by construction: the armpit and the hip (a joint that opens),
    the hands and feet, and the head — which includes the carved maw, whose long
    bore edges are not a torso defect.
    """
    if ctx["trunk"][a] < TRUNK_EDGE_MIN_W or ctx["trunk"][b] < TRUNK_EDGE_MIN_W:
        return False
    return (
        ctx["limb"][a] < TRUNK_EDGE_MAX_LIMB_W
        and ctx["limb"][b] < TRUNK_EDGE_MAX_LIMB_W
    )


def make_edge_gap_fn(body, arm):
    """Weight gap between two verts, memoised, for candidate edges only.

    Computing gaps for all 30 000 edges would be wasted work: only edges that
    already look stretched need the mechanism test, and that is a handful. Reads
    live weights, so it cannot go stale across a repair pass.
    """
    bone_groups = armature_bone_groups(body, arm)
    verts = body.data.vertices
    memo = {}

    def gap(a: int, b: int) -> float:
        for i in (a, b):
            if i not in memo:
                memo[i] = bone_weight_map(verts[i], bone_groups)
        return BR.weight_gap(memo[a], memo[b])

    return gap


def scan_torso_edges(
    ctx: dict,
    verts_w: list,
    gap_fn,
    *,
    limit_m: float,
    limit_stretch: float,
    min_excess_m: float,
    max_gap: float,
) -> dict:
    """Measure every trunk posed edge against the tear criteria.

    A trunk edge is flagged when it exceeds ``limit_m`` outright, or when all
    three of these hold. Each answers a different question, and every one of
    them was learned from a bake that got it wrong:

    * ``stretch > limit_stretch`` -- much further than it should have, relative.
      f4d2059 had none of this and passed a ~10 mm chest edge that reached
      91 mm.
    * ``grown > min_excess_m`` -- far enough to see, absolute. 46fc7b0 had only
      the ratio and refused on a 2.8 mm toe seam at 3.88x that had moved 8 mm.
    * ``gap > max_gap`` -- driven by disjoint bones, i.e. actually a tear.
      9ce780d had only the geometry and refused on a spine_03/upperarm_r seam
      whose weights differed by 0.127; there was no discontinuity to repair, so
      three smoothing passes could not move it. This is also the only one of the
      three that smoothing can change, which is what lets the repair converge.

    The absolute cap stays unconditional: geometry that absurd is refused
    whatever caused it.
    """
    worst_m = 0.0
    worst_m_pair = (-1, -1)
    worst_s = 0.0
    worst_s_pair = (-1, -1)
    worst_s_len = 0.0
    worst_s_rest = 0.0
    out_of_scope_m = 0.0
    out_of_scope_s = 0.0
    over = []
    near_miss = []
    growth = []
    stretches = []
    for k, (a, b) in enumerate(ctx["edges"]):
        d = (verts_w[a] - verts_w[b]).length
        rest = ctx["rest"][k]
        if not is_trunk_edge(ctx, a, b):
            if d > out_of_scope_m:
                out_of_scope_m = d
            s_out = d / rest
            if s_out > out_of_scope_s:
                out_of_scope_s = s_out
            continue
        s = d / rest
        stretches.append(s)
        growth.append((d - rest, d, rest, a, b))
        if d > worst_m:
            worst_m = d
            worst_m_pair = (a, b)
        if s > worst_s:
            worst_s = s
            worst_s_pair = (a, b)
            worst_s_len = d
            worst_s_rest = rest
        if d > limit_m:
            over.append((d, s, rest, gap_fn(a, b), a, b))
        elif s > limit_stretch and (d - rest) > min_excess_m:
            g = gap_fn(a, b)
            if g > max_gap:
                over.append((d, s, rest, g, a, b))
            else:
                near_miss.append((d, s, rest, g, a, b))
    stretches.sort()
    growth.sort(reverse=True)

    def pct(f: float) -> float:
        if not stretches:
            return 0.0
        i = int(round(f * (len(stretches) - 1)))
        return stretches[max(0, min(len(stretches) - 1, i))]

    top = [
        (d, rest, gap_fn(a, b), a, b)
        for _g, d, rest, a, b in growth[:TORSO_TOP_GROWTH_REPORTED]
    ]
    return {
        "worst_m": worst_m,
        "worst_m_pair": worst_m_pair,
        "worst_stretch": worst_s,
        "worst_stretch_pair": worst_s_pair,
        "worst_stretch_len": worst_s_len,
        "worst_stretch_rest": worst_s_rest,
        "out_of_scope_m": out_of_scope_m,
        "out_of_scope_stretch": out_of_scope_s,
        "over": over,
        "near_miss": near_miss,
        "top_growth": top,
        "n": len(stretches),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p99": pct(0.99),
        "p999": pct(0.999),
    }


def format_stretch_stats(scan: dict) -> str:
    """Trunk edge distribution, so the limits stay calibrated against bakes.

    Reports the biggest trunk edges by GROWTH with their weight gaps, whether or
    not anything was flagged. That is the evidence the last four bakes each
    lacked: a passing bake now says what the chest is actually doing, so a
    pixel artefact that slips through arrives with numbers attached.
    """
    excess = scan["worst_stretch_len"] - scan["worst_stretch_rest"]
    top = "; ".join(
        f"({a},{b}) {d * 1000:.1f} mm from {rest * 1000:.1f} mm "
        f"(+{(d - rest) * 1000:.1f} mm, gap {g:.2f})"
        for d, rest, g, a, b in scan["top_growth"]
    )
    near = ""
    if scan["near_miss"]:
        d, sr, rest, g, a, b = max(scan["near_miss"], key=lambda o: o[0] - o[2])
        near = (
            f"; {len(scan['near_miss'])} stretched but smoothly bound "
            f"(worst ({a},{b}) {d * 1000:.1f} mm, {sr:.2f}x, "
            f"+{(d - rest) * 1000:.1f} mm, gap {g:.2f})"
        )
    return (
        f"trunk n={scan['n']} stretch p50={scan['p50']:.2f} p90={scan['p90']:.2f} "
        f"p99={scan['p99']:.2f} p99.9={scan['p999']:.2f} "
        f"max={scan['worst_stretch']:.2f} at {scan['worst_stretch_pair']} "
        f"({scan['worst_stretch_len'] * 1000:.1f} mm from "
        f"{scan['worst_stretch_rest'] * 1000:.1f} mm rest, +{excess * 1000:.1f} mm); "
        f"top growth: {top}{near}; out of scope: worst "
        f"{scan['out_of_scope_m'] * 1000:.1f} mm / "
        f"{scan['out_of_scope_stretch']:.2f}x"
    )


def describe_vert_bind(body, arm, index: int) -> str:
    """Bone weights of one vert, by name, for diagnostics.

    Five bakes refused on verts (1876, 1891) while reporting only spine and
    head weights, which are 1.00 and 0.00 on that pair and say nothing about
    what is actually driving them.
    """
    bone_groups = armature_bone_groups(body, arm)
    v = body.data.vertices[index]
    named = {
        vertex_group_name(body, int(g.group)): round(float(g.weight), 3)
        for g in v.groups
        if float(g.weight) > 0.0
    }
    eff = effective_bind_weight(v, bone_groups)
    return f"{index}: groups={named} effective_bone_weight={eff:.3f}"


def smooth_bind_weights(body, arm, seed: set, *, rings: int, iterations: int) -> int:
    """Spread a hard weight discontinuity over several vertex rings.

    Two adjacent verts driven by disjoint bones tear apart under any pose that
    separates those bones. That is a bind defect, not a restyle artefact, and
    moving rest positions cannot fix it. The repair is to blend the weights so
    neighbours share influence.

    Blending a single pair is not enough: it moves the tear one edge outward.
    So dilate the seed, hold the outer ring fixed, and Laplacian-smooth the
    interior — see ``orc_bind_repair``, where the algorithm and its guarantees
    (no new extremes, monotone in the worst weight gap) are tested offline.
    """
    me = body.data
    bone_groups = armature_bone_groups(body, arm)
    adj = _mesh_adjacency(me)
    region = BR.dilate(adj, seed, rings)
    interior = BR.interior_of(adj, region)
    if not interior:
        raise RuntimeError(
            f"smooth_bind_weights: dilating {len(seed)} seed vert(s) by {rings} "
            f"ring(s) produced no interior to smooth (region={len(region)})"
        )
    cur = [bone_weight_map(v, bone_groups) for v in me.vertices]
    updates = BR.smooth_weights_jacobi(
        adj, cur, interior, lam=BIND_SMOOTH_LAMBDA, iterations=iterations
    )
    for i, w in sorted(updates.items()):
        write_bone_weights(body, i, w, bone_groups)
    log(
        f"smoothed bind weights on {len(updates)} vert(s) "
        f"(seed={len(seed)} dilated {rings} ring(s) -> region={len(region)}, "
        f"interior={len(interior)}, {iterations} Jacobi iterations, "
        f"lambda={BIND_SMOOTH_LAMBDA})"
    )
    return len(updates)


def bind_probe_poses(arm) -> list:
    """(label, action, frames) covering the poses the still gate will judge.

    Several frames per clip, not just the still frame: the Death still picks its
    on-back frame at render time, so a bind that only survives one frame per
    clip is not repaired.
    """
    have = {a.name: a for a in bpy.data.actions}
    kinds = {"Idle": "idle", "Walk": "walk", "Punch": "punch", "Death": "death"}
    out = []
    for label, candidates in REQUIRED_CLIP_GROUPS:
        act = None
        for name in candidates:
            act = have.get(name)
            if act is not None:
                break
        if act is None:
            raise RuntimeError(
                f"bind_probe_poses: no {label} action in the scene (tried "
                f"{list(candidates)}); have={sorted(have)[:20]} — cannot prove "
                f"the bind survives the poses the stills will use"
            )
        fr = tuple(act.frame_range)
        lo, hi = int(round(fr[0])), int(round(fr[1]))
        frames = {int(action_frame_for_action(act, kinds[label]))}
        if hi > lo:
            for k in range(BIND_SEAM_PROBE_FRAMES):
                frames.add(
                    lo + int(round((hi - lo) * k / (BIND_SEAM_PROBE_FRAMES - 1)))
                )
        out.append((label, act, sorted(frames)))
        log(f"bind probe {label}: {act.name!r} frames={sorted(frames)}")
    return out


def probe_stretched_bind_seams(arm, body, ctx: dict, poses: list) -> tuple:
    """Worst trunk posed edge, absolute and relative, across every probe pose."""
    over = {}
    worst_m = 0.0
    worst_m_pair = (-1, -1)
    worst_s = 0.0
    worst_s_pair = (-1, -1)
    worst_s_len = 0.0
    worst_at = "(none)"
    worst_out_of_scope = 0.0
    worst_scan = None
    for label, act, frames in poses:
        for f in frames:
            apply_action_datablock(arm, act, int(f), quiet=True)
            verts_w = _evaluated_mesh_verts_world(body)
            if len(verts_w) != len(body.data.vertices):
                raise RuntimeError(
                    f"bind probe {label}@{f}: eval vert count {len(verts_w)} != "
                    f"{len(body.data.vertices)}"
                )
            scan = scan_torso_edges(
                ctx,
                verts_w,
                make_edge_gap_fn(body, arm),
                limit_m=BIND_SEAM_TARGET_M,
                limit_stretch=BIND_SEAM_TARGET_STRETCH,
                min_excess_m=BIND_SEAM_TARGET_EXCESS_M,
                max_gap=BIND_SEAM_TARGET_GAP,
            )
            if scan["worst_m"] > worst_m:
                worst_m = scan["worst_m"]
                worst_m_pair = scan["worst_m_pair"]
            if scan["worst_stretch"] > worst_s:
                worst_s = scan["worst_stretch"]
                worst_s_pair = scan["worst_stretch_pair"]
                worst_s_len = scan["worst_stretch_len"]
                worst_at = f"{label}:{act.name}@{f}"
                worst_scan = scan
            worst_out_of_scope = max(worst_out_of_scope, scan["out_of_scope_m"])
            for d, s, rest, g, a, b in scan["over"]:
                key = (a, b)
                prev = over.get(key)
                if prev is None or (d - rest) > (prev[0] - prev[2]):
                    over[key] = (d, s, rest, g)
    return over, {
        "worst_m": worst_m,
        "worst_m_pair": worst_m_pair,
        "worst_stretch": worst_s,
        "worst_stretch_pair": worst_s_pair,
        "worst_stretch_len": worst_s_len,
        "at": worst_at,
        "out_of_scope_m": worst_out_of_scope,
        "stats": format_stretch_stats(worst_scan) if worst_scan else "(no scan)",
    }


def repair_bind_seams(arm) -> int:
    """Repair the donor bind until no torso edge tears under the still poses.

    This is the fix for ``Punch:Punch_Cross@13 stretched male_body torso edge
    0.2129 verts=(1876, 1891) spine=(1.00,0.00) head=(0.00,0.00)``. Two facts
    pin it down:

      * 0.2129 was reported identically on b4d8e69 and on af0e428, restyles
        that share almost no torso code. Neither touches that vertex pair, so
        flattening or skipping restyle on it — what the previous passes tried —
        could never move the number.
      * spine=(1.00, 0.00) with head=(0.00, 0.00) describes a bind with no
        blend across a seam. Adjacent verts driven by disjoint bones separate
        by whatever those bones do, and Punch_Cross throws the shoulder across
        the body.

    So repair the bind, at the bind. Measure the posed edges over the poses the
    stills will use, blend the weights across the seams that tear, and
    re-measure. The stopping condition is the measurement rather than a guess,
    and if it will not converge it fails with the bone names instead of leaving
    the next bake to rediscover the same pair.
    """
    body = male_body_mesh(arm)
    poses = bind_probe_poses(arm)
    # This is a measurement pass, so leave the armature exactly as found.
    # ``apply_action_datablock`` zeroes the object location/rotation, and
    # ``hip_height_z`` reads through ``arm.matrix_world`` — a probe that shifted
    # the object would show up as a pelvis-moved failure much later.
    arm_basis = arm.matrix_basis.copy()
    # Classify the edges ONCE, before any weight moves. Smoothing pushes arm
    # weight onto chest verts, so a rebuilt classification could promote a torn
    # edge to "limb" and let the repair pass by reclassification instead of by
    # shortening anything. Measuring against the pre-repair classification
    # keeps the improvement geometric.
    ctx = stretch_gate_context(body, arm)
    smoothed = 0
    stats = {}
    for attempt, (rings, iterations) in enumerate(BIND_SEAM_ATTEMPTS):
        over, stats = probe_stretched_bind_seams(arm, body, ctx, poses)
        log(
            f"bind seam probe {attempt}: worst trunk edge "
            f"{stats['worst_m']:.4f} m at {stats['worst_m_pair']}, worst stretch "
            f"{stats['worst_stretch']:.2f}x ({stats['worst_stretch_len']:.4f} m) "
            f"at {stats['worst_stretch_pair']} on {stats['at']} "
            f"(out-of-scope edges up to {stats['out_of_scope_m']:.4f} m ignored); "
            f"{len(over)} edge(s) flagged. {stats['stats']}"
        )
        if not over:
            arm.matrix_basis = arm_basis
            force_armature_rest(arm)
            log(
                f"bind seams clear on every probe pose (nothing over "
                f"{BIND_SEAM_TARGET_M} m, or {BIND_SEAM_TARGET_STRETCH}x with "
                f"{BIND_SEAM_TARGET_EXCESS_M * 1000:.0f} mm growth and gap "
                f"{BIND_SEAM_TARGET_GAP})"
            )
            return smoothed
        for (a, b), (d, sr, rest, g) in sorted(
            over.items(), key=lambda kv: -(kv[1][0] - kv[1][2])
        )[:6]:
            log(
                f"  torn seam {d * 1000:.1f} mm ({sr:.2f}x from "
                f"{rest * 1000:.1f} mm rest, +{(d - rest) * 1000:.1f} mm, "
                f"weight gap {g:.2f}) ({a},{b}) "
                f"[{describe_vert_bind(body, arm, a)}] "
                f"[{describe_vert_bind(body, arm, b)}]"
            )
        seed = set()
        for a, b in over:
            seed.add(a)
            seed.add(b)
        # A handful of verts is a seam. A tenth of the mesh is not, and
        # re-weighting that much of the character on the strength of a posed
        # edge measurement is not a repair — fail and say so.
        cap = int(BIND_SEAM_MAX_SEED_FRAC * len(body.data.vertices))
        if len(seed) > cap:
            raise RuntimeError(
                f"bind seam repair: {len(over)} torn edge(s) touch {len(seed)} "
                f"vert(s), over the {cap}-vert cap "
                f"({BIND_SEAM_MAX_SEED_FRAC} of male_body). That is not a seam, "
                f"it is a broken bind. Worst {stats['worst_m']:.4f} m / "
                f"{stats['worst_stretch']:.2f}x on {stats['at']}. {stats['stats']}"
            )
        arm.matrix_basis = arm_basis
        force_armature_rest(arm)
        smoothed += smooth_bind_weights(
            body, arm, seed, rings=rings, iterations=iterations
        )
        assert_all_skin_verts_bound(arm, f"after bind seam smoothing {attempt}")

    over, stats = probe_stretched_bind_seams(arm, body, ctx, poses)
    arm.matrix_basis = arm_basis
    force_armature_rest(arm)
    if over:
        # Report the worst edge that is actually FLAGGED, by how far it grew.
        # 46fc7b0 reported its unconditional worst stretch instead, which was a
        # 2.8 mm toe seam that had moved 8 mm — true, and not what was blocking.
        (a, b), (d, sr, rest, g) = max(
            over.items(), key=lambda kv: kv[1][0] - kv[1][2]
        )
        raise RuntimeError(
            f"bind seam repair did not converge after {len(BIND_SEAM_ATTEMPTS)} "
            f"attempts: {len(over)} trunk edge(s) still over "
            f"{BIND_SEAM_TARGET_M} m / {BIND_SEAM_TARGET_STRETCH}x / "
            f"{BIND_SEAM_TARGET_EXCESS_M * 1000:.0f} mm growth / gap "
            f"{BIND_SEAM_TARGET_GAP}. Worst by growth: {d * 1000:.1f} mm "
            f"({sr:.2f}x from {rest * 1000:.1f} mm rest, "
            f"+{(d - rest) * 1000:.1f} mm, weight gap {g:.2f}) verts=({a},{b}) "
            f"on {stats['at']} "
            f"[{describe_vert_bind(body, arm, a)}] "
            f"[{describe_vert_bind(body, arm, b)}]. {stats['stats']} — the "
            f"percentiles say what a normal trunk edge on this mesh does; the "
            f"bones named above are the seam that tears."
        )
    log(
        f"bind seams repaired: worst trunk edge {stats['worst_m']:.4f} m / "
        f"{stats['worst_stretch']:.2f}x on {stats['at']} over "
        f"{sum(len(f) for _l, _a, f in poses)} probe poses "
        f"({smoothed} vert weight writes). {stats['stats']}"
    )
    return smoothed


def body_world_scale(body) -> float:
    """Uniform object scale of male_body, after refusing a rotated/skewed matrix.

    Everything in this module mixes body object space with world space on
    purpose: vertex coordinates are compared against ``rest_world`` bone
    heights, the mouth aperture is solved in object space and then used as a
    world frame, and the face is assumed to look down ``-Y`` with ``+Z`` up.
    That is true for the MakeHuman glTF imports this bake uses, and it has been
    true for every logged run. If it ever stops being true, the numbers stay
    plausible while the geometry is silently wrong, so check it once, loudly.
    """
    mw = body.matrix_world
    rot = mw.to_3x3()
    scale = mw.to_scale()
    ident = Matrix.Identity(3)
    worst = 0.0
    for i in range(3):
        for j in range(3):
            worst = max(worst, abs(float(rot[i][j]) / max(float(scale[j]), 1e-9)
                                   - float(ident[i][j])))
    log(
        f"{body.name!r} matrix_world translation="
        f"{tuple(round(c, 4) for c in mw.to_translation())} "
        f"scale={tuple(round(c, 4) for c in scale)} rot_dev={worst:.6f}"
    )
    if worst > 1e-3:
        raise RuntimeError(
            f"{body.name!r} object matrix is rotated/skewed (rot_dev={worst:.6f}). "
            f"This module treats body object space as world-aligned (-Y forward, "
            f"+Z up); a rotated bind would make every mouth/tusk coordinate "
            f"wrong while still looking plausible. matrix_world={mw}"
        )
    sx, sy, sz = (float(c) for c in scale)
    if max(abs(sx - sy), abs(sy - sz), abs(sx - sz)) > 1e-3:
        raise RuntimeError(
            f"{body.name!r} object matrix scales non-uniformly {(sx, sy, sz)}; "
            f"the aperture is an ellipse in mesh space and would not stay one "
            f"in world space"
        )
    return sx


def skull_vert_indices(body) -> list[int]:
    """male_body vert indices that belong to the skull, not the neck seam.

    Mouth skin on the MH 53-bone bind is pure ``head``. Requiring head
    dominance and excluding neck/spine influence keeps the cloud on the skull,
    which is what makes the head bounding box a usable measuring stick.
    """
    head_i = vg_index(body, "head")
    if head_i is None:
        raise RuntimeError(f"{body.name!r} missing head vertex group for mouth anchors")
    neck_i = vg_index(body, "neck_01") or vg_index(body, "neck")
    spine3_i = vg_index(body, "spine_03")
    out = []
    for v in body.data.vertices:
        if vg_weight(v, head_i) < SKULL_HEAD_W_MIN:
            continue
        if vg_weight(v, neck_i) > SKULL_NECK_W_MAX:
            continue
        if vg_weight(v, spine3_i) > SKULL_SPINE_W_MAX:
            continue
        out.append(int(v.index))
    return out


def resolve_mouth_aperture(arm):
    """Measure the one authoritative mouth aperture on male_body.

    This is the single owner of "where the mouth is". The carve, the tusk
    author, the tusk still gate and the head close-up camera all read this
    frame; none of them re-derives it. The previous bakes had three
    disagreeing derivations, which is how tusks ended up seated near the jaw
    angle while a lip-part gate refused a mouth it was measuring in the wrong
    place. See ``tools/orc_mouth_geometry.py`` for the measurement itself.
    """
    body = male_body_mesh(arm)
    body_world_scale(body)
    if "head" not in arm.data.bones:
        raise RuntimeError("53-bone bind missing head bone for mouth anchors")
    idx = skull_vert_indices(body)
    points = [
        (
            float(body.data.vertices[i].co.x),
            float(body.data.vertices[i].co.y),
            float(body.data.vertices[i].co.z),
        )
        for i in idx
    ]
    log(
        f"skull cloud verts={len(points)} of {len(body.data.vertices)} "
        f"(head>={SKULL_HEAD_W_MIN}, neck<={SKULL_NECK_W_MAX}, "
        f"spine_03<={SKULL_SPINE_W_MAX})"
    )
    try:
        aperture = MG.solve_mouth_aperture(points)
    except MG.MouthGeometryError as exc:
        # Dump the profile the solver was looking at so a local bake explains
        # itself instead of leaving the next run to guess.
        prof = MG.forward_profile(points, bins=32)
        for z, y, n in prof:
            log(f"  midline-ish profile z={z:.4f} y_front={y:.4f} n={n}")
        raise RuntimeError(f"mouth aperture not measurable: {exc}") from exc
    log(f"mouth aperture {aperture.describe()}")
    head_z = float(HQ.rest_world(arm, "head").to_translation().z)
    log(
        f"mouth aperture vs head bone: head_rest_z={head_z:.4f} "
        f"dz_center={aperture.center_z - head_z:.4f} "
        f"dz_nose={aperture.nose_z - head_z:.4f} "
        f"dz_chin={aperture.chin_z - head_z:.4f}"
    )
    mid = [
        p
        for p in points
        if abs(p[0] - aperture.head_center_x) <= aperture.midline_strip_half
    ]
    for z, y, n in MG.forward_profile(mid, bins=28):
        log(f"  mid-sagittal profile z={z:.4f} y_front={y:.4f} n={n}")
    return aperture


def mouth_aperture_report(aperture) -> dict:
    """Measured aperture as JSON for the Art Reviewer packet."""
    return {
        "center": [round(float(c), 5) for c in aperture.center],
        "half_width": round(float(aperture.half_width), 5),
        "half_height": round(float(aperture.half_height), 5),
        "depth": round(float(aperture.depth), 5),
        "head_width": round(float(aperture.head_width), 5),
        "nose_z": round(float(aperture.nose_z), 5),
        "chin_z": round(float(aperture.chin_z), 5),
        "lip_slit_from_chin": round(float(aperture.mouth_z_from_chin), 5),
        "lip_slit_from_nose": round(float(aperture.mouth_z_from_nose), 5),
        "face_half_width_at_mouth": round(float(aperture.face_half_width_at_mouth), 5),
        "skull_cloud_verts": int(aperture.cloud_points),
        "midline_verts": int(aperture.midline_points),
    }


def store_mouth_aperture(arm, aperture) -> None:
    """Publish the aperture in head-bone-rest space on the body object.

    Stored in head space, not body space, because that is the frame the still
    gate needs: the mouth is rigidly attached to the head bone, so the posed
    aperture is just ``head_pose_matrix @ stored``. The measured numbers also
    go into the Art Reviewer packet via ``mouth_aperture_report``.
    """
    body = male_body_mesh(arm)
    # The published frame is head-*rest* local, so the armature must be at rest
    # when it is captured. A leftover donor action here would bake a posed head
    # into the frame and every later gate would measure against a phantom mouth.
    force_armature_rest(arm)
    head_inv = head_pose_world_matrix(arm).inverted()
    rot_inv = head_pose_world_matrix(arm).to_3x3().inverted()
    center_w = body_local_to_world(body, Vector(aperture.center))
    center_hl = head_inv @ center_w
    body_rot = body.matrix_world.to_3x3()
    axes = {}
    for name, axis_b in (
        ("right", Vector((1.0, 0.0, 0.0))),
        ("up", Vector((0.0, 0.0, 1.0))),
        ("inward", Vector((0.0, 1.0, 0.0))),
    ):
        axes[name] = (rot_inv @ (body_rot @ axis_b)).normalized()
    body["orc_aperture_head_center"] = [float(c) for c in center_hl]
    body["orc_aperture_head_right"] = [float(c) for c in axes["right"]]
    body["orc_aperture_head_up"] = [float(c) for c in axes["up"]]
    body["orc_aperture_head_inward"] = [float(c) for c in axes["inward"]]
    # Radii are mesh-space lengths; the posed frame is world space, so carry the
    # object scale across once here rather than at every gate.
    scale = body_world_scale(body)
    body["orc_aperture_half_width"] = float(aperture.half_width * scale)
    body["orc_aperture_half_height"] = float(aperture.half_height * scale)
    body["orc_aperture_depth"] = float(aperture.depth * scale)
    body["orc_aperture_head_width"] = float(aperture.head_width * scale)
    log(
        f"published aperture in head-rest space center="
        f"{tuple(round(c, 4) for c in center_hl)} "
        f"right={tuple(round(c, 3) for c in axes['right'])} "
        f"up={tuple(round(c, 3) for c in axes['up'])} "
        f"inward={tuple(round(c, 3) for c in axes['inward'])} "
        f"half=({aperture.half_width:.4f},{aperture.half_height:.4f}) "
        f"depth={aperture.depth:.4f} body_scale={scale:.6f}"
    )
    if center_hl.length > HEAD_MOUTH_MAX_LOCAL:
        raise RuntimeError(
            f"aperture centre is {center_hl.length:.4f} from the head bone origin "
            f"(> {HEAD_MOUTH_MAX_LOCAL}) — that is not a mouth on this skull"
        )


def posed_aperture_frame(arm) -> dict:
    """The aperture in world space for the current pose.

    Reads the frame published by ``store_mouth_aperture`` and rides the head
    bone. One function, so the carve proof, the tusk gate and the close-up
    camera cannot drift apart.
    """
    body = male_body_mesh(arm)
    for key in (
        "orc_aperture_head_center",
        "orc_aperture_head_right",
        "orc_aperture_head_up",
        "orc_aperture_head_inward",
        "orc_aperture_half_width",
        "orc_aperture_half_height",
        "orc_aperture_depth",
        "orc_aperture_head_width",
    ):
        if key not in body:
            raise RuntimeError(
                f"{body.name!r} missing {key} — the mouth aperture was never "
                f"published; resolve_mouth_aperture/store_mouth_aperture must "
                f"run before any mouth gate"
            )
    m = head_pose_world_matrix(arm)
    rot = m.to_3x3()

    def vec(key: str) -> Vector:
        raw = body[key]
        return Vector((float(raw[0]), float(raw[1]), float(raw[2])))

    right = (rot @ vec("orc_aperture_head_right")).normalized()
    up = (rot @ vec("orc_aperture_head_up")).normalized()
    inward = (rot @ vec("orc_aperture_head_inward")).normalized()
    return {
        "center": m @ vec("orc_aperture_head_center"),
        "right": right,
        "up": up,
        "inward": inward,
        "half_width": float(body["orc_aperture_half_width"]),
        "half_height": float(body["orc_aperture_half_height"]),
        "depth": float(body["orc_aperture_depth"]),
        "head_width": float(body["orc_aperture_head_width"]),
    }


def aperture_coords_world(frame: dict, p: Vector) -> tuple[float, float, float]:
    rel = Vector(p) - frame["center"]
    return (
        float(rel.dot(frame["right"])),
        float(rel.dot(frame["up"])),
        float(rel.dot(frame["inward"])),
    )


def aperture_radial(frame: dict, u: float, w: float, *, margin: float = 0.0) -> float:
    """Normalised rim-ellipse radius; ``<= 1`` is inside the aperture."""
    return math.hypot(
        u / (frame["half_width"] + margin), w / (frame["half_height"] + margin)
    )


def mouth_interior_material():
    return make_opaque_mat("OrcMouthInterior", MOUTH_INTERIOR, 0.65)


def aperture_region_edge_stats(me, aperture) -> tuple[list[int], float]:
    """Edges touching the aperture neighbourhood, and their mean length.

    An edge qualifies when either end is inside ``CAVITY_SUBDIV_REGION_R`` of
    the aperture, so a mouth that currently holds only a handful of verts still
    gathers the surrounding edges to refine.
    """
    inside = []
    for v in me.vertices:
        u, w, _d = aperture.aperture_coords(
            (float(v.co.x), float(v.co.y), float(v.co.z))
        )
        inside.append(aperture.radial(u, w) <= CAVITY_SUBDIV_REGION_R)
    picked = []
    total = 0.0
    for e in me.edges:
        a, b = int(e.vertices[0]), int(e.vertices[1])
        if not (inside[a] or inside[b]):
            continue
        picked.append(int(e.index))
        total += (me.vertices[a].co - me.vertices[b].co).length
    mean = (total / len(picked)) if picked else 0.0
    return picked, mean


def subdivide_for_cavity(arm, body, aperture) -> int:
    """Refine the mouth neighbourhood until a smooth bore is representable.

    A 62 x 40 mm maw cannot be carved into geometry that has three verts there:
    the "cavity" comes out as a triangular dent with 30 mm steps between
    neighbours, which is a hole punched in the face rather than a mouth. So
    measure the local edge length and cut until the aperture is sampled at
    least ``CAVITY_SUBDIV_TARGET_SAMPLES`` times across its half-width.

    Only the mouth neighbourhood is touched, the vert budget is capped, and
    nothing downstream captured a vertex index before this point (the rim
    anchors are chosen after the carve), so adding verts here is safe.
    """
    me = body.data
    target = aperture.half_width / float(CAVITY_SUBDIV_TARGET_SAMPLES)
    budget = max(
        CAVITY_SUBDIV_MIN_BUDGET,
        int(CAVITY_SUBDIV_MAX_ADDED_FRAC * len(me.vertices)),
    )
    added_total = 0
    for step in range(CAVITY_SUBDIV_MAX_PASSES):
        edges, mean = aperture_region_edge_stats(me, aperture)
        if not edges:
            raise RuntimeError(
                f"subdivide_for_cavity: no edges near the aperture "
                f"({aperture.describe()}) — the solver placed the mouth off the mesh"
            )
        log(
            f"cavity subdiv pass {step}: region_edges={len(edges)} "
            f"mean_edge={mean:.4f} target={target:.4f} verts={len(me.vertices)}"
        )
        if mean <= target:
            break
        before = len(me.vertices)
        if added_total + len(edges) > budget:
            log(
                f"cavity subdiv stopping: {len(edges)} cuts would exceed the "
                f"{budget}-vert budget (added={added_total})"
            )
            break
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.edges.ensure_lookup_table()
        pick = [bm.edges[i] for i in edges]
        bmesh.ops.subdivide_edges(bm, edges=pick, cuts=1, use_grid_fill=True)
        bm.to_mesh(me)
        bm.free()
        me.update()
        added_total += len(me.vertices) - before
        log(
            f"cavity subdiv pass {step}: verts {before} -> {len(me.vertices)} "
            f"(+{len(me.vertices) - before}, total +{added_total})"
        )
    else:
        _edges, mean = aperture_region_edge_stats(me, aperture)
        if mean > target:
            log(
                f"cavity subdiv hit {CAVITY_SUBDIV_MAX_PASSES} passes with "
                f"mean_edge={mean:.4f} > target={target:.4f}; carving anyway "
                f"(the carve gates below decide whether that is enough)"
            )
    if added_total:
        bind_new_cavity_verts_to_head(arm, body, aperture)
    return added_total


def bind_new_cavity_verts_to_head(arm, body, aperture) -> int:
    """Guarantee every vert the subdivision added is head-bound.

    ``bmesh.ops.subdivide_edges`` interpolates the deform layer, so new verts
    normally arrive with their parents' weights. This makes that explicit
    rather than assumed, because the failure mode is the worst one in this
    script: an unweighted vert sits at rest object space while the mesh
    deforms, and the edges to its neighbours render as a strand.

    Anything unbound *outside* the mouth neighbourhood means the subdivision
    touched geometry it was not aimed at, so that is a hard error rather than
    something to patch up.
    """
    me = body.data
    head_vg = body.vertex_groups.get("head")
    if head_vg is None:
        raise RuntimeError(f"{body.name!r} has no head vertex group to bind cavity verts")
    bone_groups = armature_bone_groups(body, arm)
    fixed = 0
    for v in me.vertices:
        if effective_bind_weight(v, bone_groups) > 1e-6:
            continue
        u, w, _d = aperture.aperture_coords(
            (float(v.co.x), float(v.co.y), float(v.co.z))
        )
        r = aperture.radial(u, w)
        if r > CAVITY_SUBDIV_REGION_R:
            raise RuntimeError(
                f"{body.name!r} vert {int(v.index)} is unbound at aperture radius "
                f"{r:.3f} — outside the mouth neighbourhood the cavity subdivision "
                f"was aimed at; refusing to guess a bone for it"
            )
        head_vg.add([int(v.index)], 1.0, "REPLACE")
        fixed += 1
    log(
        f"cavity subdivision verts needing an explicit head bind: {fixed} "
        f"(0 means bmesh interpolated the deform layer as expected)"
    )
    return fixed


def carve_orc_mouth_cavity(arm, aperture) -> int:
    """Bore a real oral cavity into male_body at the measured aperture.

    New hypothesis, replacing "part the lips in Z".

    Pushing a handful of surface verts apart never worked and could not work:
    the outer rim moved while the inner loop sealed the hole (the 15:26 stills
    read closed at a gap that passed the numeric gate), and the skin left
    behind the "opening" then hid anything seated in it — which is why two
    EXIT-0 bakes shipped stills with no visible tusks. There was nothing behind
    the parted lips except more face.

    So do not part the lips. Displace the skin inside the aperture ellipse
    *into the head*, onto a raised-cosine bore profile, and paint the bore with
    a dark interior material. The result is a genuine concave maw with room in
    it.

    The profile is continuous and reaches exactly zero at the rim, and each
    vert is only ever moved to the profile (never past it), so the carve cannot
    invert geometry or overshoot.
    """
    body = male_body_mesh(arm)
    subdivide_for_cavity(arm, body, aperture)
    me = body.data
    skull = set(skull_vert_indices(body))
    if not skull:
        raise RuntimeError("carve_orc_mouth_cavity: empty skull cloud")
    carved = 0
    deepest = 0.0
    falloffs = [0.0] * len(me.vertices)
    for i in sorted(skull):
        v = me.vertices[i]
        u, w, d = aperture.aperture_coords(
            (float(v.co.x), float(v.co.y), float(v.co.z))
        )
        f = aperture.falloff(u, w)
        if f <= 0.0:
            continue
        falloffs[i] = f
        target_d = aperture.depth * f
        if d >= target_d:
            continue  # already at or behind the bore profile
        v.co.y += target_d - d
        deepest = max(deepest, target_d)
        carved += 1
    me.update()

    if carved < CAVITY_MIN_CARVED_VERTS:
        raise RuntimeError(
            f"carve_orc_mouth_cavity: only {carved} verts inside the measured "
            f"aperture (need {CAVITY_MIN_CARVED_VERTS}); "
            f"aperture={aperture.describe()} — the mouth would still read closed"
        )
    min_depth = CAVITY_MIN_ACHIEVED_DEPTH_FRAC * aperture.depth
    if deepest < min_depth:
        raise RuntimeError(
            f"carve_orc_mouth_cavity: deepest bore reached {deepest:.4f} < "
            f"{min_depth:.4f} ({CAVITY_MIN_ACHIEVED_DEPTH_FRAC} of "
            f"{aperture.depth:.4f}) over {carved} verts — the mesh has no "
            f"geometry near the aperture centre, so the camera would still see "
            f"a closed mouth"
        )

    # Paint the bore. Slot 1 is the interior; apply_finished_olive_skin rebuilds
    # the slots in that order so this survives every re-paint.
    interior = mouth_interior_material()
    me.materials.clear()
    me.materials.append(make_opaque_mat(f"OrcSkin_{body.name}", OLIVE, 0.88))
    me.materials.append(interior)
    body["orc_mouth_interior_slot"] = 1
    painted = 0
    for poly in me.polygons:
        vids = list(poly.vertices)
        mean_f = sum(falloffs[int(j)] for j in vids) / float(len(vids))
        if mean_f >= CAVITY_INTERIOR_POLY_FALLOFF:
            poly.material_index = 1
            painted += 1
        else:
            poly.material_index = 0
    if painted <= 0:
        raise RuntimeError(
            f"carve_orc_mouth_cavity: no polygon reached mean falloff "
            f"{CAVITY_INTERIOR_POLY_FALLOFF} — the maw would render as skin "
            f"and read closed (carved={carved} deepest={deepest:.4f})"
        )
    me.update()
    assert_all_skin_verts_bound(arm, "after mouth cavity carve")
    log(
        f"carved orc mouth cavity verts={carved} deepest={deepest:.4f} "
        f"(target {aperture.depth:.4f}) interior_polys={painted} "
        f"rim=({aperture.half_width:.4f},{aperture.half_height:.4f}) "
        f"center_z={aperture.center_z:.4f}"
    )
    return carved


def mouth_rim_anchor_verts(arm, aperture) -> tuple[int, int]:
    """male_body verts nearest the left/right aperture rim.

    Kept so the still gate can prove the mouth *skin* still follows the head,
    not just that the tusks follow the bone. These are real rim verts by
    construction now — the old corner hunt returned jaw-side verts at
    |x-cx|=82 mm, i.e. a 164 mm wide "mouth", and seated the tusks there.

    Only near-pure head verts qualify: an anchor with neck bleed would drift
    under Death and the gate could not tell that from a broken bind.
    """
    body = male_body_mesh(arm)
    me = body.data
    head_i = vg_index(body, "head")
    candidates = [
        i
        for i in skull_vert_indices(body)
        if vg_weight(me.vertices[i], head_i) >= MOUTH_RIM_HEAD_W_MIN
    ]
    if not candidates:
        raise RuntimeError(
            f"no male_body vert with head weight >= {MOUTH_RIM_HEAD_W_MIN} near the "
            f"mouth — cannot anchor the rim-tracking proof"
        )
    picked = {}
    for side, sign in (("L", -1.0), ("R", 1.0)):
        target = Vector(
            (
                aperture.center_x + sign * aperture.half_width,
                aperture.center_y,
                aperture.center_z,
            )
        )
        pick = -1
        pick_d = 1e9
        for i in candidates:
            d = (me.vertices[i].co - target).length
            if d < pick_d:
                pick_d = d
                pick = int(i)
        if pick_d > aperture.half_width:
            raise RuntimeError(
                f"nearest head-bound vert to the {side} aperture rim is {pick_d:.4f} "
                f"away (> half_width {aperture.half_width:.4f}) — the mesh has "
                f"no geometry on this rim"
            )
        picked[side] = pick
        log(
            f"mouth rim anchor {side} vert={pick} dist={pick_d:.4f} "
            f"head_w={vg_weight(me.vertices[pick], head_i):.3f} "
            f"co={tuple(round(c, 4) for c in me.vertices[pick].co)}"
        )
    return picked["L"], picked["R"]


def is_junk_companion_mesh(obj) -> bool:
    """True for leftover companion meshes that are not the nude orc identity.

    Eyes may exist as a separate MH export mesh — hide as junk. Icosphere may
    appear on some imports. Thin stray spikes on Idle/Death stills (21:56) are
    typically these leftovers, not male_body brow verts.
    """
    low = obj.name.lower()
    if low in ("eyes", "eye") or low.startswith("eyes") or low.startswith("eye"):
        return True
    if any(
        k in low
        for k in (
            "icosphere",
            "sphere",
            "cornea",
            "pupil",
            "sclera",
            "lash",
            "eyebrow",
            "tearduct",
            "eye_",
            "_eye",
        )
    ):
        return True
    return False


def hide_junk_companion_meshes(arm) -> list[str]:
    """Hide Eyes / Icosphere / eye-sphere junk. Not brow-spike flatten."""
    hidden = []
    for obj in list(mesh_objects()):
        if not is_junk_companion_mesh(obj):
            continue
        # Keep them out of view-layer draw; hide flags alone missed some
        # Idle/Death spike stills when a junk mesh stayed in a rendered collection.
        obj.hide_render = True
        obj.hide_viewport = True
        try:
            obj.hide_set(True)
        except Exception:
            pass
        # hide flags alone left Eyes in a rendered collection (Idle/Death spikes).
        for col in list(obj.users_collection):
            col.objects.unlink(obj)
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


def _evaluated_mesh_verts_world(obj) -> list[Vector]:
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        if not me.vertices:
            raise RuntimeError(f"evaluated mesh empty: {obj.name!r}")
        mw = ev.matrix_world
        return [mw @ v.co for v in me.vertices]
    finally:
        ev.to_mesh_clear()


def world_dir_to_head_local(arm, world_dir: Vector) -> Vector:
    """Rotate a world direction into head-bone / tip-parent space (no translation)."""
    local = head_pose_world_matrix(arm).to_3x3().inverted() @ Vector(world_dir)
    if local.length < 1e-8:
        raise RuntimeError("world_dir_to_head_local: collapsed direction")
    return local.normalized()


def _axis_frame(axis: Vector) -> tuple[Vector, Vector, Vector]:
    """Orthonormal (right, binormal, axis) for authoring a cone along ``axis``."""
    a = Vector(axis).normalized()
    helper = Vector((1.0, 0.0, 0.0))
    if abs(float(a.dot(helper))) > 0.90:
        helper = Vector((0.0, 0.0, 1.0))
    x = a.cross(helper)
    if x.length < 1e-8:
        helper = Vector((0.0, 1.0, 0.0))
        x = a.cross(helper)
    x.normalize()
    y = a.cross(x).normalized()
    return x, y, a


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


def assert_no_torso_spike(arm, label: str) -> None:
    """Refuse a posed male_body vert flying off the torso (Death chest spike).

    a4a5c61 Death still: tusks were in the mouth, but a long grey spike ran
    through the sternum into the ground. That is a body-vert outlier, not a
    50mm aperture tusk. Idle pec pinch is the rest-pose form of the same class.

    The stretched-edge half of this gate now shares its edge classification and
    scan with ``repair_bind_seams`` (``stretch_gate_context`` /
    ``scan_torso_edges``), so the repair cannot disagree with the gate about
    which edges count. Its failure message names the bones on both ends: five
    bakes refused on verts (1876, 1891) while reporting only spine and head
    weights, which are 1.00 and 0.00 on that pair and say nothing about what is
    actually driving them.
    """
    body = male_body_mesh(arm)
    spine_groups = [
        vg_index(body, "spine_01"),
        vg_index(body, "spine_02"),
        vg_index(body, "spine_03"),
    ]
    neck_i = vg_index(body, "neck_01") or vg_index(body, "neck")
    head_i = vg_index(body, "head")
    verts_w = _evaluated_mesh_verts_world(body)
    if len(verts_w) != len(body.data.vertices):
        raise RuntimeError(
            f"{label}: eval male_body vert count {len(verts_w)} != "
            f"{len(body.data.vertices)}"
        )
    torso = []
    for i, v in enumerate(body.data.vertices):
        tw = spine_weight(v, spine_groups)
        if tw < 0.28:
            continue
        if vg_weight(v, head_i) >= 0.40:
            continue
        if vg_weight(v, neck_i) >= 0.35:
            continue
        torso.append(verts_w[i])
    if len(torso) < 12:
        raise RuntimeError(
            f"{label}: too few torso verts for spike gate ({len(torso)})"
        )
    mx = sorted(p.x for p in torso)[len(torso) // 2]
    my = sorted(p.y for p in torso)[len(torso) // 2]
    mz = sorted(p.z for p in torso)[len(torso) // 2]
    med = Vector((mx, my, mz))
    dists = [(p - med).length for p in torso]
    worst = max(dists)
    mid_d = sorted(dists)[len(dists) // 2]
    if worst > TORSO_SPIKE_MAX_M:
        raise RuntimeError(
            f"{label} still: male_body torso spike "
            f"(worst={worst:.4f} > {TORSO_SPIKE_MAX_M} from torso median "
            f"{tuple(round(c, 3) for c in med)}; median_dist={mid_d:.4f}) — "
            f"Death through-chest / Idle pec-pinch class; refusing PNG"
        )
    log(
        f"{label} torso spike gate: worst={worst:.4f} median_dist={mid_d:.4f} "
        f"n={len(torso)}"
    )
    ctx = stretch_gate_context(body, arm)
    scan = scan_torso_edges(
        ctx,
        verts_w,
        make_edge_gap_fn(body, arm),
        limit_m=TORSO_EDGE_MAX_M,
        limit_stretch=TORSO_EDGE_MAX_STRETCH,
        min_excess_m=TORSO_EDGE_MIN_EXCESS_M,
        max_gap=TORSO_EDGE_MAX_GAP,
    )
    log(f"{label} torso edge stats: {format_stretch_stats(scan)}")
    if scan["worst_m"] > TORSO_EDGE_MAX_M:
        a, b = scan["worst_m_pair"]
        raise RuntimeError(
            f"{label} still: stretched male_body trunk edge {scan['worst_m']:.4f} > "
            f"{TORSO_EDGE_MAX_M} verts=({a},{b}) "
            f"[{describe_vert_bind(body, arm, a)}] "
            f"[{describe_vert_bind(body, arm, b)}] "
            f"({len(scan['over'])} edge(s) over) — through-torso / pec-pinch "
            f"spike; refusing PNG. The bones named above are the seam that "
            f"tears; repair_bind_seams should have blended them"
        )
    if scan["over"]:
        # Flagged means over the absolute cap, or stretched past the ratio AND
        # grown by a visible amount. Report the worst by growth: that is the one
        # a reviewer would point at.
        d, sr, rest, g, a, b = max(scan["over"], key=lambda o: o[0] - o[2])
        grew = d - rest
        raise RuntimeError(
            f"{label} still: male_body trunk edge stretched {sr:.2f}x "
            f"(> {TORSO_EDGE_MAX_STRETCH}) to {d * 1000:.1f} mm, grown "
            f"{grew * 1000:.1f} mm (> {TORSO_EDGE_MIN_EXCESS_M * 1000:.0f} mm), "
            f"weight gap {g:.2f} (> {TORSO_EDGE_MAX_GAP}) verts=({a},{b}) "
            f"[{describe_vert_bind(body, arm, a)}] "
            f"[{describe_vert_bind(body, arm, b)}] "
            f"({len(scan['over'])} edge(s) over). {format_stretch_stats(scan)}. "
            f"This is the f4d2059 pixel class: short enough to pass a metre cap, "
            f"stretched far enough to read as a jagged band; refusing PNG"
        )
    log(
        f"{label} stretched-edge gate: worst_trunk={scan['worst_m']:.4f} m "
        f"verts={scan['worst_m_pair']} "
        f"worst_stretch={scan['worst_stretch']:.2f}x (none flagged)"
    )


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


def assert_tusk_rigid_bind(arm, tusk, label: str) -> float:
    """The authored centroid must land exactly where the head pose puts it.

    Single owner of the rigid-bind proof: a drifting ``matrix_parent_inverse``,
    a stray Armature modifier or a re-parent shows up here as millimetres long
    before it shows up as a floating cone in a PNG.
    """
    if "orc_tusk_centroid_head_local" not in tusk:
        raise RuntimeError(
            f"{label}: {tusk.name!r} missing orc_tusk_centroid_head_local — "
            f"cannot prove the tusk is rigidly bound to the head"
        )
    chl = tusk["orc_tusk_centroid_head_local"]
    expected = head_pose_world_matrix(arm) @ Vector(
        (float(chl[0]), float(chl[1]), float(chl[2]))
    )
    centroid = _evaluated_mesh_centroid_world(tusk)
    drift = (centroid - expected).length
    if drift > TUSK_BIND_MAX_M:
        raise RuntimeError(
            f"{label}: {tusk.name!r} centroid is {drift:.4f} from its head-local "
            f"bind target (> {TUSK_BIND_MAX_M}) "
            f"tusk_w={tuple(round(c, 3) for c in centroid)} "
            f"bind_w={tuple(round(c, 3) for c in expected)} — not rigidly "
            f"attached to the head"
        )
    return drift


def assert_tusks_in_mouth_for_current_pose(arm, tusks: list, label: str) -> None:
    """Gate the PNG the Reviewer sees: tusks inside the posed maw.

    One containment test in the posed aperture frame replaces the seven
    overlapping world-distance caps this used to carry. Those caps each encoded
    a different guess about where the mouth was (gum offset, lip-corner
    distance, opening depth, aperture radius, tip rise, skull punch, chin
    hang), they were tuned against different failed bakes, and they could all
    pass while the tusk sat under the ear -- because the "mouth corner" they
    all measured from was a jaw-side vert.

    Every pixel-failure class they defended against is still refused here, and
    now by construction rather than by a tuned number:

      cheek float (21:10)          -> ellipse radius > 1
      chin needle (0706a32)        -> w below the rim ellipse
      tip past the posed lip (21:56) -> d < 0
      buried / invisible (1116245) -> front fraction below TUSK_MIN_FRONT_FRAC
      Death chest spike (ac21975)  -> d > depth

    It also adds what the old gate could not check: that the mouth *skin* is
    still tracking the head (``MOUTH_RIM_TRACK_MAX_M``), and that the tusk is
    rigidly bound rather than drifting (``TUSK_BIND_MAX_M``).
    """
    if not tusks:
        raise RuntimeError(f"{label}: no tusks for in-mouth still gate")
    body = male_body_mesh(arm)
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()
    frame = posed_aperture_frame(arm)
    depth = frame["depth"]
    half_h = frame["half_height"]
    margin = TUSK_APERTURE_MARGIN

    for tusk in tusks:
        if tusk.parent != arm or tusk.parent_type != "BONE" or tusk.parent_bone != "head":
            raise RuntimeError(
                f"{label} still: {tusk.name!r} lost head BONE parent "
                f"(parent={getattr(tusk.parent, 'name', None)!r} "
                f"type={tusk.parent_type!r} bone={tusk.parent_bone!r})"
            )
        if not _matrix_is_identity(tusk.matrix_parent_inverse):
            raise RuntimeError(
                f"{label} still: {tusk.name!r} matrix_parent_inverse not Identity"
            )
        for key in (
            "orc_mouth_vert",
            "orc_mouth_vert_head_local",
            "orc_tusk_side",
            "orc_tusk_base_head_local",
            "orc_tusk_centroid_head_local",
            "orc_tusk_axis_head_local",
        ):
            if key not in tusk:
                raise RuntimeError(
                    f"{label} still: {tusk.name!r} missing {key} — cannot prove "
                    f"the tusk is seated in the measured aperture"
                )

        dist_bind = assert_tusk_rigid_bind(arm, tusk, f"{label} still")

        # The mouth skin must still ride the head, or the maw and the tusks
        # part company under Punch/Death whatever the tusk numbers say.
        rim_idx = int(tusk["orc_mouth_vert"])
        rim_w = evaluated_vertex_world(body, rim_idx)
        rhl = tusk["orc_mouth_vert_head_local"]
        rim_expected = head_pose_world_matrix(arm) @ Vector(
            (float(rhl[0]), float(rhl[1]), float(rhl[2]))
        )
        rim_drift = (rim_w - rim_expected).length
        if rim_drift > MOUTH_RIM_TRACK_MAX_M:
            raise RuntimeError(
                f"{label} still: mouth rim vert {rim_idx} deviates {rim_drift:.4f} "
                f"from rigid head motion (> {MOUTH_RIM_TRACK_MAX_M}) "
                f"vert_w={tuple(round(c, 3) for c in rim_w)} "
                f"rigid_w={tuple(round(c, 3) for c in rim_expected)} — the mouth skin "
                f"and the head bone have parted; refusing PNG"
            )

        # Orientation: the tusk must still rise through the maw and lean out of
        # it. A mirrored or inverted cone can otherwise satisfy containment
        # while pointing down the throat.
        axis_w = (
            head_pose_world_matrix(arm).to_3x3()
            @ Vector(
                (
                    float(tusk["orc_tusk_axis_head_local"][0]),
                    float(tusk["orc_tusk_axis_head_local"][1]),
                    float(tusk["orc_tusk_axis_head_local"][2]),
                )
            )
        ).normalized()
        rise_dot = float(axis_w.dot(frame["up"]))
        inward_dot = float(axis_w.dot(frame["inward"]))
        if rise_dot < TUSK_MIN_AXIS_RISE_DOT or inward_dot > 0.0:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} axis does not rise out of the maw "
                f"(up_dot={rise_dot:.3f} < {TUSK_MIN_AXIS_RISE_DOT}, "
                f"inward_dot={inward_dot:.3f} must be <= 0) — inverted or "
                f"throat-facing cone; refusing PNG"
            )
        base_hl = tusk["orc_tusk_base_head_local"]
        base_w = head_pose_world_matrix(arm) @ Vector(
            (float(base_hl[0]), float(base_hl[1]), float(base_hl[2]))
        )
        _base_u, base_up, _base_d = aperture_coords_world(frame, base_w)
        if base_up >= 0.0:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} is rooted at or above the aperture "
                f"centre line (w={base_up:.4f}) — a tusk grows from the lower "
                f"gum; refusing PNG"
            )

        verts_w = _evaluated_mesh_verts_world(tusk)
        worst_radial = 0.0
        worst_radial_uw = (0.0, 0.0)
        min_d = 1e9
        max_d = -1e9
        w_lo = 1e9
        w_hi = -1e9
        front = 0
        front_limit = TUSK_FRONT_D_FRAC * depth
        worst_buried = -1e9
        worst_buried_uw = (0.0, 0.0, 0.0)
        for vw in verts_w:
            u, w, d = aperture_coords_world(frame, vw)
            r = aperture_radial(frame, u, w, margin=margin)
            if r > worst_radial:
                worst_radial = r
                worst_radial_uw = (u, w)
            wall = depth * MG.bore_frac(aperture_radial(frame, u, w))
            buried = d - (wall - TUSK_BORE_CLEARANCE_M)
            if buried > worst_buried:
                worst_buried = buried
                worst_buried_uw = (u, w, wall)
            min_d = min(min_d, d)
            max_d = max(max_d, d)
            w_lo = min(w_lo, w)
            w_hi = max(w_hi, w)
            if d <= front_limit:
                front += 1
        front_frac = front / float(len(verts_w))
        w_span = w_hi - w_lo

        if worst_radial > 1.0:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} leaves the mouth aperture "
                f"(radial={worst_radial:.3f} > 1 at u={worst_radial_uw[0]:.4f} "
                f"w={worst_radial_uw[1]:.4f}; rim=({frame['half_width']:.4f},"
                f"{half_h:.4f})) — cheek-float / chin-needle class; refusing PNG"
            )
        if min_d < -margin:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} pokes out past the posed lip plane "
                f"(min_d={min_d:.4f} < {-margin:.4f}) — 21:56 Punch class; "
                f"refusing PNG"
            )
        if max_d > depth + margin:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} punches through the cavity floor "
                f"into the skull (max_d={max_d:.4f} > depth {depth:.4f}) — "
                f"Death chest-spike class; refusing PNG"
            )
        if worst_buried > 0.0:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} is embedded in the cavity wall "
                f"(worst vert is {worst_buried:.4f} past the wall at "
                f"u={worst_buried_uw[0]:.4f} w={worst_buried_uw[1]:.4f}, where the "
                f"bore is only {worst_buried_uw[2]:.4f} deep and clearance is "
                f"{TUSK_BORE_CLEARANCE_M}) — in the flesh, not in the maw; "
                f"refusing PNG"
            )
        if front_frac < TUSK_MIN_FRONT_FRAC:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} sits at the back of the maw "
                f"(front_frac={front_frac:.3f} < {TUSK_MIN_FRONT_FRAC}; "
                f"front means d <= {front_limit:.4f} of depth {depth:.4f}) — "
                f"buried-in-cavity class, invisible in stills; refusing PNG"
            )
        if w_span < TUSK_MIN_W_SPAN_HH_FRAC * half_h:
            raise RuntimeError(
                f"{label} still: {tusk.name!r} spans only {w_span:.4f} of the "
                f"aperture height (< {TUSK_MIN_W_SPAN_HH_FRAC} * {half_h:.4f}) — "
                f"a stub the still cannot show; refusing PNG"
            )
        log(
            f"{label} still gate: {tusk.name} side={tusk['orc_tusk_side']} "
            f"bind={dist_bind:.4f} rim_drift={rim_drift:.4f} "
            f"radial={worst_radial:.3f} d=[{min_d:.4f},{max_d:.4f}] of {depth:.4f} "
            f"front_frac={front_frac:.3f} w_span={w_span:.4f} "
            f"wall_clearance={-worst_buried:.4f} "
            f"axis_up={rise_dot:.3f} axis_inward={inward_dot:.3f}"
        )
    log(f"{label} still gate: tusks inside the posed mouth aperture")
    assert_no_torso_spike(arm, label)


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
                assert_tusk_rigid_bind(arm, tusk, label)
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
                assert_tusk_rigid_bind(arm, tusk, f"{label}@{frame}")
            tested.append(f"{label}:{act.name}@{frame}Δ={head_delta:.3f}")
            assert_tusks_in_mouth_for_current_pose(
                arm, tusks, f"{label}:{act.name}@{frame}"
            )
            if arm.animation_data is not None:
                arm.animation_data.action = None

        # 2b) Punch still frame — 21:56 tip floated past lip while Idle/Walk OK.
        punch = None
        for name in ("Punch_Cross", "Punch"):
            punch = bpy.data.actions.get(name)
            if punch is not None:
                break
        if punch is not None:
            punch_frame = action_frame_for_action(punch, "punch")
            HQ.reset_pose(arm)
            HQ.assign_action(arm, punch)
            bpy.context.scene.frame_set(int(punch_frame))
            bpy.context.view_layer.update()
            bpy.context.evaluated_depsgraph_get().update()
            assert_tusks_in_mouth_for_current_pose(
                arm, tusks, f"Punch:{punch.name}@{punch_frame}"
            )
            tested.append(f"Punch:{punch.name}@{punch_frame}")
            if arm.animation_data is not None:
                arm.animation_data.action = None
        else:
            log(
                "assert_tusks_follow_head: no Punch/Punch_Cross in scene yet "
                "(Orrun still import may add it later); still gate will catch Punch"
            )

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
        assert_tusks_in_mouth_for_current_pose(
            arm, tusks, f"Death:{death.name}@{death_frame}"
        )
        log(f"tusk head-local lock OK on clips {tested}")
    finally:
        # Do NOT restore the prior action/NLA mute state here — that left the
        # Death hold frame driving the armature and made rest_after_bind lie.
        force_armature_rest(arm)


def tusk_seat_in_body_space(aperture, sign_x: float) -> tuple[Vector, Vector, float, float, float]:
    """Where one tusk starts, which way it grows, and how big it is.

    Everything is a fraction of the measured aperture, so the tusk scales with
    the maw instead of being a 48 mm constant hoping to land inside it. The
    axis rises (``+Z``), converges toward the midline (dental arch) and leans
    back out of the mouth (``-Y``) so the tip ends up near the rim plane where
    a camera can see it, rather than deep at the cavity floor.

    Returns ``(base, axis, length, radius_base, radius_tip)`` in body object
    space.
    """
    hw = float(aperture.half_width)
    hh = float(aperture.half_height)
    dp = float(aperture.depth)
    base = Vector(
        (
            aperture.center_x + sign_x * TUSK_SEAT_U_FRAC * hw,
            aperture.center_y + TUSK_SEAT_D_FRAC * dp,
            aperture.center_z + TUSK_SEAT_W_FRAC * hh,
        )
    )
    axis = Vector((-sign_x * TUSK_AXIS_MEDIAL, -TUSK_AXIS_OUTWARD, 1.0)).normalized()
    return (
        base,
        axis,
        TUSK_LENGTH_HH_FRAC * hh,
        TUSK_RADIUS_BASE_HH_FRAC * hh,
        TUSK_RADIUS_TIP_HH_FRAC * hh,
    )


def add_tusks(arm, aperture) -> list:
    """Tusks inside the carved maw, BONE-parented to head (follow all clips).

    Author path: measured aperture -> gum seat in body object space -> world ->
    head rest local -> **tip / BONE-parent object space** -> ``parent_type=BONE``
    with Identity ``matrix_parent_inverse``. No Armature modifier, no new bones.

    The cone lives entirely inside the cavity that ``carve_orc_mouth_cavity``
    just bored, which is what makes it visible: there is dark interior behind
    it and open air in front of it. Earlier passes seated cones against an
    unbroken face, so even a numerically perfect placement rendered as skin.
    """
    if "head" not in arm.data.bones:
        raise RuntimeError("53-bone bind missing head bone")
    force_armature_rest(arm)

    body = male_body_mesh(arm)
    left_rim_idx, right_rim_idx = mouth_rim_anchor_verts(arm, aperture)
    head_rest = head_pose_world_matrix(arm)
    head_rest_inv = head_rest.inverted()
    body_rot = body.matrix_world.to_3x3()
    bone_len = head_bone_length(arm)

    mat = make_opaque_mat("OrcTusk", TUSK, 0.55)
    created = []
    for name, sign_x, rim_idx in (
        ("OrcTusk_L", -1.0, left_rim_idx),
        ("OrcTusk_R", 1.0, right_rim_idx),
    ):
        base_b, axis_b, length, r_base, r_tip = tusk_seat_in_body_space(
            aperture, sign_x
        )
        base_w = body_local_to_world(body, base_b)
        axis_w = (body_rot @ axis_b).normalized()
        base_hl = head_rest_inv @ base_w
        axis_hl = world_dir_to_head_local(arm, axis_w)
        base_tp = head_local_to_bone_parent_local(arm, base_hl)
        right, binormal, along = _axis_frame(axis_hl)
        log(
            f"{name} seat body={tuple(round(c, 4) for c in base_b)} "
            f"axis_body={tuple(round(c, 3) for c in axis_b)} "
            f"len={length:.4f} r=({r_base:.4f},{r_tip:.4f}) "
            f"head_local={tuple(round(c, 4) for c in base_hl)} "
            f"axis_head={tuple(round(c, 3) for c in axis_hl)} "
            f"tip_parent={tuple(round(c, 4) for c in base_tp)} "
            f"head_bone_length={bone_len:.4f}"
        )
        if base_hl.length > HEAD_MOUTH_MAX_LOCAL:
            raise RuntimeError(
                f"{name} seat is {base_hl.length:.4f} from the head bone origin "
                f"(> {HEAD_MOUTH_MAX_LOCAL}) — not a mouth on this skull"
            )

        bm = bmesh.new()
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=True,
            segments=TUSK_SEGMENTS,
            radius1=r_base,
            radius2=r_tip,
            depth=length,
        )
        half = 0.5 * length
        for v in bm.verts:
            rise = float(v.co.z) + half
            v.co = (
                Vector(base_tp)
                + float(v.co.x) * right
                + float(v.co.y) * binormal
                + rise * along
            )
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        if not me.vertices:
            raise RuntimeError(f"{name}: cone build produced no vertices")
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append(mat)

        tip_offset = Vector((0.0, bone_len, 0.0))
        acc = Vector((0.0, 0.0, 0.0))
        for v in me.vertices:
            acc += Vector(v.co) + tip_offset
        centroid_hl = acc / float(len(me.vertices))
        rim_hl = head_rest_inv @ evaluated_vertex_world(body, rim_idx)
        obj["orc_tusk_side"] = "R" if sign_x > 0.0 else "L"
        obj["orc_mouth_vert"] = int(rim_idx)
        obj["orc_mouth_vert_head_local"] = [float(c) for c in rim_hl]
        obj["orc_tusk_base_head_local"] = [float(c) for c in base_hl]
        obj["orc_tusk_axis_head_local"] = [float(c) for c in axis_hl]
        obj["orc_tusk_centroid_head_local"] = [float(c) for c in centroid_hl]
        bind_tusk_to_head_bone(obj, arm)
        created.append(obj)

    force_armature_rest(arm)
    assert_tusks_in_mouth_for_current_pose(arm, created, "rest_before_follow")
    assert_tusks_follow_head(arm, created)
    force_armature_rest(arm)
    assert_tusks_in_mouth_for_current_pose(arm, created, "rest_after_bind")
    log(
        f"tusks: {[o.name for o in created]} BONE-parented to head "
        f"(inside the carved maw, aperture-relative seat and scale)"
    )
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
        # The carve painted the oral cavity with material_index 1, and polygon
        # material indices survive a slot rebuild. Re-appending the interior in
        # the same slot is what keeps the maw dark through every re-paint;
        # render_clip_stills calls this twice per still.
        interior_slot = int(obj.get("orc_mouth_interior_slot", -1))
        if interior_slot >= 0:
            if interior_slot != 1:
                raise RuntimeError(
                    f"{obj.name!r} records mouth interior in slot {interior_slot}; "
                    f"this bake only ever authors slot 1"
                )
            me.materials.append(mouth_interior_material())
        worst_slot = max((int(p.material_index) for p in me.polygons), default=0)
        if worst_slot >= len(me.materials):
            raise RuntimeError(
                f"{obj.name!r} has a polygon on material slot {worst_slot} but only "
                f"{len(me.materials)} slot(s) — the mouth interior would render as "
                f"skin and the maw would read closed"
            )
        log(
            f"finished olive-grey skin on mesh={obj.name!r} mat={mat_name!r} "
            f"slots={[m.name for m in me.materials]} "
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


def apply_action_datablock(arm, act, frame: int, *, quiet: bool = False) -> None:
    """Pose dest armature with an exact Action datablock at frame (active action).

    ``quiet`` suppresses the per-pose log line; the bind seam probe applies
    dozens of poses and its own summary is the useful record.
    """
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
    if not quiet:
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


def _preview_stage(*, ground: bool = True) -> None:
    """Ground plane + world background shared by every preview camera."""
    clear_preview_helpers()
    if ground:
        ground_mat = make_opaque_mat("PreviewGround", (0.18, 0.175, 0.165), 1.0)
        bpy.ops.mesh.primitive_plane_add(size=12.0, location=(0.0, 0.0, 0.0))
        plane = bpy.context.active_object
        plane.name = "PreviewGround"
        plane.data.materials.append(ground_mat)
    world = bpy.data.worlds.new("PreviewWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.14, 0.145, 0.155, 1.0)
        bg.inputs[1].default_value = 1.0


def _preview_lights(scale: float = 1.0) -> None:
    """Key / fill / rim rig shared by every preview camera."""

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
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0 * scale, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0 * scale, size=1.6)


def _preview_camera(location: Vector, target: Vector, *, lens: float = STILL_LENS_MM):
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = lens
    # Pin the sensor: orc_still_visibility measures the tusk footprint in pixels
    # against these exact numbers, and a default that drifted would make the
    # measurement and the render disagree.
    cam_data.sensor_fit = "AUTO"
    cam_data.sensor_width = STILL_SENSOR_MM
    # The mouth close-up stands ~0.3 m off the face, so the nose is within the
    # 0.1 m default near plane and would be clipped out of the frame.
    cam_data.clip_start = 0.01
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector(location)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def _preview_render_settings(width: int, height: int) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue


def setup_standing_preview(center, extent, *, look_at=None, show_head: bool = False) -> None:
    _preview_stage()
    span = max(float(extent.x), float(extent.y), float(extent.z), 0.8)
    if look_at is None:
        target = Vector((center.x, center.y, max(center.z, 0.9)))
    else:
        target = Vector(look_at)
    if show_head:
        # Pull back / raise so Punch keeps dest head + tusks in frame.
        location = Vector(
            (
                center.x + span * 1.55,
                center.y - span * 2.25,
                max(target.z + span * 0.20, center.z + span * 0.55, 1.75),
            )
        )
    else:
        location = Vector(
            (
                center.x + span * 1.35,
                center.y - span * 1.85,
                max(center.z + span * 0.35, 1.55),
            )
        )
    cam = _preview_camera(location, target, lens=STILL_LENS_MM)
    _preview_lights()
    _preview_render_settings(640, 800)
    if show_head:
        log(
            f"standing cam (head) loc={tuple(round(c, 3) for c in cam.location)} "
            f"look={tuple(round(c, 3) for c in target)}"
        )


def setup_death_preview(center, extent, *, look_at=None) -> None:
    """Camera framing from preview_bandit_death / bake_bandit_death."""
    _preview_stage()
    span = max(float(extent.x), float(extent.y), float(extent.z), 0.8)
    location = Vector(
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
    cam = _preview_camera(location, target, lens=STILL_LENS_MM)
    _preview_lights()
    _preview_render_settings(800, 1000)
    log(
        f"death cam={tuple(round(c, 3) for c in cam.location)} "
        f"look={tuple(round(c, 3) for c in target)}"
    )


def _t3(v) -> tuple:
    return (float(v[0]), float(v[1]), float(v[2]))


def tusk_target_points(tusks: list) -> list:
    """Sampled tusk world points for the visibility measurement.

    Subsampled because occlusion is exact segment-triangle work and the sweep
    tries many camera directions; the whole cone is not needed to know whether
    a reviewer can see it.
    """
    pts = []
    for tusk in tusks:
        verts = _evaluated_mesh_verts_world(tusk)
        if not verts:
            raise RuntimeError(f"{tusk.name!r} evaluated to no vertices")
        step = max(1, len(verts) // max(1, STILL_TUSK_SAMPLES_PER_TUSK))
        pts.extend(_t3(v) for v in verts[::step])
    if not pts:
        raise RuntimeError("tusk_target_points: no tusk vertices to measure")
    return pts


def near_head_occluder_tris(arm, tusks: list, centre, radius: float) -> list:
    """Triangles near the mouth from everything except the tusks themselves.

    Includes the head: from an oblique angle the cheek is exactly what blocks
    the view into the maw, and a sweep that ignored it would happily pick a
    camera looking through the face.
    """
    skip = {t.name for t in tusks}
    c = Vector(centre)
    r2 = radius * radius
    tris = []
    deps = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.name in skip:
            continue
        if obj.name.startswith("Preview") or obj.name == "PreviewGround":
            continue
        if obj.hide_render or obj.hide_viewport:
            continue
        if not obj.users_collection:
            continue  # unlinked junk (hidden Eyes) cannot occlude a render
        ev = obj.evaluated_get(deps)
        me = ev.to_mesh()
        try:
            if not me.vertices:
                continue
            mw = ev.matrix_world
            world = [mw @ v.co for v in me.vertices]
            near = [(p - c).length_squared <= r2 for p in world]
            if hasattr(me, "calc_loop_triangles"):
                me.calc_loop_triangles()
            if me.polygons and not me.loop_triangles:
                raise RuntimeError(
                    f"{obj.name!r} evaluated mesh has {len(me.polygons)} polygon(s) "
                    f"but no loop triangles — cannot test what occludes the mouth"
                )
            for lt in me.loop_triangles:
                a, b, d = (int(i) for i in lt.vertices)
                if not (near[a] or near[b] or near[d]):
                    continue
                tris.append((_t3(world[a]), _t3(world[b]), _t3(world[d])))
        finally:
            ev.to_mesh_clear()
    return tris


def measure_tusk_visibility(
    cam_origin, look_at, up_hint, targets: list, tris: list, *, res_x: int, res_y: int
) -> dict:
    """Visibility of the tusks from one camera placement, in pixels."""
    return SV.visibility_report(
        _t3(cam_origin),
        _t3(look_at),
        _t3(up_hint),
        targets,
        tris,
        lens=STILL_LENS_MM,
        sensor_width=STILL_SENSOR_MM,
        sensor_height=STILL_SENSOR_MM,
        res_x=int(res_x),
        res_y=int(res_y),
    )


def choose_mouth_closeup_view(arm, tusks: list, *, strict: bool = True):
    """Pick a close-up camera placement that can actually see the tusks.

    Sweeps azimuth and elevation around the mouth axis and takes the first
    placement that clears ``STILL_MIN_VISIBLE_FRAC`` and
    ``STILL_MIN_TUSK_PX``, straight-on first. This is the fix for "Punch: tusks
    not readable on this still": Punch_Cross holds the guard hand in front of
    the mouth, so the straight-on view is a picture of the back of a hand. No
    tusk-placement gate can detect that — only measuring the camera can.
    """
    frame = posed_aperture_frame(arm)
    centre = frame["center"]
    out = -Vector(frame["inward"])
    up = Vector(frame["up"])
    reach = MOUTH_CLOSEUP_REACH_HEAD_WIDTHS * float(frame["head_width"])
    targets = tusk_target_points(tusks)
    tris = near_head_occluder_tris(
        arm, tusks, centre, STILL_OCCLUDER_RADIUS_HEAD_WIDTHS * float(frame["head_width"])
    )
    candidates = SV.view_directions(
        _t3(out), _t3(up), MOUTH_CLOSEUP_AZIMUTHS, MOUTH_CLOSEUP_ELEVATIONS
    )
    best = None
    tried = 0
    for az, el, d in candidates:
        direction = Vector(d)
        location = centre + direction * reach
        if float(location.z) < MOUTH_CLOSEUP_MIN_CAM_Z:
            continue  # under the preview ground plane; it would render the plane
        report = measure_tusk_visibility(
            location,
            centre,
            STILL_CAMERA_UP,
            targets,
            tris,
            res_x=MOUTH_CLOSEUP_RES,
            res_y=MOUTH_CLOSEUP_RES,
        )
        tried += 1
        scored = {
            "azimuth": az,
            "elevation": el,
            "location": location,
            "reach": reach,
            "report": report,
        }
        if best is None or report["visible_frac"] > best["report"]["visible_frac"]:
            best = scored
        if (
            report["visible_frac"] >= STILL_MIN_VISIBLE_FRAC
            and max(report["px_w"], report["px_h"]) >= STILL_MIN_TUSK_PX
        ):
            scored["ok"] = True
            log(
                f"mouth close-up view azimuth={az:.0f} elevation={el:.0f} "
                f"visible_frac={report['visible_frac']:.2f} "
                f"px={report['px_w']:.0f}x{report['px_h']:.0f} "
                f"(candidate {tried} of {len(candidates)}, "
                f"{len(tris)} occluder tris, {len(targets)} tusk samples)"
            )
            return scored
    if best is None:
        raise RuntimeError(
            "mouth close-up: every candidate camera fell below the ground plane "
            f"(reach={reach:.3f}, centre={tuple(round(c, 3) for c in centre)})"
        )
    best["ok"] = False
    r = best["report"]
    if not strict:
        return best
    raise RuntimeError(
        f"mouth close-up cannot see the tusks from any of {tried} view(s): best "
        f"visible_frac={r['visible_frac']:.2f} (need {STILL_MIN_VISIBLE_FRAC}) "
        f"px={r['px_w']:.0f}x{r['px_h']:.0f} (need {STILL_MIN_TUSK_PX} on the "
        f"larger axis) "
        f"at azimuth={best['azimuth']:.0f} elevation={best['elevation']:.0f}; "
        f"{len(tris)} occluder tris within "
        f"{STILL_OCCLUDER_RADIUS_HEAD_WIDTHS} head widths. Something is in front "
        f"of the mouth in this pose — refusing a still that cannot show the maw"
    )


def setup_mouth_closeup_preview(arm, tusks: list) -> dict:
    """Frame the posed maw so the tusks are actually made of pixels.

    The body stills cannot do this job. They frame a ~1.8 m figure from ~5 m on
    a 50 mm lens at 640x800, about 4.4 mm per pixel, so a 26 mm tusk is around
    ten pixels — and on Punch the guard hand covers the mouth outright while on
    Death the overhead camera sees the top of a supine head. So render a second
    still per clip on a view direction chosen by measuring what it can see.
    """
    view = choose_mouth_closeup_view(arm, tusks)
    frame = posed_aperture_frame(arm)
    centre = frame["center"]
    up = Vector(frame["up"])
    location = view["location"]
    reach = view["reach"]
    _preview_stage()
    cam = _preview_camera(location, centre, lens=STILL_LENS_MM)
    _preview_lights(scale=0.35)
    # A dedicated fill on the mouth axis: a concave cavity is self-shadowing,
    # so without it the maw renders as a black hole and takes the ivory with it.
    # Power is derived from the standoff instead of being a fixed wattage: this
    # light sits ~0.3 m from the face, where the body rig's 200 W fill at 3 m
    # would be a hundred times too bright.
    key_distance = MOUTH_CLOSEUP_KEY_STANDOFF * reach
    key_dir = (location - centre).normalized()
    mouth_key = bpy.data.lights.new("MouthKey", "AREA")
    mouth_key.energy = (
        MOUTH_CLOSEUP_KEY_IRRADIANCE * 2.0 * math.pi * key_distance * key_distance
    )
    mouth_key.size = max(0.5 * reach, 0.05)
    key_obj = bpy.data.objects.new("MouthKey", mouth_key)
    key_obj.location = centre + key_dir * key_distance + up * (0.35 * key_distance)
    key_obj.rotation_euler = (
        (centre - key_obj.location).to_track_quat("-Z", "Y").to_euler()
    )
    bpy.context.scene.collection.objects.link(key_obj)
    _preview_render_settings(MOUTH_CLOSEUP_RES, MOUTH_CLOSEUP_RES)
    report = view["report"]
    log(
        f"mouth close-up cam loc={tuple(round(c, 3) for c in cam.location)} "
        f"look={tuple(round(c, 3) for c in centre)} reach={reach:.3f} "
        f"azimuth={view['azimuth']:.0f} elevation={view['elevation']:.0f} "
        f"tusk_visible_frac={report['visible_frac']:.2f} "
        f"tusk_px={report['px_w']:.0f}x{report['px_h']:.0f} "
        f"key_dist={key_distance:.3f} key_energy={mouth_key.energy:.2f}W"
    )
    return {
        "camera": [round(float(c), 4) for c in cam.location],
        "look_at": [round(float(c), 4) for c in centre],
        "reach_m": round(reach, 4),
        "azimuth_deg": round(float(view["azimuth"]), 1),
        "elevation_deg": round(float(view["elevation"]), 1),
        "tusk_visible_frac": round(float(report["visible_frac"]), 3),
        "tusk_px_w": round(float(report["px_w"]), 1),
        "tusk_px_h": round(float(report["px_h"]), 1),
    }


def live_tusk_meshes(arm) -> list:
    """The tusk objects for the stills, from the visible set or the whole scene."""
    meshes = ensure_dest_identity_visible(arm)
    tusks = [
        o
        for o in meshes
        if o.name.startswith("OrcTusk_") or "tusk" in o.name.lower()
    ]
    if len(tusks) < 2:
        tusks = [
            o
            for o in bpy.data.objects
            if o.type == "MESH"
            and (o.name.startswith("OrcTusk_") or "tusk" in o.name.lower())
        ]
    if len(tusks) < 2:
        raise RuntimeError(
            f"expected two tusk meshes for the stills, found "
            f"{[o.name for o in tusks]}"
        )
    return tusks


def choose_punch_still_frame(arm, punch_act, tusks: list) -> int:
    """Pick the Punch still frame by measuring whether the mouth is visible.

    Punch_Cross keeps the guard hand at the chin through much of the throw, so
    a fixed 55 % frame can be a picture of the back of a hand — which is
    exactly what f4d2059's Punch still was. Same clip and no invented pose:
    only the frame moves, and only inside a band that still reads as a punch.
    The direction sweep is tried at each frame first, so the frame only moves
    when no camera angle can see past the hand.
    """
    fr = tuple(punch_act.frame_range)
    lo, hi = int(round(fr[0])), int(round(fr[1]))
    if hi <= lo:
        return int(action_frame_for_action(punch_act, "punch"))
    tried = []
    for frac in PUNCH_STILL_FRAME_FRACS:
        frame = lo + max(1, int(round((hi - lo) * frac)))
        apply_action_datablock(arm, punch_act, frame, quiet=True)
        view = choose_mouth_closeup_view(arm, tusks, strict=False)
        report = view["report"]
        tried.append(
            f"{frac:.0%}@{frame}: visible_frac={report['visible_frac']:.2f} "
            f"px_h={report['px_h']:.0f}"
        )
        if view.get("ok"):
            log(
                f"Punch still frame {frame} ({frac:.0%} of {punch_act.name!r}) "
                "shows the maw; tried " + "; ".join(tried)
            )
            return frame
    raise RuntimeError(
        f"no {punch_act.name!r} frame in the "
        f"{min(PUNCH_STILL_FRAME_FRACS):.0%}-{max(PUNCH_STILL_FRAME_FRACS):.0%} "
        "band lets any camera see the maw: " + "; ".join(tried) + ". Something "
        "covers the mouth throughout the throw. Do not invent a clip."
    )


def log_body_still_tusk_visibility(arm, tusks: list, label: str) -> dict:
    """Report what the body still shows of the tusks. Logged, never gated.

    The body still exists to show silhouette and torso; whether it happens to
    read the tusks depends on the pose, and on Punch and Death it does not.
    Measuring it anyway keeps that a number in the log rather than an argument.
    """
    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        raise RuntimeError(f"{label}: no scene camera to measure tusk visibility")
    frame = posed_aperture_frame(arm)
    targets = tusk_target_points(tusks)
    tris = near_head_occluder_tris(
        arm,
        tusks,
        frame["center"],
        STILL_OCCLUDER_RADIUS_HEAD_WIDTHS * float(frame["head_width"]),
    )
    report = measure_tusk_visibility(
        cam.location,
        frame["center"],
        STILL_CAMERA_UP,
        targets,
        tris,
        res_x=scene.render.resolution_x,
        res_y=scene.render.resolution_y,
    )
    log(
        f"{label} body still tusk visibility: visible_frac="
        f"{report['visible_frac']:.2f} in_frame_frac={report['in_frame_frac']:.2f} "
        f"px={report['px_w']:.0f}x{report['px_h']:.0f} — the *_mouth close-up is "
        f"the tusk evidence for this clip"
    )
    return report


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

    # Tusks are the same objects for every clip; the Punch frame choice needs
    # them before the render loop starts.
    tusks_live = live_tusk_meshes(arm)
    frames = {
        "Idle": action_frame(resolved["Idle"], "idle"),
        "Walk": action_frame(resolved["Walk"], "walk"),
        "Punch": choose_punch_still_frame(arm, punch_act, tusks_live),
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
    mouth_out = {}
    mouth_cams = {}
    body_vis = {}
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
        # Gate the PNG Reviewer sees — numeric lock alone passed while stills floated.
        hide_junk_companion_meshes(arm)
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
            # Idle/Walk: same head-aware framing as Punch so 50mm mouth tusks
            # read in the PNG (full-body far cam hid a4a5c61 ivory).
            head = head_world_pos(arm)
            center = Vector((center.x, center.y, max(center.z, head.z * 0.55 + 0.35)))
            setup_standing_preview(center, extent, look_at=head, show_head=True)

        # Re-assert after camera setup (must not have broken bone parent).
        hide_junk_companion_meshes(arm)
        assert_tusks_in_mouth_for_current_pose(arm, tusks_live, f"{label}_pre_render")
        body_vis[label] = {
            k: round(float(v), 3)
            for k, v in log_body_still_tusk_visibility(arm, tusks_live, label).items()
        }
        path = still_path(tag, label)
        render_png(path)
        out[label] = str(path)

        # Second still on the mouth axis. The body still proves the silhouette;
        # only this one can show whether the tusks are in the maw.
        cam_info = setup_mouth_closeup_preview(arm, tusks_live)
        assert_tusks_in_mouth_for_current_pose(
            arm, tusks_live, f"{label}_pre_mouth_render"
        )
        mouth_path = still_path(tag, label, view="mouth")
        render_png(mouth_path)
        mouth_out[label] = str(mouth_path)
        mouth_cams[label] = cam_info
        log(
            f"still {tag}/{label} arm={arm.name!r} action={clip_label!r} "
            f"frame={frame} meshes={sorted(o.name for o in meshes)} -> "
            f"{path.name} + {mouth_path.name}"
        )
    out["_frames"] = {k: frames[k] for k in PREVIEW_CLIPS}
    out["_actions"] = {k: action_for[k] for k in PREVIEW_CLIPS}
    out["_mouth"] = mouth_out
    out["_mouth_cams"] = mouth_cams
    out["_body_vis"] = body_vis
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
    # Complete the bind before anything reads or edits it. A vert whose only
    # weight is on a group no bone drives is frozen at rest, and every gate
    # downstream assumes that cannot happen.
    rehome_unbound_verts(arm, "male_base attach")
    assert_all_skin_verts_bound(arm, "male_base attach")
    # Measure the mouth ONCE, on the untouched male_base face, before any
    # restyle offset can move the landmarks it is measured from. Everything
    # downstream reads this frame instead of re-deriving the mouth.
    aperture = resolve_mouth_aperture(arm)
    restyle_face(arm, aperture)  # jaw + brow flatten only, no mouth, no chest
    carve_orc_mouth_cavity(arm, aperture)
    # Repair torso seams that tear under the still poses, measured on the
    # shipped mesh. Must precede add_tusks: its Punch/Death follow probes run
    # the same torso gate, which is where af0e428 refused.
    repair_bind_seams(arm)
    store_mouth_aperture(arm, aperture)
    tusks = add_tusks(arm, aperture)
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
    mouth_previews = after_previews.pop("_mouth", {})
    mouth_cams = after_previews.pop("_mouth_cams", {})
    body_vis = after_previews.pop("_body_vis", {})
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
        mouth_previews=mouth_previews,
        hip_before=hip_before,
        hip_after=hip_after,
        tusks=[o.name for o in tusks],
        gear=[],  # nude pass — no invented clothes
        removed_garments=removed_garments,
    )
    packet["still_frames"] = still_frames
    packet["still_actions"] = still_actions
    packet["mouth_cameras"] = mouth_cams
    packet["body_still_tusk_visibility"] = body_vis
    packet["mouth_aperture"] = mouth_aperture_report(aperture)
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
        "previews_after_mouth": mouth_previews,
        "mouth_cameras": mouth_cams,
        "body_still_tusk_visibility": body_vis,
        "mouth_aperture": mouth_aperture_report(aperture),
        "still_frames": still_frames,
        "still_actions": still_actions,
        "art_review_packet": str(ART_REVIEW_PACKET),
        "clip_list_md": str(CLIP_LIST_MD),
        "uv_layout_hint": str(UV_LAYOUT),
        "lookdev": str(LOOKDEV),
        "note": (
            "Nude pass: DEST after stills; measured mouth aperture -> bored "
            "cavity -> tusks seated in it; male_body brow flatten; no OrcGear; "
            "Punch=Orrun Punch_Cross; Death=dest-native metrics (not root_z=0 "
            "FP); olive on male_body; mouth close-up still per clip"
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
