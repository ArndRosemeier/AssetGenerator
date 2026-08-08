# Blender Asset Lab

Engine-agnostic 3D asset generation, orchestrated from Cursor and executed by a headless
Blender. You describe an asset in a small JSON spec, one command builds it, gates it on
automated quality checks, exports a `.glb` and renders preview images.

You never open Blender.

## Setup / regenerate everything

**You install:** Python 3.11+ on `PATH`.  
**The script installs:** pinned headless Blender (Windows auto-download; elsewhere set `BLENDER_BIN`).

```bash
python tools/regenerate_assets.py
```

On a fresh clone this will:

1. Verify host prerequisites (Python version, stdlib modules, writable dirs, disk space, network to Blender CDN when needed) and print install hints on failure
2. Download the pinned Blender 4.5.12 LTS portable build (~400 MB) into `tools/blender-bin/` if missing
3. Verify its checksum and run a smoke test
4. Rebuild every asset listed under `assets/specs/` into `assets/out/`

Generated `.glb` files and previews are gitignored on purpose — the specs are the source of
truth and can always be regenerated. If Blender is already bootstrapped:

```bash
python tools/ag.py regenerate
```

Optional flags: `--no-preview` (faster), `--skip-bootstrap`, `--no-smoke`.

If you already have Blender installed elsewhere, set `BLENDER_BIN` to its executable.

## Character Studio (face / body morphs)

Focused Godot app with a **front-facing** preview and body/face sliders. The humans are
built here by `tools/character_studio/blender_export_humans.py` (MPFB body + 28 face
morphs + MakeHuman eyes), reusing City's vendored Blender/MPFB without modifying City.

```bat
character_studio\CharacterStudio.bat
```

See [`character_studio/README.md`](character_studio/README.md).

## Make one asset

```bash
python tools/ag.py generate crate_small
```

That writes `assets/out/crate_small.glb` and three renders in `assets/out/previews/`.

![Generated crate](assets/out/previews/crate_small_hero.png)

## Commands

| Command | What it does |
| --- | --- |
| `python tools/regenerate_assets.py` | Bootstrap Blender if needed, then rebuild all specs |
| `python tools/ag.py doctor` | Toolchain, paths, registered generators, available specs |
| `python tools/ag.py generate <id>` | Build, QA-gate, export, verify the export, render previews |
| `python tools/ag.py regenerate` | Rebuild every asset in `assets/specs/` |
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

Read [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) — especially **Process (must follow)**.
Always-on Cursor rules live in [`.cursor/rules/asset-lab.mdc`](.cursor/rules/asset-lab.mdc).

Pattern in one line: commit specs under `assets/specs/`; regenerate products into
`assets/out/` with `python tools/regenerate_assets.py` (or `python tools/ag.py regenerate`).

## Scope

Meshes and flat PBR values only. Texture map generation, AI mesh services, rigging and
engine-specific packaging are deliberately out of scope for now; the spec/QA/preview
loop is the foundation they would plug into.
