# Agent guide: Blender Asset Lab

How to generate 3D assets in this repo, and what usually goes wrong.

Cursor is the orchestrator. Headless Blender is a deterministic worker. You drive
everything through `tools/ag.py`. You do **not** open the Blender UI.

Also see:

- Always-on rules: [`.cursor/rules/asset-lab.mdc`](../.cursor/rules/asset-lab.mdc)
- Skill (short workflow): [`.cursor/skills/asset-lab/SKILL.md`](../.cursor/skills/asset-lab/SKILL.md)
- Human overview: [`README.md`](../README.md)

---

## Process (must follow)

This is the only supported asset workflow. Do not invent a parallel one.

| Layer | Path | In git? | Role |
| --- | --- | --- | --- |
| Spec / recipe | `assets/specs/<id>.json` | **Yes** | Exact generation recipe (params, materials, QA, `seed`) |
| Generator | `blender/generators/*.py` | **Yes** | Parametric builder, registered by name |
| Products | `assets/out/**` | **No** (gitignored) | Regenerable `.glb`, previews, bake dumps |

**Rules of the process**

1. Create or change an asset by editing a **spec**, not by hand-editing a `.glb`.
2. Same spec ⇒ same output. Use `seed` and params for controlled variation.
3. Register **generators** in `blender/lib/registry.py`. Do **not** maintain a separate
   list of asset IDs — `regenerate` discovers every `assets/specs/*.json` via glob.
4. Fresh clone / full library rebuild:

   ```bash
   python tools/regenerate_assets.py
   ```

   Blender already present:

   ```bash
   python tools/ag.py regenerate
   ```

5. Single-asset work:

   ```bash
   python tools/ag.py generate <id>
   ```

6. Commit the spec (and generator code if you added one). Do not commit `assets/out/`
   unless the user explicitly asks. Products stay rebuildable from specs.

If a future “recipes” rename happens, the pattern stays the same: committed JSON recipe
in, regenerable products out.

---

## Mental model

```text
JSON spec  -->  generator (bpy)  -->  QA gates  -->  .glb export
                      |                               |
                      +---- preview PNGs <------------+
                      |                               |
                      v                               v
                 agent reads report + looks at images, then iterates
```

- **Specs** (`assets/specs/*.json`) are the source of truth. Diffable, strict, no prose.
- **Generators** (`blender/generators/`) are parametric builders. Prefer tuning a
  parameter over inventing one-off geometry.
- **QA** measures the mesh that will ship. Modifiers are applied before export.
- **Previews** are how you judge look. Numbers alone are not enough.

---

## First actions in a session

```bash
python tools/ag.py doctor
```

| Result | What to do |
| --- | --- |
| Blender found, paths OK | Proceed |
| Blender not found | Run `python tools/regenerate_assets.py` or `python tools/bootstrap.py` (~400 MB) |
| Spec/generator missing | Create them; do not invent a parallel pipeline |

Fresh clone one-liner (prereq check + bootstrap + rebuild every spec):

```bash
python tools/regenerate_assets.py
```

That command first verifies clone-host requirements via `tools/prereqs.py`:

| Check | Why |
| --- | --- |
| Python ≥ 3.11 | Language baseline (`requires-python`) |
| Stdlib modules | No `pip install` — broken/embed Python fails here |
| Repo layout | `assets/specs/`, `blender/entrypoints/` present |
| Writable `assets/out/` and `tools/blender-bin/` | Outputs + Blender extract |
| Blender present **or** Windows + CDN + ~2 GiB free | Auto-bootstrap path |
| `BLENDER_BIN` | Non-Windows / custom installs |

Failures print a `fix:` line. Do not skip with `--skip-prereqs` unless debugging.

Override an existing Blender install with `BLENDER_BIN` if needed. Bootstrap still
pins and prefers the managed 4.5.12 LTS under `tools/blender-bin/` for reproducibility.

---

## Commands

| Command | Use when |
| --- | --- |
| `python tools/regenerate_assets.py` | Fresh clone / rebuild the whole library |
| `python tools/ag.py doctor` | Session start / toolchain suspicion |
| `python tools/ag.py generate <id>` | Build + QA + export + round-trip + previews |
| `python tools/ag.py generate <id> --no-preview` | Fast geometry iteration |
| `python tools/ag.py regenerate` | Rebuild all specs (Blender already present) |
| `python tools/ag.py preview <id>` | Re-render after a generate that skipped previews |
| `python tools/ag.py validate <id>` | Re-check the shipped `.glb` against its spec |
| `python tools/ag.py specs` / `generators` | Discover what exists |
| `... --json` | Machine-readable report |
| `python tools/cave_profile.py <id>` | Read floor/ceiling heights out of a shipped cave `.glb`: flat rows mean flat rock |
| `python tools/texel_detail.py <id>` | Check a baked albedo really carries grain, not just large blotches |

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Pass |
| `1` | Build or QA failed (report has the measured values) |
| `2` | Bad spec, unknown id, or missing toolchain |

Outputs:

- `assets/out/<id>.glb`
- `assets/out/previews/<id>_{hero,front,side}.png`

Never call `blender.exe` directly. Direct calls skip the report contract and lose
the feedback loop.

---

## The iteration loop (do this every time)

1. Write or edit `assets/specs/<id>.json`.
2. Run `generate` (use `--no-preview` until geometry is stable, then full generate).
3. Read the report. Failed gates print the actual measured value.
4. **Open the preview PNGs with the image reader and look at them.** Check:
   - proportions / silhouette
   - plank or panel rhythm
   - z-fighting (black speckles, flickering seams)
   - blown-out or too-dark materials
   - whether it reads as the intended object at a glance
5. Fix the **spec** first. Touch the generator only when no parameter can express the change.
6. Stop when exit code is `0` **and** the previews look correct.

Do not declare success from a green report alone.

Interior pieces (cave tiles, rooms) are the exception to step 4: the fixed preview
cameras only see them from outside, where they are a box by design. Measure the
inside instead (`cave_profile.py`, `texel_detail.py`) and take an engine
screenshot from a first-person position before believing a shape or a texture.

---

## Writing specs

Specs are strict. Unknown keys, missing keys, wrong types, and material slot mismatches
all fail **before** Blender launches.

Required top-level keys:

- `spec_version` (currently `1`)
- `id` (letters, digits, `_`, `-` only)
- `generator` (must exist in `blender/lib/registry.py`)
- `params` (generator-specific)
- `materials` (exact slot names the generator declares)
- `qa` (`max_triangles`, `require_uvs`, `require_manifold`, `require_origin_at_base`, `max_dimension_m`)

Conventions:

- Units are **meters**.
- Authoring is **Z-up**; glTF export converts to Y-up.
- Dungeon `storey_role` (`cell` / `floor` / `rise` / `vault`) only changes the mesh. Vertical openness is a catalog profile (`storey_void`), not this flag.
- Origin is footprint centre, base on Z=0.
- Materials are Principled BSDF values (`base_color` RGBA 0–1, `roughness`, `metallic`).
  Procedural detail that must survive glTF is baked to albedo / roughness / normal
  (`nature.rock`, `hard_surface.kit_cell` when `texture_resolution` is set).

Reference sample: [`assets/specs/crate_small.json`](../assets/specs/crate_small.json).

---

## Interpreting QA gates

| Gate | Typical cause | Fix direction |
| --- | --- | --- |
| `triangle_budget` | Too many planks/segments/bevels | Lower counts, or raise the budget deliberately and say why |
| `size_limit` | Spec dimensions too large | Shrink params or raise `max_dimension_m` deliberately |
| `uvs_present` / `uvs_in_unit_square` | Missing unwrap or bad smart-project | Ensure generator calls `unwrap`; inspect UV packing |
| `manifold` / `no_loose_geometry` | Open boxes, stranded verts (authoring only) | Fix builder; do not disable the gate |
| `normals_outward` | Inside-out faces | Rebuild with outward normals; will look black in engines if ignored |
| `no_degenerate_faces` | A dimension collapsed to ~0 | Param validation / spacing math |
| `materials_assigned` | Slot name mismatch or unused faces | Match `MATERIAL_SLOTS` exactly |
| `transforms_identity` | Location/rotation/scale left on the object | Apply transforms / build in place |
| `origin_at_base` | Pivot not centred/grounded | Rebuild so footprint centre is (0,0) and min Z is 0 |
| `roundtrip_*` | Export lost tris/materials/UVs/size | Export flags, materials, or applied-modifier state |

### Important: `validate` vs `generate` topology

`generate` checks manifoldness on the **authored** mesh.

`validate` deliberately **omits** `manifold` and `no_loose_geometry` on the reimported
`.glb`. glTF stores one vertex per unique normal/UV combination, so flat-shaded meshes
look non-manifold after import even when authored correctly. That is a format limit, not
a pipeline bug. Do not “fix” this by weakening authoring checks.

---

## What to watch for (known failure modes)

These are the defects that already bit this project. Prefer fixing the cause over
papering over the symptom.

### 1. Coplanar faces / z-fighting

Two boxes that **butt** with coplanar outer faces produce black speckles or shimmering
in every renderer (including our previews).

**Rule:** let structural pieces **interpenetrate** slightly, or sink posts into lids/floors,
instead of perfectly flush contact on visible surfaces.

**Kit cells:** a wall that extends past `cell_y` occupies the next storey and z-fights
whatever sits there (floor, jetty, roof). A wall that sits on `z=0` shares a plane
with the plinth below. `hard_surface.kit_cell` fails the build if either happens.
Storey pieces occupy `[overlap, cell_y]`. Join-axis shiplap is the only allowed overrun.

The same generator also fails if two boxes share a **Z** face with overlapping area
(intra-mesh, or a stacked phantom: plinth below, ground under a jetty, wall/window
under a roof). That is the guard against looking-up flicker. Do not delete it or
raise the epsilon to get a green generate — offset the box on Z.

### 2. Green report, wrong-looking asset

QA cannot see “crate looks like a filing cabinet.” Always inspect `hero` / `front` /
`side` previews. If the silhouette is wrong, change params (or the generator).

This is the single most expensive failure class in the repo. `docs/CREATURE_BAKE_LESSONS.md`
works through a week of green `EXIT 0` bakes whose renders were wrong, and the
rules that came out of it — chiefly: a gate that re-reads the buffer the edit
wrote cannot detect a discarded edit, and anything whose purpose is to be
visible needs one pixel or ray gate. Read it before writing a new gate.

### 3. Blown-out or mud-dark previews

Preview lighting is tuned for mid-grey subjects under Standard view transform. If an
asset looks clipped white or crushed black, check material `base_color` / roughness
first; only then touch `blender/lib/preview.py` light powers.

### 4. One-off geometry edits

Do not hardcode a single asset’s sizes into a generator. Put the values in the spec.
Generators stay reusable; specs stay the dials.

### 5. Weakening QA to get a green check

Never delete gates, catch-and-ignore exceptions, or add silent defaults for missing
fields. If a budget is genuinely wrong, change the number in the **spec** and say why.

### 6. Calling Blender or inventing a second pipeline

No MCP, no GUI, no ad-hoc `blender --python` one-liners for production assets. The
report JSON from `ag.py` is the feedback channel.

### 7. Bootstrap / download surprises

- First bootstrap downloads ~400 MB; expect a few minutes **with** progress lines.
- `download.blender.org` returns **403** without a real User-Agent (already handled in
  `tools/blenderctl.py`). If download fails oddly, check that code path before blaming
  the network.
- Checksums are pinned. A mismatch deletes the archive and fails loudly — re-run bootstrap.

### 8. Timing expectations (so you know when something is stuck)

| Operation | Normal | Something is wrong |
| --- | --- | --- |
| `doctor` | < 5 s | — |
| `generate --no-preview` | a few seconds | > 60 s with no report |
| `generate` / `preview` (3 Cycles PNGs) | ~15–30 s | > 2–3 min with no report |
| First `bootstrap` download | a few minutes + progress | Silent for minutes with no % lines |

If a command is silent far beyond these windows, kill it and diagnose. Do not wait
without feedback.

### 9. Scope boundaries (do not invent these yet)

Out of scope for the current pipeline:

- Texture / PBR map generation
- AI mesh APIs (Meshy, Tripo, etc.)
- Engine-specific packaging (Godot `.tres`, Unity prefabs, …)
- Rigging / animation
- Blender MCP / live GUI bridge

If asked for those, say they are deferred and either stay inside the current loop or
propose a concrete extension that still ends in QA + previews + `.glb`.

---

## Nature generators (current)

| Generator | Spec knobs | Notes |
| --- | --- | --- |
| `nature.pine` | height, canopy, branch counts, seed | Stylized icosphere foliage; no leaf textures yet |
| `nature.rock` | `elongation`, `stretch_axis`, `smoothness`, `displace_amount`, vein_*, `seed` | Bakes albedo/roughness/normal into the `.glb` via Cycles |

Rock materials need slots `rock` and `vein` (vein colour is baked into albedo streaks). Baked PNG dumps land in `assets/out/textures/` for inspection. Vein knobs that are too aggressive produce zebra/contour banding — prefer fewer thicker streaks.

## Adding a generator

1. Create `blender/generators/<family>_<name>.py` with:
   - `MATERIAL_SLOTS: tuple[str, ...]`
   - `build(spec: AssetSpec) -> list[bpy.types.Object]`
2. Register the module path in `blender/lib/registry.py`.
3. Parse `spec.params` into a frozen dataclass using the strict helpers in
   `blender/lib/spec.py`. Reject impossible dimensions with messages that include the
   **actual numbers**.
4. Prefer `BoxBuilder` from `blender/lib/scene.py`. Interpenetrate boxes; avoid
   coplanar exterior faces.
5. Finish with `apply_bevel` → `shade_flat` → `unwrap` so QA measures the shipped mesh.
6. Add a sample spec under `assets/specs/` and run `generate` until report + previews
   both look right.

Reference implementation: [`blender/generators/hard_surface_crate.py`](../blender/generators/hard_surface_crate.py).

---

## Repo map

```text
assets/specs/           committed asset definitions
assets/out/             generated .glb + previews (gitignored)
blender/lib/            scene, materials, QA, export, preview helpers
blender/generators/     parametric builders
blender/entrypoints/    scripts Blender runs; they only write a JSON report
tools/ag.py             the only CLI you should use day to day
tools/bootstrap.py      one-shot Blender install + smoke test
tools/blenderctl.py     locate / download / invoke Blender
.cursor/rules/          always-on working agreement
.cursor/skills/         short skill for the generate loop
docs/AGENT_GUIDE.md     this file
```

---

## Definition of done for an asset request

An asset request is done only when **all** of these are true:

1. Spec exists under `assets/specs/<id>.json` and is the recipe you would regenerate from.
2. `python tools/ag.py generate <id>` exits `0`.
3. You have inspected the preview PNGs and they match the request.
4. A full sweep would include it: `python tools/ag.py regenerate` globs that spec
   (no hard-coded allowlist to update).
5. You have not asked the user to click around in Blender.
6. Failures were fixed by changing specs/generators, not by silencing checks.
7. You did not rely on committing `assets/out/` as the source of truth.
