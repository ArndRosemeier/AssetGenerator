"""The dog's clips: everything it does in the game, as baked actions on its skeleton.

Loops: Idle, Trot, Gallop, Stalk (the low circling walk), Lie (lying up at the den), Crouch (the tell
before a lunge, quivering), Graze (head down at a food spot, chewing or lapping, now and then a look
up). Once: Lunge, Bite (the snap), Hurt (a flinch, made to be layered on top of whatever it is doing),
Die.

Gaits are written for the stride lengths in `STRIDES` (metres per cycle at size 1): the game plays
them by distance travelled, so the paws stay put on the ground at any speed.

Each pose is a handful of named numbers (how low the body is, how the head is carried, the paws'
places), so a clip can ease from one pose to another by mixing the numbers.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import bpy
from mathutils import Vector

from blender.backend import compat
from blender.generators.quadruped_generator.pose import Paw, Pose, Rig, X, Y, Z, turn

FPS = 30
STRIDES = {"Trot": 1.0, "Gallop": 1.9, "Stalk": 0.55}

Params = dict[str, float]

#: The resting values of every pose number.
BASE: Params = {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "pitch": 0.0,
    "roll": 0.0,
    "yaw": 0.0,
    "back": 0.0,
    "chest": 0.0,
    "hips": 0.0,
    "bend": 0.0,
    "twist": 0.0,
    "neck": 0.0,
    "neck_yaw": 0.0,
    "head": 0.0,
    "head_yaw": 0.0,
    "head_roll": 0.0,
    "jaw": 0.0,
    "ears": 0.0,
    "ears_out": 0.0,
    "ear_flick": 0.0,
    "tail": 0.0,
    "tail_yaw": 0.0,
    "tail_curl": 0.0,
    "tail_wave": 0.0,
    "tail_phase": 0.0,
}


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a: Params, b: Params, k: float) -> Params:
    keys = set(a) | set(b)
    return {
        n: a.get(n, BASE.get(n, 0.0)) + (b.get(n, BASE.get(n, 0.0)) - a.get(n, BASE.get(n, 0.0))) * k
        for n in keys
    }


def build(rig: Rig, p: Params, paws: dict[str, Paw] | None) -> Pose:
    v = dict(BASE)
    v.update(p)
    pose = Pose()
    pose.lift = Vector((v["x"], v["y"], v["z"]))
    pose.roll = turn(Z, v["yaw"]) @ turn(Y, v["roll"]) @ turn(X, v["pitch"])
    pose.add("spine1", turn(Z, v["bend"]) @ turn(Y, v["twist"]) @ turn(X, v["back"]))
    pose.add("spine2", turn(Z, v["bend"]) @ turn(X, v["chest"]))
    pose.add("pelvis", turn(Z, -v["bend"] * 0.5) @ turn(X, v["hips"]))
    pose.add("neck", turn(Z, v["neck_yaw"]) @ turn(X, v["neck"]))
    pose.add("head", turn(Y, v["head_roll"]) @ turn(Z, v["head_yaw"]) @ turn(X, v["head"]))
    pose.add("jaw", turn(X, -0.6 * v["jaw"]))
    for side, s in (("L", 1.0), ("R", -1.0)):
        flick = v["ear_flick"] if side == "L" else 0.0
        pose.add(f"ear.{side}", turn(Y, s * v["ears_out"]) @ turn(X, v["ears"] + flick))
    # The tail's turns are spread over however many bones it has (written for four), and a wave runs down it.
    n = len(rig.tails)
    f = 4.0 / max(n, 1)
    for i, name in enumerate(rig.tails, 1):
        k = 1.0 if i == 1 else 0.6 * f
        wave = v["tail_wave"] * math.sin(v["tail_phase"] - 0.8 * (i - 1))
        pose.add(
            name,
            turn(Z, v["tail_yaw"] * (0.6 + 0.25 * i) * f + wave)
            @ turn(X, (v["tail"] * k) + v["tail_curl"] * (i - 1) * 0.35 * f * f),
        )
    if paws is not None:
        pose.paws = paws
    return pose


# --- Paws ---------------------------------------------------------------------------------------


def planted(
    rig: Rig, shift: dict[str, Vector] | None = None, slope: dict[str, float] | None = None
) -> dict[str, Paw]:
    out = {}
    for k in rig.leg_keys:
        p = rig.neutral_paw(k)
        if shift and k in shift:
            p.ball = p.ball + shift[k]
        if slope and k in slope:
            p.slope += slope[k]
        out[k] = p
    return out


@dataclass(frozen=True)
class Gait:
    stride: float
    duty: float
    offsets: dict[str, float]
    lift: tuple[float, float]  # fore, hind
    tuck: tuple[float, float]  # extra slope mid-swing: fore, hind
    centre: tuple[float, float] = (0.0, 0.0)  # where the sweep is centred, along the body: fore, hind


def stepping(rig: Rig, g: Gait, t: float) -> dict[str, Paw]:
    """Paws through one cycle of a gait at phase `t` (0..1): back along the ground in stance, up and forward in swing."""
    out = {}
    sweep = g.stride * g.duty
    for k in rig.leg_keys:
        fore = k.startswith("fore")
        p = rig.neutral_paw(k)
        u = (t + g.offsets[k]) % 1.0
        centre = g.centre[0] if fore else g.centre[1]
        if u < g.duty:
            s = u / g.duty
            y = sweep * (0.5 - s)
            h = 0.0
            slope = p.slope + (0.15 * (s - 0.5) if fore else 0.1 * (s - 0.5))
            curl = -0.25 * max(0.0, s - 0.7) / 0.3
        else:
            s = (u - g.duty) / (1.0 - g.duty)
            e = ease(s)
            y = sweep * (e - 0.5)
            arc = math.sin(math.pi * s)
            h = (g.lift[0] if fore else g.lift[1]) * arc
            slope = p.slope + (g.tuck[0] if fore else g.tuck[1]) * math.sin(math.pi * min(1.0, s * 1.3))
            curl = 0.7 * arc
        p.ball = p.ball + Vector((0.0, y + centre, h))
        p.slope = slope
        p.curl = curl
        out[k] = p
    return out


TROT = Gait(
    STRIDES["Trot"],
    0.42,
    {"fore.L": 0.0, "hind.R": 0.0, "fore.R": 0.5, "hind.L": 0.5},
    (0.075, 0.065),
    (1.2, 0.45),
)
GALLOP = Gait(
    STRIDES["Gallop"],
    0.27,
    {"hind.L": 0.0, "hind.R": 0.09, "fore.R": 0.42, "fore.L": 0.52},
    (0.12, 0.1),
    (1.5, 0.6),
    (0.0, 0.04),
)
STALK = Gait(
    STRIDES["Stalk"],
    0.68,
    {"hind.L": 0.0, "fore.L": 0.25, "hind.R": 0.5, "fore.R": 0.75},
    (0.06, 0.05),
    (1.0, 0.4),
)


# --- Clips --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Clip:
    name: str
    frames: int
    loop: bool
    at: Callable[[Rig, float], Pose]


def _idle(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    breath = math.sin(3 * w)
    flick = max(0.0, math.sin(math.pi * (t - 0.6) / 0.06)) if 0.6 <= t < 0.66 else 0.0
    p = {
        "z": 0.003 * breath,
        "chest": 0.012 * breath,
        "neck": -0.04 + 0.04 * math.sin(w + 1.0),
        "neck_yaw": 0.28 * math.sin(w),
        "head_yaw": 0.18 * math.sin(w + 0.6),
        "head": 0.05 * math.sin(2 * w),
        "ear_flick": 0.6 * flick,
        "tail": 0.05,
        "tail_yaw": 0.12 * math.sin(2 * w),
    }
    return build(rig, p, planted(rig))


def _trot(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    p = {
        "z": -0.012 + 0.012 * math.cos(2 * w),
        "roll": 0.03 * math.sin(w),
        "pitch": 0.015 * math.sin(2 * w),
        "neck": -0.08 + 0.03 * math.cos(2 * w + 0.6),
        "head": 0.04,
        "ears": -0.05,
        "tail": -0.15,
        "tail_yaw": 0.12 * math.sin(w),
    }
    return build(rig, p, stepping(rig, TROT, t))


def _gallop(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    flex = math.cos(w - 0.6)  # +1 gathered (back arched, legs under), -1 stretched out
    p = {
        "z": -0.02 + 0.035 * math.sin(w + 0.4),
        "pitch": 0.07 * math.sin(w - 0.4),
        "chest": -0.12 * flex,
        "hips": -0.16 * flex,
        "back": 0.05 * flex,
        "neck": -0.2 - 0.08 * flex,
        "head": 0.12 + 0.06 * flex,
        "jaw": 0.12,
        "ears": 0.7,
        "ears_out": 0.1,
        "tail": -0.75,
        "tail_curl": -0.15 * flex,
        "tail_yaw": 0.05 * math.sin(w),
    }
    return build(rig, p, stepping(rig, GALLOP, t))


STALK_POSE: Params = {
    "z": -0.075,
    "chest": -0.05,
    "neck": -0.5,
    "head": 0.32,
    "jaw": 0.14,
    "ears": 0.55,
    "ears_out": 0.15,
    "tail": 0.35,
    "tail_curl": 0.1,
}


def _stalk(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    p = dict(STALK_POSE)
    p["z"] += 0.006 * math.cos(2 * w)
    p["roll"] = 0.025 * math.sin(w)
    p["neck_yaw"] = 0.05 * math.sin(w)
    p["jaw"] += 0.03 * math.sin(9 * w)
    return build(rig, p, stepping(rig, STALK, t))


LIE_POSE: Params = {
    "z": -0.3,
    "chest": 0.05,
    "hips": -0.06,
    "neck": -0.42,
    "head": 0.36,
    "ears": 0.25,
    "tail": 0.55,
    "tail_curl": 0.45,
    "tail_yaw": 0.5,
}


def lying_paws(rig: Rig) -> dict[str, Paw]:
    out = {}
    for k in rig.leg_keys:
        p = rig.neutral_paw(k)
        s = 1.0 if k.endswith("L") else -1.0
        if k.startswith("fore"):
            p.ball = Vector((0.075 * s, 0.4, 0.022))
            p.slope = math.pi / 2
        else:
            p.ball = Vector((0.12 * s, -0.12, 0.022))
            p.slope = math.pi / 2
        out[k] = p
    return out


def _lie(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    breath = math.sin(4 * w)
    flick = max(0.0, math.sin(math.pi * (t - 0.3) / 0.05)) if 0.3 <= t < 0.35 else 0.0
    p = dict(LIE_POSE)
    p["chest"] += 0.015 * breath
    p["z"] += 0.003 * breath
    p["ear_flick"] = 0.7 * flick
    p["head_yaw"] = 0.08 * math.sin(w)
    p["tail_yaw"] += 0.06 * math.sin(2 * w)
    return build(rig, p, lying_paws(rig))


CROUCH_POSE: Params = {
    "z": -0.1,
    "pitch": 0.04,
    "chest": -0.06,
    "hips": 0.18,
    "back": -0.06,
    "neck": -0.42,
    "head": 0.3,
    "jaw": 0.35,
    "ears": 0.75,
    "ears_out": 0.15,
    "tail": 0.25,
}
CROUCH_SHIFT = {
    "hind.L": Vector((0.0, 0.08, 0.0)),
    "hind.R": Vector((0.0, 0.08, 0.0)),
    "fore.L": Vector((0.0, -0.03, 0.0)),
    "fore.R": Vector((0.0, -0.03, 0.0)),
}
CROUCH_SLOPE = {"hind.L": 0.55, "hind.R": 0.55, "fore.L": 0.25, "fore.R": 0.25}


def _crouch(rig: Rig, t: float) -> Pose:
    w = 2 * math.pi * t
    p = dict(CROUCH_POSE)
    p["z"] += 0.003 * math.sin(6 * w)
    p["jaw"] += 0.06 * math.sin(4 * w)
    p["head_roll"] = 0.02 * math.sin(5 * w)
    return build(rig, p, planted(rig, CROUCH_SHIFT, CROUCH_SLOPE))


#: Head down at the food: the forelegs give at the elbow and the chest drops so the short neck reaches,
#: the nose just off the floor in front of the forepaws (which stand a little forward, under the head).
GRAZE_POSE: Params = {
    "z": -0.05,
    "pitch": -0.12,
    "chest": -0.33,
    "neck": -1.22,
    "head": 0.42,
    "ears": 0.15,
    "ears_out": 0.12,
    "tail": 0.3,
}
#: The look up from the food: head raised to the withers, ears up, still bent over the spot.
GRAZE_UP: Params = {
    "z": -0.025,
    "pitch": -0.05,
    "chest": -0.15,
    "neck": -0.4,
    "head": 0.18,
    "ears": 0.6,
    "ears_out": 0.05,
    "tail": 0.2,
}
GRAZE_SHIFT = {"fore.L": Vector((0.0, 0.06, 0.0)), "fore.R": Vector((0.0, 0.06, 0.0))}


def _graze(rig: Rig, t: float) -> Pose:
    """Five seconds at the food: chewing and lapping with the head down, an ear flick, and one look up
    and round (0.6..0.8 of the loop) before the head goes down again. The paws stay where they are."""
    w = 2 * math.pi * t
    up = ease((t - 0.58) / 0.07) * (1.0 - ease((t - 0.78) / 0.08))
    breath = math.sin(5 * w)
    chew = 0.5 + 0.5 * math.sin(16 * w)
    flick = max(0.0, math.sin(math.pi * (t - 0.3) / 0.05)) if 0.3 <= t < 0.35 else 0.0
    p = mix(GRAZE_POSE, GRAZE_UP, up)
    p["z"] += 0.003 * breath
    p["chest"] += 0.012 * breath
    # The chew: the jaw working and the head nodding up off the food with it (never down into the floor).
    p["jaw"] = 0.08 + (0.22 - 0.1 * up) * chew
    p["head"] += 0.05 * (1.0 - up) * (0.5 + 0.5 * math.sin(16 * w + 0.9))
    p["neck_yaw"] = 0.06 * math.sin(w) * (1.0 - up) + 0.22 * up * math.sin(2 * math.pi * (t - 0.58) / 0.28)
    p["head_yaw"] = 0.04 * math.sin(3 * w) * (1.0 - up)
    p["ear_flick"] = 0.7 * flick
    p["tail_yaw"] = 0.1 * math.sin(2 * w)
    return build(rig, p, planted(rig, GRAZE_SHIFT))


LUNGE_POSE: Params = {
    "z": 0.08,
    "pitch": -0.05,
    "chest": 0.1,
    "hips": -0.12,
    "back": 0.04,
    "neck": 0.05,
    "head": 0.08,
    "jaw": 0.8,
    "ears": 0.9,
    "ears_out": 0.1,
    "tail": -0.55,
}


def _lunge_paws(rig: Rig) -> dict[str, Paw]:
    out = {}
    for k in rig.leg_keys:
        p = rig.neutral_paw(k)
        if k.startswith("fore"):
            p.ball = p.ball + Vector((0.0, 0.26, 0.2))
            p.slope = 0.9
            p.curl = 0.4
        else:
            p.ball = p.ball + Vector((0.0, -0.3, 0.02))
            p.slope = -0.2
            p.curl = -0.3
        out[k] = p
    return out


def _blend_paws(a: dict[str, Paw], b: dict[str, Paw], k: float) -> dict[str, Paw]:
    return {
        n: Paw(
            a[n].ball.lerp(b[n].ball, k),
            a[n].slope + (b[n].slope - a[n].slope) * k,
            a[n].curl + (b[n].curl - a[n].curl) * k,
        )
        for n in a
    }


def _lunge(rig: Rig, t: float) -> Pose:
    k = ease(t / 0.4)
    p = mix(CROUCH_POSE, LUNGE_POSE, k)
    paws = _blend_paws(planted(rig, CROUCH_SHIFT, CROUCH_SLOPE), _lunge_paws(rig), k)
    return build(rig, p, paws)


def _bite(rig: Rig, t: float) -> Pose:
    snap = ease(t / 0.25)
    shake = math.sin(t * 2 * math.pi * 3) * (1 - t) * (t > 0.2)
    p = {
        "z": -0.02,
        "chest": -0.04,
        "neck": -0.18 - 0.12 * snap + 0.08 * ease((t - 0.4) / 0.6),
        "head": 0.12,
        "jaw": 0.8 * (1 - snap),
        "head_yaw": 0.25 * shake,
        "head_roll": 0.2 * shake,
        "ears": 0.8,
        "tail": -0.2,
    }
    return build(rig, p, planted(rig))


def _hurt(rig: Rig, t: float) -> Pose:
    k = math.sin(math.pi * min(1.0, t / 0.9)) if t > 0 else 0.0
    k = k * (1.0 - 0.3 * t)
    p = {
        "bend": 0.2 * k,
        "twist": 0.1 * k,
        "z": -0.03 * k,
        "neck": 0.25 * k,
        "head": -0.1 * k,
        "head_yaw": -0.2 * k,
        "jaw": 0.35 * k,
        "ears": 0.9 * k,
        "tail": 0.4 * k,
    }
    return build(rig, p, planted(rig))


def _die(rig: Rig, t: float) -> Pose:
    sag = ease(t / 0.35)
    over = ease((t - 0.25) / 0.45)
    stiff = ease((t - 0.6) / 0.4)
    p = {
        "z": -0.22 * sag * (1 - over) + 0.11 * over,
        "x": -0.42 * over,
        "roll": (math.pi / 2) * over,
        "neck": -0.35 * sag + 0.2 * over,
        "head": -0.1 * sag + 0.25 * over,
        "jaw": 0.25 * stiff,
        "ears": 0.3,
        "tail": 0.3 * sag - 0.3 * over,
        "chest": 0.05 * stiff,
        "hips": -0.05 * stiff,
    }
    pose = build(rig, p, None)
    # The legs: folding as it drops, then out stiff.
    for side in ("L", "R"):
        fold = sag * (1 - stiff)
        pose.add(f"upperarm.{side}", turn(X, 0.5 * fold - 0.5 * stiff))
        pose.add(f"forearm.{side}", turn(X, -0.9 * fold + 0.2 * stiff))
        pose.add(f"forepaw.{side}", turn(X, 0.6 * fold))
        pose.add(f"thigh.{side}", turn(X, 0.6 * fold + 0.5 * stiff))
        pose.add(f"shin.{side}", turn(X, -1.0 * fold - 0.2 * stiff))
        pose.add(f"hindpaw.{side}", turn(X, 0.8 * fold))
    return pose


CLIPS = [
    Clip("Idle", 90, True, _idle),
    Clip("Trot", 20, True, _trot),
    Clip("Gallop", 16, True, _gallop),
    Clip("Stalk", 36, True, _stalk),
    Clip("Lie", 120, True, _lie),
    Clip("Crouch", 24, True, _crouch),
    Clip("Graze", 150, True, _graze),
    Clip("Lunge", 14, False, _lunge),
    Clip("Bite", 10, False, _bite),
    Clip("Hurt", 10, False, _hurt),
    Clip("Die", 36, False, _die),
]


def bake_clips(armature: bpy.types.Object, rig: Rig, clips: list[Clip] = CLIPS) -> None:
    """Key every clip as its own action, each on its own NLA track (one glTF animation per track)."""
    scene = bpy.context.scene
    scene.render.fps = FPS
    if armature.animation_data is None:
        armature.animation_data_create()
    for clip in clips:
        action = bpy.data.actions.new(clip.name)
        armature.animation_data.action = action
        rig._last.clear()
        # Loops key the first frame again at the end, so they close without a seam.
        count = clip.frames + 1 if clip.loop else clip.frames
        for f in range(count):
            t = (f % clip.frames) / clip.frames if clip.loop else f / max(1, clip.frames - 1)
            rig.key(clip.at(rig, t), f + 1)
        for fc in compat.action_fcurves(action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        armature.animation_data.action = None
        track = armature.animation_data.nla_tracks.new()
        track.name = clip.name
        strip = track.strips.new(clip.name, 1, action)
        strip.name = clip.name
