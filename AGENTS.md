# Working in this repo (for coding agents)

This repo builds engine-agnostic 3D assets (.glb) from JSON specs, with Blender running
headless underneath. You never open Blender and never write `bpy` in a generator.

**Read first:** [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) (process, commands, QA gates,
known pitfalls), then [`docs/ASSETKIT.md`](docs/ASSETKIT.md) (the kit: shapes, rigs and
animation, materials, the inspection sheet).

## The loop

1. An asset is a spec: `assets/specs/<id>.json`. Change the **spec** first; change a
   generator only when no parameter can express what you need.
2. `python tools/ag.py look <id>`: the inspection sheet `assets/out/look/<id>.png` in seconds,
   without Blender (kit generators). **Open the PNG and look at it**, and read the report lines:
   floating parts, holes, inside-out faces, balance, z-fighting, and for rigs and materials
   their own flags (`<id>_rig.png`; `pattern ...` coverage per layer). Assets that fit
   together (tiles): `look kit:<name>` measures every joint.
3. `python tools/ag.py generate <id>`: build in Blender, QA gates, export, previews. Exit 0 is
   green. Blender as a Python module: set `BLENDER_PYTHON` (see README).
4. `python -m unittest discover tests` must pass. Commit specs and code, never `assets/out/`.

## What exists, and where to start

| You want | Write | Reference |
| --- | --- | --- |
| Rocks, stumps, creatures, any organic form | an `organic.sculpt` spec: a JSON tree of shapes | "Sculpting organic forms" in ASSETKIT.md, `assets/specs/sculpt_*.json`, `creature_*.json` |
| It moves | a `rig` in that spec: bones, skin, clips (gait, limps, turns, keys) | "Rigging and animating a sculpt", `creature_gloom_crawler.json` (six legs), `creature_crypt_husk.json` (biped, limp) |
| Lanterns, chests, tools, furniture: turned, cut and bent parts | a `prop.assembly` spec: exact pieces, repeated and mirrored | "Hard-surface props in JSON", `prop_crypt_lantern.json` |
| Bark, rust, moss, chitin, worn edges, dirt, glass, grooves and bumps | a `pattern` (or `alpha`; `relief` for a normal map) on the spec's material | "Materials", `sculpt_tree_stump.json`, `prop_crypt_lantern.json` |
| Wheels, doors, cranks; cloth, banners, sails | a `rig` in a `prop.assembly` spec: pieces tied to a `bone` (rigid) or `bones` (bending); `spin`, `wave` | "Moving parts", `prop_mill_waterwheel.json`, `prop_hanging_banner.json` |
| Walls, floors, fences: tiles that fit together | `prop.assembly` with `settle: false`, patterns with a `period` (`bricks`), and a kit `assets/kits/<name>.json` | "Tiles that fit together", "Kits", `tile_brick_wall.json`, `brick_wall_run.json` |

## Rules

- Generators listed in `KIT_GENERATORS` import `assetkit` and the standard library only.
  Blender-version differences live in `blender/backend/compat.py`, nowhere else.
- Same spec, same output: vary with `seed`, never with unseeded randomness.
- Do not weaken a QA gate to get green; fix the spec or the generator.
- Read the report's flags before you look: they name what to fix and where (`skin tears ...
  at chest/upper_arm.L`, `cavities (layer 4) does not show`, `1 floating part`, `tips over`).
