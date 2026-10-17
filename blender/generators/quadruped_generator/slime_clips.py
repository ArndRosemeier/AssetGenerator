"""The slimes' clips: squash and stretch (pose.Pose.scales) rather than legs.

Loops: Rest (slumped, the jelly trembling and breathing), Ooze (one pulse of its crawl: gather into a
heap, then flow forward, the front lobe out first), Feed (spread out over its food, the front lobe
slowly drawing it in, ripples running back through it), Sleep (sagged flat, slow deep breaths, no
tremble). Once: Blow (the squash down and back, the game's
tell, then thrown forward at you, then settling), Hurt (a quiver, layered on top), Die (melting
into a puddle).

Ooze is one pulse per cycle; the game plays it by the slime's own pulse.
"""

from __future__ import annotations

import math

from mathutils import Vector

from blender.generators.quadruped_generator.clips import Clip, ease
from blender.generators.quadruped_generator.pose import Pose, Rig, X, Y, turn


def _shape(
    squash: float = 0.0,
    flow: float = 0.0,
    lean: float = 0.0,
    sway: float = 0.0,
    dome: float = 0.0,
    spread: float = 0.0,
    shift: float = 0.0,
) -> Pose:
    """`squash` down and out (negative: drawn up tall), `flow` forward (the front lobe out, the back
    one in), `lean` the dome forward, `sway` it sideways, `dome` flattened (negative: peaked),
    `spread` the whole skirt out, `shift` the heap forward (metres)."""
    p = Pose()
    p.lift = Vector((0.0, shift, 0.0))
    out = 1.0 + 0.6 * squash
    p.scales["spine1"] = Vector((out, out + 0.3 * flow, 1.0 - squash))
    p.scales["head"] = Vector((1.0 + 0.4 * dome, 1.0 + 0.4 * dome + 0.2 * flow, 1.0 - dome))
    p.add("head", turn(Y, sway) @ turn(X, -lean))
    p.scales["front"] = Vector((1.0 + 0.3 * flow, 1.0 + spread + 1.6 * flow, 1.0 - 0.3 * flow))
    p.scales["back"] = Vector((1.0, max(0.2, 1.0 + spread - 0.8 * flow), 1.0))
    for side in ("L", "R"):
        p.scales[f"side.{side}"] = Vector((1.0 + spread + 0.3 * squash, 1.0, 1.0))
    return p


def _rest(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    tremble = 0.02 * math.sin(9 * w) * (0.5 + 0.5 * math.sin(2 * w))
    return _shape(
        squash=0.04 * math.sin(2 * w) + tremble,
        lean=0.04 * math.sin(w),
        sway=0.05 * math.sin(w + 1.3),
        dome=0.03 * math.sin(3 * w + 0.5),
    )


def _ooze(rig: Rig, t: float) -> Pose:
    """Gather (0..0.45: heaped, the skirt drawn in), then pour forward (0.45..1)."""
    w = 2 * math.pi * t
    pour = math.sin(math.pi * max(0.0, (t - 0.4) / 0.6))
    gather = math.sin(math.pi * min(1.0, t / 0.45))
    return _shape(
        squash=-0.12 * gather + 0.12 * pour,
        flow=0.35 * pour - 0.1 * gather,
        lean=0.18 * pour - 0.08 * gather,
        sway=0.04 * math.sin(w),
        dome=-0.08 * gather + 0.05 * pour,
        spread=-0.15 * gather + 0.1 * pour,
    )


def _feed(rig: Rig, t: float) -> Pose:
    """Three seconds of feeding: spread out low, the front lobe reaching out and drawing back twice."""
    w = 2 * math.pi * t
    draw = 0.5 + 0.5 * math.sin(2 * w)
    ripple = 0.03 * math.sin(6 * w)
    return _shape(
        squash=0.2 + ripple,
        flow=0.25 * draw,
        lean=0.12 * draw,
        sway=0.03 * math.sin(w + 0.4),
        dome=0.15 + 0.04 * math.sin(4 * w),
        spread=0.12 + 0.05 * draw,
    )


def _sleep(rig: Rig, t: float) -> Pose:
    """Four seconds asleep: sagged flat, breathing slowly."""
    w = 2 * math.pi * t
    breath = math.sin(2 * w)
    return _shape(squash=0.28 + 0.04 * breath, dome=0.22 + 0.03 * breath, spread=0.15, sway=0.02 * math.sin(w))


SQUASH = 0.4 / 0.88  # of the clip: the game's squash (the tell), then the throw, then the settle
THROW = (0.4 + 0.18) / 0.88


def _blow(rig: Rig, t: float) -> Pose:
    if t < SQUASH:
        k = ease(t / SQUASH)
        quiver = 0.03 * math.sin(t * 60) * k
        return _shape(squash=0.38 * k + quiver, lean=-0.25 * k, dome=0.2 * k, spread=0.2 * k, shift=-0.04 * k)
    if t < THROW:
        k = ease((t - SQUASH) / (THROW - SQUASH))
        return _shape(
            squash=0.38 - 0.6 * k,
            flow=0.9 * k,
            lean=-0.25 + 0.75 * k,
            dome=0.2 - 0.4 * k,
            spread=0.2 - 0.1 * k,
            shift=-0.04 + 0.2 * k,
        )
    k = ease((t - THROW) / (1.0 - THROW))
    wob = 0.08 * math.sin(k * math.pi * 3) * (1 - k)
    return _shape(
        squash=(-0.22 + wob) * (1 - k),
        flow=0.9 * (1 - k),
        lean=0.5 * (1 - k),
        dome=-0.2 * (1 - k),
        spread=0.1 * (1 - k),
        shift=0.16 * (1 - k),
    )


def _hurt(rig: Rig, t: float) -> Pose:
    k = (1.0 - t) * math.sin(t * math.pi * 5)
    return _shape(squash=0.18 * k, dome=-0.15 * k, sway=0.12 * k, lean=-0.1 * k)


def _die(rig: Rig, t: float) -> Pose:
    """It quivers, sags and runs out over the ground."""
    k = ease(t / 0.85)
    quiver = 0.05 * math.sin(t * 50) * (1 - k)
    return _shape(squash=0.65 * k + quiver, dome=0.6 * k, spread=0.2 * k, sway=0.1 * k, lean=-0.05 * k)


CLIPS = [
    Clip("Rest", 60, True, _rest),
    Clip("Ooze", 20, True, _ooze),
    Clip("Feed", 90, True, _feed),
    Clip("Sleep", 120, True, _sleep),
    Clip("Blow", 26, False, _blow),
    Clip("Hurt", 10, False, _hurt),
    Clip("Die", 36, False, _die),
]
