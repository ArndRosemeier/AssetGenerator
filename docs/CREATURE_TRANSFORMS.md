# Turning `male_base` into a creature

Written after `male_orc_01`: a week in which three cloud models and several local
runs produced green `EXIT 0` bakes whose renders were wrong, followed by a day in
which the same script produced an orc. This file is here so the goblin, the
kobold, the ogre and the elf cost the day and not the week.

Two halves:

- **Parts 1–5 are the recipe.** What to do, in order, with the numbers already
  measured and the knobs already named.
- **Parts 6–7 are the lessons.** Every one is a rule with a receipt, because a
  rule without a receipt gets argued away at the first inconvenience. The
  receipts are in `tools/bake_human_orc.py` history.

**The ninety-second version.** The pipeline is a sequence of vertex-displacement
passes over one 53-bone MakeHuman donor, each gated. Nothing about it is
orc-specific except roughly forty numbers. To make a new creature you change
those numbers, in this order: body mass gains, then mouth aperture fractions,
then teeth, then brow and jaw, then colour — looking at a render after each. You
do not touch the pass structure or the gates. The failure mode that costs days is
never a wrong number; it is a gate that measures something other than what the
renderer draws, so before you change anything, make sure you can render and look.

---

# Part 1 — The recipe

## 1. Write the creature down as measurements, not adjectives

"Goblin" is not actionable. What the pipeline can act on is a table like:

| | value |
|---|---|
| overall height | 0.65 × human |
| trunk mass | −0.10 (thinner than donor) |
| neck mass | −0.05 |
| maw half-width | 0.26 of head width (human 0.20) |
| maw half-height | 0.18 of lower face (orc 0.27) |
| teeth | 6 small, 0.08 of head width |
| brow | none |
| ears | +0.35 of head width, swept back |
| skin | sallow yellow-green |

Do this before opening the script. Half of the orc's wasted iterations were
"make it more orcish" with no target, and an amplitude raised until something
looked wrong. The other half were fixed by asking which *direction* the mass
should go, which only has an answer once you have written the table.

Every row above maps to a named constant. Part 3 is the map.

## 2. Make the run work before you change anything

A run that cannot render cannot do look-dev, and three cloud models proved that
the hard way (rule 11). Get to a render of the *unmodified* orc first.

On Arnd's machine, with the pinned Blender:

```powershell
python tools\ag.py doctor
tools\blender-bin\blender-4.5.12-windows-x64\blender.exe --background --factory-startup --python tools\bake_human_orc.py
```

Anywhere else — including a cloud agent — the script runs against the `bpy` PyPI
module instead:

```bash
pip install "bpy==4.5.9"          # must match the pinned 4.5.x, see rule 18
export ORRUN_ROOT=/path/to/OrrunWithEngine
python tools/bake_human_orc.py
```

Two things bite here:

- **The donors are not in the repo.** `.gitignore` line 20 excludes
  `assets/humans/**`, so a fresh clone has no `male_base.glb` and no animation
  donor, and the bake refuses immediately. They live in the `OrrunWithEngine`
  repo; fetch `male_base.glb` and `male_dressed_male_worksuit01.glb` into
  `assets/humans/` before the first run.
- **`ORRUN_ROOT`** defaults to `C:\Projekte\OrrunWithEngine`. Set it or the
  animation donor lookup fails.

Outputs land in `tools/_human_orc_bake/previews/` — four body stills, four mouth
close-ups, and `art_review_packet.json` with every measurement the run made.
Read the PNGs. If you cannot read the PNGs, you are not doing look-dev; say so in
your summary rather than reporting a look pass done.

## 3. Run the six harnesses before you touch anything

They need no Blender install, no donor, and no GPU, and they take seconds:

```bash
python tools/orc_mouth_geometry.py            # landmark + aperture solver
python tools/orc_mouth_selfcheck.py           # maw carve + tusk gates, replayed
python tools/orc_mouth_rim.py                 # the elliptical rim cut
python tools/orc_bind_repair.py               # seam repair on modelled skinning
python tools/orc_still_visibility.py          # projection + occlusion
python tools/orc_carve_integration_check.py   # calls the real bake, synthetically
```

The last one is the valuable one: it builds a synthetic skinned head as a real
Blender object and calls `bake_human_orc`'s actual functions. The first time it
ran it found three bugs the pure-Python harnesses had passed (rule 10). The
others are cheap enough that there is no reason not to run all six.

`orc_mouth_selfcheck.py` reads the constants straight out of `bake_human_orc.py`
by AST so the two cannot drift. That also means **renaming a constant can stop it
from starting**, and a harness that exits before its first check looks a lot like
a harness that passed. Treat "cannot start" as a red build.

## 4. Copy the script for creature #2; extract a spec before creature #3

`bake_human_orc.py` is one creature hardcoded — 6990 lines with the orc's numbers
as module constants. That is a known violation of this repo's own rule that every
asset is a spec (`.cursor/rules/asset-lab.mdc`), and Part 5 says what to do about
it.

For the *second* creature, copy the file anyway. You do not yet know which forty
numbers vary and which are donor facts, and an abstraction guessed at that point
is worse than a duplicate. Copy, change numbers, ship, and keep a list of every
constant you touched. That list is the spec schema, discovered rather than
designed. Do the extraction before the third.

## 5. The pass order, and what each pass owns

This is `run_restyle()`. The order is load-bearing and the comments in it explain
why; the short version:

| # | pass | owns |
|---|---|---|
| 1 | `strip_dressed_meshes_attach_male_base` | nude body on the 53-bone bind |
| 2 | `rehome_unbound_verts` / `assert_all_skin_verts_bound` | a complete bind before anything reads it |
| 3 | `drop_morph_shape_keys` | making `mesh.vertices` authoritative (rule 1) |
| 4 | `resolve_mouth_aperture` (pass 1) | landmarks on the untouched donor face |
| 5 | `restyle_face` | jaw push + brow ridge |
| 6 | `build_orc_body_mass` | neck, shoulders, trunk, limbs |
| 7 | `resolve_mouth_aperture` (pass 2) | landmarks **re-measured** on the built face |
| 8 | `carve_orc_mouth_cavity` | rim loop cut, bore, interior paint, lip roll |
| 9 | `repair_bind_seams` | torso seams that tear under the still poses |
| 10 | `add_tusks` | teeth, bone-parented to head |
| 11 | `apply_finished_olive_skin` | materials |
| 12 | `render_clip_stills` | the four clips, and refusal if teeth are invisible |
| 13 | `export_glb` | dest — **only after the stills pass** |

Three properties of that order are worth protecting:

- **Landmarks are measured twice.** Once for the face build to aim at, once after
  it so the mouth is cut into the face that actually ships. The earlier design
  measured once and then faded the jaw to zero across the mouth so the carve
  would still see the face it had solved on — which froze the one region a muzzle
  *is* (rule 3).
- **Body mass runs before the second measurement and before seam repair**, so the
  mouth is solved on the shipped mesh and the seam repair sees the thickened
  trunk.
- **Dest is written last.** A failed gate leaves the previous asset intact.

## 6. Change numbers, in this order

Bottom-up, because each stage changes what the next one measures, and because the
coarse read is what fails first.

1. **Silhouette at body distance** — `BODY_BONE_GAIN`, overall scale. Judge on
   the Idle body still. Nothing about the face matters if the figure reads wrong
   at ten metres.
2. **Head shape** — `JAW_FORWARD_M`, `BROW_*`. Judge on the mouth close-up.
3. **The maw** — `MOUTH_*` fractions in `orc_mouth_geometry.py`.
4. **Teeth** — `TUSK_*`. These are anchored on head width, deliberately not on
   the aperture, so 3 and 4 are independent (rule 7).
5. **Colour** — `OLIVE`, `OLIVE_SHADOW`, `OLIVE_WARM`, `TUSK`, `MOUTH_INTERIOR`.

Re-run the harnesses after each step; re-render after each step. A step that
changes no pixels is a step you got wrong, and the script's gates
(`BODY_MASS_MIN_MOVED_VERTS`, `CAVITY_MIN_CARVED_VERTS`) exist because a pass
that silently moves nothing is how the orc's face kept coming back human.

## 7. Read the renders in this order

1. **Body still, Idle.** Silhouette only. Squint. Does it read as the creature?
2. **Body still, Death.** Same figure, unfamiliar pose — this is where bind seams
   and stretched torso edges show.
3. **Mouth close-up, all four clips.** Teeth present, rooted, not floating.
4. **Body still, Punch.** The guard hand is in frame; check the teeth are still
   readable past it.

Then go looking for specific defects, because these three took a real bake each
to find and all three are invisible in a loose shot: pectoral lumps from
isotropic trunk gain, a seam line down the shin from smoothing across a UV seam,
and a ragged mouth rim. Frame tightly enough to see them (rule 17).

---

# Part 2 — The donor, already measured

Do not re-measure these. Sizing something off head width when you meant face
height is how a maw tuned green opened 2.8 mm through the chin (rule 13).

| fact | value | why it matters |
|---|---|---|
| bind | 53 bones, MakeHuman | never add bones; teeth and horns bone-parent to `head` |
| skull cloud width | **176 mm** | includes ears and cranium — larger than you expect |
| nose tip → chin | **61 mm** | the *lower* face is only ~46 mm of that |
| face/head ratio | **0.35** | the naive synthetic fixture is 0.56 — see rule 13 |
| nose tip Z | 1.6272 | body space, Z-up, −Y forward |
| chin bottom Z | 1.5658 | |
| lip slit Z | 1.5926 | |
| crown Z | 1.7779 | |
| neck Z | 1.5465 | |
| morph shape keys | **29, all at 0** | `face_jaw_width__pos` etc. — see rule 1 |
| duplicate verts | **1137** | glTF splits the mesh along UV seams |
| boundary edges | **2266** | so the surface is patches, not one manifold |
| jaw/neck bind | **rigid** | `head=1.00` adjacent to `neck_01=1.00`, nothing between |
| inner mouth bag | 20–35 mm behind the lip | a second sheet; any mouth-region cut hits it too |
| eyeballs | separate `Eyes` mesh | identity geometry — see rule 8 |

Those numbers are kept live as the `MAKEHUMAN_MALE_BASE` fixture preset in
`orc_mouth_geometry.py`, and the solver sweeps are run against it. A fixture is a
claim about the donor; if you change donor, re-measure and update the preset
before believing any harness.

---

# Part 3 — The knobs that matter

Values are the orc's, as shipped. Everything in `bake_human_orc.py` unless noted.

**Body mass**

| constant | orc | what it does |
|---|---|---|
| `BODY_BONE_GAIN` | per-bone `(x, y, z)` | radial thickening per bone, **anisotropic** |
| | `neck_01: 0.34` | the single biggest contributor to a brute read |
| | `clavicle: 0.30, 0.16, 0.22` | shoulder yoke — where the mass belongs |
| | `spine_03: 0.22, 0.04, 0.10` | widens, barely deepens: a trunk is a slab (rule 14) |
| | `upperarm: 0.18` isotropic | limbs really are round |
| | `thigh: 0.14, calf: 0.12` | keeps legs from reading spindly under a heavy top |
| `BODY_ZERO_GAIN_PREFIXES` | head, pelvis, foot, ball, fingers | a wider pelvis reads as fat; a thick foot lifts the sole off the ground |
| `BODY_MASS_SMOOTH_ITERATIONS` | 10 | Laplacian passes over the offset field (rule 15) |
| `BODY_MASS_MAX_NEIGHBOUR_STEP_M` | 0.008 | anti-tear gate. **Raise gains and smoothing, never this** |

**Mouth** (in `orc_mouth_geometry.py`)

| constant | orc | what it does |
|---|---|---|
| `MOUTH_HALF_WIDTH_FRAC` | 0.20 | of head width |
| `MOUTH_HALF_HEIGHT_LOWER_FACE_FRAC` | 0.27 | of *lower face*, not head width — that is the room it has |
| `MOUTH_HALF_HEIGHT_AVAIL_FRAC` | 0.90 | cap against the room that actually exists at each end |
| `MOUTH_CENTER_BELOW_SLIT_FRAC` | 0.60 | the maw is not centred on the lip; mandibles drop |
| `MOUTH_DEPTH_FRAC` | 0.20 | bore depth, of head width |
| `MOUTH_MAX_FACE_WIDTH_FRAC` | 0.62 | stops the maw becoming a face-wide part |
| `MOUTH_RIM_BELOW_SUBNASALE_FRAC` | 0.10 | clearance from the nose base |
| `MOUTH_RIM_ABOVE_CHIN_FRAC` | 0.10 | clearance from the chin |

**Teeth**

| constant | orc | what it does |
|---|---|---|
| `TUSK_LENGTH_HEAD_W_FRAC` | 0.21 | of head width — independent of the maw by design |
| `TUSK_RADIUS_BASE/TIP_HEAD_W_FRAC` | 0.030 / 0.005 | tip is a near-point, not a flat cap |
| `TUSK_SEAT_U_FRAC` / `_W_FRAC` | 0.65 / −0.70 | where on the rim it erupts, normalised |
| `TUSK_AXIS_SPLAY` / `_OUTWARD` | 0.26 / 0.68 | direction |
| `TUSK_ROOT_BURY_HEAD_W_FRAC` | 0.045 | how deep the root sits in flesh |
| `TUSK_MIN/MAX_PROTRUSION_M` | 0.003 / 0.018 | how far past the lip plane. **This is the silhouette break** |

**Face**

| constant | orc | what it does |
|---|---|---|
| `JAW_FORWARD_M` | 0.014 | muzzle push. 0.022 pushed past the nose and read as a deformity |
| `JAW_DROP_RATIO` | 0.20 | |
| `JAW_BEHIND_NOSE_MIN_M` | 0.004 | the jaw may not lead the nose — **blocks snouts**, see Part 4 |
| `BROW_FORWARD_M` | 0.008 | brow shelf |
| `BROW_BAND_ABOVE_NASION` | (0.0, 0.16) | of head width, from the nose root up |

**Framing** — `STILL_BODY_FILL_FRAC = 0.92`, derived from the posed bbox. If you
cannot see the defect, the framing is the bug (rule 17).

---

# Part 4 — The four creatures you named

Recommended order: **ogre → goblin → *extract the spec* → kobold → elf.** That is
increasing order of new code, and it puts the spec extraction exactly where the
duplication starts hurting.

## Ogre — a day, no new code

The one that is genuinely just numbers. It is the orc with the dials up.

- Trunk and yoke gains up by half to double: `neck_01` ~0.45, `clavicle` ~0.42,
  `spine_03` ~0.32 lateral. Keep the anisotropy — a bigger isotropic gain gives
  you bigger pectoral lumps, not more mass (rule 14).
- Overall scale ~1.2 (see the scale note below).
- Maw wider and deeper: `MOUTH_HALF_WIDTH_FRAC` ~0.24, `MOUTH_DEPTH_FRAC` ~0.24.
- Teeth longer: `TUSK_LENGTH_HEAD_W_FRAC` ~0.28, `TUSK_MAX_PROTRUSION_M` ~0.026.
- Brow heavier: `BROW_FORWARD_M` ~0.012.
- Colour: desaturate toward grey-brown; keep the three-tone structure.

**What will break first:** `BODY_MASS_MAX_NEIGHBOUR_STEP_M` at 8 mm. The answer
is more smoothing iterations, not a looser gate — the gate is measuring exactly
the thing that goes wrong (a permanent ledge in the rest mesh).

**On the hunch.** `bake_human_orc.py`'s header says "no ogre hunch", which was an
orc constraint, not a law. But a hunch means rotating spine bones in the *rest*
pose, and every donor clip is authored against that rest — so you would be
re-verifying all four clips plus `PELVIS_MAX_DELTA_M`. Get the hunch from
clavicle and neck mass and a forward-biased head first. It is most of the read
for none of the risk.

## Goblin — two or three days, one new pass

- **Size is the defining trait**, and it is the one thing radial displacement
  cannot do. See the scale note below.
- **Body gains go negative.** Wiry, not thick: trunk ~−0.08, limbs ~−0.05, and
  possibly skip `build_orc_body_mass` on the trunk entirely. Be aware that
  negative gains are untested — the radius guard and the anti-tear gate should
  both still hold, but run `orc_carve_integration_check.py` before believing it,
  and check `BODY_MASS_MIN_NECK_GROWTH_M`, which asserts *growth* and will refuse
  a shrink. That gate needs to become "moved by at least", not "grew by at
  least".
- **Ears are a new pass.** MakeHuman ears are part of `male_body` with no vertex
  group of their own, so selection is positional: a band in Z around the ear
  height, outboard of some fraction of head width. The pattern to copy is
  `build_orc_brow_ridge` — landmark, eased band, displace, gate that it moved.
  Budget half a day including the gate. Build it once; the elf wants it too.
- **Maw wide and shallow:** `MOUTH_HALF_WIDTH_FRAC` ~0.26,
  `MOUTH_HALF_HEIGHT_LOWER_FACE_FRAC` ~0.18.
- **Many small teeth.** `add_tusks` builds exactly two cones, from a two-entry
  loop over a mirrored seat. Generalising it to N is a seat table and a loop —
  the gates already take a list of tusks, so no gate logic changes. This is the
  cheapest generalisation in the script and both the goblin and the kobold need
  it.
- Skin: sallow yellow-green; keep `OLIVE`/`OLIVE_SHADOW`/`OLIVE_WARM` structure.

## Kobold — the hard one; needs a landmark change

- **A snout is currently forbidden by construction.** The mouth solver finds the
  nose by taking the most-forward midline vertex, and both the jaw and the brow
  have explicit `*_BEHIND_NOSE_MIN_M` gates. Prognathism cannot happen while the
  nose is a fixed reference the face build must stay behind.

  The fix is structural but not large: the pass order already re-measures
  landmarks after the face build (Part 1, step 5), so the *mechanism* for a
  moving nose exists. What has to change is that the nose becomes an **output**
  of the face build — a `build_snout` pass that carries the subnasale and nose
  forward together with the jaw — and the two `BEHIND_NOSE` gates get replaced by
  "the nose leads the jaw by at least X", which is the same invariant stated so
  that it permits the fix instead of forbidding it (rule 4).
- **Horns reuse half the tusk machinery.** `bind_tusk_to_head_bone` works
  unchanged — cone, bone-parented to `head`, no new bones. What does *not* carry
  over is containment: `assert_tusks_in_mouth_for_current_pose` checks the mouth
  rim, and a horn is rooted in the skull. It needs its own gate saying "rooted in
  skull, emerging, tip clear of geometry". That gate is the real work here, and
  it is worth doing properly, because a floating horn is the same defect class as
  the floating tusk that cost the orc four bakes.
- **Scales are a material, not geometry.** `apply_finished_olive_skin` already
  builds a noise → colour-ramp graph; a scale pattern is the same graph with
  different scale and contrast. Cheap, and much cheaper than displacement.
- Do this one *after* the spec extraction. You will be adding real passes, and
  adding them to a copy of a copy is how the fifth creature ends up with a file
  called `orc_something` deciding whether its beak is legal.

## Elf — deceptively hard; do it last

- **It is the first creature that needs the passes to be optional.** No maw, no
  teeth. Right now `add_tusks` is unconditional and `render_clip_stills`
  *refuses* a still that cannot see ivory (`STILL_MIN_TUSK_PX`,
  `choose_mouth_closeup_view(strict=True)`). An elf is therefore not a constant
  change; it is the change described in Part 5, item 2.
- **Ears:** the goblin's pass, different amplitude and sweep.
- **Body:** near-zero or slightly negative gains. Mostly this pass just doesn't
  run.
- **Use the 29 morph shape keys.** What reads as an elf is facial *refinement* —
  cheekbones, a narrower jaw, finer features — which is precisely what
  hand-rolled radial displacement is worst at and what those topology-aware
  MakeHuman morphs are for. `drop_morph_shape_keys` logs every name. Drive them
  to the values you want, bake the mix down, *then* make `mesh.vertices`
  authoritative and continue with the normal pass order. This is the single
  biggest unused lever in the pipeline (rule 1).
- **The honest warning:** an elf is a human with pointed ears and better bones.
  There is no silhouette break and no dark maw to draw the eye, so every defect
  the orc's mass and teeth distracted from will be plainly visible. The quality
  bar is much higher than for the orc, not lower. Do not do this one second.

## The scale note

Overall size is the one proportion change the pipeline cannot express, because
bone scale is forbidden (`assert_no_leg_bone_scale`, `NO_SCALE_BONES`) and vertex
displacement moves verts perpendicular to bone axes.

The available lever is **uniform scale on the armature object**.
`body_world_scale` already anticipates it: it refuses a rotated, skewed or
non-uniformly scaled matrix and returns the uniform factor for everything
downstream to use. glTF export bakes it in.

It is, however, untested in this pipeline. Before relying on it: set the scale
*before* the first measurement so `hip_height_z` and `PELVIS_MAX_DELTA_M` compare
like with like, re-run all six harnesses, and check that Character Studio's
inspector does not assume a human height. Verify it on the ogre, where a wrong
answer is obvious, rather than discovering it on the goblin.

---

# Part 5 — What the pipeline cannot do yet

In the order they will hurt:

1. **The creature is hardcoded.** Extract a `CreatureSpec` — body gains, aperture
   fractions, a teeth seat list, colours, and a per-pass enable flag — loaded
   from `assets/specs/creatures/<id>.json`, with one `bake_human_creature.py`
   owning the pass order. **The passes and the gates do not change**; only the
   numbers move out. This is what this repo's own asset-lab rule has said all
   along, and the human bakes predate it. Do it after the goblin, when you know
   from two creatures what actually varies.
2. **Passes are not optional.** The maw, the teeth and the ivory-visibility still
   gate are unconditional. They need to become "if the spec has teeth, gate
   them", or no creature without tusks can pass.
3. **Teeth are hardcoded at two.** A seat list instead of a two-entry tuple.
   Gates already take a list.
4. **No ear pass**, and three of the four creatures want one.
5. **The nose is a fixed reference, not an editable feature.** Blocks every
   snouted or beaked creature.
6. **The 29 morph shape keys are deleted at zero and thrown away.** They are
   topology-aware morphs authored for this exact mesh — a far better tool for a
   heavy jaw or a fine elven one than anything hand-rolled.
7. **Everything is named `orc_*`.** Rename the shared modules when the spec
   lands, before the name becomes load-bearing in five bakes.

---

# Part 6 — Traps that cost the week

The one-sentence version of the first eleven: **every failure that week was a
gate reading an authority that was not the one the renderer read.** Nothing was
mis-measured. Everything was measured against the wrong thing, and said so
confidently.

## 1. A gate that re-reads the authority the edit wrote cannot detect a discarded edit

`male_base.glb` ships the MakeHuman face sliders as 29 relative shape keys, all
at value 0. **While a mesh has shape keys, Blender builds the evaluated mesh from
the key blocks and ignores `mesh.vertices[i].co` entirely.** So the jaw muzzle,
the brow pass and the whole mouth cavity were written to a buffer that nothing
rendered, exported or ray-cast.

This was invisible to every gate, because each gate re-read the same
`mesh.vertices` it had just written and was told exactly what it wrote.
`carve_orc_mouth_cavity` reported `deepest=0.0353` against a target of `0.0353`
and it was telling the truth. A ray down the mouth axis in the same scene hit
skin 5.2 mm behind the lip plane.

Note the asymmetry that gives the class away: the *tusk* gates used
`evaluated_vertex_world` and were correct all along. The *mouth* gates used raw
`mesh.vertices` and were wrong all along. Same script, same day, same author.

**Rules**

- Geometry gates measure through the depsgraph (`obj.evaluated_get(...)`) or by
  ray-cast. Never through the buffer the edit wrote.
- Before the first vertex edit, assert the mesh has no shape keys, or apply the
  mix down and drop them. `assert_vertex_positions_authoritative` is that assert.
- One authority per piece of state. Mirroring every edit into a second authority
  would have "fixed" this and left two owners of the same vertex.

## 2. A check that computes its own metric after the step it checks is validating its own damage

`carve_orc_mouth_cavity` painted 1052 polygons with `material_index = 1`.
`apply_finished_olive_skin` then called `mesh.materials.clear()`, which removes
every slot and clamps every polygon index to 0. The guard meant to catch that
computed the worst index *after* the clear, measured 0, and passed.

**Rule:** capture the invariant *before* the destructive operation and assert it
after.

## 3. Never protect a measurement from the change it is supposed to measure

The mouth aperture was solved once on the untouched donor face, and the jaw
offset was then faded to zero across that aperture so that "the carve still sees
the face the aperture was solved on". The region around the mouth *is* the
muzzle, so the keepout guaranteed a flat human mid-face with a hole in it, and no
jaw amplitude could have changed that.

**Rule:** keep landmark solvers pure and cheap, and re-measure after each shape
step. Re-measuring costs a log line. If a build step can invalidate a
measurement, that is an argument for measuring again, never for freezing the
build.

## 4. State the invariant you want, not the failure you last saw

The tusk gate required every vertex to stay inside the rim ellipse *and* at least
4 mm behind the lip plane. Both came from a real defect: a cone floating 22 mm in
front of the gum. Together they make a readable tusk impossible — a shape that
may never cross the rim and never reach the lip can only be seen down a hole
pointed at the camera, which is what every still showed. The gate also blocked
its own fix: moving the seat out toward the commissure, where a hypertrophied
canine actually erupts, takes the containment radius past 1.

The invariant actually wanted was "rooted in flesh, emerging through the mouth".
Written that way it *requires* the silhouette break that makes a tusk read.

**Rule:** when a gate is written to refuse a specific bad picture, ask what the
good picture requires, and gate that.

## 5. Anything whose purpose is to be visible needs one pixel or ray gate

The whole week was "EXIT 0, wrong picture". Analytic gates are necessary and never
sufficient. `orc_still_visibility` — which ray-casts from the still camera at the
emergent ivory — is what finally caught it, because it trusted none of the
analytic numbers.

**Rule:** for every feature whose acceptance criterion is "you can see it", at
least one gate must sample the render or cast a ray in the posed scene. Budget
for it up front; it is cheaper than a week.

## 6. A boundary drawn per existing element can only be as smooth as the mesh

The ragged rim was not a carve bug. Two boundaries — where displacement stopped,
and where the dark interior stopped — were each decided per existing vertex or
polygon, so both could only follow the mesh's own topology: 3.6–5.6 mm of wander
on a 33 mm maw. The interior test made it worse by being a threshold on a smooth
field (mean falloff ≥ 0.35 sits at radius ~0.85, not at the rim), so a ring of
carved-back skin was painted as skin — a second, offset ragged edge.

**Rule:** if a boundary matters visually, give it geometry. Cut the contour into
the mesh, then classify exactly. Solve the cut analytically rather than
projecting an interpolated point: the exact crossing lies on both the contour and
the original edge, so it introduces no bump.

## 7. Express a derived size in a measured unit, not in another derived quantity

Tusk length and radii were multiples of the aperture half-height, which made the
maw and the ivory one knob: shrinking the aperture by a fifth would have
shortened every tusk by a fifth for no stated reason.

**Rule:** anchor derived sizes on something measured once and stable — here, head
width. Two independently tunable quantities must not be expressed in each other.

## 8. Never hide identity geometry to silence an artefact

"Thin stray spikes on Idle/Death stills" were dealt with by classifying anything
named `eye*` as junk and unlinking it. The spikes went away. So did the eyeballs
— from the render *and* the shipped GLB. Two empty sockets then became the largest
single defect in the stills: a face that reads dead turns a new maw into a wound
rather than a mouth. `blender_export_humans.py` fits and textures those eyeballs
onto every base, and Character Studio's inspector errors without them.

**Rule:** fix artefacts at their source. Hiding or filtering identity geometry to
make a gate pass is a defensive fix that ships.

## 9. A test tolerance must not be expressed in a design constant

The solver's accuracy sweep asserted the solved lip slit was "within one aperture
half-height" of truth — which tightened the *accuracy* test every time the maw
was made smaller for *artistic* reasons, and duly failed on a solver whose error
had not changed by a millimetre.

**Rule:** a tolerance about accuracy is expressed in a measured quantity, never
in a knob someone will retune for a different reason.

## 10. Offline harnesses only help if they still start

`orc_mouth_selfcheck.py` reads the real constants out of the bake script by AST
so the two cannot drift. When `f03b828` renamed `TUSK_AXIS_MEDIAL`, the harness
exited 1 before its first check — and stayed that way for three bakes. The one
tool built to catch tusk placement problems was dead during the period tusk
placement was the problem.

**Rules**

- Run every harness in the same breath as the bake, and treat one that cannot
  start as a red build, not as noise.
- Keep them cheap and donor-free, so they run anywhere including a cloud agent.
- **A harness that reimplements the code is not a substitute for one that calls
  it.** `orc_mouth_selfcheck.py` mirrors the carve arithmetic in plain Python,
  which keeps the maths honest but cannot catch an edit landing in the wrong
  authority, a material index clamped by a later pass, or a tolerance that only
  works at the origin. `orc_carve_integration_check.py` builds a synthetic head
  as a real skinned object and calls the actual functions; first run, three bugs
  the unit tests had passed.

## 11. A run that cannot render cannot do look-dev

Three cloud models spent a week and confidently reported success, because they
could bake nothing and look at nothing. Structural, not a matter of model
quality.

**Rules**

- A run may edit the script and reason about gates without rendering.
- Only a run that can render the stills and read the PNGs may declare a look pass
  done.
- State plainly in every summary which claims are verified by a harness, which by
  a render, and which are reasoned but unseen. "Reasoned but unseen" is a
  legitimate deliverable; "verified" applied to it is not.

## 12. A fixture not proportioned like the donor predicts nothing

The real skull cloud is 176 mm wide with a 61 mm face — ratio 0.35. The default
synthetic fixture was 155 mm and 87 mm — ratio 0.56. So anything sized off head
width is ~35% larger on the real head while having ~30% less room, which is how a
maw that swept green on the fixture opened 2.8 mm through the real chin.

**Rule:** measure the donor once and keep those numbers as a fixture preset
(`MAKEHUMAN_MALE_BASE`), and sweep it. A fixture is a claim about the donor, and
an unexamined one is a guess wearing a test's clothes.

## 13. An isotropic fix for an anisotropic shape makes it worse

A first body pass put 0.18 radial gain on `spine_03` and read as two sagging
pectoral lumps over a hard crease. A radial push around the spine axis inflates
the chest *forward* exactly as much as sideways, and on this donor's pec shape
forward is the wrong direction. An orc trunk is a slab: the fix was per-axis
gains, widening strongly and deepening barely, plus moving the mass out of the
chest into the clavicles and neck where a brute read actually comes from.

**Rule:** before adding amplitude, decide which direction the mass should go.
"Bigger" is not a direction.

## 14. A displacement is only as smooth as the bind it borrows smoothness from

The argument for weight-blending a displacement is that if the skinning does not
tear under pose, a weight-blended displacement of it cannot either. True, but the
premise is that the bind is smooth — and MakeHuman binds the jaw/neck line
rigidly: adjacent verts go from `head=1.00` to `neck_01=1.00` with nothing
between. A 0.34 neck gain against a 0 head gain therefore steps the field ~20 mm
across one 8 mm edge. That is not a tear under pose; it is worse, a permanent
ledge around the jaw in the rest mesh.

**Rule:** smooth the offset field explicitly rather than trusting the weights to
be smooth, and gate on the worst neighbour step (`BODY_MASS_MAX_NEIGHBOUR_STEP_M`)
so the claim is a number.

## 15. Smoothing over an imported mesh's edge list cracks its UV seams

The glTF importer duplicates vertices along UV seams — 1137 of them on
`male_body`, leaving 2266 boundary edges, so the surface arrives as patches
rather than one manifold. Neighbour-averaging over `mesh.edges` treats coincident
copies as unrelated, so each side of a seam converges to a different offset and
the seam opens. It showed up as a line down the shin.

**Rule:** any diffusion or smoothing on an imported mesh runs on welded topology
(`welded_adjacency`), not on the edge list.

## 16. You cannot judge mass you cannot see

The pectoral lumps and the shin seam were both invisible until the body stills
were reframed to fill the frame (`STILL_BODY_FILL_FRAC = 0.92`, derived from the
posed bbox rather than a fixed camera distance).

**Rule:** frame the still on the feature under review. A wide shot is a different
test, and passing it is not evidence.

## 17. Pin the runtime you gate against

`bpy==5.2.1` removed `Action.fcurves`, and the integration harness died in a way
that read as a rig bug. The repo pins Blender 4.5.12, so the PyPI module must be
4.5.x. Related: under the PyPI module `bmesh` only resolves *after* `import bpy`,
which is why those imports carry `isort: off`.

**Rule:** the offline harness runs the same major version as the pinned Blender,
and says so in its docstring.

## 18. A gate must leave the scene as it found it

`force_head_pose_for_tusk_assert` switched the head bone to Euler to set a
rotation. The mode stayed switched, and every quaternion-keyed clip afterwards
was silently ignored. The fix was to write the quaternion.

**Rule:** verification code is the last thing that should mutate global state. If
a gate must pose, restore.

## 19. A hardcoded absolute path is why a week of cloud runs found nothing

`C:\Projekte\...` in module constants meant the bake could only run on one
machine — a large part of why cloud runs could reproduce nothing and why the
harnesses had to reimplement arithmetic instead of calling it. `AG` now derives
from `__file__` and `ORRUN_ROOT` is an environment variable.

**Rule:** any script a second machine might run derives its root from its own
location. And note the donors are gitignored, so "clone and bake" does not work
without the fetch step in Part 1 — say where they come from.

---

# Part 7 — What worked, and is worth keeping

- **Commit messages that name the pixels and the number that explains them.**
  `13d446f` and `f03b828` are the reason the shape-key bug was findable at all.
  "Here is what the still showed, here is the measurement, here is why they
  disagree" is the practice that broke the week open.
- **Refusing rather than defaulting.** Every solver in `orc_mouth_geometry.py`
  raises with the offending numbers instead of inventing an aperture, so a local
  log is diagnostic on its own.
- **Eased bands everywhere.** `band_falloff` is Lipschitz-bounded by `1.5/edge`,
  so a displacement cannot tear a step larger than the local vertex spacing times
  the ramp slope. The 48 mm chin needle was authored by a hard selection box;
  nothing since has needled.
- **Two measurements from different landmarks, cross-checked.** The lip slit is
  estimated from the chin *and* from the nose, on different scales, and
  disagreement beyond a threshold refuses. Agreement between two independent
  estimates is real evidence; one estimate is a guess with a decimal point.
- **A synthetic fixture that is a real Blender object.** Being able to call the
  actual bake functions on a fake head, in seconds, with no donor, is what made
  cloud iteration possible at all.
