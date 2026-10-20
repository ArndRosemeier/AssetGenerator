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
   floating parts, holes, inside-out faces, balance, and for rigs and materials their own
   flags (`<id>_rig.png`; `pattern ...` coverage per layer).
3. `python tools/ag.py generate <id>`: build in Blender, QA gates, export, previews. Exit 0 is
   green. Blender as a Python module: set `BLENDER_PYTHON` (see README).
4. `python -m unittest discover tests` must pass. Commit specs and code, never `assets/out/`.

## What exists, and where to start

| You want | Write | Reference |
| --- | --- | --- |
| Rocks, stumps, creatures, any organic form | an `organic.sculpt` spec: a JSON tree of shapes | "Sculpting organic forms" in ASSETKIT.md, `assets/specs/sculpt_*.json` |
| It moves | a `rig` in that spec: bones, skin, clips (gait, turns, keys) | "Rigging and animating a sculpt", `sculpt_cave_toad.json`, `sculpt_cave_imp.json` |
| Bark, grain, moss, worn edges, dirt | a `pattern` on the spec's material | "Materials", `sculpt_tree_stump.json`, `crate_small.json` |
| Boxy props | `prop.kit` / `hard_surface.crate` specs | "Writing a kit generator" |

## Rules

- Generators listed in `KIT_GENERATORS` import `assetkit` and the standard library only.
  Blender-version differences live in `blender/backend/compat.py`, nowhere else.
- Same spec, same output: vary with `seed`, never with unseeded randomness.
- Do not weaken a QA gate to get green; fix the spec or the generator.
