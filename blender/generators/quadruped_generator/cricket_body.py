"""The cave cricket's body and shell: a pale, humped, dog-sized cricket with great folded hind legs
and feelers longer than its body.

Same axes and bone naming as the dog (anatomy.py): +Y forward, +Z up, +X its left, metres. Its six
legs are `fore`, `mid` and `hind` (pose.LEGS), their knees pointing up and out (`Body.poles`). The
thorax is `spine2`, the joint behind it `spine1`, the abdomen `pelvis`; the head hangs face down
from `neck`, with its mouthparts on `jaw` and the feelers' bases on `ear.#`, each feeler a chain
`feeler1.#`.. down to its tip. Feelers, palps, cerci and the spines of the hind legs are too thin to
sculpt on the grid, so they are made as cones (Body.teeth: the `teeth` material), each rigid on its
bone.
"""

from __future__ import annotations

import math

import numpy as np

from blender.generators.quadruped_generator.anatomy import Body, Bone, _lerp, _sub
from blender.generators.quadruped_generator.coat import Noise, Palette, hair_coords, head_local, smooth
from blender.generators.quadruped_generator.sdf import Vec

# Legs, for the left side (x > 0): hip, knee, ankle, the ball of the foot, the claw.
FORE = [
    (0.035, 0.13, 0.17),
    (0.105, 0.2, 0.2),
    (0.125, 0.25, 0.03),
    (0.125, 0.27, 0.007),
    (0.125, 0.295, 0.003),
]
MID = [
    (0.045, 0.06, 0.16),
    (0.15, 0.08, 0.2),
    (0.195, 0.04, 0.03),
    (0.195, 0.02, 0.007),
    (0.195, -0.005, 0.003),
]
HIND = [
    (0.085, -0.02, 0.17),
    (0.175, -0.29, 0.39),
    (0.19, -0.12, 0.03),
    (0.19, -0.18, 0.007),
    (0.19, -0.215, 0.003),
]
ATLAS: Vec = (0.0, 0.17, 0.235)
HEAD_PITCH = -1.15
#: The feelers: their base on the head (in its frame), then (in the world, up and out, the tips
#: dropping) each joint from the one before. Kept off the ground at rest: that is the model's footprint.
FEELER = [(0.02, 0.055, 0.06), (0.06, 0.12, 0.24)]
FEELER_ON = [(0.06, 0.15, 0.1), (0.08, 0.13, 0.04), (0.07, 0.1, -0.03), (0.06, 0.08, -0.07)]
SOFTNESS = {"jaw": 0.002, "head": 0.004, "neck": 0.006}
DEFAULT_SOFTNESS = 0.006


def cave_cricket(bulk: float = 1.0) -> Body:
    """The cricket; `bulk` (about 0.8..1.3) is how swollen its abdomen is."""
    b = Body()
    b.poles = {"fore": (0.7, 0.2, 1.0), "mid": (0.8, 0.0, 1.0), "hind": (0.3, -0.6, 1.0)}
    b.bone("root", (0.0, -0.05, 0.0), (0.0, 0.05, 0.0), None)
    b.bone("spine1", (0.0, -0.02, 0.245), (0.0, 0.05, 0.25), "root")
    b.bone("pelvis", (0.0, -0.02, 0.245), (0.0, -0.36, 0.25), "spine1")
    b.bone("spine2", (0.0, 0.05, 0.25), (0.0, 0.15, 0.24), "spine1")
    b.bone("neck", (0.0, 0.15, 0.24), ATLAS, "spine2")
    for kind, j, names in (
        ("fore", FORE, ("upperarm", "forearm", "forepaw", "foretoe")),
        ("mid", MID, ("midfemur", "midtibia", "midtarsus", "midtoe")),
        ("hind", HIND, ("thigh", "shin", "hindpaw", "hindtoe")),
    ):
        parent = "pelvis" if kind == "hind" else "spine2"
        for i, n in enumerate(names):
            b.bone(f"{n}.#", j[i], j[i + 1], parent if i == 0 else f"{names[i - 1]}.#", mirror=True)

    w = bulk
    # The abdomen: a great hump of overlapping plates, highest in the middle, tapering to the cerci.
    plates = 6
    for i in range(plates):
        t = i / (plates - 1)
        y = -0.03 - 0.31 * t
        r = math.sin(math.pi * (0.25 + 0.7 * t))
        z = 0.24 + 0.05 * r
        b.blob(
            (0.0, y, z), (0.115 * w * (0.55 + 0.45 * r), 0.055, 0.12 * w * (0.5 + 0.5 * r)), "pelvis", 0.012
        )
    # The thorax under its saddle-shaped shield, the shield's lip over the neck.
    b.blob((0.0, 0.08, 0.22), (0.075, 0.085, 0.065), "spine2", 0.03)
    b.blob((0.0, 0.085, 0.26), (0.085, 0.09, 0.055), "spine2", 0.012, along=(0.0, 1.0, -0.15))
    b.blob((0.0, 0.0, 0.22), (0.07, 0.04, 0.07), "spine1", 0.03)
    # Legs: thin fore and mid legs; the hind femurs great drumsticks of muscle, the tibiae long and thin.
    for j, r0, r1, rt, bones in (
        (FORE, 0.014, 0.01, 0.0065, ("upperarm.#", "forearm.#", "forepaw.#")),
        (MID, 0.015, 0.011, 0.0065, ("midfemur.#", "midtibia.#", "midtarsus.#")),
    ):
        b.cone(j[0], j[1], r0, r1, bones[0], 0.012, mirror=True)
        b.cone(j[1], j[2], r1 * 0.75, rt, bones[1], 0.006, mirror=True)
        b.cone(j[2], j[3], rt, rt * 0.8, bones[2], 0.004, mirror=True)
    femur = _sub(HIND[1], HIND[0])
    b.blob(
        _lerp(HIND[0], HIND[1], 0.4),
        (0.042, 0.15, 0.056),
        "thigh.#",
        0.015,
        along=femur,
        third=(0.3, 0.4, 1.0),
        mirror=True,
    )
    b.cone(HIND[0], HIND[1], 0.03, 0.016, "thigh.#", 0.015, mirror=True)
    b.cone(HIND[1], HIND[2], 0.012, 0.008, "shin.#", 0.006, mirror=True)
    b.cone(HIND[2], HIND[3], 0.0075, 0.0065, "hindpaw.#", 0.004, mirror=True)
    # Spines down the back of the hind tibiae, in pairs.
    for k in range(7):
        t = 0.15 + 0.11 * k
        p = _lerp(HIND[1], HIND[2], t)
        for dx in (-0.006, 0.006):
            root = (p[0] + dx, p[1] - 0.006, p[2])
            b.teeth.append((root, (root[0] + dx * 1.5, root[1] - 0.022, root[2] + 0.012), 0.0022, "shin.L"))
            mr = (-root[0], root[1], root[2])
            b.teeth.append((mr, (-root[0] - dx * 1.5, root[1] - 0.022, root[2] + 0.012), 0.0022, "shin.R"))
    # The cerci at the tip of the abdomen.
    for s in (1.0, -1.0):
        b.teeth.append(((0.02 * s, -0.36, 0.25), (0.05 * s, -0.43, 0.29), 0.006, "pelvis"))
    _head(b)
    return b


def _head(b: Body) -> None:
    """The head, hanging face down from the shield: +Y in its frame runs down the face to the mouth."""
    b.frame(ATLAS, HEAD_PITCH)
    b.bone("head", (0.0, 0.0, 0.0), (0.0, 0.09, 0.0), "neck")
    b.bone("jaw", (0.0, 0.09, -0.01), (0.0, 0.13, -0.015), "head")
    b.bone("ear.#", (0.02, 0.055, 0.06), (0.03, 0.07, 0.1), "head", mirror=True)
    # The head capsule, smooth and rounded; the face.
    b.blob((0.0, 0.05, 0.005), (0.06, 0.07, 0.058), "head", 0.025)
    b.blob((0.0, 0.085, 0.02), (0.045, 0.04, 0.035), "head", 0.02)
    # Mouthparts: the labrum and the mandibles under it.
    b.blob((0.0, 0.122, 0.01), (0.03, 0.018, 0.016), "head", 0.008)
    b.blob((0.016, 0.125, -0.008), (0.014, 0.02, 0.012), "jaw", 0.006, mirror=True)
    # Small dark eyes high on the sides.
    for s in (1.0, -1.0):
        b.blob((0.05 * s, 0.05, 0.03), (0.013, 0.016, 0.012), "head", 0.004, carve=True)
        b.eyes.append((b.at((0.049 * s, 0.05, 0.03)), 0.012))
    # Palps: two pairs, hanging from the mouth.
    for s in (1.0, -1.0):
        b.teeth.append((b.at((0.022 * s, 0.13, -0.004)), b.at((0.03 * s, 0.17, -0.03)), 0.005, "jaw"))
        b.teeth.append((b.at((0.03 * s, 0.17, -0.03)), b.at((0.034 * s, 0.2, -0.016)), 0.0042, "jaw"))
    # The feelers: their bones, and a cone along each.
    pts = [b.at(p) for p in FEELER]
    b.frame()
    for d in FEELER_ON:
        pts.append(tuple(a + e for a, e in zip(pts[-1], d, strict=True)))
    for side, s in (("L", 1.0), ("R", -1.0)):
        q = [(p[0] * s, p[1], p[2]) for p in pts]
        for i in range(len(q) - 1):
            name = f"feeler{i + 1}.{side}"
            b.bones.append(Bone(name, q[i], q[i + 1], f"ear.{side}" if i == 0 else f"feeler{i}.{side}"))
            r0 = 0.0055 * (1.0 - i / len(q)) + 0.0015
            b.teeth.append((q[i], q[i + 1], r0, name))


# --- The shell ----------------------------------------------------------------------------------


def hair(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The bake's grain: a fine pebbling of the shell, finer still on the legs, no strands."""
    flow = np.repeat(np.array([[0.0, -1.0, 0.0]]), len(p), axis=0)
    return hair_coords(p, 300.0, 300.0, flow), hair_coords(p, 90.0, 90.0, flow)


def fur_offsets(p: np.ndarray, n: np.ndarray, noise: Noise, length: float) -> np.ndarray:
    """A shell has nothing standing off it: only the faintest unevenness."""
    return length * (noise.fbm(p * 40.0, 2) - 0.5)


def coat_colours(p: np.ndarray, n: np.ndarray, noise: Noise, pal: Palette, mange: float) -> np.ndarray:
    """Pale and half translucent: `coat` the shell, `saddle` the mottling on top, `pale` underneath,
    `mask` the dark edges of the plates and the leg bands, `nose` the mouthparts, `dirt` on the feet."""

    def c(rgb: tuple[float, float, float]) -> np.ndarray:
        return np.asarray(rgb, dtype=float)[None, :]

    def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
        return a + (b - a) * np.clip(t, 0.0, 1.0)[:, None]

    up = n[:, 2]
    wobble = noise.fbm(p * 25.0, 3)
    col = np.repeat(c(pal.coat), len(p), axis=0)
    col = mix(col, c(pal.pale), smooth(-0.1, -0.6, up))
    # Mottled darker across the back.
    mottle = smooth(0.5, 0.7, noise.fbm(p * 18.0 + 7.0, 3))
    col = mix(col, c(pal.saddle), mottle * smooth(0.1, 0.6, up) * 0.8)
    # The back edge of each abdominal plate, dark.
    on_abdomen = smooth(-0.02, -0.06, p[:, 1]) * smooth(0.12, 0.16, p[:, 2])
    plate = ((-0.03 - p[:, 1]) / (0.31 / 5)) % 1.0
    col = mix(col, c(pal.mask), on_abdomen * smooth(0.55, 0.85, plate) * smooth(-0.3, 0.3, up))
    # Chevrons down the hind femurs (measured along each femur, mirrored).
    h = head_local(p, ATLAS, HEAD_PITCH)
    on_head = smooth(-0.01, 0.02, h[:, 1]) * smooth(0.08, 0.06, np.abs(h[:, 0])) * smooth(0.16, 0.2, p[:, 1])
    hip, knee = np.asarray(HIND[0]), np.asarray(HIND[1])
    axis = knee - hip
    q = np.column_stack((np.abs(p[:, 0]), p[:, 1], p[:, 2])) - hip
    t = q @ axis / (axis @ axis)
    off = np.linalg.norm(q - t[:, None] * axis[None, :], axis=1)
    femur = smooth(0.075, 0.06, off) * smooth(0.05, 0.12, t) * smooth(1.0, 0.9, t)
    chevron = 0.5 + 0.5 * np.sin(2 * np.pi * (6.0 * t + 12.0 * np.abs(q[:, 2] - t * axis[2])))
    col = mix(col, c(pal.mask), femur * smooth(0.55, 0.85, chevron) * 0.75)
    col = mix(col, c(pal.nose), on_head * smooth(0.1, 0.13, h[:, 1]))
    col = mix(col, c(pal.dirt), smooth(0.03, 0.005, p[:, 2]) * (0.5 + 0.5 * wobble))
    col *= (0.9 + 0.2 * noise.fbm(p * 200.0, 2))[:, None]
    return np.clip(col, 0.0, 1.0)
