---
name: asset-lab
description: Generate, QA and preview engine-agnostic 3D assets with headless Blender. Use when asked to create, modify or inspect a 3D model, prop, mesh or .glb in this repo, or when a QA gate or preview render needs interpreting.
---

# Asset Lab

Build 3D assets by editing a JSON spec and running one CLI. Blender never opens a window.

For the full agent manual (process, pitfalls, timing, QA quirks), read
[`docs/AGENT_GUIDE.md`](../../../docs/AGENT_GUIDE.md) before improvising.

## Process pattern (mandatory)

| Commit | Do not commit (regenerate) |
| --- | --- |
| `assets/specs/<id>.json` — recipe | `assets/out/**` — `.glb`, previews, bake dumps |
| `blender/generators/*` — builders | |

- Specs are the source of truth. Same JSON ⇒ same asset (`seed` + params).
- New asset = new file in `assets/specs/`. `regenerate` auto-discovers `*.json` (no ID list).
- Generators are registered by name in `blender/lib/registry.py`; asset IDs are not.

Fresh clone / rebuild library:

```bash
python tools/regenerate_assets.py
```

That runs host prerequisite checks first (Python ≥ 3.11, stdlib, writable dirs, Blender
or Windows CDN bootstrap path) with `fix:` hints, then bootstraps Blender and rebuilds
all specs. See `tools/prereqs.py`.

Blender already set up:

```bash
python tools/ag.py regenerate
```

## Check the toolchain first

```bash
python tools/ag.py doctor
```

Doctor prints the same prerequisite report. If anything FAILs, run
`python tools/regenerate_assets.py` after fixing the listed items.

## Commands

| Command | What it does |
| --- | --- |
| `python tools/regenerate_assets.py` | Bootstrap if needed + rebuild all specs |
| `python tools/ag.py doctor` | Toolchain, paths, generators, specs |
| `python tools/ag.py generate <id>` | Build, QA, export `.glb`, verify, previews |
| `python tools/ag.py generate <id> --no-preview` | Fast geometry iteration |
| `python tools/ag.py regenerate` | Rebuild every `assets/specs/*.json` |
| `python tools/ag.py preview <id>` | Re-render previews from existing `.glb` |
| `python tools/ag.py validate <id>` | Re-check shipped `.glb` against its spec |
| `python tools/ag.py specs` / `generators` | List what exists |

Add `--json` for the raw report. Exit codes: `0` pass, `1` QA/build failure, `2` bad
spec or missing toolchain.

Outputs land in `assets/out/<id>.glb` and `assets/out/previews/<id>_{hero,front,side}.png`.

## The iteration loop

1. Create or edit `assets/specs/<id>.json`.
2. Run `generate`.
3. Read the report. Failed gates include measured values.
4. **Open the preview PNGs and look at them.** Numbers cannot catch a bad silhouette.
5. Adjust the **spec** first; change the generator only when params cannot express it.

## Writing a spec

```json
{
  "spec_version": 1,
  "id": "crate_small",
  "generator": "hard_surface.crate",
  "params": { "width": 0.6, "depth": 0.6, "height": 0.6, "...": "generator specific" },
  "materials": {
    "frame":  { "base_color": [0.19, 0.12, 0.07, 1.0], "roughness": 0.82, "metallic": 0.0 },
    "planks": { "base_color": [0.42, 0.28, 0.15, 1.0], "roughness": 0.75, "metallic": 0.0 }
  },
  "qa": {
    "max_triangles": 6000,
    "require_uvs": true,
    "require_manifold": true,
    "require_origin_at_base": true,
    "max_dimension_m": 1.5
  }
}
```

Parsing is strict: unknown keys, missing keys, wrong types fail before Blender starts.
Material slots must match the generator's `MATERIAL_SLOTS`. Dimensions are meters.
Use `seed` (where supported) for reproducible variation inside a family.

## Interpreting the gates

| Gate | Meaning when it fails |
| --- | --- |
| `triangle_budget` | Reduce detail params, or raise the budget deliberately |
| `uvs_present`, `uvs_in_unit_square` | Unwrap failed or left bad UVs |
| `manifold`, `no_loose_geometry` | Broken topology at authoring time |
| `normals_outward` | Inside-out geometry |
| `no_degenerate_faces` | Collapsed faces from bad params |
| `transforms_identity`, `origin_at_base` | Pivot/placement convention broken |
| `roundtrip_*` | Export lost data vs the authored scene |

`validate` omits manifold checks on reimported glTF (format splits verts). Topology is
guaranteed by `generate` at authoring time.

## Adding a generator

Create `blender/generators/<family>_<name>.py` with `MATERIAL_SLOTS` and
`build(spec) -> list[bpy.types.Object]`, register in `blender/lib/registry.py`, add a
sample spec under `assets/specs/`, then prove `generate` and that `regenerate` picks it up.
