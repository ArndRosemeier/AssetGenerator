"""The puffcap: a pale cave mushroom (the props' own, grown tall) that never moves from where it grows, but
puffs spores at you. It leans back on its stalk, its gills glowing faintly; to puff, it draws its cap in
and down, swelling (the tell), then flares it open and whips forward over the top, throwing the spores.

Squash and stretch (pose.Pose.scales), like the slimes. Loops: Rest (swaying, the cap breathing). Once:
Puff (the game lets the spores go at RELEASE of it), Hurt (a quiver, layered on top), Die (the stalk
buckles and the cap flops over).
"""

from __future__ import annotations

import math

from mathutils import Vector

from blender.generators.mushroom_creature.parts import STALK, Plan, mushroom_body
from blender.generators.quadruped_generator.clips import Clip, ease
from blender.generators.quadruped_generator.pose import Pose, Rig, X, Y, turn
from blender.lib.mushroom import Mushroom


def plan(m: Mushroom) -> Plan:
    # Leaning back (-Y): it faces you over the top of its stalk.
    m.yaw = -math.pi / 2
    b, pieces = mushroom_body(m)
    b.squash = True
    return Plan(b, pieces)


def _shape(
    bend: float = 0.0, side: float = 0.0, cap: float = 0.0, stalk: float = 0.0, nod: float = 0.0
) -> Pose:
    """`bend` the stalk back (forward when negative) and to the `side`; the `cap` flared open (drawn in
    and swollen when negative), the `stalk` stretched (squashed when negative), the cap `nod`ded back."""
    p = Pose()
    for s in STALK:
        p.add(s, turn(Y, side / 3) @ turn(X, bend / 3))
    p.add("cap", turn(X, nod))
    p.scales["stalk1"] = Vector((1.0 - 0.3 * stalk, 1.0 - 0.3 * stalk, 1.0 + stalk))
    p.scales["cap"] = Vector((1.0 + cap, 1.0 + cap, 1.0 - 1.2 * cap))
    return p


def _rest(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    return _shape(
        bend=0.05 * math.sin(w),
        side=0.05 * math.sin(w + 1.3),
        cap=0.025 * math.sin(2 * w),
        nod=0.04 * math.sin(w + 0.4),
    )


#: Of the Puff clip: drawn in by DRAW (the tell), the spores let go at RELEASE, flared and thrown by THROWN.
DRAW = 0.55
RELEASE = 0.62
THROWN = 0.7


def _puff(rig: Rig, t: float) -> Pose:
    if t < DRAW:
        u = ease(t / DRAW)
        q = 0.012 * math.sin(t * 90) * u
        return _shape(bend=0.3 * u, cap=-0.16 * u + q, stalk=-0.08 * u, nod=0.15 * u)
    if t < THROWN:
        u = ease((t - DRAW) / (THROWN - DRAW))
        return _shape(bend=0.3 - 1.05 * u, cap=-0.16 + 0.4 * u, stalk=-0.08 + 0.14 * u, nod=0.15 - 0.45 * u)
    u = ease((t - THROWN) / (1 - THROWN))
    wob = 0.05 * math.sin(u * math.pi * 3) * (1 - u)
    return _shape(bend=-0.75 * (1 - u) + wob, cap=0.24 * (1 - u), stalk=0.06 * (1 - u), nod=-0.3 * (1 - u))


def _hurt(rig: Rig, t: float) -> Pose:
    q = (1.0 - t) * math.sin(t * math.pi * 5)
    return _shape(bend=0.12 * q, side=0.1 * q, cap=-0.08 * q)


def _die(rig: Rig, t: float) -> Pose:
    u = ease(t / 0.85)
    p = _shape(bend=-0.25 * u, side=0.2 * u, cap=0.12 * u, stalk=-0.1 * u, nod=-0.35 * u)
    # The stalk gives way at its middle.
    p.add("stalk2", turn(X, -0.85 * u))
    return p


CLIPS = [
    Clip("Rest", 90, True, _rest),
    Clip("Puff", 45, False, _puff),
    Clip("Hurt", 10, False, _hurt),
    Clip("Die", 45, False, _die),
]
