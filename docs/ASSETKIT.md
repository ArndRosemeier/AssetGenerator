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
| `add_painted(verts, faces, slots)` | A closed shell with a material slot per face (`sdf.paint`) |
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

A moving asset adds `Asset(parts, skeleton=Skeleton(...), clips=(Clip(...), ...))` and a
`Part(..., skin=Skin(...))` (`assetkit/rig.py`): bones with heads, tails and parents; per vertex
up to four bone weights; per clip, per frame, each bone's rigid motion of the rest skeleton
(rotation and translation, asset space). The backend turns the motions into Blender's local
bone transforms from Blender's own rest matrices, so bone roll never reaches a generator.
`assetkit.skinning.deform` moves a mesh exactly as Blender's armature does.

## Sculpting organic forms

Boxes, lathes and sweeps model furniture and tools well and bodies, roots and rocks badly.
For those, say what the form *is* and let the kit find the vertices: `assetkit.sdf` builds
shapes as signed distance functions, and `organic.sculpt` takes the shape tree straight from
the spec, so a new organic asset is a JSON file, not code.

```json
"generator": "organic.sculpt",
"params": {
  "parts": {
    "eye": {"sphere": {"centre": [0.095, -0.215, 0.33], "radius": 0.045}}
  },
  "shape": {"above": {"height": 0.0, "shape": {
    "displace": {"amount": 0.006, "scale": 22.0, "seed": 11, "shape":
      {"smooth_union": {"k": 0.05, "shapes": [
        {"ellipsoid": {"centre": [0, 0.04, 0.2], "radii": [0.2, 0.25, 0.15]}},
        {"mirror_x": {"ref": "eye"}}
      ]}}}}}},
  "base_slot": "skin",
  "paint": {"eye": {"mirror_x": {"ref": "eye"}}},
  "max_triangles": 5000
}
```

| Kind | Nodes |
| --- | --- |
| Primitives | `sphere`, `ellipsoid`, `box` (rounded), `capsule` (tapering with `radius_b`: limbs, horns, roots), `cylinder`, `cone` (flat ends: cups, spikes, shades), `torus` |
| Combinations | `union`, `smooth_union` (`k` metres of blend, like clay pressed together), `subtract` (optional `k`), `intersect` |
| Cuts | `below` / `above` a height: flat tops and flat bottoms |
| Placement | `move`, `rotate` (degrees, X then Y then Z, `about` a pivot: tilt a chest at the waist), `scale`, `mirror_x` (model one side of a body, get both) |
| Many | `repeat` (`count` copies a `step` apart, or `around` the Z axis: segments, ribs, legs), `scatter` (copies set on another shape's surface: barnacles, warts, spikes; below) |
| Surface | `displace` (seeded noise: `amount` metres, features `1/scale` across, `octaves`), `round`, `shell` (hollow) |
| Reuse | `parts` names nodes; `{"ref": "name"}` uses one, in the shape or in `paint` |

`scatter` places copies of a shape modelled at the origin, pointing up, on the surface of
another: `{"scatter": {"on": {"ref": "rock"}, "shape": {"ref": "barnacle"}, "count": 7,
"seed": 3, "spacing": 0.15, "angle": 55, "sink": 0.012, "sizes": [0.8, 1.15]}}` drops seven
at seeded places at least 15 cm apart where the rock faces within 55 degrees of up, stands each
along the surface and sinks it 12 mm in; `"at": [[x, y], ...]` sets copies at chosen places.
It returns only the copies: union them with the rock, and paint them with the same node.

Articulated bodies (insects, skeletons, armour) read as articulated when their pieces stay
distinct: join segments with `smooth_union` of a small `k` (1 to 2 cm), not one big blend; a
blob with limbs comes from a single large `k` over everything.

The full node reference, with every key, is at the top of `assetkit/sculpt.py`. Errors name
the path to the bad node (`params.shape.subtract.cut[1].sphere.radius: ...`).

`paint` gives regions their own material: a face inside a region (or within `paint_reach`)
takes its slot. A region can be a part of the shape (eyes, horns) or any volume laid over it
(moss over the top). The mesh is cut along each region's edge, so borders follow the region
instead of zigzagging along triangles. Other keys: `sharp_angle` (degrees; smooth shading
keeps sharper edges hard), `smooth`, `settle` (default on: footprint centred, resting on z=0),
`detail` (default 4, up to 16: how finely the shape is sampled, in times the budget; raise it
when small features such as a cup's rim come out torn, at the cost of build time).

How it is meshed, and what that guarantees:

1. **Marching tetrahedra** on a grid fine enough for about `detail` times the budget: always
   closed and manifold (marching cubes is not), wound outward. Where a tenth of the surface is
   thinner than a cell across its radius (legs, fingers), it samples again up to twice as
   finely, so thin parts are resolved at all.
2. **Quadric edge collapse** (`assetkit/simplify.py`) down to 85% of `max_triangles`, most
   of the way in batches of independent collapses in numpy, the last stretch one at a time:
   triangles gather where the form bends and thin out where it is flat. Each vertex's error is
   weighed by how thin the shape is there, so a 2 cm leg keeps its roundness next to a 30 cm
   body. A collapse that would pinch the surface, turn a face over or line three corners up is
   refused, so the result stays closed, manifold, outward and free of zero-area faces.
3. **Refining** spends the rest of the budget splitting the edges longest for the thickness
   where they lie, each new vertex put on the true surface, then **relaxing** evens the
   triangles out along the surface. Every vertex ends on the true surface.
4. **The same spec gives the same mesh bit for bit** on numpy 1.26 (Blender 4.5) and 2.x
   (Blender 5, CI): all vector maths is written out element by element, never through BLAS
   (`@`, `einsum`, `norm`), whose rounding differs between builds. A test holds a golden hash.

`assetkit.sdf` and `organic.sculpt` need numpy (Blender's Python has it; the rest of the kit
is standard library only). A sculpt builds in two to fifteen seconds (thin parts, noise over
everything and many scattered copies cost the most), so `ag.py look` takes about that long.

Examples: `sculpt_boulder_mossy`, `sculpt_tree_stump`, `sculpt_barnacle_rock` (scatter),
`sculpt_cave_toad`, `creature_gloom_crawler` (an insect of distinct segments),
`creature_crypt_husk` (a hunched biped, ribs by `repeat`, a ragged skirt) in `assets/specs/`.

## Hard-surface props in JSON

Lanterns, cages, chests, tools, furniture, fittings: things made of turned, cut and bent parts
with crisp edges. `prop.assembly` takes them from the spec as exact pieces, each a closed shell
with its own material slot, placed, repeated, mirrored and grouped. A new prop is a spec.

```json
"generator": "prop.assembly",
"params": {
  "parts": {"rivet": {"sphere": {"centre": [0, 0, 0], "radius": 0.0045}, "slot": "iron", "segments": 6}},
  "pieces": [
    {"lathe": {"profile": [[0.105, 0], [0.105, 0.012], [0.094, 0.03], [0.088, 0.034]]}, "slot": "iron"},
    {"cylinder": {"a": [0, 0, 0.034], "b": [0, 0, 0.318], "radius": 0.074}, "slot": "glass"},
    {"box": {"size": [0.016, 0.016, 0.31]}, "at": [0.084, 0, 0.172], "slot": "iron",
     "repeat": {"around": 4, "start": 45}},
    {"ref": "rivet", "at": [0.094, 0, 0.03], "repeat": {"around": 8}},
    {"torus": {"centre": [0, 0, 0.497], "radius": 0.032, "thickness": 0.009, "axis": "y"}, "slot": "iron"}
  ],
  "bevel": 0.0015
}
```

| Shape | Keys |
| --- | --- |
| `box` | `size` round the origin, or `lower` and `upper` corners |
| `cylinder` | `a`, `b`, `radius`, `radius_b` (a cone; 0 for a point): a rod between two points |
| `sphere` | `centre`, `radius` |
| `torus` | `centre`, `radius`, `thickness`, `axis` x, y or z: rings, hoops, handles |
| `lathe` | `profile` [[r, z], ...] turned about Z (open ends close to the axis): caps, bases, bottles |
| `tube` | `path` [[x, y, z], ...], `radius`, `smooth` (default true): bent rods, bails, wires |
| `extrude` | `outline` [[x, y], ...] raised `height` from z = 0: plates, blades, brackets |
| `sheet` | `size` [w, h], `thickness` (4 mm), `divisions` [nx, nz] (about 6 cm squares): a thin panel facing -Y, centred on the origin: cloth, banners, sails, paper. Divided so it can bend when rigged |

Every piece takes `slot`, `scale`, `rotate` (degrees, X then Y then Z), `at`, `repeat`
(`{"count", "step"}` or `{"around", "start"}`), `mirror` (`x` or `y`), `segments` and
`bevel`, applied in that order; a `group` (a list of pieces) takes them too, and `ref` uses a
named piece from `parts`. Round shapes get their sides from their size (rods, tubes and rings
at least 12, so they shade round). Pieces may overlap (a post through a cap); each stays
closed, so QA holds. The reference is at the top of `assetkit/assembly.py`.

`bevel` (metres) rounds the edges of pieces at least 8 bevels thick (caps, posts, plates) and
leaves thinner ones alone (rivets, wires, thin hoops), where a bevel would collapse or bloat
them; `"bevel": true | false` on a piece decides instead. The generator checks the triangle
count the bevel will produce against `qa.max_triangles` before Blender starts.

Example: `prop_crypt_lantern` (rusted iron, see-through glass, a candle).

### Moving parts: wheels, doors, cranks, cloth

Give the spec a `rig` and tie pieces to bones: `"bone": "wheel"` moves a piece (or a group)
rigidly with that bone; `"bones": ["cloth1", ..., "cloth6"]` bends it smoothly along a chain
(each vertex follows the nearest of those bones, blended over `softness` metres, default
0.05). Pieces tied to nothing follow the first (root) bone. Bones are `head`, `tail` and
`parent`, in the spec's coordinates; clips use the motions of "Rigging and animating a sculpt"
below, and two made for mechanisms:

```json
"rig": {
  "bones": {"frame": {"head": [0, 0, 0], "tail": [0, 0, 0.4]},
            "wheel": {"parent": "frame", "head": [-0.62, 0, 1.2], "tail": [0.62, 0, 1.2]}},
  "clips": {"Turn": {"seconds": 6, "motions": [{"spin": {"bone": "wheel", "turns": 1}}]}}
}
```

- **A wheel, a drum, a crank, a fan**: build it in its own group, tie the group to a bone whose
  head-to-tail line is the axle, and `spin` it. A loop needs whole `turns`.
- **A door, a lid, a lever**: a bone with its head on the hinge, and a `turn` or `keys`.
- **Cloth, a banner, a sail, a rope**: a `sheet` piece tied to a chain of bones hanging down
  it, and a `wave` (`pitch`, `yaw`, `roll` degrees; `cycles`; `lag`, the delay per bone in
  cycles; `grow`, the swing's growth bone to bone so the free end flaps most).

Examples: `prop_mill_waterwheel` (a wheel on a frame), `prop_hanging_banner` (cloth on six
bones). `generate` holds Blender's skinning to the kit's (`rig_matches_kit`).

### Tiles that fit together

Modular pieces (wall runs, floors, fences) want their origin on the grid, not centred:
`"settle": false` keeps the coordinates as written, with `qa.require_origin_at_base: false`.
Then give their materials a `period` (see "Materials") equal to the grid step, so the patterns
run on across every joint, and look at them together as a kit (see "Kits").
A `bevel` rounds a tile's ends too, so each joint shows as a groove that wide (here 4 mm, it
reads as one more mortar joint); leave it off where the joint must vanish.
`tile_brick_wall` and `tile_brick_corner` are a 2 m wall and its corner;
`assets/kits/brick_wall_run.json` lays four of them out.

## Rigging and animating a sculpt

A sculpt rigs itself from what it already knows: which part every point of its surface lies
on. Add a `rig` to an `organic.sculpt` spec and the kit builds the skeleton, the skin weights
and the clips; the backend makes them a Blender armature and glTF animations.
`assets/specs/sculpt_cave_toad.json` (four legs) and `sculpt_cave_imp.json` (two legs, arms)
are complete examples.

### The recipe

1. **Model limbs as capsule parts, one per bone, on the left (+X) side**, and put them in
   the shape with `mirror_x`. Model the body in an A-pose: arms out from the flanks, legs
   apart, every limb further from the body than the smooth-union `k`. A limb within `k` is
   glued to the body, and that skin tears when the limb moves.
2. **Bones**: one per moving piece. Take limb bones `from` their capsule part (head at `a`,
   tail at `b`); place the others (body, head, feet) by `head` and `tail`. Name left bones
   `*.L`: the `*.R` twin is made for you.
3. **Carry**: say which parts each bone carries (`"head": ["head", "snout"]`). A bone taken
   `from` a part carries it already. The skin weights follow from the distance to those parts.
4. **Legs**: name each two-bone limb that walks (`"hind.L": {"upper", "lower", "foot"}`).
5. **Clips**: a few motions each (below).
6. **Look**: `python tools/ag.py look <id>` writes `assets/out/look/<id>_rig.png` and prints a
   line per clip. Fix what it flags, then `generate`.

### Conventions

| Word | Means |
| --- | --- |
| front, up, left | -Y, +Z, +X (the creature's left; `*.L` bones) |
| `pitch` | turn about X: a nose, or a limb's far end, up and forward (+) |
| `yaw` | turn about Z: towards the creature's left (+) |
| `roll` | turn about Y: its right side down (+) |

Turns are in degrees, in the rest pose's axes, about the bone's head, after its parent has
moved. `"bone": "ear.*"` turns both ears, the right one mirrored. Times `t` run 0..1 over a clip.

### Motions

| Motion | Does |
| --- | --- |
| `turn` | a bone swings: `pitch`/`yaw`/`roll` degrees times a wave (`sine`, `bounce`, `constant`) at `cycles` per clip, `phase` 0..1 |
| `move` | the whole body moves `x`/`y`/`z` metres: bob (`bounce`), sway, hop |
| `keys` | poses at times (`at: [{t, turns, move}]`), eased `smooth` or `linear`; a key leaves out what is at rest |
| `spin` | a bone turns steadily about its own axis (head to tail), `turns` per clip: wheels, drums, propellers |
| `wave` | a chain of `bones` (root first) swings the same way, each `lag` of a cycle after the one before, `grow` times as far: flags, tails, tentacles, ropes |
| `gait` | legs step in place: `legs: {name: phase}`, `stride`, `lift`, `duty` (share of a cycle on the ground). Feet are planted by inverse kinematics; knees bend the way they were modelled. A `.L` leg's twin steps half a cycle later unless listed. `per_leg: {"leg.R": {"lift": 0.015, "duty": 0.5}}` gives one leg its own lift and duty: a **limp** (its stride follows from its duty, so no foot skates) |

Recipes that work: a **walk** staggers four feet (`hind.L 0, fore.L 0.25, hind.R 0.5,
fore.R 0.75`) or alternates two (`leg.L 0`), with a `bounce` bob at two cycles. **Arms** swing
against the legs: `upper_arm.L` and `upper_arm.R` as two `turn`s half a cycle apart (`.*`
would swing them together). **Feet stay put** in a clip that is not a walk (idle, attack):
add a `gait` with `stride: 0`. A **loop** must hold whole cycles; the clip ends where it began.

Every clip lasts exactly its `seconds`: without an `fps` the rig picks the first of 24, 30, 25,
60, ... at which every clip is a whole number of frames (3.0, 1.2 and 0.9 s give 30), and
`generate` reads the clips back from the shipped file (`roundtrip_clips_match`: names, lengths,
loops that end where they start).

### What the checks mean

The rig sheet shows the bones, the weights (each bone's colour, mixed by weight: a joint is a
gradient) and six frames of every clip. Its frames are the skinning sum Blender runs:
`generate` holds Blender to it (`rig_matches_kit`, measured at 5e-7 m on 4.5 and 5.2).

| Flag | Cause | Fix |
| --- | --- | --- |
| `skin tears ... at chest/upper_arm.L` | the named bones' skin stretches past 2x (or folds under 0.25x) | turn those joints less, soften those bones, or model them further apart |
| `X shares skin with Y: model them apart` | a limb fused to the body or another limb | move the limb out of the smooth-union `k` (A-pose, legs apart) |
| `skin tears` (over 2x) / `skin folds` (under 0.25x) | a joint turned too far for its blend, or fused geometry | turn less, soften that bone (`softness`), model apart |
| `sinks into the ground` | the body moves down while feet are not planted | add a `gait` with `stride: 0`, or move less |
| `nothing moves` | every motion is zero or cancels | check bones and amplitudes |

Limits worth knowing:
- glTF engines skin by linear blending, and a thick joint (a shoulder against a chest)
  turned much past 80 to 90 degrees tears there. The flag catches it; keep such turns smaller.
- A feature thinner than the meshing step (a 1 cm ear tip on a 1 m body) is dropped as a
  crumb. Thicken it, or raise `max_triangles`.
- Weights blend over `softness` metres (default 2% of the size): smaller is a crisper joint.
  Then they are joined and smoothed. A vertex never belongs to two bones that do not touch;
  where they meet, the bone between them takes over. Then each joint's blend is spread over
  a few vertices.

## Materials: recipes baked to textures

A material in a spec can carry a `pattern`: layers painted over its base colour and roughness,
each through a mask the kit computes from the surface. The backend bakes them into one colour
and one roughness texture per part, on the part's final mesh and UVs, and wires them into
every patterned slot. glTF carries the result; any engine shows it.

```json
"bark": {"base_color": [0.17, 0.11, 0.07, 1], "roughness": 0.92, "metallic": 0.0,
         "pattern": {"layers": [
           {"mottle":   {"color": [0.07, 0.045, 0.03], "scale": 7, "stretch": [1, 1, 6], "coverage": 0.45}},
           {"mottle":   {"color": [0.13, 0.19, 0.05], "scale": 4, "coverage": 0.22, "seed": 7}},
           {"cavities": {"color": [0.03, 0.02, 0.012], "radius": 0.05}},
           {"edges":    {"color": [0.3, 0.23, 0.15], "radius": 0.03, "amount": 0.45, "breakup": 0.6}}
         ]}}
```

Layers paint in order. Each has a `color` (linear 0..1, like `base_color`), an `amount`
(default 1), optionally a `roughness` it blends in too and a `relief` (metres, raised or sunk
where it paints; see "Normal maps" below). Distances are metres.

| Layer | Paints | Keys (defaults) |
| --- | --- | --- |
| `mottle` | patches of noise | `scale` features per metre (6), `coverage` 0..1 (0.5), `contrast` (2), `octaves` (3), `seed`, `stretch` [x, y, z] ([1, 1, 1]; [1, 1, 6] makes streaks six times taller) |
| `grain` | stripes | `spacing` (required), `axis` x, y, z (layers across that axis) or `radial` (rings round Z: a cut log), `warp` in spacings (1), `sharpness` (2: higher is thinner lines), `seed` |
| `spots` | round spots | `size` diameter (required), `spacing` on the surface (2 x size), `density` share of places with a spot (0.7), `softness` 0 crisp to 1 blurred (0.3), `seed` |
| `gradient` | a fade | `axis` (z), full at `from`, none at `to`: grime at the base, sun-bleached tops; `breakup` 0..1 makes the line ragged |
| `facing` | where the surface faces `direction` ([0, 0, 1]: up) within `angle` degrees (45), fading over `soft` more (20) | `breakup`, `scale`, `seed`: moss and snow on tops, dust on ledges, rust under overhangs ([0, 0, -1]) |
| `cells` | lines where cells `size` across meet, `width` wide (8% of size) | `fill` 0..1 paints each cell's inside by a random share: plates, scales, cracks, cobbles |
| `edges` | outward bends tighter than `radius` (0.05) | `breakup` 0..1 breaks the line with noise; worn, lighter edges |
| `cavities` | inward bends tighter than `radius` | the same keys; dirt in creases and joins |
| `bricks` | the mortar joints of a running bond: courses `size` [length, height] up Z, bricks running along both X and Y, so every wall face and corner shows the bond | `mortar` joint width (0.012; 0 for none), `fill` 0..1 paints each brick by a random share (a second `bricks` layer with `mortar: 0` and `fill` tints brick by brick), `seed`; with a negative `relief` the joints are sunk |

`edges` and `cavities` read the surface two ways, so they work on any mesh: smooth bends by
curvature (a sculpt's shoulders, where a leg joins the body), sharp ones by distance to the
crease (a crate's bevelled corners, which no vertex curvature sees). A right-angled edge reads
the same before and after a one-segment bevel.

**Tiles: `period`.** `"pattern": {"period": 2, "layers": [...]}` makes every layer repeat
every 2 m (or `[x, y, z]`, 0 for an axis that need not repeat): noise, cells, spots, grain and
bricks fit a whole number of features into the period (a 0.24 m brick becomes 0.25 m in a 2 m
period), so a tile 2 m long placed next to another shows one continuous wall. Bricks also line
up across a 90 degree turn (a corner tile); noise and cells do not, so keep them subtle where
turned tiles meet. `look kit:<name>` measures it.

A material's `alpha` (0..1, default 1) makes it see-through: glass, a membrane. It ships as
glTF `alphaMode: BLEND`, and the inspection sheet draws it as a fine checker so what is behind
it shows.

Patterns are written in the coordinates the asset was written in: a sculpt's patterns in its
shape's coordinates, before it is settled on the ground (the same as its rig). A kit generator
says where that origin went with `Part(..., pattern_origin=...)`. A part with a patterned slot
needs an `Unwrap` step.

How it is built:
- `assetkit/material.py` parses the pattern (standard library, so a spec fails before Blender
  starts) and evaluates it (numpy). `Surface` holds the mesh's curvature and creases.
- `assetkit/texbake.py` fills every texel inside a UV triangle with the pattern at the 3D point
  it maps to, grows each island 8 texels outward so filtering never reaches the empty gap, and
  picks the size: about 512 texels per metre, the nearest power of two, 256 to 1024.
- The backend (`_paint` in `blender/backend/__init__.py`) only reads the final mesh and UVs and
  wires two packed images. The kit does the baking, so the maps do not depend on the Blender
  version beyond the UV layout it unwraps.

What `look` shows:
- A kit asset's sheet evaluates the patterns at each pixel (no Blender, no UVs). The rig sheet
  does it at rest, so the patterns move with the skin.
- A shipped file's sheet (`--glb`) samples its base colour textures through its UVs. The two
  agree to within 8-bit rounding (median 0.002 on the stump), so the kit sheet is what ships.
- The report gives each layer's coverage, the share of its material it paints:
  `pattern bark: mottle 42%, mottle 20%, cavities 21%, edges 8%`, measured at points spread
  evenly over the surface (a 4 mm worn edge registers on a large flat face). A layer under 1% does not
  show (`spots` too small or sparse, `radius` too small for the mesh); over 90% hides every
  layer beneath it. Both are flagged.

### Normal maps: detail the triangles cannot hold

A sculpt ships its exact shape along with its mesh (`Part.shape`, the distance function it was
meshed from), and any pattern layer can take a `relief` in metres (`+` raised, `-` sunk:
`{"cells": {..., "relief": -0.003}}` cuts grooves between plates). Where either applies, the
kit bakes a tangent-space normal map: per texel, the point moves onto the exact surface and
takes its normal there, tilted by the relief's slope. It is baked against the shading frames
Blender computes (MikkTSpace tangents, `compat.corner_frames`) and the .glb stores the tangents,
so a viewer reads it back as baked: on `sculpt_barnacle_rock`, normals read back from the
shipped file lie 0.5 degrees (median) from the exact shape's, against 6.6 from the mesh alone.
So displacement noise, cup rims and small bumps show without more triangles. `ag.py look` lights
the kit sheet with the same normals.

Limits:
- Patterns are solid textures (they fill space, the surface cuts them), so a pattern has no
  idea which way a plank runs. Pick the `axis`/`stretch` that suits most faces.
- Detail finer than a texel (a 2 mm grain line at 512 texels per metre) aliases. Keep
  `spacing` above about 5 mm.
- `ag.py pack` (vertex colours, no textures) colours each vertex by its material's pattern
  there, so detail finer than the triangles is lost in a pack (no normal maps either).

Examples: `sculpt_tree_stump` (bark, moss, rings), `sculpt_boulder_mossy` (strata, lichen),
`sculpt_barnacle_rock` (moss creeping down by `facing`), `sculpt_cave_toad` (warts),
`creature_gloom_crawler` (chitin plates by `cells`), `crate_small` (grain, worn edges),
`prop_crypt_lantern` (rust, worn edges, glass).

## Looking at an asset

`assetview/` draws a nine-view inspection sheet and measures what pictures show badly. It uses
numpy and a small software rasterizer, not Blender, so a kit asset is drawn straight from its
generator in about a second:

```bash
python tools/ag.py look prop_shovel          # kit: from the generator, before bevel and unwrap
python tools/ag.py look prop_shovel --glb    # any asset: from the shipped .glb
```

The colour views are lit as the asset ships: smooth where its shading is smooth, hard at
creases and on flat parts (a kit asset by its shading steps, a shipped file by its own
normals). The wire and facing views stay flat per triangle, to show the topology.

Every `generate` writes the same sheet from the shipped file (`assets/out/look/<id>.png`) and adds
its measurements to the report: size, triangles per material, parts, floating parts (not on the
ground and touching nothing that is), open edges, inside-out parts, and balance (centre of mass
against the hull of the footing). These are measurements, not gates: a chain hangs and a
bracket sits on a wall on purpose.

`z-fighting 64.8 cm2 at (-0.28, 0.25, 0.49)`: faces of two different parts lie in one plane,
facing the same way, and overlap; no renderer can tell which is in front, so that area
flickers. A plank flush with its frame, two crossed beams of the same width, a trim plate at
the wall's own depth. The FACING view marks them yellow. Move one part a millimetre or more,
or make one a little narrower. (Faces resting on the ground are left out: nobody sees them.)

### Kits: assets that go together

A kit places several assets and looks at them as one: `assets/kits/<name>.json`,

```json
{"place": [
  {"asset": "tile_brick_wall", "at": [-2, 0, 0]},
  {"asset": "tile_brick_wall", "at": [0, 0, 0]},
  {"asset": "tile_brick_corner", "at": [2, 0, 0]},
  {"asset": "tile_brick_wall", "at": [2, 2, 0], "turn": 90}
]}
```

`python tools/ag.py look kit:brick_wall_run` draws the sheet (`assets/out/look/kit_<name>.png`)
with every asset painted in its own frame, as the game will show them, and adds a line per
joint between neighbours:

```
joint tile_brick_wall#2 | tile_brick_corner#3 at x = 1.00: meets cleanly
joint loose_tile#1 | loose_tile#2 at x = 1.00: 3.0 mm gap; pattern steps along 9% of it: give the pattern a `period` the tiles fit (the grid step)
```

A gap shows a crack of light, an overlap z-fights (the header says where); a pattern that
steps along more than 5% of a joint reads as a seam.

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

When a generator needs something the kit lacks (a boolean, a modifier, a new kind of map):

- If it is geometry, prefer plain Python in `assetkit` (testable, version-proof).
- If it needs Blender, add a step (a frozen dataclass in `assetkit/asset.py`) and carry it
  out in `blender/backend/__init__.py`. The step names the result, not the Blender operator.
- Adding is not breaking. Renaming or changing what an export means bumps `API_VERSION` and
  moves every kit generator along in the same change.

Not in the kit: Blender node-tree materials. The generators built on those
(`nature.rock`, `hard_surface.kit_cell`) and the older creature generators (`creature.*`, with
their own rigs) stay on `bpy`. Sculpted creatures are rigged and animated by the kit, and kit
materials are recipes baked to textures.
