"""The toadstool: a fly agaric (the props' own, grown big) that is a monster. Disguised, it is just a
mushroom, its roots folded up inside its foot; woken, it shivers, tears six roots out of the ground and
stands up on them, the cap tipping back to show two eyes hidden under the gills; it scuttles on its roots
like a spider, and it strikes by rearing back and slamming its cap down.

The bind pose stands on the roots (so they skin cleanly); the clips lay each root out themselves, as a
chain of three bones (pose.Pose.aims): planted where it stands, or folded back into the foot.

Loops: Rest (the disguise: folded, still), Stand (up on its roots, swaying), Walk (a stride clip: two
tripods of roots in turn). Once: Wake (the shiver, then up), Settle (back down into the disguise), Slam
(back, the tell, then down), Hurt (a jerk, layered on top), Die (the roots curl, it topples over).
"""

from __future__ import annotations

import math

from mathutils import Matrix, Quaternion, Vector

from blender.generators.mushroom_creature.parts import STALK, Piece, Plan, ball, mushroom_body
from blender.generators.quadruped_generator.clips import Clip, ease
from blender.generators.quadruped_generator.pose import Pose, Rig, X, Y, turn
from blender.lib.mushroom import Mushroom
from assetkit.shells import circle, sweep

ROOTS = 6
#: Metres for a stalk 0.8 m tall (scaled with it). The foot stands this high on its roots.
LIFT = 0.18
#: A root in its own upright plane, (out from the stalk's axis, up from the ground): where it leaves the
#: foot, then its joints to its tip. Standing (the bind pose), and folded up inside the foot (the foot
#: on the ground).
STAND = ((0.07, 0.24), (0.26, 0.30), (0.42, 0.12), (0.48, 0.0))
FOLD = ((0.07, 0.06), (0.03, 0.255), (0.08, 0.02), (0.05, 0.15))
#: How thick a root is, at the foot and at the tip.
THICK = (0.042, 0.008)


def _angle(i: int) -> float:
    return math.pi / 6 + i * math.pi / 3


def _legs(i: int) -> tuple[str, str, str]:
    return (f"leg{i}a", f"leg{i}b", f"leg{i}c")


def plan(m: Mushroom) -> Plan:
    k = m.stalk_height / 0.8
    m.at = (0.0, 0.0, LIFT * k)
    b, pieces = mushroom_body(m)
    for i in range(ROOTS):
        a = _angle(i)
        pts = [(r * k * math.cos(a), r * k * math.sin(a), z * k) for r, z in STAND]
        parent = "root"
        for j, name in enumerate(_legs(i)):
            b.bone(name, pts[j], pts[j + 1], parent)
            parent = name
        # The tube, three steps to a joint.
        path = []
        for j in range(3):
            p, q = pts[j], pts[j + 1]
            path += [tuple(p[c] + (q[c] - p[c]) * s / 3 for c in range(3)) for s in range(3)]
        path.append(pts[3])

        def girth(t: float) -> tuple[float, float]:
            r = (THICK[0] + (THICK[1] - THICK[0]) * t) * k
            return (r, r)

        pieces.append(Piece(sweep(path, circle(1.0, 8), scale=girth), "root", _legs(i), 0.03 * k))
    # The eyes, under the gills at the front (+Y), on the stalk's top.
    top = m.at[2] + m.stalk_height
    for s in (1.0, -1.0):
        eye = ball((0.04 * k * s, 0.07 * k, top - 0.065 * k), 0.034 * k)
        pieces.append(Piece(eye, "eye", ("stalk3",)))
    return Plan(b, pieces)


# --- Posing ---------------------------------------------------------------------------------------


def _reach(a: Vector, t: Vector, out: Vector, lengths: list[float], rise: float) -> list[Vector]:
    """A root from `a` to its tip at `t`: the first bone out (along `out`) and up by `rise`, then the
    other two to the tip, the joint between them bowed up and out."""
    l1, l2, l3 = lengths
    j1 = a + (out * math.cos(rise) + Vector((0.0, 0.0, math.sin(rise)))) * l1
    to = t - j1
    d = min(max(to.length, abs(l2 - l3) + 1e-4), l2 + l3 - 1e-4)
    axis = to.normalized()
    bow = out * 0.4 + Vector((0.0, 0.0, 1.0))
    side = (bow - axis * bow.dot(axis)).normalized()
    c = (l2 * l2 + d * d - l3 * l3) / (2 * l2 * d)
    j2 = j1 + axis * (l2 * c) + side * (l2 * math.sqrt(max(0.0, 1 - c * c)))
    end = j2 + (j1 + axis * d - j2).normalized() * l3
    return [a, j1, j2, end]


def _lay(a: Vector, through: list[Vector], lengths: list[float]) -> list[Vector]:
    """From `a`, each bone pointed at the next of `through`, at its own length."""
    pts = [a]
    for p, n in zip(through[1:], lengths, strict=True):
        d = p - pts[-1]
        pts.append(pts[-1] + (d.normalized() if d.length > 1e-6 else Vector((0.0, 0.0, -1.0))) * n)
    return pts


def _pose(
    rig: Rig,
    *,
    lift: float = 0.0,
    roll: Quaternion | None = None,
    bend: float = 0.0,
    side: float = 0.0,
    nod: float = 0.0,
    fold: float = 0.0,
    tips: list[Vector] | None = None,
) -> Pose:
    """`lift` the body (metres; the bind pose stands, -foot() sits it on the ground), `roll` it about the
    ground under its foot, `bend` the stalk back (forward when negative) and to the `side`, `nod` the cap
    back; the roots `fold`ed into the foot (0 standing, 1 folded), on their `tips` (armature space)."""
    p = Pose()
    p.lift = Vector((0.0, 0.0, lift))
    p.roll = roll or Quaternion()
    for s in STALK:
        p.add(s, turn(Y, side / 3) @ turn(X, bend / 3))
    p.add("cap", turn(X, nod))
    body = Matrix.Translation(p.lift) @ p.roll.to_matrix().to_4x4()
    k = _k(rig)
    up = foot(rig)
    ground = rig.tail[_legs(0)[2]].z
    for i in range(ROOTS):
        names = _legs(i)
        lengths = [rig.length(n) for n in names]
        a = body @ rig.head[names[0]]
        rest = [rig.head[n] for n in names] + [rig.tail[names[2]]]
        out = Vector((rest[3].x - rest[0].x, rest[3].y - rest[0].y, 0.0)).normalized()
        tip = tips[i] if tips else rest[3]
        stand = _reach(a, tip, out, lengths, math.atan2(rest[1].z - rest[0].z, (rest[1] - rest[0]).xy.length))
        if fold > 0.0:
            # Folded: in the body's own frame, the foot on the ground.
            c, s = out.x, out.y
            folded = [
                body
                @ Vector(
                    (
                        r * k * c + rest[0].x - 0.07 * k * c,
                        r * k * s + rest[0].y - 0.07 * k * s,
                        ground + z * k + up,
                    )
                )
                for r, z in FOLD
            ]
            pts = _lay(a, [x.lerp(y, fold) for x, y in zip(stand, folded, strict=True)], lengths)
        else:
            pts = stand
        for j, n in enumerate(names):
            p.aims[n] = (pts[j], pts[j + 1])
    return p


def _k(rig: Rig) -> float:
    return (rig.head["cap"].z - rig.head["stalk1"].z) / 0.8


def foot(rig: Rig) -> float:
    """How high the foot stands over the ground in the bind pose."""
    return rig.head["stalk1"].z - rig.tail[_legs(0)[2]].z


# --- Clips ----------------------------------------------------------------------------------------


def _rest(rig: Rig, t: float) -> Pose:
    # Never quite still: a millimetre (the export check takes a clip in which nothing moves for one
    # that came out as a still).
    w = 2 * math.pi * t
    return _pose(rig, lift=-foot(rig) + 0.001 * math.sin(w), fold=1.0, nod=0.003 * math.sin(w))


def _stand(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    return _pose(
        rig,
        lift=0.012 * math.sin(2 * w),
        bend=0.05 * math.sin(w),
        side=0.06 * math.sin(w + 1.1),
        nod=0.06 * math.sin(2 * w + 0.5),
    )


#: The walk: how far a planted tip slides back while it bears (metres, scaled), of the cycle it bears.
STEP = 0.2
BEAR = 0.55
#: Metres per Walk cycle, for a stalk 0.8 m tall (the game paces the clip by it).
STRIDE = STEP / BEAR


def _walk(rig: Rig, t: float) -> Pose:
    k = _k(rig)
    tips = []
    for i in range(ROOTS):
        rest = rig.tail[_legs(i)[2]]
        ph = (t + 0.5 * (i % 2)) % 1.0
        if ph < BEAR:
            y, z = STEP * k * (0.5 - ph / BEAR), 0.0
        else:
            u = (ph - BEAR) / (1 - BEAR)
            y, z = STEP * k * (-0.5 + ease(u)), 0.09 * k * math.sin(math.pi * u)
        tips.append(rest + Vector((0.0, y, z)))
    w = 2 * math.pi * t
    return _pose(
        rig,
        tips=tips,
        lift=0.02 * k * abs(math.sin(2 * w)),
        bend=-0.1,
        side=0.07 * math.sin(2 * w),
        nod=0.05 * math.sin(2 * w + 1.0),
    )


#: Of the Wake clip: the shiver, then up.
SHIVER = 0.35


def _wake(rig: Rig, t: float) -> Pose:
    if t < SHIVER:
        q = 0.05 * math.sin(t * 95) * (t / SHIVER)
        return _pose(rig, lift=-foot(rig), fold=1.0, side=q, nod=0.6 * q, bend=0.3 * q)
    u = ease((t - SHIVER) / 0.45)
    look = math.sin(math.pi * min(1.0, (t - SHIVER) / (1 - SHIVER)))
    return _pose(rig, lift=-foot(rig) * (1 - u), fold=1 - u, bend=0.35 * look, nod=0.25 * look)


def _settle(rig: Rig, t: float) -> Pose:
    u = ease(t / 0.8)
    return _pose(rig, lift=-foot(rig) * u, fold=u, bend=-0.08 * math.sin(math.pi * u))


#: Of the Slam clip: reared back by REAR (the tell), down by DOWN.
REAR = 0.45
DOWN = 0.6


def _slam(rig: Rig, t: float) -> Pose:
    k = _k(rig)
    if t < REAR:
        u = ease(t / REAR)
        return _pose(rig, lift=0.06 * k * u, bend=0.5 * u, nod=0.25 * u)
    if t < DOWN:
        u = ease((t - REAR) / (DOWN - REAR))
        return _pose(
            rig,
            lift=0.06 * k - 0.1 * k * u,
            bend=0.5 - 1.6 * u,
            nod=0.25 - 0.55 * u,
            roll=turn(X, -0.25 * u),
        )
    u = ease((t - DOWN) / (1 - DOWN))
    return _pose(
        rig, lift=-0.04 * k * (1 - u), bend=-1.1 * (1 - u), nod=-0.3 * (1 - u), roll=turn(X, -0.25 * (1 - u))
    )


def _hurt(rig: Rig, t: float) -> Pose:
    q = (1.0 - t) * math.sin(math.pi * min(1.0, t / 0.35))
    return _pose(rig, bend=0.25 * q, side=-0.2 * q, nod=0.3 * q)


def _die(rig: Rig, t: float) -> Pose:
    u = ease(t / 0.8)
    return _pose(
        rig,
        lift=-foot(rig) * 0.7 * u,
        fold=0.75 * u,
        roll=turn(Y, 1.15 * u),
        bend=0.15 * u,
        nod=-0.3 * u,
    )


CLIPS = [
    Clip("Rest", 30, True, _rest),
    Clip("Stand", 60, True, _stand),
    Clip("Walk", 24, True, _walk),
    Clip("Wake", 40, False, _wake),
    Clip("Settle", 30, False, _settle),
    Clip("Slam", 30, False, _slam),
    Clip("Hurt", 10, False, _hurt),
    Clip("Die", 40, False, _die),
]
