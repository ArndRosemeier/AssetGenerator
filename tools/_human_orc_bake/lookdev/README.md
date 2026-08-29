# Orc Look-Dev & Material Targets (`male_orc_01`)

This directory contains artistic look-dev stills, material targets, concept albedo reference boards, and UV island layout paintovers for the ambitious orc restyle on the MakeHuman 53-bone skeleton donor (`male_dressed_male_worksuit01.glb` -> `male_orc_01.glb`).

> **CRITICAL LOOK-DEV DISCLAIMER**:
> This directory is **strictly look-dev exploration only**. These assets are **NOT** drop-in albedo textures, **NOT** final game-ready UV unwraps, and **NOT** a skinned-mesh review packet.
> Any UV-oriented sheets (such as `orc_male_base_uv_paintover_not_uv_ready.png` and `orc_albedo_concept_not_uv_ready.png`) are marked **`NOT UV-READY`**. They serve purely as guide paintovers to visualize how albedo detail, skin tones, and gear line up with MakeHuman `male_base` UV islands. Final texture baking and projection must be executed through the Art Pipeline.

---

## Look-Dev Render Gallery

### 1. Full Body Stills (Upright Humanoid, No Weapons)
- **Three-Quarter View**: `orc_lookdev_threequarter_not_uv_ready.png` — Upright posture without ogre hunch, broad shoulders, muscular build, olive-grey skin, leather chest harness with bronze/iron ring, studded belt, loincloth, forearm and shin wraps. Cleaver and shield dropped.
- **Front View**: `orc_lookdev_front.png` — Upright posture, broad shoulders, muscular chest, dark leather harness, studded belt, loincloth, arm & leg wraps. No cleaver or shield.
- **Side View**: `orc_lookdev_side.png` — Natural spine curvature, plantigrade stance, protruding lower jaw with upward lower tusks, leather strap harness, profile silhouette.
- **Back View**: `orc_lookdev_back.png` — Defined back and lat muscle anatomy, topknot hair fastening, rear harness ring connections, loincloth draping.

### 2. Facial Close-Up
- **Face Close-Up**: `orc_lookdev_face_closeup.png` — Heavy squared lower jaw, upward lower ivory tusks, pointed ears, weathered skin pores/scars, amber eyes, epidermal shading reference.

### 3. PBR Material Target Board
- **Material Board**: `orc_material_board.png`
  - **1) Olive-Grey Skin**: Base Color `#485638` (sRGB), Roughness `0.65`, Subsurface Scattering.
  - **2) Weathered Leather**: Base Color `#3D261A`, Roughness `0.78`, distressed hide grain.
  - **3) Tusk Ivory**: Base Color `#EAE0C8`, Roughness `0.35`, gradient from warm base to bone white.
  - **4) Cast Metal Rings**: Metallic `0.90`, Roughness `0.40`, dark hammered iron / bronze.

### 4. UV Island Concept Paintovers & Albedo Swatch Sheets (Not UV-Ready)
- **MakeHuman UV Island Look-Dev Paintover**: `male_base_orc_lookdev_albedo_not_uv_ready.png` & `orc_male_base_uv_paintover_not_uv_ready.png`
  - Look-dev paintover painted directly into the MakeHuman `male_base` destination UV island layout:
    - Main body island (left): olive-grey skin, muscular torso, leather chest X-harness with bronze ring, studded belt, loincloth, leg wraps.
    - Head island (right): olive-grey skin, heavy brow, upward tusks, pointed ears, scars.
    - Peripheral islands: ears (far left), feet (bottom left), hands (bottom center-right), and neck/scalp (bottom right).
  - Explicitly watermarked: `NOT UV-READY - FOR LOOK-DEV ONLY (REQUIRES BLENDER PROJECTION)`.
- **Concept Reference & Palette**: `orc_albedo_concept_not_uv_ready.png`
  - Flat color swatches, textile references, skin palettes, and scars/markings marked explicitly as `CONCEPT ALBEDO REFERENCE - NOT UV READY`.

---

## Anatomy & Rigging Design Constraints
- **Creature Family**: Distinct orc anatomy (not a painted human or cartoon caricature).
- **Skeleton**: Preserves MakeHuman 53-bone bind hierarchy.
- **Locomotion Invariants**: No scaling on pelvis/thigh/calf bones; upright humanoid gait without ogre hunch, digitigrade legs, wings, or tails.
- **Gear**: Dropped cleaver and shield from donor model; focused on base body mesh, head/jaw/tusk geometry, and harness/wrap attire.
- **No Animations / Script Edits**: No punch/death animations invented, no `.glb` exports generated, no edits to Python bake/retarget scripts (`tools/bake_human_orc.py` untouched).
