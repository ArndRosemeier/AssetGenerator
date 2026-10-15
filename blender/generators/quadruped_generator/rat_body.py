"""The quarry rat's body and coat: its skeleton, the shapes sculpted round it, where its fur stands and
what colour it is.

Same axes and bone names as the dog (anatomy.py), so the same posing and clip machinery drives it:
+Y forward, +Z up, +X its left, metres. The rat is a big one, about 0.42 m from nose to rump and
0.2 m high at the arch of its back: a fat, pear-shaped body low on short legs, the haunches heavier
than the shoulders, a long tapering snout with orange incisors, round naked ears and a long naked
scaly tail. Its coat is a coarse grizzled brown, darker down the back, grey underneath, with the
guard hairs standing off the back and haunches.
"""

from __future__ import annotations

import numpy as np

from blender.generators.quadruped_generator.anatomy import Body, _lerp, _sub
from blender.generators.quadruped_generator.coat import Noise, Palette, hair_coords, head_local, smooth
from blender.generators.quadruped_generator.sdf import Vec

# Joints, for the left side (x > 0).
SCAPULA_TOP: Vec = (0.028, 0.06, 0.15)
SHOULDER: Vec = (0.042, 0.1, 0.085)
ELBOW: Vec = (0.045, 0.066, 0.05)
WRIST: Vec = (0.043, 0.095, 0.016)
FORE_BALL: Vec = (0.043, 0.108, 0.006)
FORE_TOE: Vec = (0.043, 0.126, 0.003)
HIP: Vec = (0.045, -0.13, 0.105)
STIFLE: Vec = (0.062, -0.075, 0.06)
HOCK: Vec = (0.054, -0.155, 0.028)
HIND_BALL: Vec = (0.054, -0.1, 0.006)
HIND_TOE: Vec = (0.054, -0.074, 0.003)
ATLAS: Vec = (0.0, 0.15, 0.13)
HEAD_PITCH = -0.3
#: The tail: up off the rump and down to trail along the ground.
TAIL: list[Vec] = [
    (0.0, -0.2, 0.1),
    (0.0, -0.245, 0.078),
    (0.0, -0.292, 0.055),
    (0.0, -0.34, 0.036),
    (0.0, -0.39, 0.022),
    (0.0, -0.44, 0.014),
    (0.0, -0.49, 0.01),
    (0.0, -0.54, 0.008),
    (0.0, -0.585, 0.007),
]
TAIL_RADII = [0.017, 0.0135, 0.011, 0.009, 0.0075, 0.0062, 0.005, 0.0039, 0.003]
#: How softly each bone's weight falls off (skin.py); the tail's bones are short, so tighter than the dog's default.
SOFTNESS = {"jaw": 0.0015, "head": 0.004, "ear.L": 0.002, "ear.R": 0.002, "neck": 0.008}
DEFAULT_SOFTNESS = 0.011


def quarry_rat(fat: float = 1.0) -> Body:
    """The rat; `fat` (about 0.8..1.3) is how heavy the body is."""
    b = Body()
    b.bone("root", (0.0, -0.05, 0.0), (0.0, 0.05, 0.0), None)
    b.bone("spine1", (0.0, -0.12, 0.14), (0.0, 0.0, 0.16), "root")
    b.bone("pelvis", (0.0, -0.12, 0.14), (0.0, -0.2, 0.105), "spine1")
    b.bone("spine2", (0.0, 0.0, 0.16), (0.0, 0.09, 0.14), "spine1")
    b.bone("neck", (0.0, 0.09, 0.14), ATLAS, "spine2")
    for i in range(len(TAIL) - 1):
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

    w = fat
    # The trunk: heavy rump, the loin arching over it, a sagging belly, the ribcage, narrower shoulders.
    b.blob((0.0, -0.15, 0.104), (0.064 * w, 0.075, 0.068), "pelvis", 0.04)
    b.blob((0.0, -0.065, 0.118), (0.07 * w, 0.085, 0.074), "spine1", 0.04)
    b.blob((0.0, -0.05, 0.078), (0.062 * w, 0.085, 0.048 * w), "spine1", 0.04)
    b.blob((0.0, 0.035, 0.106), (0.054 * w, 0.078, 0.062), "spine2", 0.04)
    b.blob((0.0, 0.08, 0.098), (0.044, 0.05, 0.05), "spine2", 0.035)
    # Hind legs: the thighs bulging off the rump, a slim shin, the long hind foot.
    thigh = _sub(STIFLE, HIP)
    b.blob(_lerp(HIP, STIFLE, 0.4), (0.03, 0.055, 0.045), "thigh.#", 0.03, along=thigh, mirror=True)
    b.cone(STIFLE, HOCK, 0.019, 0.01, "shin.#", 0.02, mirror=True)
    b.cone(HOCK, HIND_BALL, 0.0095, 0.0085, "hindpaw.#", 0.008, mirror=True)
    _toes(b, HIND_BALL, "hindtoe.#", 0.024, 0.0042)
    # Front legs: short, mostly inside the body; thin wrists, small hands.
    b.blob(
        _lerp(SCAPULA_TOP, SHOULDER, 0.5),
        (0.02, 0.045, 0.03),
        "scapula.#",
        0.03,
        along=_sub(SHOULDER, SCAPULA_TOP),
        mirror=True,
    )
    b.cone(SHOULDER, ELBOW, 0.021, 0.014, "upperarm.#", 0.025, mirror=True)
    b.cone(ELBOW, WRIST, 0.012, 0.0075, "forearm.#", 0.012, mirror=True)
    b.cone(WRIST, FORE_BALL, 0.0075, 0.0068, "forepaw.#", 0.006, mirror=True)
    _toes(b, FORE_BALL, "foretoe.#", 0.017, 0.0033)
    # The neck: thick and short, the head carried low.
    b.cone((0.0, 0.07, 0.112), (0.0, 0.155, 0.125), 0.05, 0.034, "neck", 0.04)
    _head(b)
    for i in range(len(TAIL) - 1):
        b.cone(
            TAIL[i], TAIL[i + 1], TAIL_RADII[i], TAIL_RADII[i + 1], f"tail{i + 1}", 0.012 if i == 0 else 0.004
        )
    return b


def _head(b: Body) -> None:
    """The head, in its own frame: origin at the atlas, +Y along the skull to the nose."""
    b.frame(ATLAS, HEAD_PITCH)
    b.bone("head", (0.0, 0.0, 0.0), (0.0, 0.08, 0.0), "neck")
    b.bone("jaw", (0.0, 0.03, -0.022), (0.0, 0.1, -0.032), "head")
    b.bone("ear.#", (0.024, 0.012, 0.022), (0.034, 0.004, 0.048), "head", mirror=True)
    # Skull, the long snout tapering to the nose, the whisker pads either side, the nose leather.
    b.blob((0.0, 0.022, 0.006), (0.033, 0.045, 0.03), "head", 0.03)
    b.cone((0.0, 0.045, -0.002), (0.0, 0.122, -0.016), 0.024, 0.0082, "head", 0.022)
    b.blob((0.011, 0.095, -0.017), (0.0115, 0.024, 0.011), "head", 0.012, mirror=True)
    b.blob((0.0, 0.128, -0.015), (0.0072, 0.0058, 0.0064), "head", 0.004)
    # The lower jaw, small and set back; the chin.
    b.cone((0.0, 0.03, -0.024), (0.0, 0.103, -0.032), 0.012, 0.0055, "jaw", 0.01)
    b.blob((0.0, 0.085, -0.035), (0.0075, 0.02, 0.006), "jaw", 0.008)
    # The mouth, a slit under the snout so the jaw can drop.
    b.blob((0.0, 0.092, -0.026), (0.015, 0.038, 0.0022), "head", 0.002, carve=True)
    # Eyes: small and beady, set high on the side of the head.
    for s in (1.0, -1.0):
        b.blob((0.021 * s, 0.058, 0.009), (0.0072, 0.0072, 0.0068), "head", 0.003, carve=True)
        b.eyes.append((b.at((0.0205 * s, 0.058, 0.009)), 0.0062))
    # Ears: round, thin and naked, cupped forward.
    b.ear((0.024, 0.012, 0.022), (0.034, 0.004, 0.044), 0.011, 0.0155, (0.55, 1.0, 0.1), "ear.#", 0.005)
    # The incisors: long, orange, two up and two down at the front of the mouth.
    for s in (1.0, -1.0):
        b.teeth.append((b.at((0.0028 * s, 0.116, -0.021)), b.at((0.0028 * s, 0.12, -0.034)), 0.0026, "head"))
        b.teeth.append((b.at((0.0025 * s, 0.096, -0.037)), b.at((0.0025 * s, 0.108, -0.029)), 0.0021, "jaw"))
    b.frame()


def _toes(b: Body, ball: Vec, bone: str, reach: float, r: float) -> None:
    """A rat's hand or foot: a pad and slender toes spread in front."""
    b.blob((ball[0], ball[1] + reach * 0.2, 0.004), (r * 2.2, reach * 0.4, r * 1.2), bone, 0.006, mirror=True)
    for dx, k in ((-1.6, 0.8), (-0.55, 1.0), (0.55, 1.0), (1.6, 0.8)):
        tip = (ball[0] + dx * r * 1.6, ball[1] + reach * k, 0.0025)
        b.cone(
            (ball[0] + dx * r * 0.7, ball[1] + reach * 0.3, 0.004),
            tip,
            r * 0.75,
            r * 0.5,
            bone,
            0.003,
            mirror=True,
        )


# --- The coat -----------------------------------------------------------------------------------


def _head_mask(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h = head_local(p, ATLAS, HEAD_PITCH)
    on_head = smooth(-0.01, 0.02, h[:, 1]) * smooth(0.06, 0.04, np.abs(h[:, 0]))
    return h, on_head


def _skin(p: np.ndarray, n: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Soft masks of the naked parts: the tail, the ears, the hands and feet, the nose; and the head."""
    h, on_head = _head_mask(p)
    tail = smooth(-0.205, -0.225, p[:, 1]) * smooth(0.03, 0.02, np.abs(p[:, 0]))
    ear = on_head * smooth(0.024, 0.03, h[:, 2]) * smooth(0.016, 0.022, np.abs(h[:, 0]))
    paws = smooth(0.022, 0.012, p[:, 2]) * (1.0 - tail)
    nose = on_head * smooth(0.119, 0.125, h[:, 1])
    return tail, ear, paws, nose, on_head


def hair_flow(p: np.ndarray) -> np.ndarray:
    """Back along the body and head, down the legs, along the tail."""
    leg = smooth(0.06, 0.03, p[:, 2])[:, None]
    body = np.array([0.0, -1.0, -0.3])[None, :]
    legs = np.array([0.0, -0.3, -1.0])[None, :]
    flow = body + (legs - body) * leg
    return flow / np.linalg.norm(flow, axis=1, keepdims=True)


def hair(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The bake's strand and tuft coordinates: fine hair on the body; on the tail, rings of scales instead."""
    flow = hair_flow(p)
    strands = hair_coords(p, 60.0, 480.0, flow)
    tufts = hair_coords(p, 20.0, 140.0, flow)
    tail = smooth(-0.21, -0.23, p[:, 1])[:, None]
    # Across the tail: the noise varies fast along it (one ring every couple of millimetres) and slowly round it.
    rings = np.stack([p[:, 0] * 40.0, p[:, 1] * 450.0, p[:, 2] * 40.0], axis=1)
    strands = strands + (rings - strands) * tail
    tufts = tufts + (rings * 0.5 - tufts) * tail
    return strands, tufts


def fur_offsets(p: np.ndarray, n: np.ndarray, noise: Noise, length: float) -> np.ndarray:
    """The guard hairs standing off the back and the rump, in ragged clumps; nothing on the naked parts."""
    tail, ear, paws, nose, on_head = _skin(p, n)
    up = n[:, 2]
    back = smooth(-0.2, 0.6, up) * smooth(0.05, 0.1, p[:, 2])
    rump = smooth(-0.07, -0.15, p[:, 1])
    ridged = 1.0 - np.abs(2.0 * noise.fbm(hair_coords(p, 30.0, 140.0, hair_flow(p)), 3) - 1.0)
    clumps = ridged**3.0
    reach = (0.8 * back + 0.5 * rump + 0.25) * (1.0 - 0.7 * on_head)
    reach *= np.clip(1.0 - tail - ear - paws - nose, 0.0, 1.0)
    return length * reach * (0.15 + 0.85 * clumps) * (0.6 + 0.8 * noise.fbm(p * 60.0 + 5.0, 2))


def coat_colours(p: np.ndarray, n: np.ndarray, noise: Noise, pal: Palette, mange: float) -> np.ndarray:
    """Grizzled brown (pale-tipped hairs), dark down the spine, grey underneath; pink naked skin
    (`mask` in the palette), a darker nose; scabby patches; grime on the feet and under the tail."""
    tail, ear, paws, nose, on_head = _skin(p, n)

    def c(rgb: tuple[float, float, float]) -> np.ndarray:
        return np.asarray(rgb, dtype=float)[None, :]

    def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
        return a + (b - a) * np.clip(t, 0.0, 1.0)[:, None]

    up = n[:, 2]
    wobble = noise.fbm(p * 30.0, 3)
    col = np.repeat(c(pal.coat), len(p), axis=0)
    col = mix(col, c(pal.pale), smooth(-0.2, -0.7, up + 0.3 * (wobble - 0.5)) * (1.0 - on_head * 0.5))
    col = mix(col, c(pal.saddle), smooth(0.45, 0.9, up + 0.3 * (wobble - 0.5)) * smooth(0.09, 0.14, p[:, 2]))
    # Grizzle: pale-tipped guard hairs scattered through the brown.
    grizzle = smooth(0.6, 0.72, noise.fbm(p * 420.0 + 3.0, 2))
    col = mix(col, col * 1.9 + 0.02, grizzle * 0.6 * (1.0 - tail))
    # The naked parts: pink-grey skin, the tail darker towards its root and ringed; a darker nose.
    skin = np.clip(tail + ear + paws, 0.0, 1.0)
    skin_col = c(pal.mask) * (0.85 + 0.3 * noise.fbm(p * 80.0, 2))[:, None]
    tail_root = smooth(-0.32, -0.22, p[:, 1]) * tail
    skin_col = mix(skin_col, skin_col * 0.55, tail_root)
    rings = 0.5 + 0.5 * np.cos(p[:, 1] * (2.0 * np.pi / 0.0045))
    skin_col = mix(skin_col, skin_col * 0.7, tail * smooth(0.6, 0.95, rings))
    col = mix(col, skin_col, skin)
    col = mix(col, c(pal.nose), nose)
    if mange > 0:
        bald = smooth(0.66, 0.74, noise.fbm(p * 22.0 + 31.0, 3)) * (1.0 - on_head) * (1.0 - skin) * mange
        col = mix(col, c(pal.mange), bald)
    # Grime: the feet, the belly where it drags, the underside of the tail root.
    col = mix(col, c(pal.dirt), smooth(0.03, 0.008, p[:, 2]) * (0.5 + 0.5 * wobble))
    col *= (0.84 + 0.32 * noise.fbm(p * 300.0, 2))[:, None]
    return np.clip(col, 0.0, 1.0)
