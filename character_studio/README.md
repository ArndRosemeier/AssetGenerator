# Character Studio

Focused Godot app for editing MPFB body + face morphs with a **front-facing** preview.
The character is assembled at runtime: a body plus one suit and one pair of shoes,
all bound to a single skeleton, so no outfit combination has to be pre-baked.
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
| Suit / Shoes | Equip a garment, or `None` |
| Body + Face sliders | Live morphs |
| Randomize / Reset | Props |

## Assets

Everything is built by Asset Lab’s own MPFB export
(`tools/character_studio/blender_export_humans.py`):

| Output | Contents |
| --- | --- |
| `assets/humans/{sex}_base.glb` | Nude body, 28 face morphs, fitted `Eyes` mesh |
| `assets/humans/{sex}_dressed_{suit}.glb` | Same body with that suit’s delete mask applied |
| `assets/humans/pieces/{sex}_{garment}.glb` | One garment on the shared `game_engine` rig |
| `assets/humans/wardrobe.json` | Slot/label/path catalogue the runtime reads |

Choosing a suit swaps the body; choosing shoes does not, because shoes enclose
the foot and need no delete mask. That keeps the body count linear in the number
of suits (11 today) instead of combinatorial.

```bash
python tools/sync_character_studio_assets.py                     # full modular set
python tools/sync_character_studio_assets.py --only male_base    # one at a time
tools\character_studio\export_humans.bat                         # same, straight to Blender
```

The export reuses the Blender 4.2 + MPFB + MakeHuman assets vendored in the City
checkout (`CITY_ROOT`, default `..\City`) but writes nothing there.

`tools/shoot_studio.gd` renders a handful of wardrobe combinations to PNG for
review; it needs a real window, so run it without `--headless`:

```bash
"<godot>" --path character_studio --script tools/shoot_studio.gd -- --out=C:/tmp/shots
```

## Adding a garment

Add it to `WARDROBE_SUITS` or `WARDROBE_SHOES` in
`tools/character_studio/blender_export_humans.py` and re-export. A new suit also
means a new dressed body; a new pair of shoes is just one more piece.

Eye morph caveat: `face_eye_size` / `face_eye_spacing` deform the basemesh lids
only. The eyeballs are a separate fitted mesh, so extreme values on those two
sliders can drift from the lids.
