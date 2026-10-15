"""The rat's clips, on the dog's posing machinery (clips.py): the same pose numbers, scaled to a rat.

Loops: Sniff (stood still, nose working, head casting about), Scurry (the quick pottering trot), Run
(the bounding run at you, back flexing), Rear (up on the hind legs, front paws hanging, sniffing: it
has noticed you). Once: Bite (rearing back with the mouth wide, then the snap forward with the paws
out), Hurt (a flinch, layered on top), Die (over onto its back, the legs curling up).

Gaits are written for the strides in `STRIDES` (metres per cycle at size 1), played by distance.
"""

from __future__ import annotations

import math

from mathutils import Vector

from blender.generators.quadruped_generator.clips import (
    Clip,
    Gait,
    Params,
    build,
    ease,
    mix,
    planted,
    stepping,
)
from blender.generators.quadruped_generator.pose import Pose, Rig, X, turn

STRIDES = {"Scurry": 0.22, "Run": 0.45}

SCURRY = Gait(
    STRIDES["Scurry"],
    0.38,
    {"fore.L": 0.0, "hind.R": 0.05, "fore.R": 0.5, "hind.L": 0.55},
    (0.016, 0.018),
    (0.45, 0.3),
)
#: A half-bound: the hind feet land almost together, the front ones one after the other.
RUN = Gait(
    STRIDES["Run"],
    0.18,
    {"hind.L": 0.0, "hind.R": 0.06, "fore.L": 0.48, "fore.R": 0.58},
    (0.028, 0.032),
    (0.6, 0.4),
    (0.01, -0.01),
)


def _sniff(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    breath = math.sin(5 * w)
    twitch = math.sin(28 * w) * (0.5 + 0.5 * math.sin(3 * w))
    p = {
        "z": 0.0008 * breath,
        "chest": 0.01 * breath,
        "neck": -0.12 + 0.12 * math.sin(w + 0.5),
        "neck_yaw": 0.35 * math.sin(w),
        "head": 0.1 * math.sin(2 * w) + 0.04 * twitch,
        "head_yaw": 0.2 * math.sin(2 * w + 1.0),
        "jaw": 0.05 * max(0.0, twitch),
        "ears": 0.15 * math.sin(4 * w),
        "tail_wave": 0.12,
        "tail_phase": w,
    }
    return build(rig, p, planted(rig))


def _scurry(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    p = {
        "z": -0.004 + 0.003 * math.cos(2 * w),
        "roll": 0.04 * math.sin(w),
        "pitch": 0.02 * math.sin(2 * w),
        "neck": -0.1 + 0.05 * math.cos(2 * w + 0.6),
        "head": 0.06,
        "head_yaw": 0.08 * math.sin(w),
        "tail": 0.05,
        "tail_wave": 0.22,
        "tail_phase": w,
    }
    return build(rig, p, stepping(rig, SCURRY, t))


def _run(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    flex = math.cos(w - 0.6)  # +1 gathered (back humped, feet under), -1 stretched out
    p = {
        "z": -0.006 + 0.012 * math.sin(w + 0.4),
        "pitch": 0.1 * math.sin(w - 0.4),
        "chest": -0.2 * flex,
        "hips": -0.25 * flex,
        "back": 0.12 * flex,
        "neck": -0.15 - 0.08 * flex,
        "head": 0.15 + 0.05 * flex,
        "ears": -0.3,
        "tail": 0.1,
        "tail_wave": 0.3,
        "tail_phase": w,
    }
    return build(rig, p, stepping(rig, RUN, t))


#: The rump stays down and the rest of it comes up off the front feet (turned at the loin; the pelvis turned back level).
REAR_POSE: Params = {
    "z": 0.008,
    "back": 0.85,
    "hips": -0.85,
    "chest": 0.1,
    "neck": -0.55,
    "head": -0.3,
    "ears": 0.3,
    "tail": 0.05,
}
#: Sat back on the hind feet: heels down (the hock to the ground), the feet a little forward.
REAR_SHIFT = {"hind.L": Vector((0.0, 0.03, 0.0)), "hind.R": Vector((0.0, 0.03, 0.0))}
REAR_SLOPE = {"hind.L": 0.3, "hind.R": 0.3}


def _hind_only(rig: Rig) -> dict:
    paws = planted(rig, REAR_SHIFT, REAR_SLOPE)
    return {k: v for k, v in paws.items() if k.startswith("hind")}


def _hands(pose: Pose, hang: float, reach: float = 0.0) -> None:
    """The front legs off the ground: hanging in front of the chest, or reaching out to grab."""
    for side in ("L", "R"):
        pose.add(f"upperarm.{side}", turn(X, -1.0 * hang + 0.9 * reach))
        pose.add(f"forearm.{side}", turn(X, 1.6 * hang - 0.5 * reach))
        pose.add(f"forepaw.{side}", turn(X, 0.9 * hang))


def _rear(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    twitch = math.sin(24 * w) * (0.5 + 0.5 * math.sin(2 * w))
    p = dict(REAR_POSE)
    p["z"] += 0.0015 * math.sin(4 * w)
    p["head"] += 0.05 * twitch + 0.08 * math.sin(w)
    p["neck_yaw"] = 0.25 * math.sin(w)
    p["jaw"] = 0.06 * max(0.0, twitch)
    p["tail_wave"] = 0.15
    p["tail_phase"] = w
    pose = build(rig, p, _hind_only(rig))
    _hands(pose, 1.0)
    return pose


# The bite: 0.3 s rearing back (the game's wind-up), the snap, a moment's hold.
BACK_POSE: Params = {
    "back": 0.45,
    "hips": -0.45,
    "y": -0.02,
    "chest": -0.1,
    "neck": -0.1,
    "head": 0.25,
    "jaw": 1.0,
    "ears": -0.4,
    "tail": 0.3,
}
SNAP_POSE: Params = {
    "pitch": -0.12,
    "y": 0.04,
    "z": -0.006,
    "back": -0.1,
    "hips": 0.1,
    "chest": 0.15,
    "neck": 0.25,
    "head": -0.1,
    "jaw": 0.0,
    "ears": -0.5,
    "tail": -0.1,
}
WINDUP = 0.45  # of the clip


def _bite(rig: Rig, t: float) -> Pose:
    """The front feet come off the ground for the whole bite: up and hanging as it rears, flung
    forward in the snap, back down as it settles."""
    if t < WINDUP:
        k = ease(t / WINDUP)
        pose = build(rig, mix({}, BACK_POSE, k), _hind_only(rig))
        _hands(pose, 0.6 * k)
        return pose
    s = (t - WINDUP) / (1.0 - WINDUP)
    k = ease(s / 0.35)
    settle = ease((s - 0.6) / 0.4)
    p = mix(mix(BACK_POSE, SNAP_POSE, k), {}, settle)
    # The jaw: wide through the drive, snapping shut at the end of it.
    p["jaw"] = 1.0 * (1.0 - ease((s - 0.25) / 0.15))
    p["head_yaw"] = 0.15 * math.sin(s * 2 * math.pi * 2.5) * (s > 0.4) * (1.0 - s)
    reach = math.sin(math.pi * min(1.0, s / 0.7))
    pose = build(rig, p, _hind_only(rig))
    _hands(pose, 0.6 * (1.0 - k), reach * (1.0 - settle))
    return pose


def _hurt(rig: Rig, t: float) -> Pose:
    k = math.sin(math.pi * min(1.0, t / 0.9)) if t > 0 else 0.0
    k = k * (1.0 - 0.3 * t)
    p = {
        "bend": 0.25 * k,
        "twist": 0.12 * k,
        "pitch": 0.12 * k,
        "z": 0.008 * k,
        "neck": 0.35 * k,
        "head": -0.15 * k,
        "head_yaw": -0.25 * k,
        "jaw": 0.5 * k,
        "ears": -0.6 * k,
        "tail": 0.4 * k,
    }
    return build(rig, p, planted(rig))


def _die(rig: Rig, t: float) -> Pose:
    jerk = math.sin(math.pi * min(1.0, t / 0.25))
    over = ease((t - 0.1) / 0.5)
    curl = ease((t - 0.35) / 0.5)
    p = {
        "z": 0.04 * jerk * (1 - over) + 0.205 * over,
        "pitch": 0.35 * jerk * (1 - over),
        "roll": math.pi * over,
        "x": 0.0,
        "neck": 0.3 * curl,
        "head": 0.4 * curl,
        "jaw": 0.5 * jerk + 0.3 * curl,
        "ears": -0.3,
        "hips": -0.2 * curl,
        "chest": -0.15 * curl,
        "tail": -0.6 * over,
        "tail_curl": 0.15 * curl,
    }
    pose = build(rig, p, None)
    # The legs, up in the air, curling in.
    for side in ("L", "R"):
        pose.add(f"upperarm.{side}", turn(X, -0.6 * curl))
        pose.add(f"forearm.{side}", turn(X, 1.4 * curl))
        pose.add(f"forepaw.{side}", turn(X, 0.9 * curl))
        pose.add(f"thigh.{side}", turn(X, 0.9 * curl))
        pose.add(f"shin.{side}", turn(X, -1.2 * curl))
        pose.add(f"hindpaw.{side}", turn(X, 0.8 * curl))
    return pose


CLIPS = [
    Clip("Sniff", 60, True, _sniff),
    Clip("Scurry", 12, True, _scurry),
    Clip("Run", 10, True, _run),
    Clip("Rear", 60, True, _rear),
    Clip("Bite", 20, False, _bite),
    Clip("Hurt", 8, False, _hurt),
    Clip("Die", 24, False, _die),
]
