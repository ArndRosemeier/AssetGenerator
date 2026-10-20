"""Clips as JSON: what a body does, said in a few motions, sampled into frames.

A clip is a list of motions, applied in order and added up:

    {"turn": {"bone": "head", "pitch": 8, "yaw": 0, "roll": 0,
              "wave": "sine", "cycles": 1, "phase": 0.0}}
        a bone swings: degrees times the wave at (cycles * t + phase), t running 0..1 over the
        clip. Waves: "sine", "bounce" (|sine|: up twice per cycle, never down), "constant"
        (held all clip). "bone": "ear.*" turns both ears, the right one mirrored.

    {"move": {"x": 0, "y": 0, "z": 0.01, "wave": "bounce", "cycles": 2, "phase": 0.0}}
        the whole body moves (metres): a bob, a sway, a hop.

    {"keys": {"ease": "smooth", "at": [
        {"t": 0.0, "turns": {"head": {"pitch": 0}}, "move": [0, 0, 0]},
        {"t": 0.4, "turns": {"head": {"pitch": 25}, "jaw": {"pitch": -30}}},
        {"t": 1.0, "turns": {"head": {"pitch": 0}}}]}}
        poses at times, eased between ("smooth" or "linear"). A turn or move a key leaves out is
        the rest pose there. A loop's keys wrap from the last back to the first.

    {"gait": {"legs": {"hind.L": 0.0, "fore.L": 0.5}, "stride": 0.12, "lift": 0.04,
              "duty": 0.6, "cycles": 1}}
        legs step in place (the game moves the body): each foot is planted for `duty` of its
        cycle, sliding back `stride` metres as the body would pass over it, then lifts `lift`
        metres and swings forward. Phases (0..1) set the rhythm: a walk staggers the four feet,
        a trot pairs diagonals, a hop moves them together. A '.L' leg's '.R' twin steps half a
        cycle later unless it is listed itself. The legs are solved by inverse kinematics: the
        feet stay on the ground, the knees bend the way they were modelled.
        `"per_leg": {"leg.R": {"lift": 0.01, "duty": 0.45}}` gives one leg its own lift and
        duty (a limp: the bad leg drags and bears weight briefly); its stride follows from its
        duty so its planted foot keeps pace with the body and nothing skates.

    {"spin": {"bone": "drum", "turns": 2}}
        a bone turns steadily about its own axis (head to tail), `turns` times over the clip:
        wheels, drums, cranks, propellers. A loop needs whole turns.

    {"wave": {"bones": ["flag1", "flag2", "flag3"], "yaw": 12, "cycles": 2, "lag": 0.12,
              "grow": 1.3}}
        a chain of bones (root first) swinging alike, each `lag` of a cycle after the one
        before: a ripple running along a flag, a tail, a rope; `grow` scales the swing from
        bone to bone (the free end swings most).

A loop must contain whole cycles (it ends where it began); `cycles` defaults to 1.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

from assetkit.rig import Clip, Leg, Pose, Skeleton, Vec, add, q_axis, solve, sub, turn, twin_name, unit


class MotionError(ValueError):
    """A clip that does not parse; the message names the path to the problem."""


_WAVES: dict[str, Callable[[float], float]] = {
    "sine": lambda x: math.sin(2 * math.pi * x),
    "bounce": lambda x: abs(math.sin(math.pi * x)),
    "constant": lambda x: 1.0,
}


def build_clip(
    name: str,
    raw: object,
    skeleton: Skeleton,
    legs: Mapping[str, Leg],
    fps: int,
    path: str,
) -> Clip:
    spec = _object(raw, path)
    _only(spec, ("seconds", "loop", "motions"), path)
    seconds = _number(spec, "seconds", path)
    if seconds <= 0:
        raise MotionError(f"{path}.seconds: must be positive")
    loop = spec.get("loop", True)
    if not isinstance(loop, bool):
        raise MotionError(f"{path}.loop: expected true or false")
    motions_raw = spec.get("motions")
    if not isinstance(motions_raw, list) or not motions_raw:
        raise MotionError(f"{path}.motions: expected a non-empty list")
    motions = [_motion(m, skeleton, legs, loop, f"{path}.motions[{i}]") for i, m in enumerate(motions_raw)]
    # A loop of n frames lasts n / fps (the backend closes it with frame 0 again); a clip played
    # once spans its first to its last frame, so it needs one frame more.
    steps = round(seconds * fps)
    if abs(steps - seconds * fps) > 1e-6:
        raise MotionError(
            f"{path}.seconds: {seconds} s is not a whole number of frames at {fps} fps; "
            f"give the rig an `fps` that fits ({_fitting_rates([seconds])}) or round the length"
        )
    count = max(2, steps if loop else steps + 1)
    by_upper = {leg.upper: leg for leg in legs.values()}
    frames = []
    for f in range(count):
        t = f / count if loop else f / (count - 1)
        pose = Pose()
        for apply in motions:
            apply(pose, t)
        frames.append(solve(skeleton, pose, by_upper))
    return Clip(name=name, fps=fps, loop=loop, frames=tuple(frames))


def build_clips(
    spec: Mapping[str, object], skeleton: Skeleton, legs: Mapping[str, Leg], path: str
) -> list[Clip]:
    """A rig's `clips` (and `fps`): every clip lasting exactly its seconds. Without an `fps`,
    the first common rate (24, 30, 25, 60, ...) at which every clip is whole frames."""
    clips_raw = _object(spec.get("clips", {}), f"{path}.clips")
    fps = spec.get("fps")
    if fps is None:
        # Without an fps, the first common rate at which every clip lasts exactly its seconds.
        lengths = [
            float(c["seconds"])
            for c in clips_raw.values()
            if isinstance(c, dict) and isinstance(c.get("seconds"), int | float) and c["seconds"] > 0
        ]
        fps = pick_fps(lengths) if lengths else 24
        if fps is None:
            raise MotionError(
                f"{path}.clips: no common frame rate ({', '.join(map(str, RATES))}) makes every clip "
                f"length {sorted(set(lengths))} s a whole number of frames; set `fps` or round the lengths"
            )
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
        raise MotionError(f"{path}.fps: expected a whole number 1..120")
    clips = []
    for name, value in clips_raw.items():
        try:
            clips.append(build_clip(name, value, skeleton, legs, fps, f"{path}.clips.{name}"))
        except MotionError:
            raise
        except ValueError as exc:
            raise MotionError(f"{path}.clips.{name}: {exc}") from exc
    return clips


RATES = (24, 30, 25, 60, 48, 50, 120)


def _fitting_rates(lengths: Sequence[float]) -> str:
    rates = [r for r in RATES if all(abs(round(s * r) - s * r) < 1e-6 for s in lengths)]
    return ", ".join(str(r) for r in rates) if rates else "none of " + ", ".join(map(str, RATES))


def pick_fps(lengths: Sequence[float]) -> int | None:
    """The first common frame rate (24, 30, 25, 60, ...) at which every length in seconds is a
    whole number of frames, so every clip lasts exactly what the spec says; None if none does."""
    for rate in RATES:
        if all(abs(round(s * rate) - s * rate) < 1e-6 for s in lengths):
            return rate
    return None


Apply = Callable[[Pose, float], None]


def _motion(raw: object, skeleton: Skeleton, legs: Mapping[str, Leg], loop: bool, path: str) -> Apply:
    node = _object(raw, path)
    if len(node) != 1:
        raise MotionError(f"{path}: a motion is an object with one key: turn, move, keys, gait, spin or wave")
    ((kind, body),) = node.items()
    here = f"{path}.{kind}"
    fields = _object(body, here)
    if kind == "turn":
        return _turn(fields, skeleton, loop, here)
    if kind == "move":
        return _move(fields, loop, here)
    if kind == "keys":
        return _keys(fields, skeleton, loop, here)
    if kind == "gait":
        return _gait(fields, skeleton, legs, loop, here)
    if kind == "spin":
        return _spin(fields, skeleton, loop, here)
    if kind == "wave":
        return _wave_chain(fields, skeleton, loop, here)
    raise MotionError(f"{path}: unknown motion '{kind}'; motions are turn, move, keys, gait, spin, wave")


def _spin(fields: dict, skeleton: Skeleton, loop: bool, path: str) -> Apply:
    """A bone turning steadily about its own axis (head to tail): a wheel, a drum, a crank, a
    propeller. `turns` whole turns over the clip (negative: the other way)."""
    _only(fields, ("bone", "turns"), path)
    bones = _bones(fields.get("bone"), skeleton, path)
    turns = _number(fields, "turns", path)
    if loop and abs(turns - round(turns)) > 1e-9:
        raise MotionError(f"{path}.turns: a loop needs whole turns, got {turns}")
    axes = {bone: unit(sub(skeleton[bone].tail, skeleton[bone].head)) for bone, _ in bones}

    def apply(pose: Pose, t: float) -> None:
        for bone, side in bones:
            pose.add_turn(bone, q_axis(axes[bone], math.tau * turns * t * side))

    return apply


def _wave_chain(fields: dict, skeleton: Skeleton, loop: bool, path: str) -> Apply:
    """A chain of bones turning the same way, each a little later than the one before: a ripple
    running along a flag, a tail, a tentacle, a rope. `lag` is the delay per bone (share of a
    cycle), `grow` multiplies the swing from bone to bone (a flag's free end swings most)."""
    _only(fields, ("bones", "pitch", "yaw", "roll", "cycles", "lag", "grow"), path)
    names = fields.get("bones")
    if not isinstance(names, list) or not names:
        raise MotionError(f"{path}.bones: expected a list of bone names, root first")
    for name in names:
        _bones(name, skeleton, f"{path}.bones")
    pitch, yaw, roll = (_number(fields, k, path, 0.0) for k in ("pitch", "yaw", "roll"))
    cycles = _number(fields, "cycles", path, 1.0)
    if loop and abs(cycles - round(cycles)) > 1e-9:
        raise MotionError(f"{path}.cycles: a loop needs whole cycles, got {cycles}")
    lag = _number(fields, "lag", path, 0.12)
    grow = _number(fields, "grow", path, 1.0)

    def apply(pose: Pose, t: float) -> None:
        for i, name in enumerate(names):
            s = math.sin(2 * math.pi * (cycles * t - i * lag)) * grow**i
            pose.add_turn(name, turn(pitch * s, yaw * s, roll * s))

    return apply


def _wave(fields: dict, loop: bool, path: str) -> Callable[[float], float]:
    wave_name = fields.get("wave", "sine")
    if wave_name not in _WAVES:
        raise MotionError(f"{path}.wave: '{wave_name}' is not one of {sorted(_WAVES)}")
    wave = _WAVES[wave_name]
    cycles = _number(fields, "cycles", path, 1.0)
    phase = _number(fields, "phase", path, 0.0)
    if loop and wave_name != "constant" and abs(cycles - round(cycles)) > 1e-9:
        raise MotionError(f"{path}.cycles: a loop needs whole cycles, got {cycles}")
    return lambda t: wave(cycles * t + phase)


def _bones(name: object, skeleton: Skeleton, path: str) -> list[tuple[str, float]]:
    """The bones a motion names, with the sign its yaw and roll take on each ('ear.*' -> both)."""
    if not isinstance(name, str):
        raise MotionError(f"{path}.bone: expected a bone name")
    if name.endswith(".*"):
        pair = [(name[:-2] + ".L", 1.0), (name[:-2] + ".R", -1.0)]
        for bone, _ in pair:
            if bone not in skeleton:
                raise MotionError(f"{path}.bone: no bone '{bone}'; bones are {list(skeleton.names)}")
        return pair
    if name not in skeleton:
        raise MotionError(f"{path}.bone: no bone '{name}'; bones are {list(skeleton.names)}")
    return [(name, 1.0)]


def _turn(fields: dict, skeleton: Skeleton, loop: bool, path: str) -> Apply:
    _only(fields, ("bone", "pitch", "yaw", "roll", "wave", "cycles", "phase"), path)
    bones = _bones(fields.get("bone"), skeleton, path)
    pitch, yaw, roll = (_number(fields, k, path, 0.0) for k in ("pitch", "yaw", "roll"))
    wave = _wave(fields, loop, path)

    def apply(pose: Pose, t: float) -> None:
        s = wave(t)
        for bone, side in bones:
            pose.add_turn(bone, turn(pitch * s, yaw * s * side, roll * s * side))

    return apply


def _move(fields: dict, loop: bool, path: str) -> Apply:
    _only(fields, ("x", "y", "z", "wave", "cycles", "phase"), path)
    offset = tuple(_number(fields, k, path, 0.0) for k in ("x", "y", "z"))
    wave = _wave(fields, loop, path)

    def apply(pose: Pose, t: float) -> None:
        s = wave(t)
        pose.lift = add(pose.lift, (offset[0] * s, offset[1] * s, offset[2] * s))

    return apply


def _keys(fields: dict, skeleton: Skeleton, loop: bool, path: str) -> Apply:
    _only(fields, ("ease", "at"), path)
    ease_name = fields.get("ease", "smooth")
    if ease_name not in ("smooth", "linear"):
        raise MotionError(f"{path}.ease: expected 'smooth' or 'linear'")
    raw_keys = fields.get("at")
    if not isinstance(raw_keys, list) or len(raw_keys) < 2:
        raise MotionError(f"{path}.at: expected a list of two or more keys")
    keys: list[tuple[float, dict[tuple[str, str], float], Vec]] = []
    for i, raw in enumerate(raw_keys):
        here = f"{path}.at[{i}]"
        key = _object(raw, here)
        _only(key, ("t", "turns", "move"), here)
        t = _number(key, "t", here)
        if not 0.0 <= t <= 1.0:
            raise MotionError(f"{here}.t: expected 0..1, got {t}")
        if keys and t <= keys[-1][0]:
            raise MotionError(f"{here}.t: keys must run forward in time")
        channels: dict[tuple[str, str], float] = {}
        for bone_name, angles in _object(key.get("turns", {}), f"{here}.turns").items():
            angle_fields = _object(angles, f"{here}.turns.{bone_name}")
            _only(angle_fields, ("pitch", "yaw", "roll"), f"{here}.turns.{bone_name}")
            for bone, side in _bones(bone_name, skeleton, f"{here}.turns.{bone_name}"):
                for axis in ("pitch", "yaw", "roll"):
                    value = _number(angle_fields, axis, f"{here}.turns.{bone_name}", 0.0)
                    channels[(bone, axis)] = value * (side if axis != "pitch" else 1.0)
        move = _vec(key, "move", here) if "move" in key else (0.0, 0.0, 0.0)
        keys.append((t, channels, move))
    if loop:
        first = keys[0]
        if keys[-1][0] < 1.0:
            keys.append((1.0 + first[0], first[1], first[2]))
    every = sorted({c for _, channels, _ in keys for c in channels})
    ease = (lambda u: u * u * (3 - 2 * u)) if ease_name == "smooth" else (lambda u: u)

    def apply(pose: Pose, t: float) -> None:
        if loop and t < keys[0][0]:
            t += 1.0
        t = min(max(t, keys[0][0]), keys[-1][0])
        k = max(i for i in range(len(keys)) if keys[i][0] <= t)
        k = min(k, len(keys) - 2)
        (t0, c0, m0), (t1, c1, m1) = keys[k], keys[k + 1]
        u = ease((t - t0) / (t1 - t0))
        angles: dict[str, dict[str, float]] = {}
        for bone, axis in every:
            value = c0.get((bone, axis), 0.0) + (c1.get((bone, axis), 0.0) - c0.get((bone, axis), 0.0)) * u
            angles.setdefault(bone, {})[axis] = value
        for bone, a in angles.items():
            pose.add_turn(bone, turn(a.get("pitch", 0.0), a.get("yaw", 0.0), a.get("roll", 0.0)))
        pose.lift = add(pose.lift, tuple(m0[i] + (m1[i] - m0[i]) * u for i in range(3)))

    return apply


def _gait(fields: dict, skeleton: Skeleton, legs: Mapping[str, Leg], loop: bool, path: str) -> Apply:
    _only(fields, ("legs", "stride", "lift", "duty", "cycles", "direction", "per_leg"), path)
    phases_raw = _object(fields.get("legs"), f"{path}.legs")
    if not phases_raw:
        raise MotionError(f"{path}.legs: name at least one leg")
    by_name = {name: leg for name, leg in legs.items()}
    phases: dict[str, float] = {}
    for leg_name, phase in phases_raw.items():
        if leg_name not in by_name:
            raise MotionError(f"{path}.legs: no leg '{leg_name}'; legs are {sorted(by_name)}")
        if isinstance(phase, bool) or not isinstance(phase, int | float):
            raise MotionError(f"{path}.legs.{leg_name}: expected a phase 0..1")
        phases[leg_name] = float(phase)
    for leg_name, phase in list(phases.items()):
        twin = twin_name(leg_name)
        if twin and twin in by_name and twin not in phases:
            phases[twin] = (phase + 0.5) % 1.0
    stride = _number(fields, "stride", path)
    lift = _number(fields, "lift", path, stride * 0.3)
    duty = _number(fields, "duty", path, 0.6)
    if not 0.05 <= duty <= 0.95:
        raise MotionError(f"{path}.duty: expected 0.05..0.95, got {duty}")
    cycles = _number(fields, "cycles", path, 1.0)
    if loop and abs(cycles - round(cycles)) > 1e-9:
        raise MotionError(f"{path}.cycles: a loop needs whole cycles, got {cycles}")
    direction = fields.get("direction", [0.0, -1.0])
    if not (
        isinstance(direction, list)
        and len(direction) == 2
        and all(isinstance(v, int | float) for v in direction)
    ):
        raise MotionError(f"{path}.direction: expected [x, y], the way the body walks (default [0, -1])")
    norm = math.hypot(direction[0], direction[1])
    if norm < 1e-9:
        raise MotionError(f"{path}.direction: must not be [0, 0]")
    dx, dy = direction[0] / norm, direction[1] / norm
    ankles = {name: skeleton[by_name[name].lower].tail for name in phases}
    # Per leg: its own lift and duty (a limp: the bad leg barely lifts and bears weight briefly).
    # Its stride follows from its duty, so every planted foot keeps pace with the body: no skating.
    own = {name: (lift, duty, stride) for name in phases}
    for leg_name, raw in _object(fields.get("per_leg", {}), f"{path}.per_leg").items():
        here = f"{path}.per_leg.{leg_name}"
        if leg_name not in phases:
            raise MotionError(f"{here}: no leg '{leg_name}' in this gait ({sorted(phases)})")
        entry = _object(raw, here)
        _only(entry, ("lift", "duty"), here)
        d = _number(entry, "duty", here, duty)
        if not 0.05 <= d <= 0.95:
            raise MotionError(f"{here}.duty: expected 0.05..0.95, got {d}")
        own[leg_name] = (_number(entry, "lift", here, lift), d, stride * d / duty)

    def apply(pose: Pose, t: float) -> None:
        for leg_name, phase in phases.items():
            leg_lift, leg_duty, leg_stride = own[leg_name]
            s = (cycles * t + phase) % 1.0
            if s < leg_duty:  # planted: slides back under the body as it passes over
                along = 0.5 - s / leg_duty
                up = 0.0
            else:  # swinging forward, lifted
                u = (s - leg_duty) / (1.0 - leg_duty)
                along = -0.5 + u * u * (3 - 2 * u)
                up = leg_lift * math.sin(math.pi * u)
            ankle = ankles[leg_name]
            pose.reach[by_name[leg_name].upper] = (
                ankle[0] + dx * leg_stride * along,
                ankle[1] + dy * leg_stride * along,
                ankle[2] + up,
            )

    return apply


# --------------------------------------------------------------------------------------------


def _object(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise MotionError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _only(fields: dict, allowed: tuple[str, ...], path: str) -> None:
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        raise MotionError(f"{path}: unknown key(s) {unknown}; allowed are {sorted(allowed)}")


def _number(fields: dict, key: str, path: str, default: float | None = None) -> float:
    if key not in fields:
        if default is None:
            raise MotionError(f"{path}: missing '{key}'")
        return default
    value = fields[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MotionError(f"{path}.{key}: expected a number, got {value!r}")
    return float(value)


def _vec(fields: dict, key: str, path: str) -> Vec:
    value = fields[key]
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, int | float) for v in value)):
        raise MotionError(f"{path}.{key}: expected [x, y, z]")
    return (float(value[0]), float(value[1]), float(value[2]))
