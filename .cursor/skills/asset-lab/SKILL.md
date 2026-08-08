---
name: asset-lab
description: Generate, QA and preview engine-agnostic 3D assets with headless Blender. Use when asked to create, modify or inspect a 3D model, prop, mesh or .glb in this repo, or when a QA gate or preview render needs interpreting.
---

# Asset Lab

Build 3D assets by editing a JSON spec and running one CLI. Blender never opens a window.

For the full agent manual (pitfalls, timing, QA quirks, generator rules), read
[`docs/AGENT_GUIDE.md`](../../../docs/AGENT_GUIDE.md) before improvising.

## Check the toolchain first

```bash
python tools/ag.py doctor
```

If it reports no Blender, run `python tools/bootstrap.py` once. It downloads a pinned
portable Blender 4.5 LTS into `tools/blender-bin/`, verifies its checksum and runs a
build-export-reimport self test. Nothing is installed system-wide.

## Commands

| Command | What it does |
| --- | --- |
| `python tools/ag.py doctor` | Toolchain, paths, registered generators, available specs |
| `python tools/ag.py generate <id>` | Build, QA-gate, export `.glb`, verify the export, render previews |
| `python tools/ag.py generate <id> --no-preview` | Same without renders (fast iteration on geometry) |
| `python tools/ag.py preview <id>` | Re-render previews from the existing `.glb` |
| `python tools/ag.py validate <id>` | Re-open the shipped `.glb` and re-run the gates on it |
| `python tools/ag.py specs` / `generators` | List what exists |

Add `--json` to any command for the raw report. Exit codes: `0` pass, `1` QA or build
failure, `2` bad spec or missing toolchain.

Outputs land in `assets/out/<id>.glb` and `assets/out/previews/<id>_{hero,front,side}.png`.

## The iteration loop

1. Create or edit `assets/specs/<id>.json`.
2. Run `generate`.
3. Read the report. Every gate is listed with its measured value, so a failure tells you
   the number to fix.
4. **Open the preview PNGs and actually look at them.** The numbers cannot tell you that
   a crate looks like a filing cabinet. Check proportions, silhouette, plank rhythm,
   material read.
5. Adjust the spec and repeat.

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

Parsing is strict on purpose: unknown keys, missing keys and wrong types all fail before
Blender starts. Material slots must match the generator's `MATERIAL_SLOTS` exactly.
Dimensions are meters.

## Interpreting the gates

| Gate | Meaning when it fails |
| --- | --- |
| `triangle_budget` | Reduce plank/segment counts, or raise the budget if the asset genuinely needs it |
| `uvs_present`, `uvs_in_unit_square` | The unwrap did not produce usable texture space |
| `manifold`, `no_loose_geometry` | Boxes were built open or geometry was left stranded |
| `normals_outward` | Inside-out geometry; it will render black in engines |
| `no_degenerate_faces` | Zero-area faces, usually from a parameter collapsing to 0 |
| `transforms_identity`, `origin_at_base` | Pivot convention broken; the asset will not place correctly |
| `roundtrip_*` | The exported file disagrees with the authored scene, so the export lost something |

`validate` deliberately omits `manifold` and `no_loose_geometry`: glTF stores one vertex
per unique normal/UV pair, so edge connectivity is not something the format preserves.
Topology is guaranteed at authoring time by `generate` instead.

## Adding a generator

Create `blender/generators/<family>_<name>.py` with `MATERIAL_SLOTS: tuple[str, ...]`
and `build(spec: AssetSpec) -> list[bpy.types.Object]`, then register the module in
`blender/lib/registry.py`. Follow `hard_surface_crate.py`: parse params into a frozen
dataclass, reject impossible dimensions with the real numbers in the message, assemble
with `BoxBuilder`, then `apply_bevel` / `shade_flat` / `unwrap`.

Let boxes interpenetrate rather than butt together. Two coplanar faces on the outside of
an asset z-fight in every renderer, and that is exactly the class of defect that makes
generated assets look broken.
