"""The feral dog's body: its skeleton and the shapes sculpted round it.

Blender axes, metres: +Y is forward (the nose), +Z up, +X the dog's left. Every
shape names the bone that carries it, which is where its skin weights come from.
Side parts are written once, for the left, and mirrored.

The build is a gaunt, deep-chested street dog: a strong tuck-up, ribs and spine
showing, hip bones, a long muzzle with a mouth that opens, pricked ears.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from blender.generators.quadruped_generator.sdf import (
    Shape,
    Vec,
    box_of_ellipsoid,
    box_of_round_cone,
    ellipsoid,
    flattened,
    rotation,
    round_cone,
)


@dataclass(frozen=True)
class Bone:
    name: str
    head: Vec
    tail: Vec
    parent: str | None


@dataclass
class Body:
    bones: list[Bone] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    eyes: list[tuple[Vec, float]] = field(default_factory=list)
    teeth: list[tuple[Vec, Vec, float, str]] = field(default_factory=list)
    #: Where knees point, per leg kind, when not simply forward or back (pose.Rig).
    poles: dict[str, Vec] = field(default_factory=dict)
    #: Where shapes are being placed: an origin and a pitch (radians, nose down when negative).
    origin: Vec = (0.0, 0.0, 0.0)
    pitch: float = 0.0

    def at(self, p: Vec) -> Vec:
        """A point of the current frame, in the body's space."""
        c, s = np.cos(self.pitch), np.sin(self.pitch)
        return (
            self.origin[0] + p[0],
            self.origin[1] + p[1] * c - p[2] * s,
            self.origin[2] + p[1] * s + p[2] * c,
        )

    def turn(self, d: Vec) -> Vec:
        c, s = np.cos(self.pitch), np.sin(self.pitch)
        return (d[0], d[1] * c - d[2] * s, d[1] * s + d[2] * c)

    def moved(self, by: Vec) -> Body:
        """The skeleton, eyes and teeth moved by `by` (the shapes stay where they were sculpted)."""

        def m(p: Vec) -> Vec:
            return (p[0] + by[0], p[1] + by[1], p[2] + by[2])

        return Body(
            bones=[Bone(b.name, m(b.head), m(b.tail), b.parent) for b in self.bones],
            shapes=self.shapes,
            eyes=[(m(c), r) for c, r in self.eyes],
            teeth=[(m(a), m(b), r, bone) for a, b, r, bone in self.teeth],
            poles=self.poles,
        )

    def frame(self, origin: Vec = (0.0, 0.0, 0.0), pitch: float = 0.0) -> None:
        self.origin, self.pitch = origin, pitch

    def bone(self, name: str, head: Vec, tail: Vec, parent: str | None, mirror: bool = False) -> None:
        if not mirror:
            self.bones.append(Bone(name, self.at(head), self.at(tail), parent))
            return
        for side, s in (("L", 1.0), ("R", -1.0)):
            p = None if parent is None else parent.replace("#", side)
            self.bones.append(Bone(name.replace("#", side), self.at(_mx(head, s)), self.at(_mx(tail, s)), p))

    def cone(
        self, a: Vec, b: Vec, ra: float, rb: float, bone: str, blend: float = 0.03, mirror: bool = False
    ) -> None:
        for s, name in _sides(bone, mirror):
            aa, bb = self.at(_mx(a, s)), self.at(_mx(b, s))
            lo, hi = box_of_round_cone(aa, bb, ra, rb)
            self.shapes.append(Shape(round_cone(aa, bb, ra, rb), lo, hi, blend, name))

    def blob(
        self,
        c: Vec,
        r: Vec,
        bone: str,
        blend: float = 0.03,
        along: Vec = (0.0, 1.0, 0.0),
        third: Vec = (0.0, 0.0, 1.0),
        mirror: bool = False,
        carve: bool = False,
    ) -> None:
        """An ellipsoid: radii (side, along, third) about `c`, its long axis along `along`."""
        for s, name in _sides(bone, mirror):
            cc = self.at(_mx(c, s))
            rot = rotation(self.turn(_mx(along, s)), self.turn(_mx(third, s)))
            lo, hi = box_of_ellipsoid(cc, r)
            self.shapes.append(Shape(ellipsoid(cc, r, rot), lo, hi, blend, name, carve))

    def ear(self, a: Vec, b: Vec, ra: float, rb: float, facing: Vec, bone: str, blend: float = 0.012) -> None:
        for s, name in _sides(bone, True):
            aa, bb = self.at(_mx(a, s)), self.at(_mx(b, s))
            lo, hi = box_of_round_cone(aa, bb, ra, rb)
            self.shapes.append(
                Shape(
                    flattened(round_cone(aa, bb, ra, rb), aa, self.turn(_mx(facing, s)), 0.3),
                    lo,
                    hi,
                    blend,
                    name,
                )
            )


def _mx(v: Vec, s: float) -> Vec:
    return (v[0] * s, v[1], v[2])


def _sides(bone: str, mirror: bool) -> list[tuple[float, str]]:
    if not mirror:
        return [(1.0, bone)]
    return [(1.0, bone.replace("#", "L")), (-1.0, bone.replace("#", "R"))]


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _lerp(a: Vec, b: Vec, t: float) -> Vec:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


# Joints, for the left side (x > 0).
SCAPULA_TOP: Vec = (0.052, 0.13, 0.622)
SHOULDER: Vec = (0.08, 0.25, 0.455)
ELBOW: Vec = (0.076, 0.165, 0.31)
WRIST: Vec = (0.07, 0.185, 0.1)
FORE_BALL: Vec = (0.07, 0.207, 0.032)
FORE_TOE: Vec = (0.07, 0.25, 0.016)
HIP: Vec = (0.076, -0.31, 0.51)
STIFLE: Vec = (0.088, -0.2, 0.33)
HOCK: Vec = (0.08, -0.37, 0.15)
HIND_BALL: Vec = (0.076, -0.342, 0.032)
HIND_TOE: Vec = (0.076, -0.298, 0.016)
#: The atlas joint (where the head turns on the neck) and the head's carriage: low, nose about level with the withers.
ATLAS: Vec = (0.0, 0.37, 0.715)
HEAD_PITCH = -0.33
TAIL: list[Vec] = [
    (0.0, -0.37, 0.552),
    (0.0, -0.45, 0.52),
    (0.0, -0.51, 0.452),
    (0.0, -0.545, 0.372),
    (0.0, -0.556, 0.292),
]


def feral_dog(lean: float = 1.0) -> Body:
    """The dog at a withers height of about 0.62 m; `lean` (0..1) is how much bone shows."""
    b = Body()
    # The skeleton.
    b.bone("root", (0.0, -0.06, 0.0), (0.0, 0.1, 0.0), None)
    b.bone("spine1", (0.0, -0.22, 0.56), (0.0, -0.02, 0.57), "root")
    b.bone("pelvis", (0.0, -0.22, 0.56), (0.0, -0.37, 0.535), "spine1")
    b.bone("spine2", (0.0, -0.02, 0.57), (0.0, 0.18, 0.6), "spine1")
    b.bone("neck", (0.0, 0.2, 0.6), ATLAS, "spine2")
    for i in range(4):
        b.bone(f"tail{i + 1}", TAIL[i], TAIL[i + 1], "pelvis" if i == 0 else f"tail{i}")
    b.bone("scapula.#", SCAPULA_TOP, SHOULDER, "spine2", mirror=True)
    b.bone("upperarm.#", SHOULDER, ELBOW, "scapula.#", mirror=True)
    b.bone("forearm.#", ELBOW, WRIST, "upperarm.#", mirror=True)
    b.bone("forepaw.#", WRIST, FORE_BALL, "forearm.#", mirror=True)
    b.bone("foretoe.#", FORE_BALL, FORE_TOE, "forepaw.#", mirror=True)
    b.bone("thigh.#", HIP, STIFLE, "pelvis", mirror=True)
    b.bone("shin.#", STIFLE, HOCK, "thigh.#", mirror=True)
    b.bone("hindpaw.#", HOCK, HIND_BALL, "shin.#", mirror=True)
    b.bone("hindtoe.#", HIND_BALL, HIND_TOE, "hindpaw.#", mirror=True)

    # Trunk: a deep, narrow ribcage, deepest at the elbow and rising to a tucked-up loin; the croup.
    b.blob((0.0, 0.06, 0.505), (0.092, 0.19, 0.138), "spine2", 0.05, along=(0.0, 1.0, -0.22))
    b.blob((0.0, 0.235, 0.462), (0.066, 0.06, 0.088), "spine2", 0.05)  # the brisket, in front of the legs
    b.cone((0.0, -0.3, 0.572), (0.0, -0.04, 0.585), 0.055, 0.058, "spine1", 0.04)
    b.cone((0.0, -0.04, 0.585), (0.0, 0.17, 0.61), 0.058, 0.055, "spine2", 0.04)
    b.blob((0.0, -0.13, 0.555), (0.07, 0.13, 0.062), "spine1", 0.05)
    b.blob((0.0, -0.29, 0.54), (0.086, 0.1, 0.08), "pelvis", 0.05)
    # Bones under the skin: spine knobs, hip points, pin bones, the withers.
    knobs = 11
    for i in range(knobs):
        t = i / (knobs - 1)
        y = -0.27 + 0.42 * t
        z = 0.624 + 0.02 * t + 0.006 * np.sin(t * np.pi)
        b.blob((0.0, y, z), (0.0085, 0.01, 0.009 * lean), "spine1" if y < -0.02 else "spine2", 0.012)
    b.blob((0.052, -0.245, 0.598), (0.017 * lean, 0.022, 0.016), "pelvis", 0.025, mirror=True)
    b.blob((0.03, -0.355, 0.568), (0.015, 0.02, 0.014), "pelvis", 0.02, mirror=True)
    b.blob((0.028, 0.15, 0.63), (0.016, 0.05, 0.016), "spine2", 0.025, mirror=True)

    # Hind legs: a broad haunch down to the stifle, the second thigh, a slim shin, the hock, a long metatarsus.
    thigh = _sub(STIFLE, HIP)
    b.blob(
        _lerp(HIP, STIFLE, 0.5),
        (0.048, 0.135, 0.078),
        "thigh.#",
        0.045,
        along=thigh,
        third=(0.0, -1.0, 0.25),
        mirror=True,
    )
    b.blob(
        _lerp(HIP, STIFLE, 0.2),
        (0.042, 0.08, 0.075),
        "thigh.#",
        0.04,
        along=thigh,
        third=(0.0, -1.0, 0.0),
        mirror=True,
    )
    shin = _sub(HOCK, STIFLE)
    b.blob(
        _lerp(STIFLE, HOCK, 0.22),
        (0.032, 0.09, 0.052),
        "shin.#",
        0.035,
        along=shin,
        third=(0.0, -1.0, 0.4),
        mirror=True,
    )
    # The fold of the flank: skin from the tuck-up to the stifle.
    b.blob(
        (0.055, -0.19, 0.435),
        (0.035, 0.05, 0.075),
        "thigh.#",
        0.05,
        along=(0.0, 0.2, -1.0),
        third=(0.0, 1.0, 0.0),
        mirror=True,
    )
    b.cone(STIFLE, HOCK, 0.03, 0.017, "shin.#", 0.025, mirror=True)
    b.cone(
        _lerp(STIFLE, HOCK, 0.35),
        (HOCK[0], HOCK[1] - 0.016, HOCK[2] + 0.01),
        0.012,
        0.012,
        "shin.#",
        0.02,
        mirror=True,
    )
    b.blob((HOCK[0], HOCK[1] - 0.008, HOCK[2]), (0.016, 0.02, 0.02), "shin.#", 0.012, mirror=True)
    b.cone(HOCK, HIND_BALL, 0.017, 0.016, "hindpaw.#", 0.014, mirror=True)
    _paw(b, HIND_BALL, "hindtoe.#")

    # Front legs: the shoulder blade, upper arm and triceps, the point of the elbow, a straight forearm.
    scap = _sub(SHOULDER, SCAPULA_TOP)
    b.blob(
        _lerp(SCAPULA_TOP, SHOULDER, 0.45),
        (0.03, 0.11, 0.062),
        "scapula.#",
        0.04,
        along=scap,
        third=(0.0, -1.0, 0.0),
        mirror=True,
    )
    arm = _sub(ELBOW, SHOULDER)
    b.cone(SHOULDER, ELBOW, 0.042, 0.032, "upperarm.#", 0.035, mirror=True)
    b.blob(
        _lerp(SHOULDER, ELBOW, 0.55),
        (0.034, 0.072, 0.04),
        "upperarm.#",
        0.03,
        along=arm,
        third=(0.0, -1.0, -0.3),
        mirror=True,
    )
    b.blob(
        (ELBOW[0], ELBOW[1] - 0.018, ELBOW[2] + 0.005), (0.02, 0.022, 0.02), "forearm.#", 0.015, mirror=True
    )
    b.cone(ELBOW, WRIST, 0.028, 0.018, "forearm.#", 0.025, mirror=True)
    b.blob(
        (WRIST[0], WRIST[1] - 0.012, WRIST[2] + 0.005), (0.012, 0.012, 0.014), "forearm.#", 0.01, mirror=True
    )
    b.cone(WRIST, FORE_BALL, 0.017, 0.016, "forepaw.#", 0.014, mirror=True)
    _paw(b, FORE_BALL, "foretoe.#")

    # Neck: thick, with a crest on top (the hackles stand here) and the throat below.
    b.cone((0.0, 0.17, 0.545), (0.0, 0.375, 0.69), 0.074, 0.054, "neck", 0.05)
    b.cone((0.0, 0.12, 0.628), (0.0, 0.35, 0.745), 0.044, 0.034, "neck", 0.045)
    b.blob((0.0, 0.31, 0.64), (0.042, 0.06, 0.036), "neck", 0.04, along=(0.0, 0.7, 0.7))

    _head(b)

    radii = [0.032, 0.03, 0.026, 0.021, 0.013]
    for i in range(4):
        b.cone(TAIL[i], TAIL[i + 1], radii[i], radii[i + 1], f"tail{i + 1}", 0.02)
    return b


def _head(b: Body) -> None:
    """The head, in its own frame: origin at the atlas, +Y along the skull to the nose."""
    b.frame(ATLAS, HEAD_PITCH)
    b.bone("head", (0.0, 0.0, 0.0), (0.0, 0.12, 0.03), "neck")
    b.bone("jaw", (0.0, 0.06, -0.035), (0.0, 0.215, -0.045), "head")
    b.bone("ear.#", (0.034, 0.045, 0.05), (0.052, 0.03, 0.12), "head", mirror=True)
    # Cranium, the crest at the back, the cheekbones flaring, the jaw muscles, the brow.
    b.blob((0.0, 0.055, 0.018), (0.048, 0.062, 0.044), "head", 0.03)
    b.blob((0.0, 0.025, 0.048), (0.012, 0.035, 0.014), "head", 0.02)
    b.blob((0.042, 0.088, -0.006), (0.017, 0.036, 0.018), "head", 0.02, mirror=True)
    b.blob((0.036, 0.062, -0.03), (0.024, 0.04, 0.03), "head", 0.025, mirror=True)
    b.blob((0.024, 0.118, 0.028), (0.017, 0.016, 0.011), "head", 0.015, mirror=True)
    # The muzzle: deep at the stop, narrowing to the nose; the nose leather; the flews hanging over the jaw.
    b.cone((0.0, 0.12, 0.002), (0.0, 0.212, -0.01), 0.031, 0.021, "head", 0.025)
    b.blob((0.0, 0.16, -0.008), (0.03, 0.058, 0.027), "head", 0.02)
    b.blob((0.0, 0.223, -0.004), (0.018, 0.012, 0.015), "head", 0.006)
    b.blob((0.019, 0.155, -0.03), (0.015, 0.062, 0.016), "head", 0.012, mirror=True)
    # The lower jaw: narrower, inside the flews; the chin.
    b.cone((0.0, 0.07, -0.046), (0.0, 0.205, -0.045), 0.021, 0.012, "jaw", 0.012)
    b.blob((0.0, 0.17, -0.056), (0.014, 0.04, 0.01), "jaw", 0.012)
    # The mouth: a slit from the corners to the front, so the jaw can open.
    b.blob((0.0, 0.16, -0.035), (0.04, 0.075, 0.0045), "head", 0.003, carve=True)
    # Eye sockets, and the eyes set in them, looking forward and a little out.
    for s in (1.0, -1.0):
        b.blob((0.03 * s, 0.112, 0.012), (0.012, 0.012, 0.011), "head", 0.004, carve=True)
        b.eyes.append((b.at((0.029 * s, 0.111, 0.012)), 0.0105))
    # Ears: pricked, broad at the base, turned a little out.
    b.ear((0.034, 0.045, 0.05), (0.052, 0.03, 0.122), 0.03, 0.005, (0.35, 1.0, 0.0), "ear.#")
    for s in (1.0, -1.0):
        b.teeth.append((b.at((0.014 * s, 0.205, -0.032)), b.at((0.015 * s, 0.208, -0.046)), 0.0042, "head"))
        b.teeth.append((b.at((0.012 * s, 0.192, -0.044)), b.at((0.013 * s, 0.19, -0.031)), 0.0036, "jaw"))
    b.frame()


def _paw(b: Body, ball: Vec, bone: str) -> None:
    """A paw: the pad under the ball, four toes fanned in front."""
    b.blob((ball[0], ball[1] + 0.012, 0.022), (0.026, 0.032, 0.02), bone, 0.015, mirror=True)
    for dx, dy in ((-0.016, 0.03), (-0.006, 0.038), (0.006, 0.038), (0.016, 0.03)):
        b.blob((ball[0] + dx, ball[1] + dy, 0.014), (0.0095, 0.012, 0.012), bone, 0.007, mirror=True)
