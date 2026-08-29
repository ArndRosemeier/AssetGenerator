# -*- coding: utf-8 -*-
"""Run the real carve path on a synthetic head, headless, with no donor assets.

``tools/orc_mouth_selfcheck.py`` reimplements the carve arithmetic so it can run
in plain Python; that keeps the maths honest but it is a copy, and a copy cannot
catch the class of bug that cost the most: an edit that lands in the wrong
authority, a material index clamped by a later pass, a boundary that follows
topology instead of the shape it is supposed to follow. Those only show up when
the actual functions run against an actual Blender mesh.

So build a MakeHuman-shaped head as a real skinned object -- armature, ``head`` /
``neck_01`` / ``spine_03`` vertex groups, ``male_body`` mesh name -- and call
``bake_human_orc``'s own ``resolve_mouth_aperture``, ``carve_orc_mouth_cavity``
and ``add_tusks`` on it. No ``male_base.glb``, no animation donor, no Windows
paths: everything comes from ``orc_mouth_geometry._synthetic_head``.

Run with a Blender python, or with the ``bpy`` PyPI module::

    blender --background --python tools/orc_carve_integration_check.py
    python tools/orc_carve_integration_check.py     # needs `pip install bpy`

Wants a 4.x Blender, matching ``blenderctl.BLENDER_VERSION``. Blender 5 removed
the legacy ``Action.fcurves`` collection in favour of slotted actions, and
``bake_human_orc`` still reads it, so the clip-follow half of this check raises
an ``AttributeError`` there. That is an API difference, not a bake bug -- but it
is worth knowing before the pinned version moves.

What it still cannot check: the render. A tusk can pass every measurement here
and look wrong. That is what the mouth close-up stills are for.
"""
from __future__ import annotations

import sys
from pathlib import Path

# isort: off
# bpy first: under the `bpy` PyPI module `bmesh` only resolves once `bpy` has
# been imported. See the same note in bake_human_orc.py.
import bpy
import bmesh

# isort: on

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import orc_mouth_geometry as MG  # noqa: E402


def build_synthetic_skinned_head(**kw: float | int) -> tuple:
    """A quad-grid synthetic head skinned to a 3-bone stand-in rig.

    Ring-major topology matching ``_synthetic_head``, so the quad grid closes
    around each ring exactly as the point cloud is generated. Weights are the
    ones every mouth pass reads: pure ``head`` on the skull, ramping into
    ``neck_01`` and ``spine_03`` below the jaw, so ``skull_vert_indices`` has the
    same job to do here as on the donor.
    """
    rings = int(kw.pop("rings", 64))
    per_ring = int(kw.pop("per_ring", 48))
    pts = list(MG._synthetic_head(rings=rings, per_ring=per_ring, **kw))
    n_rings = len(pts) // per_ring

    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in pts]
    bm.verts.index_update()
    for i in range(n_rings - 1):
        for j in range(per_ring):
            a = i * per_ring + j
            b = i * per_ring + (j + 1) % per_ring
            c = (i + 1) * per_ring + (j + 1) % per_ring
            d = (i + 1) * per_ring + j
            bm.faces.new((verts[a], verts[b], verts[c], verts[d]))
    me = bpy.data.meshes.new("male_body")
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")

    body = bpy.data.objects.new("male_body", me)
    bpy.context.scene.collection.objects.link(body)

    zs = [p[2] for p in pts]
    z_min, z_max = min(zs), max(zs)
    # The synthetic head runs from a neck stub to the crown. Put the head bone
    # where MakeHuman does, at the skull base.
    head_z = z_min + 0.22 * (z_max - z_min)
    # Bone length matters, not just position: assert_tusks_follow_head rotates
    # the head and compares how far the tusk travels with how far the bone TIP
    # travels, so a bone spanning the whole skull makes a correctly-bound tusk
    # look "stuck near rest" -- it is simply much closer to the pivot than the
    # tip is. MakeHuman's head bone is a short stub at the skull base, so match
    # that rather than running it to the crown.
    head_len = 0.12
    arm_data = bpy.data.armatures.new("rig")
    arm = bpy.data.objects.new("rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    # Parented into a chain, spine_03 -> neck_01 -> head. Three loose root bones
    # look identical to every weight query and to the carve, but they break the
    # follow gate silently: rotating the neck cannot move the head bone's tail,
    # so head_tip_delta stays exactly 0 and the gate reports the pose as "too
    # close to rest" when the fixture, not the pose, is wrong.
    for name, parent, z0, z1 in (
        ("spine_03", None, head_z - 0.30, head_z - 0.16),
        ("neck_01", "spine_03", head_z - 0.16, head_z),
        ("head", "neck_01", head_z, head_z + head_len),
    ):
        b = arm_data.edit_bones.new(name)
        b.head = (0.0, 0.0, z0)
        b.tail = (0.0, 0.0, z1)
        if parent is not None:
            b.parent = made[parent]
            b.use_connect = True
        made[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")

    g_head = body.vertex_groups.new(name="head")
    g_neck = body.vertex_groups.new(name="neck_01")
    g_spine = body.vertex_groups.new(name="spine_03")
    # Pure head over the skull, pure spine_03 at the very bottom of the neck
    # stub, one smooth crossover between. Two things this has to get right, both
    # learned by getting them wrong:
    #
    #   * Both ramps must land inside the mesh's actual Z range. A first version
    #     put the spine crossover 240 mm below the head bone -- below the bottom
    #     of the cloud -- so every vert came out head-weighted and
    #     assert_no_torso_spike refused with "too few torso verts (0)".
    #   * The CHIN must be fully head-weighted. The MakeHuman 53-bone rig has no
    #     jaw bone, so the whole mandible rides `head`. With the crossover too
    #     high the chin fell out of skull_vert_indices, the solver measured
    #     chin_z 23 mm above the real chin, and the lip slit rose with it until
    #     the top rim failed its nose clearance -- a fixture artefact that looked
    #     exactly like a real aperture bug.
    #   * The neck/spine crossover must be GRADUAL. Squeezing it into 22 mm put a
    #     0.31 weight gap across 4.6 mm edges, and the trunk-stretch gate refused
    #     the Death pose at 4.9x stretch -- correctly: that is a bad bind, and the
    #     gate exists to catch exactly it. Spread over 55 mm the gap is ~0.12.
    # Both ramp widths are bounded from two sides. Too narrow and the weight gap
    # across one 4.6 mm ring exceeds the 0.25 the trunk gate allows (the gap is
    # about 1.5 * spacing / width). Too wide and the chin drops below the 0.55
    # head weight skull_vert_indices needs. 45 mm and 55 mm sit inside both.
    t = lambda z: MG.smoothstep((z - (z_min + 0.020)) / 0.045)  # noqa: E731
    s = lambda z: MG.smoothstep((z - z_min) / 0.055)  # noqa: E731
    for v in me.vertices:
        z = float(v.co.z)
        g_head.add([v.index], max(t(z), 1e-4), "REPLACE")
        g_neck.add([v.index], max(s(z) - t(z), 1e-4), "REPLACE")
        g_spine.add([v.index], max(1.0 - s(z), 1e-4), "REPLACE")

    body.parent = arm
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    add_stub_clips(arm)
    return arm, body, head_z


def add_stub_clips(arm) -> list[str]:
    """Minimal Idle / Walk / Death01 actions that rotate the head.

    ``assert_tusks_follow_head`` refuses to accept a tusk unless it can watch the
    head actually move: it needs a named clip per label, and Death has to swing
    the head bone tip at least 80 mm or the pose is 'too close to rest to prove
    tusk follow'. That is the right gate -- a tusk stuck at rest world while the
    head moves is the float-off artefact -- but it means the fixture has to
    supply clips. Two keys per bone is enough; nothing here judges the animation,
    only whether the ivory rides the skull.
    """
    from mathutils import Quaternion

    if arm.animation_data is None:
        arm.animation_data_create()
    made = []
    # Death has to clear require_head_delta = 0.08 m at the bone tip. A 120 mm
    # head bone swung 0.95 rad moves its tail 2*L*sin(theta/2) = 110 mm, so the
    # head bone alone supplies it. The neck stays gentle on purpose: a big neck
    # rotation on a short-edged neck stub trips the trunk-stretch gate, which is
    # a real artefact and not something a fixture should be manufacturing.
    for name, head_ang, neck_ang in (
        ("Idle", 0.10, 0.03),
        ("Walk", 0.16, 0.05),
        ("Death01", 0.95, 0.08),
    ):
        act = bpy.data.actions.new(name)
        arm.animation_data.action = act
        for bone_name, ang in (("head", head_ang), ("neck_01", neck_ang)):
            pb = arm.pose.bones[bone_name]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pb.keyframe_insert("rotation_quaternion", frame=1)
            pb.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), ang)
            pb.keyframe_insert("rotation_quaternion", frame=30)
        act.use_fake_user = True
        made.append(name)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    return made


def main() -> int:
    import bake_human_orc as B

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    cases = (
        ("baseline", {}),
        ("narrow head", {"half_width": 0.066}),
        ("broad head", {"half_width": 0.088}),
        ("long face", {"chin_z": 1.532, "nose_z": 1.642, "mouth_z": 1.596}),
        ("dense", {"rings": 96, "per_ring": 72}),
    )
    for label, kw in cases:
        print(f"\n=== {label} ===")
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        arm, body, _head_z = build_synthetic_skinned_head(**kw)

        try:
            aperture = B.resolve_mouth_aperture(arm)
            before_verts = len(body.data.vertices)
            carved = B.carve_orc_mouth_cavity(arm, aperture)
            B.store_mouth_aperture(arm, aperture)
            tusks = B.add_tusks(arm, aperture)
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            check(f"{label} carve+tusks", False, f"{type(exc).__name__}: {exc}")
            continue

        me = body.data

        # 1. The maw is open in the EVALUATED mesh, not just in mesh.vertices.
        # This is the check the whole week turned on: read it back through the
        # depsgraph, the way the renderer and the exporter do.
        #
        # The measurement is the FRONTMOST surface in the middle of the maw, not
        # the deepest. Deepest is useless here: the rim radius is a cylinder, so
        # r <= 0.30 also selects the back of the skull, a whole head depth away.
        # Frontmost is also the number that catches the failure this whole gate
        # exists for -- with the shape keys still on the mesh, every carve edit is
        # discarded and the original lip is still sitting at d ~ 0, so the maw
        # reads closed however deep the analytic bore claims to be.
        deps = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(deps)
        ev_mesh = ev.to_mesh()
        try:
            frontmost = None
            for v in ev_mesh.vertices:
                u, w, d = aperture.aperture_coords(
                    (float(v.co.x), float(v.co.y), float(v.co.z))
                )
                # Front sheet: anything past a few cavity depths is the far side
                # of the head, not the mouth.
                if aperture.radial(u, w) <= 0.30 and d < 3.0 * aperture.depth:
                    frontmost = d if frontmost is None else min(frontmost, d)
        finally:
            ev.to_mesh_clear()
        check(
            f"{label} maw is open in the evaluated mesh",
            frontmost is not None and frontmost >= 0.85 * aperture.depth,
            f"frontmost evaluated surface inside r<=0.30 sits "
            f"{-1.0 if frontmost is None else frontmost * 1000:.1f} mm back, "
            f"need {0.85 * aperture.depth * 1000:.1f} of "
            f"{aperture.depth * 1000:.1f} mm",
        )

        # 2. The rim is the exact ellipse, not a polygon boundary.
        skull = set(B.skull_vert_indices(body))
        straddle = 0
        for poly in me.polygons:
            rs = []
            for j in poly.vertices:
                v = me.vertices[int(j)]
                u, w, d = aperture.aperture_coords(
                    (float(v.co.x), float(v.co.y), float(v.co.z))
                )
                if d >= aperture.depth * 1.001:
                    rs = []
                    break
                rs.append(aperture.radial(u, w))
            if not rs:
                continue
            if min(rs) < 1.0 - 1e-4 and max(rs) > 1.0 + 1e-4:
                straddle += 1
        check(
            f"{label} no polygon straddles the rim",
            straddle == 0,
            f"{straddle} straddling polygon(s) of {len(me.polygons)}",
        )

        # 3. The dark interior is actually assigned, and only inside the rim.
        slot = int(body["orc_mouth_interior_slot"])
        painted = [p for p in me.polygons if p.material_index == slot]
        leaked = 0
        for p in painted:
            for j in p.vertices:
                v = me.vertices[int(j)]
                u, w, _d = aperture.aperture_coords(
                    (float(v.co.x), float(v.co.y), float(v.co.z))
                )
                if aperture.radial(u, w) > 1.0 + 1e-4:
                    leaked += 1
                    break
        check(
            f"{label} interior paint stays inside the rim",
            painted and leaked == 0,
            f"{len(painted)} interior polygon(s) of {len(me.polygons)}, "
            f"{leaked} reaching outside the rim, slot={slot} of "
            f"{len(me.materials)}",
        )

        # 4. Every vert the cut and the subdivision added is still bound. An
        #    unbound skin vert is frozen at rest while the mesh deforms, which is
        #    the strand artefact.
        try:
            B.assert_all_skin_verts_bound(arm, f"{label} integration")
            bound_ok, bound_detail = True, "every vert driven by a real bone"
        except RuntimeError as exc:
            bound_ok, bound_detail = False, str(exc)[:140]
        check(f"{label} all skin verts bound after cut+carve", bound_ok, bound_detail)

        # 5. The tusks emerge. Measured through the same centre-line walk the
        #    still gate uses, in the posed aperture frame.
        frame = B.posed_aperture_frame(arm)
        worst_protrusion = 1e9
        worst_rim_cross = -1e9
        for t in tusks:
            cl = B.tusk_centreline_metrics(arm, t, frame)
            worst_protrusion = min(worst_protrusion, cl["tip_protrusion"])
            if cl["rim_cross_d"] is not None:
                worst_rim_cross = max(worst_rim_cross, cl["rim_cross_d"])
        check(
            f"{label} tusks protrude past the lip plane",
            worst_protrusion >= B.TUSK_MIN_PROTRUSION_M
            and worst_rim_cross <= B.TUSK_RIM_CROSS_MAX_D,
            f"least protrusion {worst_protrusion * 1000:.1f} mm (need "
            f"{B.TUSK_MIN_PROTRUSION_M * 1000:.0f}), worst rim crossing "
            f"{worst_rim_cross * 1000:.1f} mm behind the lip plane",
        )

        # 6. The tusk shaft is smooth-shaded. Flat facets are what made the
        #    18:50 ivory read as folded paper.
        for t in tusks:
            tm = t.data
            smooth = sum(1 for p in tm.polygons if p.use_smooth)
            quads = sum(1 for p in tm.polygons if len(p.vertices) == 4)
            check(
                f"{label} {t.name} shaft is smooth-shaded",
                smooth == quads and quads > 0,
                f"{smooth} smooth of {quads} shaft quad(s), "
                f"{len(tm.polygons)} faces total",
            )

        print(
            f"     {label}: verts {before_verts} -> {len(me.vertices)}, "
            f"carved {carved}, skull {len(skull)}, "
            f"maw {aperture.half_width * 2000:.0f}x"
            f"{aperture.half_height * 2000:.0f}x{aperture.depth * 1000:.0f} mm, "
            f"nose clearance {aperture.subnasale_clearance * 1000:.1f} mm, "
            f"chin clearance {aperture.chin_clearance * 1000:.1f} mm"
        )

    print("\n=== donor that ships morphs ===")
    failures.extend(check_shape_keys_refused(B, check))

    print()
    if failures:
        print(f"CARVE INTEGRATION FAILED: {sorted(set(failures))}")
        return 1
    print("CARVE INTEGRATION OK")
    return 0


def check_shape_keys_refused(B, check) -> list[str]:
    """A donor that ships shape keys must be refused at the edit, not later.

    This is the week's root cause as a regression test. While a mesh has shape
    keys Blender builds the evaluated mesh from the key blocks and ignores
    ``mesh.vertices`` entirely, so every carve edit lands in a buffer nothing
    renders, exports or ray-casts -- and every gate that re-reads
    ``mesh.vertices`` confirms the edit it just wrote. male_base.glb ships 29 of
    them (the MakeHuman face sliders), which is why two EXIT-0 bakes shipped
    stills with no visible tusks.

    ``assert_vertex_positions_authoritative`` is the guard. Prove it fires, and
    that the message names the keys, so the next donor fails here instead of in
    an Art Reviewer packet.
    """
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    arm, body, _hz = build_synthetic_skinned_head()
    bpy.context.view_layer.objects.active = body
    body.shape_key_add(name="Basis", from_mix=False)
    body.shape_key_add(name="face_jaw_width__pos", from_mix=False)

    aperture = None
    try:
        aperture = B.resolve_mouth_aperture(arm)
        B.carve_orc_mouth_cavity(arm, aperture)
    except RuntimeError as exc:
        msg = str(exc)
        ok = "shape key" in msg and "face_jaw_width__pos" in msg
        check(
            "a donor shipping shape keys is refused at the edit",
            ok,
            msg[:160] if ok else f"refused, but not for the keys: {msg[:160]}",
        )
        return [] if ok else ["shape keys refused for the wrong reason"]
    check(
        "a donor shipping shape keys is refused at the edit",
        False,
        "the carve ran on a mesh whose vertex edits Blender would discard",
    )
    return ["shape keys not refused"]


if __name__ == "__main__":
    raise SystemExit(main())
