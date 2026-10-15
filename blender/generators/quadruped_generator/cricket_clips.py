"""The cave cricket's clips, on the dog's posing machinery (clips.py).

Loops: Idle (still, feelers sweeping slowly: on the floor or clinging to the rock, which way up is
the game's), Alert (the same, quick and twitchy: it is after you), Scuttle (the six-legged walk),
Hop (hops along the floor), Crouch (sunk on its hind legs, quivering: the tell before a leap).
Once: Leap (the hind legs kicking out straight behind, held through the flight), Bite (rearing
back, then the head driven down with the mandibles working), Hurt (a flinch, layered on top), Die
(over onto its back, legs folding in and twitching).
"""

from __future__ import annotations

import math

from mathutils import Vector

from blender.generators.quadruped_generator.clips import Clip, Gait, build, ease, planted, stepping
from blender.generators.quadruped_generator.pose import Pose, Rig, X, Z, turn

STRIDES = {"Scuttle": 0.32, "Hop": 0.7}

#: Tripods: front and back on one side with the middle on the other.
SCUTTLE = Gait(
    STRIDES["Scuttle"],
    0.5,
    {"fore.L": 0.0, "mid.R": 0.0, "hind.L": 0.0, "fore.R": 0.5, "mid.L": 0.5, "hind.R": 0.5},
    (0.03, 0.02),
    (0.3, 0.2),
)
#: All six together: down, push, up and over.
HOP = Gait(
    STRIDES["Hop"],
    0.35,
    {"fore.L": 0.03, "fore.R": 0.03, "mid.L": 0.02, "mid.R": 0.02, "hind.L": 0.0, "hind.R": 0.0},
    (0.04, 0.03),
    (0.3, 0.2),
)


def _feelers(pose: Pose, t: float, speed: float, reach: float) -> None:
    """Each feeler sweeps on its own, the movement growing towards the tip."""
    w = 2 * math.pi * t
    for side, s, ph in (("L", 1.0, 0.0), ("R", -1.0, 1.7)):
        for i in range(1, 6):
            k = reach * (0.4 + 0.25 * i)
            pose.add(
                f"feeler{i}.{side}",
                turn(Z, s * 0.12 * k * math.sin(speed * w + ph - 0.5 * i))
                @ turn(X, 0.1 * k * math.sin(speed * 0.7 * w + 2 * ph - 0.4 * i)),
            )


def _idle_like(rig: Rig, t: float, speed: float, reach: float, twitch: float) -> Pose:
    w = 2 * math.pi * t
    pulse = math.sin(3 * w)
    p = {
        "hips": 0.02 * pulse,
        "z": 0.002 * pulse,
        "head": 0.06 * math.sin(speed * w * 0.5),
        "neck_yaw": 0.08 * math.sin(w),
        "jaw": twitch * max(0.0, math.sin(speed * 3 * w)),
        "ears": 0.15 * math.sin(speed * w),
        "ears_out": 0.12 * math.sin(speed * w * 0.8 + 1.0),
    }
    pose = build(rig, p, planted(rig))
    _feelers(pose, t, speed, reach)
    return pose


def _idle(rig: Rig, t: float) -> Pose:
    return _idle_like(rig, t, 2.0, 1.0, 0.2)


def _alert(rig: Rig, t: float) -> Pose:
    return _idle_like(rig, t, 6.0, 1.5, 0.5)


def _scuttle(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    p = {"z": 0.004 * math.cos(2 * w), "roll": 0.025 * math.sin(w), "neck_yaw": 0.06 * math.sin(w)}
    pose = build(rig, p, stepping(rig, SCUTTLE, t))
    _feelers(pose, t, 2.0, 1.2)
    return pose


def _hop(rig: Rig, t: float) -> Pose:
    air = (t - HOP.duty) / (1.0 - HOP.duty)
    up = math.sin(math.pi * air) if air > 0 else 0.0
    push = math.sin(math.pi * min(1.0, t / HOP.duty))
    p = {
        "z": 0.08 * up - 0.02 * push * (t < HOP.duty * 0.5),
        "pitch": 0.12 * push - 0.1 * up,
        "hips": -0.08 * up,
        "ears": 0.3 * up,
    }
    pose = build(rig, p, stepping(rig, HOP, t))
    _feelers(pose, t, 1.0, 1.6)
    return pose


CROUCH_POSE = {"z": -0.055, "pitch": 0.12, "hips": 0.05, "head": 0.15, "ears": 0.3, "jaw": 0.2}
CROUCH_SHIFT = {"hind.L": Vector((0.0, 0.03, 0.0)), "hind.R": Vector((0.0, 0.03, 0.0))}


def _crouch(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    p = dict(CROUCH_POSE)
    p["z"] += 0.003 * math.sin(8 * w)
    pose = build(rig, p, planted(rig, CROUCH_SHIFT))
    _feelers(pose, t, 4.0, 1.4)
    return pose


def _leap(rig: Rig, t: float) -> Pose:
    """Out of the crouch: the hind legs kick out straight behind and stay there; the others reach
    forward. The feet are placed (by IK) rather than the joints turned, so the legs stay legs."""
    k = ease(t / 0.5)
    p = {
        "z": -0.055 + 0.13 * k,
        "pitch": 0.12 - 0.2 * k,
        "hips": 0.05 - 0.1 * k,
        "head": 0.15 - 0.2 * k,
        "ears": 0.3 + 0.4 * k,
    }
    shift = {}
    for side in ("L", "R"):
        shift[f"hind.{side}"] = Vector((0.0, 0.03 - 0.55 * k, 0.05 * k))
        shift[f"mid.{side}"] = Vector((0.0, 0.06 * k, 0.1 * k))
        shift[f"fore.{side}"] = Vector((0.0, 0.12 * k, 0.12 * k))
    pose = build(rig, p, planted(rig, shift))
    _feelers(pose, t, 1.0, 0.5)
    return pose


WINDUP = 0.5  # of the clip: the game's 0.3 s rear before the snap


def _bite(rig: Rig, t: float) -> Pose:
    if t < WINDUP:
        k = ease(t / WINDUP)
        p = {
            "pitch": 0.3 * k,
            "y": -0.04 * k,
            "z": 0.03 * k,
            "head": -0.3 * k,
            "jaw": 0.8 * k,
            "ears": 0.4 * k,
        }
    else:
        s = (t - WINDUP) / (1.0 - WINDUP)
        k = ease(s / 0.35)
        back = 1.0 - ease((s - 0.6) / 0.4)
        p = {
            "pitch": (0.3 - 0.5 * k) * back,
            "y": (-0.04 + 0.12 * k) * back,
            "z": 0.03 * (1 - k) * back,
            "head": (-0.3 + 0.6 * k) * back,
            "jaw": 0.8 * abs(math.cos(s * math.pi * 3)) * back,
            "ears": 0.4 * back,
        }
    pose = build(rig, p, planted(rig))
    _feelers(pose, t, 3.0, 1.5)
    return pose


def _hurt(rig: Rig, t: float) -> Pose:
    k = math.sin(math.pi * min(1.0, t / 0.9)) if t > 0 else 0.0
    k = k * (1.0 - 0.3 * t)
    p = {
        "bend": 0.2 * k,
        "roll": 0.15 * k,
        "z": 0.03 * k,
        "head": -0.2 * k,
        "jaw": 0.6 * k,
        "ears": 0.6 * k,
        "hips": 0.15 * k,
    }
    return build(rig, p, planted(rig))


def _die(rig: Rig, t: float) -> Pose:
    over = ease(t / 0.4)
    curl = ease((t - 0.25) / 0.5)
    twitch = math.sin(t * 2 * math.pi * 4) * max(0.0, 1.0 - t) * curl
    p = {
        "z": 0.51 * over,
        "roll": math.pi * over,
        "head": 0.3 * curl,
        "jaw": 0.5 * curl,
        "ears": -0.4 * curl,
        "hips": -0.2 * curl,
    }
    pose = build(rig, p, None)
    for side in ("L", "R"):
        for bone, a in (
            ("upperarm", 0.8),
            ("forearm", -1.0),
            ("midfemur", 0.6),
            ("midtibia", -1.2),
            ("thigh", -0.3),
            ("shin", 0.4),
        ):
            pose.add(f"{bone}.{side}", turn(X, a * curl + 0.2 * twitch))
    _feelers(pose, t, 1.0, 0.6 * (1.0 - curl))
    return pose


CLIPS = [
    Clip("Idle", 90, True, _idle),
    Clip("Alert", 45, True, _alert),
    Clip("Scuttle", 16, True, _scuttle),
    Clip("Hop", 14, True, _hop),
    Clip("Crouch", 24, True, _crouch),
    Clip("Leap", 10, False, _leap),
    Clip("Bite", 18, False, _bite),
    Clip("Hurt", 8, False, _hurt),
    Clip("Die", 30, False, _die),
]
