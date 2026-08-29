# Creature bake: lessons paid for

Written after a week on `male_orc_01` in which three cloud models and several
local runs produced green `EXIT 0` bakes whose renders were wrong. Everything
here is a rule with a receipt. The receipts are in `tools/bake_human_orc.py`
history; the rules are meant to apply to the next creature, not to that orc.

The single sentence version: **every failure that week was a gate reading an
authority that was not the one the renderer read.** Nothing was mis-measured.
Everything was measured against the wrong thing, and said so confidently.

---

## 1. A gate that re-reads the authority the edit wrote cannot detect a discarded edit

`male_base.glb` ships the MakeHuman face sliders as 29 relative shape keys, all
at value 0. **While a mesh has shape keys, Blender builds the evaluated mesh
from the key blocks and ignores `mesh.vertices[i].co` entirely.** So the jaw
muzzle, the brow pass and the whole mouth cavity were written to a buffer that
nothing rendered, exported or ray-cast.

This was invisible to every gate in the script, because each gate re-read the
same `mesh.vertices` it had just written and was told exactly what it wrote.
`carve_orc_mouth_cavity` reported `deepest=0.0353` against a target of `0.0353`
and it was telling the truth. A ray down the mouth axis in the same scene hit
skin 5.2 mm behind the lip plane, where the analytic bore said 35.3 mm.

Note the asymmetry that gives the class away: the *tusk* gates used
`evaluated_vertex_world` and were correct all along. The *mouth* gates used raw
`mesh.vertices` and were wrong all along. Same script, same day, same author.

**Rules**

- Geometry gates measure through the depsgraph (`obj.evaluated_get(...)`) or by
  ray-cast. Never through the buffer the edit wrote.
- Before the first vertex edit, assert the mesh has no shape keys, or apply the
  mix down into the base and drop them. `assert_vertex_positions_authoritative`
  is that assert; promote it into shared code so the next donor fails at the
  edit rather than in an Art Reviewer packet.
- One authority per piece of state. Mirroring every edit into a second authority
  would have "fixed" this and left two owners of the same vertex.

**Worth knowing for the next creature:** those 29 keys are named
`face_jaw_width__pos`, `face_lip_fullness__neg` and so on — topology-aware
morphs authored for that exact mesh, and a far better tool for a heavy jaw than
hand-rolled radial displacement. `drop_morph_shape_keys` logs the full list.
Drive them, bake the mix, *then* make `mesh.vertices` authoritative. Deleting
them at zero, as we do now, throws the sliders away.

## 2. A check that computes its own metric after the step it checks is validating its own damage

`carve_orc_mouth_cavity` painted 1052 polygons with `material_index = 1` and
logged that it had. `apply_finished_olive_skin` then called
`mesh.materials.clear()`, which removes every slot and clamps every polygon
index to 0. The guard meant to catch that computed the worst index *after* the
clear, measured 0, and passed. The comment above it asserted the opposite.

**Rule:** capture the invariant *before* the destructive operation and assert
it after. A check whose input has already been through the thing it is checking
proves nothing.

## 3. Never protect a measurement from the change it is supposed to measure

The mouth aperture was solved once on the untouched donor face. The jaw offset
was then faded to zero across that aperture, with the stated reason that "the
carve still sees the face the aperture was solved on".

The region around the mouth *is* the muzzle. The keepout therefore guaranteed a
flat human mid-face with a hole in it, and no amount of raising the jaw
amplitude could have changed that.

This is the shape-key bug one level up: a stale authority that edits are
politely routed around, rather than re-derived.

**Rule:** keep landmark solvers pure and cheap, and re-measure after each shape
step. Re-measuring costs a log line. If a build step can invalidate a
measurement, that is an argument for measuring again, never for freezing the
build.

## 4. State the invariant you want, not the failure you last saw

The tusk gate required every vertex to stay inside the mouth's rim ellipse
*and* at least 4 mm behind the lip plane. Both rules were added in response to a
real defect: a cone floating 22 mm in front of the gum, rooted in nothing,
reading as painted on the lip.

But together they make a readable orc tusk impossible. A shape that may never
cross the rim and never reach the lip plane can only be seen down a hole
pointed at the camera — which is exactly what every still showed. Measured, the
tip sat 13.2 mm *behind* the lip plane. The gate also blocked its own fix:
moving the seat out toward the commissure, where a hypertrophied canine
actually erupts, takes the containment radius past 1.

The invariant actually wanted was "rooted in flesh, emerging through the mouth".
Written that way it permits — and *requires* — the silhouette break that makes a
tusk read as a tusk.

**Rule:** when a gate is written to refuse a specific bad picture, ask what the
good picture requires, and gate that. A gate phrased as the negation of one
failure tends to forbid the fix as well.

## 5. Anything whose purpose is to be visible needs one pixel or ray gate

The whole week was "EXIT 0, wrong picture". Analytic gates are necessary and
never sufficient. `orc_still_visibility` — which ray-casts from the still camera
at the emergent ivory — is the thing that finally caught it, and it caught it
because it did not trust any of the analytic numbers.

**Rule:** for every feature whose acceptance criterion is "you can see it", at
least one gate must sample the render or cast a ray in the posed scene. Budget
for it up front; it is cheaper than a week.

## 6. A boundary drawn per existing element can only be as smooth as the mesh

The ragged, torn-looking rim on that maw was not a carve bug. Two boundaries —
where displacement stopped, and where the dark interior stopped — were both
decided per existing vertex or polygon, so both could only follow the mesh's own
topology. On a face sampled at millimetres that turns a smooth ellipse into a
zig-zag of whole polygons, measured at 3.6–5.6 mm of wander on a 33 mm maw.

The interior test made it worse by being a threshold on a smooth field: mean
falloff `>= 0.35` sits at normalised radius ~0.85, not at the rim, so a ring of
carved-back skin was painted as skin — a second, offset ragged edge.

**Rule:** if a boundary matters visually, give it geometry. Cut the contour into
the mesh, then classify exactly. Solve the cut analytically rather than
projecting an interpolated point: the exact crossing lies on both the contour
and the original edge, so it introduces no bump.

## 7. Express a derived size in a measured unit, not in another derived quantity

Tusk length, base radius and tip radius were multiples of the aperture
half-height. That made the maw and the ivory one knob: retuning the mouth
silently rescaled the tusks, so shrinking the aperture by a fifth would have
shortened every tusk by a fifth for no stated reason.

**Rule:** anchor derived sizes on something measured once and stable — here,
head width. If two quantities should be independently tunable, they must not be
expressed in each other.

## 8. Never hide identity geometry to silence an artefact

"Thin stray spikes on Idle/Death stills" were dealt with by classifying anything
named `eye*` as junk and unlinking it from every collection. The spikes went
away. So did the eyeballs — from the render *and* from the shipped GLB. Two
empty sockets then became the largest single defect in the stills: a face that
reads dead turns a new maw into a wound rather than a mouth.

`tools/character_studio/blender_export_humans.py` fits, weights and textures
those eyeballs onto every `{sex}_base.glb`, and Character Studio's own inspector
errors when a body arrives without them. One bake quietly opted out.

**Rule:** fix artefacts at their source. Hiding, unlinking or filtering
identity geometry to make a gate pass is a defensive fix that ships.

## 9. A test tolerance must not be expressed in a design constant

The mouth solver's accuracy sweep asserted the solved lip slit was "within one
aperture half-height" of the known truth. That silently tightened the
*accuracy* test every time the maw was made smaller for *artistic* reasons —
and it duly failed the moment the aperture shrank, on a solver whose error had
not changed by a millimetre.

**Rule:** a tolerance about accuracy is expressed in a measured quantity (head
width), never in a knob someone will retune for a different reason.

## 10. Offline harnesses only help if they still start

`tools/orc_mouth_selfcheck.py` reads the real constants out of the bake script
by AST, on purpose, so the two cannot drift. When `f03b828` renamed
`TUSK_AXIS_MEDIAL`, the harness exited 1 before its first check — and stayed
that way for three bakes. The one tool built specifically to catch tusk
placement problems was dead during the period tusk placement was the problem.

**Rules**

- Run every offline harness in the same breath as the bake, and treat a harness
  that cannot start as a red build, not as noise.
- Keep them Blender-free where possible. `orc_mouth_geometry.py`,
  `orc_mouth_selfcheck.py` and `orc_mouth_rim.py` need only plain Python or
  `bmesh`, which means they run in seconds anywhere — including in a cloud agent
  with no Blender install.

## 11. Process: a run that cannot render cannot do look-dev

Three cloud models spent a week on this and confidently reported success,
because they could bake nothing and look at nothing. The failure was structural,
not a matter of model quality.

**Rules**

- A run may edit the script and reason about gates without rendering.
- Only a run that can render the stills and read the PNGs may declare a look
  pass done.
- State plainly in every summary which claims are verified by a harness, which
  by a render, and which are reasoned but unseen. "Reasoned but unseen" is a
  legitimate deliverable; "verified" applied to it is not.

## 12. What worked, and is worth keeping

- **Commit messages that name the pixels and the number that explains them.**
  `13d446f` and `f03b828` are the reason the shape-key bug was findable at all.
  "Here is what the still showed, here is the measurement, here is why they
  disagree" is the practice that broke the week open.
- **Refusing rather than defaulting.** Every solver in `orc_mouth_geometry.py`
  raises with the offending numbers instead of inventing an aperture, so a local
  log is diagnostic on its own.
- **Eased bands everywhere.** `band_falloff` is Lipschitz-bounded by
  `1.5/edge`, so a displacement cannot tear a step larger than the local vertex
  spacing times the ramp slope. The 48 mm chin needle was authored by a hard
  selection box; nothing since has needled.
