# Blender Asset Lab

> Also home of the shared **TypeScript packages** (`packages/`, npm workspaces): see [`packages/README.md`](packages/README.md).

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

## Blender as a Python module (cloud containers)

Where the portable Blender cannot be downloaded, install Blender as a Python module and point
`BLENDER_PYTHON` at that interpreter; every command then runs through it:

```bash
uv venv -p 3.11 bpyenv && uv pip install -p bpyenv/bin/python "bpy==4.5.*"
export BLENDER_PYTHON=$PWD/bpyenv/bin/python
python tools/ag.py generate prop_barrel
```

## Props for vertex-coloured engines (`pack`)

`prop.kit` (blender/generators/prop_kit.py) builds small props from closed shells
(assetkit/shells.py): barrels, buckets, picks, shovels, cut stone. `ag.py pack` builds a list
of specs, bakes ambient occlusion into their vertices, multiplies it into the materials' base
colours and writes one `.fmpk` file that an engine without textures can draw (Dunfinity does):

```bash
python tools/ag.py pack prop_crate prop_barrel prop_cut_block --out props.fmpk
```

The format is described at the top of blender/entrypoints/pack.py. A model whose material is white
is shading only: the engine paints it (Dunfinity's cut stone takes each band's rock colour).

### Mushrooms

Every mushroom comes from one builder, `mushroom()` in blender/lib/mushroom.py, so props and the
creatures disguised as mushrooms look alike. It returns `(shell, slot)` parts: `cap`, `gills`,
`stalk`, `ring` (ring and volva) and `spots`, origin at the stalk's foot, Z up; `lean` bends the
stalk sideways and tips the cap with it. Keep cap and stalk apart to animate them. The specs are
assets/specs/mush_*.json (prop.kit's `mushroom` and `bracket` kinds; caps: dome, bell, cone, flat,
funnel, ball). In Dunfinity they are drawn with the VERTEX_COLOR_SOLID material (AO baked into the
vertex colours); a glowing mushroom goes into the tile's glow mesh instead.

## Character Studio (face / body morphs)

Focused Godot app with a **front-facing** preview, body/face sliders and a modular
wardrobe. The humans themselves live in [`assets/humans/`](assets/humans/) (same
library pattern as monsters). Bodies and garments are exported there by
`tools/character_studio/blender_export_humans.py` (MPFB body + 28 face morphs +
MakeHuman eyes + MakeHuman civilian clothes) and assembled onto one skeleton at
runtime, so no outfit combination is pre-baked. It reuses City's vendored
Blender/MPFB without modifying City.

```bat
character_studio\CharacterStudio.bat
```

See [`character_studio/README.md`](character_studio/README.md).

## Library viewer

One Engine window lists whatever is on disk: dressed humans, fetched monsters, and
generated `.glb` files under `assets/out/`. No registry — add a file, hit Rescan.
This is a looker, not Character Studio (no morph sliders).

```bat
Viewer.bat
```

or `cargo run -p lab`. Empty tabs print the command that produces those files.

## Sculpted creatures (quadruped generator)

`creature.quadruped` (`blender/generators/quadruped_generator/`) sculpts a creature as a field of
shapes round its skeleton, meshes it with surface nets, bakes its coat (colour and hair normals, WebP)
from the dense sculpt onto a light mesh, skins it from the sculpt's own shapes and keys every clip a
game needs, with paws planted by IK. `params.species` picks the animal (`species.py`: body plan, coat
and clips on the shared skeleton naming): `feral_dog` (`assets/specs/creature_feral_dog.json`, the
default), `quarry_rat` (`assets/specs/creature_quarry_rat.json`) and `cave_cricket`
(`assets/specs/creature_cave_cricket.json`: six legs with knee `poles`, feeler chains, mid legs under
`LEGS["mid"]`), and the slimes `lumen_slime` and `murk_slime` (`assets/specs/creature_*_slime.json`: no
legs, a body that squashes and stretches, `Body.squash` and `Pose.scales`), and `brine_eel`
(`assets/specs/creature_brine_eel.json`: a chain of body bones the game lays along its own chain; the
clips move only the head and jaw). `lean` is the build: bone showing on a dog, fat on a rat, the abdomen on a cricket, the lumps on Murk. A new animal is a body plan, a coat and a clip set in its own files plus a row
in `SPECIES`. Without a Blender binary, `pip install bpy==4.5.*` (plus numpy) runs the entrypoints directly:
`python blender/entrypoints/generate.py -- --payload p.json --result r.json`.

## Mushroom monsters

`creature.mushroom` (`blender/generators/mushroom_creature/`) builds a monster from the same shells as the
props' mushrooms (`blender/lib/mushroom.py`), so one stands among them unseen, and rigs and animates it
with the quadruped generator's skeleton, poses and clips (`Pose.aims` points a bone from a head to a
tail). `params.species`: `toadstool` (`assets/specs/creature_toadstool.json`: the fly agaric five times
over; folds six roots into its foot to hide, stands up on them to walk, slams its cap down) and `puffcap`
(`assets/specs/creature_puffcap.json`: the pale cave mushroom seven times over, rooted, glowing gills,
puffs spores). The mushroom numbers are the prop spec's, times `scale`. Materials: the mushroom's slots
plus `root` and `eye`, as vertex colours on `skin` and `eye` (the eyes and the `glow` slots).

## Quaternius monster pack

[Quaternius Ultimate Monsters](https://quaternius.com/packs/ultimatemonsters.html)
(CC0) lives here as a library other projects can copy from. Fifty bodies in three
rig families (`big`, `blob`, `flying`), one shared atlas, measured heights and
clip names in [`assets/monsters/quaternius/catalog.json`](assets/monsters/quaternius/catalog.json).

The `.glb` files are gitignored. Fetch them (copies from a sibling City checkout
when that pack is already there):

```bash
python tools/fetch_quaternius_monsters.py
```

A small Engine viewer browses humans, monsters, and generated assets by scanning
those folders. Character Studio stays Godot and is unchanged. City keeps its own
copy of the pack for now.

```bat
Viewer.bat
```

or `cargo run -p lab`. License notes: [`docs/LICENSE_ASSETS.md`](docs/LICENSE_ASSETS.md).
This pack is **not** part of `python tools/ag.py regenerate`.

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
| `python tools/ag.py look <id>` | Nine-view inspection sheet + measurements, in about a second |
| `python tools/ag.py look <id>_lod1` | A LOD level of an asset whose spec has `lods` (`generate` builds them all) |
| `python tools/ag.py look kit:<name>` | Several assets placed together (`assets/kits/<name>.json`), every joint measured |
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
proportions of a filing cabinet. Every generate writes an inspection sheet
(`assets/out/look/<id>.png`): orthographic views on one metric grid, perspective views, the
asset beside a 1.75 m person, and diagnostic views (a colour per material, inside-out faces
in red, holes in yellow, polygon edges), with the measurements a picture shows badly in its
header: floating parts, holes, inside-out parts, whether it would tip over. It is drawn by a
small software rasterizer (`assetview/`, numpy, no Blender), so `ag.py look <id>` shows a kit
asset in about a second. Three Cycles renders follow for materials and light.

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
assets/humans/         MakeHuman / MPFB library (wardrobe.json committed, .glb gitignored)
assets/monsters/       Quaternius catalog (committed) + fetched .glb files (gitignored)
assetkit/              stable generator API, no Blender (see docs/ASSETKIT.md)
assetview/             inspection sheet + measurements (numpy, no Blender)
blender/backend/       builds a kit Asset in Blender; compat.py holds every version shim
blender/lib/           scene setup, QA, export, preview helpers
blender/generators/    one module per asset family
blender/entrypoints/   scripts Blender executes; they only ever write a JSON report
tools/ag.py            the CLI everything goes through
tools/backend_matrix.py  the same specs on several Blender versions
tests/                 kit tests, no Blender needed
tools/bootstrap.py     one-command Blender setup
viewer/lab/            Engine library viewer (humans, monsters, generated assets)
.cursor/               rule and skill that keep the agent in the validated loop
```

## The asset kit: generators that outlive Blender versions

Generators are written against `assetkit/`, a small stable API (meshes, closed shells, noise,
finishing steps such as bevel, shading and unwrap) that never imports Blender. They return
plain data; `blender/backend/` builds it in whichever Blender runs, and every Blender-version
difference lives in `blender/backend/compat.py`. So a new Blender changes the backend, not the
generators, and kit generators can be tested without Blender in under a second:

```bash
python -m unittest discover tests
```

Newer Blender versions may make better assets; they must not break the spec's contract (QA
gates, materials, size) or change an asset unseen. `tools/backend_matrix.py` builds the specs
on two or more Blender versions and lists each asset as `same`, `changed` or `BROKEN`:

```bash
python tools/backend_matrix.py --python bpy45/bin/python --python bpy52/bin/python
```

`hard_surface.crate`, `prop.kit` and `organic.sculpt` are kit generators so far. Details and
the API: [`docs/ASSETKIT.md`](docs/ASSETKIT.md).

## Sculpting organic forms in JSON

`organic.sculpt` takes the shape itself from the spec: a tree of spheres, ellipsoids, rounded
boxes, tapering capsules and tori, combined with smooth unions (clay pressed together),
subtractions and flat cuts, mirrored, and roughened with seeded noise. Regions are painted with
their own materials (eyes, moss, cut wood), the mesh cut along their edges. The kit meshes it
(marching tetrahedra, then quadric simplification to `max_triangles`) into a closed, manifold,
outward mesh that passes QA, the same bit for bit on every machine. A rock, a stump with roots
or a toad is a JSON file: see `assets/specs/sculpt_*.json` and
[`docs/ASSETKIT.md`](docs/ASSETKIT.md).

## Rigged and animated, still in JSON

A sculpt's `rig` turns it into a creature: bones taken from its capsule parts (the right side
mirrored from the left), skin weights from the distance to the parts each bone carries (no
painting; limbs never share skin with unrelated bones), and clips described as a few motions:
a turn, a bob, keyed poses, and a gait whose feet stay planted by inverse kinematics. Blender
builds the armature and one glTF animation per clip, matching the kit's own skinning to 5e-7 m.
`ag.py look` adds a rig sheet: bones, weights and six frames of every clip, with flags for fused
limbs, tearing skin and feet through the floor. See `assets/specs/sculpt_cave_toad.json` and
`sculpt_cave_imp.json`.

## Hard-surface props in JSON

`prop.assembly` builds lanterns, chests, tools and fittings from exact pieces written in the
spec: boxes, rods between two points, spheres, rings, turned profiles, bent tubes and extruded
outlines, each with its own material, placed, repeated round an axis or in a row, mirrored and
grouped. A bevel rounds the pieces thick enough for one. A `rig` ties pieces to bones, rigidly
(a wheel that `spin`s) or bending along a chain (a cloth `sheet` that `wave`s). Tiles keep their
origin on the grid (`settle: false`), and a kit (`assets/kits/`) lays them out to check the
joints. See `assets/specs/prop_crypt_lantern.json`, `prop_mill_waterwheel.json`,
`prop_hanging_banner.json`, `tile_brick_wall.json` and "Hard-surface props in JSON" in
[`docs/ASSETKIT.md`](docs/ASSETKIT.md).

## Materials as recipes

A spec's material can carry a `pattern`: layers of mottling, grain, spots, cells, gradients,
moss on what faces up, worn edges and dirty creases, brick bonds, written in JSON, with
`relief` for a normal map; `alpha` makes it glass; `period` makes it repeat so tiles continue
one another. The kit evaluates them on the surface and bakes them
into colour and roughness textures on the final UVs; the .glb ships them. `ag.py look` shows the
patterns without Blender and reports how much each layer paints, so an invisible or
overpowering layer is caught before a build. See "Materials" in
[`docs/ASSETKIT.md`](docs/ASSETKIT.md) and the materials of `assets/specs/sculpt_tree_stump.json`.

## Adding a generator

Create `blender/generators/<family>_<name>.py` exposing `MATERIAL_SLOTS` and
`build(spec) -> assetkit.Asset`, register it in `blender/lib/registry.py` and add it to
`KIT_GENERATORS`. Use `blender/generators/hard_surface_crate.py` as the reference.

## For agents

Start at [`AGENTS.md`](AGENTS.md) (also loaded by Claude Code through `CLAUDE.md`), then
[`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md) — especially **Process (must follow)**.
Always-on Cursor rules live in [`.cursor/rules/asset-lab.mdc`](.cursor/rules/asset-lab.mdc).

Pattern in one line: commit specs under `assets/specs/`; regenerate products into
`assets/out/` with `python tools/regenerate_assets.py` (or `python tools/ag.py regenerate`).

## Scope

Meshes, rigs and clips, PBR values and kit patterns baked to colour, roughness and normal
maps (a sculpt's exact surface and pattern relief). AI mesh services and engine-specific
packaging are out of scope for now; the spec/QA/preview loop is the foundation they would
plug into.
