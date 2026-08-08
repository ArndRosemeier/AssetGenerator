# Blender Asset Lab

Engine-agnostic 3D asset generation, orchestrated from Cursor and executed by a headless
Blender. You describe an asset in a small JSON spec, one command builds it, gates it on
automated quality checks, exports a `.glb` and renders preview images.

You never open Blender.

## Setup

Requires Python 3.11+ on `PATH`. Nothing else.

```bash
python tools/bootstrap.py
```

This downloads the pinned Blender 4.5.12 LTS portable build (~400 MB) into
`tools/blender-bin/`, verifies its SHA-256 against the official checksum, records the
path and proves the pipeline works by building a cube, exporting it and reading it back.
Nothing is installed system-wide and no add-ons are configured.

If you already have Blender, set `BLENDER_BIN` to its executable and bootstrap will use
that instead of downloading.

## Make something

```bash
python tools/ag.py generate crate_small
```

That writes `assets/out/crate_small.glb` and three renders in `assets/out/previews/`.

![Generated crate](assets/out/previews/crate_small_hero.png)

## Commands

| Command | What it does |
| --- | --- |
| `python tools/ag.py doctor` | Toolchain, paths, registered generators, available specs |
| `python tools/ag.py generate <id>` | Build, QA-gate, export, verify the export, render previews |
| `python tools/ag.py preview <id>` | Re-render previews from the existing `.glb` |
| `python tools/ag.py validate <id>` | Re-open the shipped `.glb` and re-run the gates on it |
| `python tools/ag.py specs` | List available specs |
| `python tools/ag.py generators` | List registered generators |

Add `--json` for the raw report. Exit codes: `0` pass, `1` QA or build failure, `2` bad
spec or missing toolchain.

## Why it produces usable assets

The hard part of LLM-generated 3D is not making geometry, it is making geometry that is
actually correct. Four things do the work here.

**Specs, not prose.** An asset is a strict JSON document. Unknown keys, missing keys and
wrong types are rejected before Blender starts, so an asset is always reproducible from
a file you can diff.

**Parametric generators, not invented meshes.** Geometry comes from vetted Python that
builds clean quad topology, applies bevels and unwraps UVs. The model chooses parameters;
it does not hand-place vertices.

**Gates that measure the shipped file.** Modifiers are applied before export, so the
triangle count in the report is the triangle count in the `.glb`. After export the file
is read back in and compared against the authored scene, which catches the silent export
losses that normally travel downstream looking like success.

**Renders the agent can look at.** Numbers cannot tell you that a crate has the
proportions of a filing cabinet. Every generate ends with three Cycles renders that the
agent inspects directly.

Nothing is papered over. A failed check is an error with the measured value in it, and a
non-zero exit code.

## Conventions

- Meters, Z-up while authoring. glTF export converts to Y-up.
- Origin centred on the footprint, base sitting on Z=0.
- One `.glb` per spec, materials as plain Principled BSDF values.
- Draco compression is off. It is a delivery-time optimisation and corrupts geometry when
  applied twice; run `gltf-transform` downstream if you need it.

## Layout

```text
assets/specs/          asset definitions (the source of truth, committed)
assets/out/            generated .glb files and previews (gitignored)
blender/lib/           scene setup, QA, export, preview helpers
blender/generators/    one module per asset family
blender/entrypoints/   scripts Blender executes; they only ever write a JSON report
tools/ag.py            the CLI everything goes through
tools/bootstrap.py     one-command Blender setup
.cursor/               rule and skill that keep the agent in the validated loop
```

## Adding a generator

Create `blender/generators/<family>_<name>.py` exposing `MATERIAL_SLOTS` and
`build(spec) -> list[bpy.types.Object]`, then register it in `blender/lib/registry.py`.
Use `blender/generators/hard_surface_crate.py` as the reference.

## For agents

Read [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md). It covers the generate loop, QA gates,
timing expectations, and the failure modes that already bit this project (z-fighting,
false manifold failures after glTF reimport, preview exposure, etc.).

## Scope

Meshes and flat PBR values only. Texture map generation, AI mesh services, rigging and
engine-specific packaging are deliberately out of scope for now; the spec/QA/preview
loop is the foundation they would plug into.
