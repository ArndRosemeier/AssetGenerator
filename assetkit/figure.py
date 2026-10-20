"""A figure: a whole body from a few numbers, anatomy included. Needs numpy.

The hardest thing to sculpt from spheres and capsules is a body that reads as one: tapered
limbs with their muscle, joints that narrow, hands with fingers, feet that stand, a face. A
figure builds that from proportions, and its skeleton, skin and walk come with it:

    "figure": {"height": 1.8, "heads": 7.5, "build": 0.5, "muscle": 0.6,
               "shoulders": 1.0, "hips": 1.0, "hands": 1.0, "stance": "plantigrade",
               "arm_pairs": 1, "fingers": 4, "ears": "round", "eyes": 2}

Every key is optional. Lengths are metres, the rest factors (1 = an average adult):

    height     standing height (1.75)
    heads      height in head heights: 7.5 an adult, 8 heroic, 5 stocky, 3 a doll (7.5)
    build      0 lean .. 1 heavy: limb and torso girth (0.5)
    muscle     0 soft .. 1 defined: chest, shoulders, arms, calves (0.5)
    belly      0 flat .. 1 round (0)
    shoulders, hips          width factors (1)
    legs, arms               length factors (1)
    neck                     length factor (1)
    hands, feet              size factors (1; 1.6 for oversized hands)
    stance     "plantigrade" (on the soles) or "digitigrade" (on the toes, hocks raised)
    arm_pairs  1, 2 or 3: extra pairs lower on the ribcage, each further forward and down
    fingers    4 (default), 3 or 2 besides the thumb, or 0 for mittens
    ears       "round", "pointed" or "none"; `ear_size` (1)
    eyes       1, 2 or 3 (the third above, on the brow)
    nose, brow, jaw          size factors (1, 0.5, 1)
    arm_angle  degrees the arms hang below horizontal in the modelled pose (45: an A-pose,
               clear of the body so the skin of the arm never touches the side)

The figure faces -Y, stands on z = 0 with its centre line on x = 0, as every sculpt. Its
`pieces` (head, eyes, hands, feet, torso, ...) are refs for the spec (`figure.eyes` to paint
the eyes, `figure.head` to cut a hood around), and `landmarks` say where things are (the top
of the head, the eyes, the hands, the waist) so clothing and gear go where they belong.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from assetkit import sdf
from assetkit.rig import Bone, Leg

V = np.ndarray


class FigureError(ValueError):
    """A figure that does not parse; the message names the path to the problem."""


_NUMBERS: dict[str, tuple[float, float, float]] = {
    # key: (default, lowest, highest)
    "height": (1.75, 0.2, 8.0),
    "heads": (7.5, 2.5, 9.0),
    "build": (0.5, 0.0, 1.0),
    "muscle": (0.5, 0.0, 1.0),
    "belly": (0.0, 0.0, 1.0),
    "shoulders": (1.0, 0.6, 2.2),
    "hips": (1.0, 0.6, 2.0),
    "legs": (1.0, 0.6, 1.5),
    "arms": (1.0, 0.7, 1.6),
    "neck": (1.0, 0.2, 2.5),
    "hands": (1.0, 0.5, 2.5),
    "feet": (1.0, 0.5, 2.2),
    "ear_size": (1.0, 0.4, 3.0),
    "nose": (1.0, 0.0, 2.5),
    "brow": (0.5, 0.0, 1.0),
    "jaw": (1.0, 0.6, 1.6),
    "arm_angle": (45.0, 25.0, 75.0),
}
_CHOICES: dict[str, tuple[object, tuple[object, ...]]] = {
    "stance": ("plantigrade", ("plantigrade", "digitigrade")),
    "arm_pairs": (1, (1, 2, 3)),
    "fingers": (4, (0, 2, 3, 4)),
    "ears": ("round", ("round", "pointed", "none")),
    "eyes": (2, (1, 2, 3)),
}


@dataclass(frozen=True)
class FigureParams:
    values: Mapping[str, object]

    def __getattr__(self, key: str) -> object:
        try:
            return self.values[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def parse_figure(raw: object, path: str) -> FigureParams:
    """Standard library only, so a spec fails before Blender starts."""
    if not isinstance(raw, dict):
        raise FigureError(f"{path}: expected an object of proportions (every key optional)")
    unknown = sorted(set(raw) - set(_NUMBERS) - set(_CHOICES))
    if unknown:
        raise FigureError(f"{path}: unknown key(s) {unknown}; allowed are {sorted([*_NUMBERS, *_CHOICES])}")
    values: dict[str, object] = {}
    for key, (default, lo, hi) in _NUMBERS.items():
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise FigureError(f"{path}.{key}: expected a number, got {value!r}")
        if not lo <= value <= hi:
            raise FigureError(f"{path}.{key}: expected {lo}..{hi}, got {value}")
        values[key] = float(value)
    for key, (default, allowed) in _CHOICES.items():
        value = raw.get(key, default)
        if value not in allowed or isinstance(value, bool):
            raise FigureError(f"{path}.{key}: expected one of {list(allowed)}, got {value!r}")
        values[key] = value
    return FigureParams(values)


@dataclass
class Figure:
    shape: sdf.Shape
    pieces: dict[str, sdf.Shape]
    bones: list[Bone]  # the centre and the left ('.L') side; twins are made from them
    carry: dict[str, list[sdf.Shape]]  # per bone, the shapes whose surface follows it
    legs: dict[str, Leg]
    softness: dict[str, float]
    default_softness: float
    landmarks: dict[str, tuple[float, float, float]]
    clips: dict[str, object] = field(default_factory=dict)  # default clips, in the motion language


def _v(*xs: float) -> V:
    return np.array(xs, dtype=np.float64)


def _unit(a: V) -> V:
    return a / math.sqrt(float((a * a).sum()))


def _t(a: V) -> tuple[float, float, float]:
    return (float(a[0]), float(a[1]), float(a[2]))


def _sweep(points: list[V], radii: list[float]) -> sdf.Shape:
    return sdf.sweep([_t(p) for p in points], radii)


def _ellipsoid(c: V, r: tuple[float, float, float]) -> sdf.Shape:
    return sdf.ellipsoid(_t(c), r)


def _turn_towards(d: V, towards: V, degrees: float) -> V:
    """`d` turned `degrees` towards the direction `towards` (in their common plane)."""
    t = towards - (towards @ d) * d
    n = math.sqrt(float((t * t).sum()))
    if n < 1e-9:
        return d
    t = t / n
    a = math.radians(degrees)
    return _unit(d * math.cos(a) + t * math.sin(a))


def build_figure(p: FigureParams) -> Figure:
    H = float(p.height)  # noqa: N806 - the figure's height, the unit of everything below
    hh = H / float(p.heads)  # head height
    b, m = float(p.build), float(p.muscle)
    lf = 0.8 + 0.4 * b  # limb girth
    tf = 0.85 + 0.3 * b  # torso girth
    shoulders, hips = float(p.shoulders), float(p.hips)

    # ---- heights ------------------------------------------------------------------------
    chin_z = H - hh
    neck_h = 0.33 * hh * float(p.neck)
    shoulder_line = chin_z - neck_h
    sj_z = shoulder_line - 0.035 * H
    hip_z = 0.6 * shoulder_line * float(p.legs)
    hip_z = min(hip_z, shoulder_line - 0.25 * shoulder_line)
    torso = shoulder_line - hip_z
    waist_z = hip_z + 0.32 * torso
    chest_z = hip_z + 0.70 * torso

    # ---- torso: one swept form, deeper than wide is not, so squashed front to back ------------
    w_hip = 0.092 * H * hips * tf
    w_waist = 0.072 * H * tf * (1.0 + 0.25 * float(p.belly))
    w_chest = 0.097 * H * shoulders * tf
    w_upper = 0.094 * H * shoulders * tf
    x_sj = 0.114 * H * shoulders * (0.92 + 0.16 * b)
    belly_f = float(p.belly)
    d_hip = 0.068 * H * tf * (0.9 + 0.1 * hips)
    d_waist = 0.058 * H * tf * (1.0 + 0.5 * belly_f)
    d_chest = 0.066 * H * tf * (0.92 + 0.08 * shoulders)
    sections = [
        [hip_z - 0.075 * H, 0.055 * H * hips * tf, 0.05 * H * tf, 0.004 * H, 0.0],
        [hip_z, w_hip, d_hip, 0.006 * H, 0.0],
        [waist_z, w_waist, d_waist, -0.018 * H * belly_f, 0.0],
        [chest_z, w_chest, d_chest, 0.002 * H, 0.0],
        [shoulder_line - 0.05 * H, w_upper, 0.06 * H * tf, 0.008 * H, 0.0],
        [shoulder_line - 0.004 * H, 0.62 * x_sj, 0.045 * H * tf, 0.012 * H, 0.0],
    ]
    torso_shape = sdf.loft(sections)
    fronts = {"chest": 0.002 * H - d_chest, "waist": -0.018 * H * belly_f - d_waist, "hip": 0.006 * H - d_hip}
    pecs = sdf.mirror_x(
        _ellipsoid(
            _v(0.048 * H * shoulders, fronts["chest"] + 0.016 * H, chest_z + 0.045 * H),
            (0.058 * H * shoulders, (0.01 + 0.008 * m) * H * tf, 0.032 * H),
        )
    )
    glutes = sdf.mirror_x(
        _ellipsoid(
            _v(0.042 * H * hips, d_hip * 0.6, hip_z - 0.012 * H),
            (0.046 * H * hips * tf, 0.026 * H * tf, 0.048 * H),
        )
    )
    belly = _ellipsoid(
        _v(0, fronts["waist"] * 0.6, waist_z - 0.01 * H),
        (0.07 * H * tf * (1 + 0.3 * float(p.belly)), (0.03 + 0.07 * float(p.belly)) * H, 0.08 * H),
    )

    # ---- neck and shoulders ------------------------------------------------------------------
    r_neck = min(0.03 * H * lf, 0.22 * hh)
    neck_shape = _sweep(
        [
            _v(0, 0.006 * H, shoulder_line - 0.03 * H),
            _v(0, 0.012 * H, chin_z + 0.02 * H),
            _v(0, 0.02 * H, chin_z + 0.3 * hh),
        ],
        [r_neck * 1.15, r_neck, r_neck * 0.9],
    )
    trapezius = sdf.mirror_x(
        _sweep(
            [
                _v(0.022 * H, 0.016 * H, chin_z - 0.6 * neck_h),
                _v(x_sj * 0.6, 0.01 * H, shoulder_line - 0.002 * H),
                _v(x_sj, 0.004 * H, sj_z + 0.022 * H),
            ],
            [0.022 * H * tf, 0.024 * H * tf * (0.85 + 0.3 * m), 0.022 * H * lf],
        )  # fmt: skip
    )

    # ---- head ----------------------------------------------------------------------------------
    head_parts, eye_balls, sockets, eye_points, lids, face = _head(p, H, hh)
    head_solid = sdf.blend(head_parts[0], head_parts[1])
    head_cut = head_solid
    for socket in sockets:
        head_cut = sdf.subtract(head_cut, socket, 0.045 * hh)
    head_cut = sdf.subtract(head_cut, head_parts[2], 0.012 * hh)  # the mouth's line
    eyes = sdf.union(*eye_balls)
    head = sdf.blend([sdf.union(head_cut, eyes), *lids], [0.0, *[0.03 * hh] * len(lids)])

    # ---- arms (the left side; mirrored below) ---------------------------------------------------
    arm_shapes: list[sdf.Shape] = []
    bones: list[Bone] = []
    carry: dict[str, list[sdf.Shape]] = {}
    softness: dict[str, float] = {}
    hands: list[sdf.Shape] = []
    landmarks: dict[str, tuple[float, float, float]] = {}
    for i in range(int(p.arm_pairs)):  # type: ignore[call-overload]
        suffix = "" if i == 0 else f"_{i + 1}"
        a = math.radians(float(p.arm_angle) + 12.0 * i)
        reach = float(p.arms) * (0.92**i) * torso / (0.329 * H)  # arms follow the torso's length
        s = _v(x_sj * (1 - 0.1 * i), 0.004 * H - 0.012 * H * i, sj_z - 0.12 * H * i)
        down = _v(math.cos(a), 0.0, -math.sin(a))
        d_upper = _turn_towards(down, _v(0, -1, 0), 14.0 * i)
        elbow = s + d_upper * 0.172 * H * reach
        d_fore = _turn_towards(d_upper, _v(0, -1, 0), 12.0 + 10.0 * i)
        wrist = elbow + d_fore * 0.152 * H * reach
        af = lf * math.sqrt(shoulders)  # arm girth follows the shoulders
        deltoid = _ellipsoid(
            s + _v(0.012 * H, 0.0, 0.006 * H),
            tuple(
                r * af * (0.85 + 0.3 * m) * (1.0 if i == 0 else 0.75)
                for r in (0.034 * H, 0.033 * H, 0.04 * H)
            ),  # type: ignore[arg-type]
        )
        upper = _sweep(
            [s, s + d_upper * 0.4 * 0.172 * H * reach, elbow],
            [0.032 * H * af, 0.029 * H * af * (1 + 0.12 * m), 0.021 * H * af],
        )
        fore = _sweep(
            [elbow, elbow + d_fore * 0.28 * 0.152 * H * reach, wrist],
            [0.022 * H * af, 0.025 * H * af * (1 + 0.08 * m), 0.0155 * H * af],
        )
        hand, hand_tip, hand_landmarks = _hand(p, H, wrist, d_fore)
        arm = sdf.blend([deltoid, upper, fore, hand], [0.0, 0.02 * H, 0.012 * H, 0.006 * H])
        arm_shapes.append(arm)
        hands.append(hand)
        parent = "chest" if i == 0 else "spine"
        bones += [
            Bone(f"upper_arm{suffix}.L", _t(s), _t(elbow), parent),
            Bone(f"forearm{suffix}.L", _t(elbow), _t(wrist), f"upper_arm{suffix}.L"),
            Bone(f"hand{suffix}.L", _t(wrist), _t(hand_tip), f"forearm{suffix}.L"),
        ]
        carry[f"upper_arm{suffix}.L"] = [deltoid, upper]
        carry[f"forearm{suffix}.L"] = [fore]
        carry[f"hand{suffix}.L"] = [hand]
        softness[f"hand{suffix}.L"] = 0.006 * H
        landmarks[f"shoulder{suffix}.L"] = _t(s)
        landmarks[f"elbow{suffix}.L"] = _t(elbow)
        landmarks[f"wrist{suffix}.L"] = _t(wrist)
        for k, v in hand_landmarks.items():
            landmarks[f"{k}{suffix}.L"] = v

    # ---- legs -----------------------------------------------------------------------------------
    leg, foot, leg_bones, leg_carry, leg_marks = _leg(p, H, hip_z, lf, m)
    bones += leg_bones
    carry.update(leg_carry)
    landmarks.update(leg_marks)

    # ---- the whole --------------------------------------------------------------------------
    core = sdf.blend(
        [torso_shape, glutes, belly, pecs, trapezius, neck_shape],
        [0.0, 0.022 * H, 0.03 * H, 0.02 * H, 0.025 * H, 0.025 * H],
    )
    limbs = [sdf.mirror_x(leg), *(sdf.mirror_x(arm) for arm in arm_shapes)]
    body = sdf.blend([core, head, *limbs], [0.0, 0.012 * H, 0.03 * H, *[0.018 * H] * len(arm_shapes)])

    # ---- the spine and head bones, and what they carry ----------------------------------------
    neck_top = _v(0, 0.02 * H, chin_z + 0.12 * hh)
    bones = [
        Bone("hips", (0.0, 0.0, hip_z), (0.0, 0.0, waist_z), None),
        Bone("spine", (0.0, 0.0, waist_z), (0.0, 0.0, chest_z), "hips"),
        Bone("chest", (0.0, 0.0, chest_z), (0.0, 0.006 * H, shoulder_line), "spine"),
        Bone("neck", (0.0, 0.006 * H, shoulder_line), _t(neck_top), "chest"),
        Bone("head", _t(neck_top), (0.0, 0.02 * H, H), "neck"),
        *bones,
    ]
    below = lambda z: sdf.intersect(torso_shape, sdf.half_space(z))  # noqa: E731
    above = lambda z: sdf.intersect(torso_shape, sdf.half_space(z, above=True))  # noqa: E731
    carry.update(
        {
            "hips": [below(hip_z + 0.12 * torso), glutes],
            "spine": [
                sdf.intersect(above(hip_z + 0.12 * torso), sdf.half_space(chest_z - 0.05 * torso)),
                belly,
            ],
            "chest": [above(chest_z - 0.05 * torso), pecs, trapezius],
            "neck": [neck_shape],
            "head": [head],
        }
    )
    softness.update(
        {
            "head": 0.008 * H,
            "neck": 0.01 * H,
            "hips": 0.026 * H,
            "thigh.L": (0.02 if p.stance == "plantigrade" else 0.028) * H,
        }
    )

    landmarks.update(
        {
            "head_top": (0.0, 0.0, H),
            "chin": (0.0, -0.4 * hh, chin_z),
            "neck_base": (0.0, 0.0, shoulder_line),
            "chest_front": (0.0, fronts["chest"], chest_z),
            "waist": (0.0, 0.0, waist_z),
            "waist_front": (0.0, fronts["waist"], waist_z),
            "hips": (0.0, 0.0, hip_z),
        }
    )
    for name, point in eye_points.items():
        landmarks[name] = point
    landmarks["widths"] = (2 * x_sj, 2 * w_hip, 2 * w_waist)  # shoulders, hips, waist

    pieces = {
        "head": head,
        **face,
        "torso": torso_shape,
        "hands": sdf.mirror_x(sdf.union(*hands)),
        "feet": sdf.mirror_x(foot),
        "arms": sdf.mirror_x(sdf.union(*arm_shapes)),
        "legs": sdf.mirror_x(leg),
    }
    return Figure(
        shape=body,
        pieces=pieces,
        bones=bones,
        carry=carry,
        legs={"leg.L": Leg("thigh.L", "shin.L", "foot.L", None)},
        softness=softness,
        default_softness=0.012 * H,
        landmarks=landmarks,
        clips=_default_clips(p, H, hip_z),
    )


def _head(p: FigureParams, H: float, hh: float) -> tuple:  # noqa: N803
    """The head's blended parts (shapes, blend widths, the mouth's line), its eyeballs, their
    sockets and where the eyes are."""
    top = H
    jaw, nose, brow = float(p.jaw), float(p.nose), float(p.brow)
    shapes = [
        _ellipsoid(_v(0, 0.05 * hh, top - 0.43 * hh), (0.33 * hh, 0.43 * hh, 0.43 * hh)),  # cranium
        _ellipsoid(_v(0, -0.16 * hh, top - 0.74 * hh), (0.235 * hh * jaw, 0.25 * hh, 0.22 * hh)),  # jaw
        sdf.sphere(_t(_v(0, -0.34 * hh, top - 0.9 * hh)), 0.075 * hh * jaw),  # chin
        sdf.mirror_x(
            _ellipsoid(_v(0.17 * hh, -0.28 * hh, top - 0.6 * hh), (0.085 * hh, 0.075 * hh, 0.06 * hh))
        ),
        sdf.capsule(
            _t(_v(-0.21 * hh, -0.37 * hh, top - 0.42 * hh)),
            _t(_v(0.21 * hh, -0.37 * hh, top - 0.42 * hh)),
            0.04 * hh * (0.6 + 0.9 * brow),
        ),  # brow ridge
    ]
    ks = [0.0, 0.1 * hh, 0.06 * hh, 0.06 * hh, 0.07 * hh]
    if nose > 0:
        tip = _v(0, -0.47 * hh - 0.05 * hh * (nose - 1), top - 0.66 * hh)
        shapes += [
            sdf.capsule(_t(_v(0, -0.39 * hh, top - 0.5 * hh)), _t(tip), 0.03 * hh * nose, 0.045 * hh * nose),
            sdf.mirror_x(
                sdf.sphere(_t(_v(0.045 * hh * nose, -0.43 * hh, top - 0.68 * hh)), 0.034 * hh * nose)
            ),
        ]
        ks += [0.025 * hh, 0.02 * hh]
    lips = []
    for z, y, half, r in ((0.778, -0.412, 0.062, 0.015), (0.818, -0.405, 0.055, 0.017)):
        lips.append(
            sdf.capsule(
                _t(_v(-half * hh, y * hh, top - z * hh)), _t(_v(half * hh, y * hh, top - z * hh)), r * hh
            )
        )
    shapes += lips
    ks += [0.025 * hh, 0.025 * hh]
    ears = str(p.ears)
    size = float(p.ear_size)
    if ears == "round":
        shapes.append(
            sdf.mirror_x(
                _ellipsoid(
                    _v(0.355 * hh, 0.05 * hh, top - 0.52 * hh),
                    (0.035 * hh, 0.1 * hh * size, 0.15 * hh * size),
                )
            )
        )
        ks.append(0.025 * hh)
    elif ears == "pointed":
        root = _v(0.33 * hh, 0.04 * hh, top - 0.58 * hh)
        ear = _sweep(
            [root, root + _v(0.07 * hh, 0.06 * hh, 0.14 * hh) * size, root + _v(0.2 * hh, 0.18 * hh, 0.32 * hh) * size],
            [0.085 * hh * min(size, 1.3), 0.06 * hh * min(size, 1.3), 0.035 * hh],
        )  # fmt: skip
        ear = sdf.squash(ear, (-0.6, 1.0, 0.0), 0.5, _t(root))
        shapes.append(sdf.mirror_x(ear))
        ks.append(0.03 * hh)
    mouth = sdf.capsule(
        _t(_v(-0.058 * hh, -0.43 * hh, top - 0.797 * hh)),
        _t(_v(0.058 * hh, -0.43 * hh, top - 0.797 * hh)),
        0.006 * hh,
    )
    eye_z = top - 0.5 * hh
    centres: list[tuple[str, V, float]] = []
    count = int(p.eyes)  # type: ignore[call-overload]
    if count in (2, 3):
        centres += [("eye.L", _v(0.135 * hh, 0, eye_z), 1.0), ("eye.R", _v(-0.135 * hh, 0, eye_z), 1.0)]
    if count == 1:
        centres.append(("eye", _v(0, 0, eye_z + 0.02 * hh), 1.25))
    if count == 3:
        centres.append(("eye.C", _v(0, 0, eye_z + 0.19 * hh), 0.85))
    balls, sockets, points, lids, irises, pupils = [], [], {}, [], [], []
    for name, c, s in centres:
        r = 0.056 * hh * s
        ball = c + _v(0, -0.38 * hh + r, 0)
        balls.append(sdf.sphere(_t(ball), r))
        sockets.append(sdf.sphere(_t(c + _v(0, -0.415 * hh, 0)), 0.068 * hh * s))
        front = ball + _v(0, -r, 0)
        irises.append(sdf.sphere(_t(front), 0.5 * r))
        pupils.append(sdf.sphere(_t(front), 0.22 * r))
        # Lids: an upper and a lower fold over the ball, leaving an almond opening.
        for dz, rr in ((0.58, 0.46), (-0.66, 0.38)):
            centre = ball + _v(0, -0.6 * r, dz * r)
            lids.append(sdf.capsule(_t(centre - _v(0.75 * r, 0, 0)), _t(centre + _v(0.75 * r, 0, 0)), rr * r))
        points[name] = _t(front)
    covered = sdf.union(*lids)  # the lids' skin lies inside the balls: keep it out of the eyes
    extra = {
        "eyes": sdf.subtract(sdf.union(*balls), covered),
        "irises": sdf.subtract(sdf.union(*irises), covered),
        "pupils": sdf.subtract(sdf.union(*pupils), covered),
        "lips": sdf.round_(sdf.union(*lips), 0.006 * hh),
    }
    return (shapes, ks, mouth), balls, sockets, points, lids, extra


def _hand(p: FigureParams, H: float, wrist: V, along: V) -> tuple[sdf.Shape, V, dict]:  # noqa: N803
    """A hand at the wrist pointing `along`: a palm, fingers curling a little towards it, a
    thumb set forward. Palms face down and in, as an arm hangs."""
    s = float(p.hands)
    length = 0.108 * H * s
    palm_normal = _unit(np.cross(_v(0, 1, 0), along))  # down and in, for an arm hanging out
    if palm_normal[2] > 0:
        palm_normal = -palm_normal
    side = _unit(np.cross(along, palm_normal))  # towards the back; the thumb is on the other side
    if side[1] < 0:
        side = -side
    base = wrist + along * 0.01 * H
    knuckles = wrist + along * 0.47 * length
    width = 0.024 * H * s
    palm = sdf.squash(
        _sweep([base, knuckles], [width, width * 0.95]), _t(palm_normal), 0.42, _t((base + knuckles) / 2)
    )
    parts = [palm]
    ks = [0.0]
    n = int(p.fingers)  # type: ignore[call-overload]
    finger_r = 0.0062 * H * math.sqrt(s) * (0.85 + 0.3 * float(p.build))
    tips = []
    if n == 0:
        mitten = sdf.squash(
            _sweep([knuckles - along * 0.05 * length, knuckles + along * 0.3 * length + palm_normal * 0.08 * length,
                    knuckles + along * 0.43 * length + palm_normal * 0.18 * length], [width * 0.9, width * 0.8, width * 0.45]),
            _t(palm_normal), 0.5, _t(knuckles),
        )  # fmt: skip
        parts.append(mitten)
        ks.append(0.004 * H)
        tips.append(knuckles + along * 0.43 * length)
    else:
        lengths = {4: [0.9, 1.0, 0.95, 0.75], 3: [0.92, 1.0, 0.85], 2: [0.95, 1.0]}[n]
        spread = 2 * width * 0.82
        for j, f in enumerate(lengths):
            offset = (j - (n - 1) / 2) * spread / n * 1.1
            root = knuckles + side * offset - along * 0.02 * length
            d = _turn_towards(along, side * (1 if offset > 0 else -1), abs(offset) / width * 10.0)
            flen = 0.52 * length * f
            mid = root + d * flen * 0.55 + palm_normal * flen * 0.12
            tip = root + d * flen * 0.95 + palm_normal * flen * 0.35
            parts.append(_sweep([root, mid, tip], [finger_r, finger_r * 0.88, finger_r * 0.72]))
            ks.append(0.003 * H)
            tips.append(tip)
    thumb_root = wrist + along * 0.14 * length - side * width * 0.75 + palm_normal * 0.01 * H
    td = _unit(along * 0.6 - side * 0.5 + palm_normal * 0.45)
    thumb_mid = thumb_root + td * 0.24 * length
    thumb_tip = thumb_mid + _unit(td + along * 0.6) * 0.2 * length
    parts.append(
        _sweep([thumb_root, thumb_mid, thumb_tip], [finger_r * 1.3, finger_r * 1.1, finger_r * 0.85])
    )
    ks.append(0.005 * H)
    hand = sdf.blend(parts, ks)
    centre = (base + knuckles) / 2
    return hand, knuckles + along * 0.45 * length, {"hand": _t(centre), "palm_normal": _t(palm_normal)}


def _leg(p: FigureParams, H: float, hip_z: float, lf: float, m: float) -> tuple:  # noqa: N803
    """The left leg and foot, their bones, what each carries, and landmarks."""
    hips = float(p.hips)
    feet = float(p.feet)
    lf = lf * math.sqrt(hips)  # leg girth follows the hips
    x = 0.05 * H * hips * (0.95 + 0.1 * float(p.build))
    hip = _v(x, 0.0, hip_z)
    bones: list[Bone]
    carry: dict[str, list[sdf.Shape]] = {}
    marks: dict[str, tuple[float, float, float]] = {}
    if p.stance == "plantigrade":
        knee = _v(x * 1.05, -0.008 * H, 0.53 * hip_z)
        ankle = _v(x * 1.12, 0.004 * H, 0.09 * hip_z)
        thigh = _sweep(
            [hip + _v(0.004 * H, 0, 0.02 * H), hip + 0.32 * (knee - hip) + _v(0, -0.01 * H, 0), knee + _v(0, 0, 0.03 * H), knee],
            [0.048 * H * lf, 0.045 * H * lf * (1 + 0.1 * m), 0.036 * H * lf, 0.033 * H * lf],
        )  # fmt: skip
        shin = _sweep(
            [knee, knee + 0.3 * (ankle - knee) + _v(0, 0.012 * H, 0), ankle + 0.25 * (knee - ankle), ankle],
            [0.032 * H * lf, 0.034 * H * lf * (1 + 0.15 * m), 0.024 * H * lf, 0.02 * H * lf],
        )
        kneecap = _ellipsoid(
            knee + _v(0, -0.026 * H * lf, 0.006 * H), (0.018 * H * lf, 0.012 * H * lf, 0.02 * H * lf)
        )
        heel = _v(ankle[0], ankle[1] + 0.018 * H, 0.022 * H)
        instep = _v(ankle[0] + 0.002 * H, ankle[1] - 0.04 * H * feet, 0.034 * H)
        ball = _v(ankle[0] + 0.006 * H, ankle[1] - 0.1 * H * feet, 0.02 * H)
        toe = _v(ankle[0] + 0.008 * H, ankle[1] - 0.135 * H * feet, 0.014 * H)
        r = 0.022 * H * math.sqrt(feet)
        foot = _sweep([heel, instep, ball, toe], [r, r * 1.15, r * 0.95, r * 0.7])
        foot = sdf.squash(foot, (1, 0, 0), 1.18, _t(_v(ankle[0], 0, 0)))
        foot = sdf.squash(foot, (0, 0, 1), 0.92, (0.0, 0.0, 0.0))
        leg = sdf.blend([thigh, kneecap, shin, foot], [0.0, 0.012 * H, 0.015 * H, 0.014 * H])
        bones = [
            Bone("thigh.L", _t(hip), _t(knee), "hips"),
            Bone("shin.L", _t(knee), _t(ankle), "thigh.L"),
            Bone("foot.L", _t(ankle), _t(ball), "shin.L"),
        ]
        carry.update({"thigh.L": [thigh], "shin.L": [shin, kneecap], "foot.L": [foot]})
        marks.update({"knee.L": _t(knee), "ankle.L": _t(ankle), "toe.L": _t(toe)})
    else:
        knee = _v(x * 1.05, -0.06 * H, 0.62 * hip_z)
        hock = _v(x * 1.1, 0.07 * H, 0.25 * hip_z)
        ball = _v(x * 1.12, 0.0, 0.022 * H)
        thigh = _sweep(
            [hip + _v(0.004 * H, 0, 0.02 * H), hip + 0.35 * (knee - hip), knee],
            [0.054 * H * lf, 0.05 * H * lf * (1 + 0.1 * m), 0.034 * H * lf],
        )
        shin = _sweep(
            [knee, knee + 0.3 * (hock - knee) + _v(0, -0.008 * H, 0), hock],
            [0.031 * H * lf, 0.03 * H * lf * (1 + 0.15 * m), 0.02 * H * lf],
        )
        spur = sdf.sphere(_t(hock + _v(0, 0.012 * H, 0)), 0.017 * H * lf)
        meta = _sweep(
            [hock, hock + 0.5 * (ball - hock), ball], [0.019 * H * lf, 0.015 * H * lf, 0.017 * H * lf]
        )
        r = 0.009 * H * math.sqrt(feet)
        toes = sdf.union(
            *[
                _sweep(
                    [
                        ball,
                        ball + _v(dx * H, -0.035 * H * feet, -0.004 * H),
                        ball + _v(dx * 1.4 * H, -0.065 * H * feet, -0.012 * H),
                    ],
                    [r, r * 0.85, r * 0.55],
                )  # fmt: skip
                for dx in (-0.016, 0.0, 0.016)
            ]
        )
        toe = ball + _v(0, -0.065 * H * feet, -0.012 * H)
        foot = sdf.blend([meta, toes], [0.0, 0.006 * H])
        leg = sdf.blend([thigh, shin, spur, foot], [0.0, 0.014 * H, 0.008 * H, 0.008 * H])
        bones = [
            Bone("thigh.L", _t(hip), _t(knee), "hips"),
            Bone("shin.L", _t(knee), _t(hock), "thigh.L"),
            Bone("foot.L", _t(hock), _t(ball), "shin.L"),
            Bone("toes.L", _t(ball), _t(toe), "foot.L"),
        ]
        carry.update({"thigh.L": [thigh], "shin.L": [shin, spur], "foot.L": [meta], "toes.L": [toes]})
        marks.update({"knee.L": _t(knee), "hock.L": _t(hock), "toe.L": _t(toe)})
    marks["hip.L"] = _t(hip)
    return leg, foot, bones, carry, marks


def _default_clips(p: FigureParams, H: float, hip_z: float) -> dict[str, object]:  # noqa: N803
    """An Idle and a Walk that read at a glance: a stride about two thirds of the leg, arms
    swinging against the legs, the chest turning against the hips, the body bobbing twice a
    step. Name a clip the same in the spec to replace it."""
    leg = hip_z
    pace = round(1.1 * math.sqrt(H / 1.75) * 20) / 20  # seconds per two steps
    pairs = int(p.arm_pairs)  # type: ignore[call-overload]
    arms_down = [
        {"turn": {"bone": f"upper_arm{'' if i == 0 else f'_{i + 1}'}.*", "roll": -25.0, "wave": "constant"}}
        for i in range(pairs)
    ]
    swing = []
    for i in range(pairs):
        suffix = "" if i == 0 else f"_{i + 1}"
        swing += [
            {"turn": {"bone": f"upper_arm{suffix}.L", "pitch": 20.0, "phase": 0.75 - 0.06 * i}},
            {"turn": {"bone": f"upper_arm{suffix}.R", "pitch": 20.0, "phase": 0.25 - 0.06 * i}},
            {"turn": {"bone": f"forearm{suffix}.*", "pitch": 14.0, "wave": "constant"}},
        ]
    walk = [
        {
            "gait": {
                "legs": {"leg.L": 0.0},
                "stride": round((0.62 if p.stance == "plantigrade" else 0.44) * leg, 3),
                "lift": round(0.11 * leg, 3),
                "duty": 0.6,
            }
        },
        {"move": {"z": round(0.022 * leg, 4), "wave": "bounce", "cycles": 2, "phase": 0.25}},
        {"turn": {"bone": "hips", "yaw": 5.0, "phase": 0.0}},
        {"turn": {"bone": "chest", "yaw": -8.0, "phase": 0.0}},
        {"turn": {"bone": "spine", "pitch": -3.0, "wave": "constant"}},
        *arms_down,
        *swing,
    ]
    idle = [
        {"gait": {"legs": {"leg.L": 0.0}, "stride": 0.0, "lift": 0.0}},
        {"turn": {"bone": "chest", "pitch": 2.0}},
        {"turn": {"bone": "head", "yaw": 6.0, "phase": 0.25}},
        {"move": {"x": round(0.006 * H, 4)}},
        *arms_down,
        {"turn": {"bone": "forearm.*", "pitch": 8.0, "wave": "constant"}},
    ]
    return {
        "Idle": {"seconds": 3.0, "loop": True, "motions": idle},
        "Walk": {"seconds": pace, "loop": True, "motions": walk},
    }
