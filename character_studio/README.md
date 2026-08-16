# Character Studio

Focused Godot app for editing MPFB body + face morphs with a **front-facing** preview.
The character is assembled at runtime: a body plus one suit and one pair of shoes,
all bound to a single skeleton, so no outfit combination has to be pre-baked.
Lives in Asset Lab; does not change the City in-game editor.

## Run

```bat
character_studio\CharacterStudio.bat
```

First launch imports the Godot project (builds `.godot/` class/cache data). That is
required once so `class_name` scripts resolve; the bat does it automatically.

Or:

```bat
python tools\sync_character_studio_assets.py
"<path-to-Godot-4.6>" --path character_studio --headless --import
"<path-to-Godot-4.6>" --path character_studio
```

Default Godot binary: `..\..\City\tools\godot\Godot_v4.6-voxel_win64.exe`  
Override with `GODOT_BIN`.

## Controls

| Input | Action |
| --- | --- |
| Left-drag | Orbit |
| Mouse wheel | Zoom |
| **Frame face** / **Frame body** | Camera presets (face is default) |
| Male / Female | Swap base sex |
| Suit / Shoes / Hair / Eyebrows | Equip a piece, or `None` |
| Body + Face sliders | Live morphs |
| Randomize / Reset | Props |

## Assets

Everything is built by Asset Lab’s own MPFB export
(`tools/character_studio/blender_export_humans.py`):

The library lives at repo-root [`assets/humans/`](../assets/humans/), not inside
this Godot project. Character Studio sees it as `res://assets/humans` through a
junction created by `python tools/sync_character_studio_assets.py --link-only`.

| Output | Contents |
| --- | --- |
| `assets/humans/{sex}_base.glb` | Nude body, 28 face morphs, fitted `Eyes` mesh |
| `assets/humans/{sex}_dressed_{suit}.glb` | Same body with that suit’s delete mask applied |
| `assets/humans/pieces/{sex}_{garment}.glb` | One garment on the shared `game_engine` rig |
| `assets/humans/wardrobe.json` | Slot/label/path catalogue the runtime reads |

Choosing a suit swaps the body; shoes, hair and eyebrows do not, because none of
them need a body delete mask. That keeps the body count linear in the number of
suits (11 today) instead of combinatorial. Eyebrows and hair both offer `None`.

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

## Medieval / community clothes

Free MakeHuman clothes (Suits 02 medieval subset + community CC0/CC-BY dresses)
live under `tools/character_studio/makehuman_extra_assets/` after:

```bash
python tools/character_studio/fetch_medieval_clothes.py
python tools/sync_character_studio_assets.py
```

License notes are in `makehuman_extra_assets/LICENSES.json`. The non-historical
medieval dress is **CC-BY** (attribution required); everything else pulled here
is CC0.

## Adding a garment

1. Put a MakeHuman `.mhclo` folder under
   `tools/character_studio/makehuman_extra_assets/clothes/` (or the City system
   pack).
2. Add it to `WARDROBE_SUITS` or `WARDROBE_SHOES` in
   `tools/character_studio/blender_export_humans.py`. Multi-piece suits use
   `(id, label, (part_a, part_b))`.
3. Re-export. A new suit also means a new dressed body; a new pair of shoes is
   just one more piece.

Eye morph caveat: `face_eye_size` / `face_eye_spacing` deform the basemesh lids
only. The eyeballs are a separate fitted mesh, so extreme values on those two
sliders can drift from the lids.
