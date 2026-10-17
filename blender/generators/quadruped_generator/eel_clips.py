"""The brine eel's clips: the head and jaw only (the game lays the body along its chain and swims it).

Loops: Swim (the head weaving a little, the mouth working as it breathes), Graze (the snout down,
nosing and snapping at the bottom), Rest (still, the mouth opening slowly as it breathes). Once: Rise (the tell:
the head rearing up out of the water, the jaw dropping wide), Strike (the head driven down and
forward, the jaw snapping shut), Hurt (a jerk of the head, the mouth wide, layered on top), Die
(the jaw falling slack).
"""

from __future__ import annotations

import math

from blender.generators.quadruped_generator.clips import Clip, ease
from blender.generators.quadruped_generator.pose import Pose, Rig, X, Y, Z, turn


def _head(pitch: float = 0.0, yaw: float = 0.0, roll: float = 0.0, jaw: float = 0.0) -> Pose:
    """`pitch` the snout up, `jaw` open (radians)."""
    p = Pose()
    p.add("head", turn(Y, roll) @ turn(Z, yaw) @ turn(X, pitch))
    p.add("jaw", turn(X, -jaw))
    return p


def _swim(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    return _head(pitch=0.04 * math.sin(2 * w), yaw=0.08 * math.sin(w), jaw=0.08 + 0.06 * math.sin(3 * w))


def _graze(rig: Rig, t: float) -> Pose:
    """Three seconds of foraging along the bottom: the snout down and casting about, a quick snap now and then."""
    w = 2 * math.pi * t
    snap = max(0.0, math.sin(math.pi * (t % 0.33) / 0.1)) if (t % 0.33) < 0.1 else 0.0
    return _head(pitch=-0.3 + 0.06 * math.sin(4 * w), yaw=0.2 * math.sin(w), jaw=0.1 + 0.35 * snap)


def _rest(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    return _head(pitch=-0.08, yaw=0.02 * math.sin(w), jaw=0.05 + 0.08 * (0.5 + 0.5 * math.sin(w)))


def _rise(rig: Rig, t: float) -> Pose:
    k = ease(t / 0.8)
    sway = 0.05 * math.sin(t * math.pi * 6) * k
    return _head(pitch=0.55 * k, yaw=sway, jaw=0.1 + 0.75 * k)


def _strike(rig: Rig, t: float) -> Pose:
    k = ease(t / 0.6)
    snap = ease((t - 0.45) / 0.3)
    return _head(pitch=0.55 - 0.85 * k, jaw=0.85 * (1.0 - snap))


def _hurt(rig: Rig, t: float) -> Pose:
    k = (1.0 - t) * math.sin(math.pi * min(1.0, t / 0.4))
    return _head(pitch=0.25 * k, yaw=-0.3 * k, roll=0.2 * k, jaw=0.6 * k)


def _die(rig: Rig, t: float) -> Pose:
    k = ease(t / 0.7)
    return _head(pitch=-0.1 * k, roll=0.15 * k, jaw=0.45 * k)


CLIPS = [
    Clip("Swim", 60, True, _swim),
    Clip("Graze", 90, True, _graze),
    Clip("Rest", 120, True, _rest),
    Clip("Rise", 16, False, _rise),
    Clip("Strike", 7, False, _strike),
    Clip("Hurt", 10, False, _hurt),
    Clip("Die", 20, False, _die),
]
