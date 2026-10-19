# The asset kit

The stable layer between asset generators and Blender. Read this before writing or changing
a generator.

```text
spec (JSON)  -->  kit generator  -->  Asset (plain data)  -->  Blender backend  -->  QA, .glb, previews
                  assetkit/ only                               blender/backend/
                  no bpy, testable                             the only place that knows
                  without Blender                              which Blender is running
```

## The line

| Layer | Path | Changes when Blender changes? |
| --- | --- | --- |
| Spec | `assets/specs/*.json` | No |
| Kit API | `assetkit/` | No. `API_VERSION` counts breaking changes |
| Kit generators | `blender/generators/*` listed in `KIT_GENERATORS` | No |
| Backend | `blender/backend/` (realize, `compat.py`), `blender/lib/` | Yes, and only here |

A kit generator imports `assetkit` and the standard library, never `bpy`, `bmesh` or
`mathutils`. `tests/test_assetkit.py` blocks those modules and builds every kit spec,
so a stray import fails in under a second, without Blender.

Version differences live in `blender/backend/compat.py`, one function each
(`set_sharp_from_angle`, `action_fcurves`, ...). Nothing else checks `bpy.app.version`
or probes with `hasattr`. Generators not moved to the kit yet (creatures, trees, kit
cells) still use `bpy` directly, but they call `compat` for anything version-dependent too.

## Version policy

Blender versions are **not** required to produce identical assets. A newer Blender may make
a better one (a better unwrap, a better bevel, a better bake); the backend should use it.
What versions are held to:

- **The contract holds on every supported version.** Every QA gate and the export round trip
  pass; the material slots are the same; the size is the same to 1 mm.
- **Changes are visible.** Geometry or UV differences between versions are listed, so an
  upgrade never changes an asset unseen.
- **Same spec, same version, same asset.** Reproducibility is per Blender version. A game
  that must not see its assets shift pins the version and upgrades on purpose.

`tools/backend_matrix.py` checks this. It builds the specs on two or more Blender installs and
prints one line per asset:

| Status | Meaning | Exit |
| --- | --- | --- |
| `same` | Same geometry (to 0.1 mm) and UV layout | 0 |
| `changed` | Contract holds; geometry or UVs differ. Read the notes, look at the previews | 0 (1 with `--strict`) |
| `BROKEN` | A gate failed on some version, or materials or size differ | 1 |

```bash
python tools/backend_matrix.py --python bpy45/bin/python --python bpy52/bin/python
python tools/backend_matrix.py --blender <blender-4.5> --blender <blender-5.2> prop_barrel
```

Supported range: `SUPPORTED_MIN` to below `SUPPORTED_BELOW` in `compat.py` (now 4.5 to 5.x).
CI (`.github/workflows/assetkit.yml`) runs the kit tests and the matrix on 4.5 LTS and 5.2.

## API (version 1)

Everything below is exported from `assetkit`.

### Geometry

`MeshBuilder(slots)`: one mesh with named material slots.

| Method | What it does |
| --- | --- |
| `add_box(center, size, slot, rotation=None)` | Box round `center`; `rotation` is XYZ Euler in radians |
| `add_box_bounds(lower, upper, slot)` | Box between two corners |
| `add(shell, slot)` / `add_shell(verts, faces, slot)` | A closed shell; faces counter-clockwise seen from outside |
| `set_point_attribute(name, values)` | One float per vertex (`shade` is multiplied into colours by `ag.py pack`) |
| `build() -> Mesh` | Freeze it |

`Mesh.settled()` moves a mesh so its footprint is centred on the origin and it rests on Z=0.
`Mesh.bounds()`, `Mesh.triangle_count()` measure it.

`assetkit.shells`: closed shells as `(vertices, faces)`. `box`, `grid_cube` (subdivided unit
cube to bend into blocks and boulders), `lathe`, `ring`, `sweep`, `circle`, `rect`,
`transform`, `place`. Shells may overlap each other (timber through iron); each stays closed.

`assetkit.noise.noise(x, y, z)`: seeded gradient noise in about [-1, 1], identical on every
machine. Use it instead of `mathutils.noise`.

### The result

```python
Asset(parts=(Part(name, mesh, materials, finish=(...)),))
```

`materials` maps each slot to the spec's material (`spec.materials`). `finish` is carried
out in order by the backend:

| Step | Meaning |
| --- | --- |
| `Bevel(width, segments=1, angle_deg=30)` | Bevel edges sharper than the angle, applied |
| `ShadeFlat()` | Every face flat |
| `ShadeSmooth(sharp_angle_deg=None)` | Smooth; edges turning more than the angle stay hard |
| `Unwrap(angle_limit_deg=66, island_margin=0.02)` | UVs into the unit square |

A step says *what*, never *how*: how Blender 4.5 or 5.2 does it is the backend's business.

## Looking at an asset

`assetview/` draws a nine-view inspection sheet and measures what pictures show badly. It uses
numpy and a small software rasterizer, not Blender, so a kit asset is drawn straight from its
generator in about a second:

```bash
python tools/ag.py look prop_shovel          # kit: from the generator, before bevel and unwrap
python tools/ag.py look prop_shovel --glb    # any asset: from the shipped .glb
```

Every `generate` writes the same sheet from the shipped file (`assets/out/look/<id>.png`) and adds
its measurements to the report: size, triangles per material, parts, floating parts (not on the
ground and touching nothing that is), open edges, inside-out parts, and balance (centre of mass
against the hull of the footing). These are measurements, not gates: a chain hangs and a
bracket sits on a wall on purpose.

The sheet found an inside-out shovel blade that every QA gate passed (QA checks the whole mesh's
volume; one inverted shell hid in the positive total). The kit tests now hold every shell.

## Writing a kit generator

1. Parse `spec.params` with the strict helpers in `blender/lib/spec.py`, as before.
2. Build with `MeshBuilder` and `assetkit.shells`; vary with `random.Random(seed)` and
   `assetkit.noise`.
3. Return an `Asset`. Finish with the steps the old `apply_bevel -> shade_flat -> unwrap`
   chain did, in the same order.
4. Register it in `blender/lib/registry.py` and add its name to `KIT_GENERATORS`.
5. `python -m unittest discover tests`, then `python tools/ag.py generate <id>` and look at the
   previews, as for any asset.

Reference: `blender/generators/hard_surface_crate.py` (boxes and a bevel) and
`blender/generators/prop_kit.py` (shells, noise, a per-vertex shade).

## Growing the kit

When a generator needs something the kit lacks (a boolean, a modifier, a baked texture):

- If it is geometry, prefer plain Python in `assetkit` (testable, version-proof).
- If it needs Blender, add a step (a frozen dataclass in `assetkit/asset.py`) and carry it
  out in `blender/backend/__init__.py`. The step names the result, not the Blender operator.
- Adding is not breaking. Renaming or changing what an export means bumps `API_VERSION` and
  moves every kit generator along in the same change.

Not in the kit yet: rigs, animation clips, baked textures and procedural materials. The
generators that need them (`creature.*`, `nature.rock`, `hard_surface.kit_cell`) stay on
`bpy` until those steps exist.
