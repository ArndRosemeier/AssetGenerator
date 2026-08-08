# Character Studio

Focused Godot app for editing MPFB body + face morphs with a **front-facing** preview.
Lives in Asset Lab; does not change the City in-game editor.

## Run

```bat
character_studio\CharacterStudio.bat
```

Or:

```bat
python tools\sync_character_studio_assets.py
"<path-to-Godot-4.6>" --path character_studio
```

Default Godot binary: `..\City\tools\godot\Godot_v4.6-voxel_win64.exe`  
Override with `GODOT_BIN`.

## Controls

| Input | Action |
| --- | --- |
| Left-drag | Orbit |
| Mouse wheel | Zoom |
| **Frame face** / **Frame body** | Camera presets (face is default) |
| Male / Female | Swap base sex |
| Nude base / Casual outfit | Swap mesh |
| Body + Face sliders | Live morphs |
| Randomize / Reset | Props |

## Assets

Human `.glb` files are built by Asset Lab’s own MPFB export
(`tools/character_studio/blender_export_humans.py`). Each one carries the 28 face
morphs plus a fitted `Eyes` mesh from the MakeHuman CC0 low-poly eyeballs,
weighted to the head bone.

```bash
python tools/sync_character_studio_assets.py                     # export all four
python tools/sync_character_studio_assets.py --only male_base    # one at a time
tools\character_studio\export_humans.bat                         # same, straight to Blender
```

The export reuses the Blender 4.2 + MPFB + MakeHuman assets vendored in the City
checkout (`CITY_ROOT`, default `..\City`) but writes nothing there. If that
toolchain is missing, `--copy-from-city` copies City’s exported GLBs instead —
those have no eyes.

Eye morph caveat: `face_eye_size` / `face_eye_spacing` deform the basemesh lids
only. The eyeballs are a separate fitted mesh, so extreme values on those two
sliders can drift from the lids.
