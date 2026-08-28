# Orc Look-Dev & Material Targets (`male_orc_01`)

This directory contains artistic look-dev stills, material targets, and concept albedo reference boards for the ambitious orc restyle on the MakeHuman 53-bone skeleton donor (`male_dressed_male_worksuit01.glb` -> `male_orc_01.glb`).

> **Note**: These images serve strictly as visual look-dev and material targets. They are **NOT** UV maps or dest-UV ready unwraps. When `male_orc_01_uv_layout.png` is generated, final albedo textures will be mapped onto the exact destination MakeHuman UV islands without automated projection artifacts.

---

## Look-Dev Render Gallery

### 1. Full Body Stills (Upright Humanoid, No Weapons)
- **Front View**: `orc_lookdev_front.png` — Upright posture (no ogre hunch), broad shoulders, muscular chest, dark leather harness, studded belt, loincloth, arm & leg wraps. No cleaver or shield.
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

### 4. Concept Albedo Reference (Not UV Ready)
- **Concept Reference**: `orc_albedo_concept_not_uv_ready.png`
  - Flat color swatches, textile references, skin palettes, and markings marked explicitly as `CONCEPT ALBEDO REFERENCE - NOT UV READY`.

---

## Anatomy & Rigging Design Constraints
- **Creature Family**: Distinct orc anatomy (not a painted human or cartoon caricature).
- **Skeleton**: Preserves MakeHuman 53-bone bind hierarchy.
- **Locomotion Invariants**: No scaling on pelvis/thigh/calf bones; upright humanoid gait without ogre hunch, digitigrade legs, wings, or tails.
- **Gear**: Dropped cleaver and shield from donor model; focused on base body mesh, head/jaw/tusk geometry, and harness/wrap attire.
