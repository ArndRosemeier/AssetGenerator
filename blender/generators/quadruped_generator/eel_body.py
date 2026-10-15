"""The brine eel's body and skin: three metres of pale, slimy eel with a blunt head, an underslung
jaw full of needle teeth, milky eyes, and a fin running down its back into the tail.

Same axes as the dog (anatomy.py): +Y forward, +Z up, metres; it lies straight along -Y. The game
lays the body along the chain its sim keeps (src/creatures/eels.ts: `EEL.segments` points `EEL.link`
apart, the head first): `root` sits on the first point (it is the eel's place and heading), and
`body1`..`body9` each run from one point to the next, so the game turns each to its link. The
clips move only `head` and `jaw` (rearing, gaping, the strike); the body's swimming is the game's.
"""

from __future__ import annotations

import numpy as np

from blender.generators.quadruped_generator.anatomy import Body
from blender.generators.quadruped_generator.coat import Noise, Palette, hair_coords, smooth

#: The chain: how many points, how far apart (src/creatures/eels.ts EEL.segments, EEL.link).
POINTS = 10
LINK = 0.3
#: How high the spine runs (the sim's chain is the spine).
SPINE = 0.14

SOFTNESS = {"jaw": 0.004, "head": 0.01}
DEFAULT_SOFTNESS = 0.02


def thick(k: float) -> float:
    """The body's radius at chain point k (0 the head end)."""
    return 0.12 * (1.0 - 0.72 * (k / (POINTS - 1)) ** 1.3)


def brine_eel(bulk: float = 1.0) -> Body:
    """The eel; `bulk` (0.8..1.3) is how thick it is."""
    b = Body()
    z = SPINE
    b.bone("root", (0.0, 0.0, z), (0.0, 0.1, z), None)
    b.bone("head", (0.0, 0.0, z), (0.0, 0.3, z), "root")
    b.bone("jaw", (0.0, 0.06, z - 0.045), (0.0, 0.3, z - 0.06), "head")
    for k in range(1, POINTS):
        b.bone(
            f"body{k}", (0.0, -LINK * (k - 1), z), (0.0, -LINK * k, z), "root" if k == 1 else f"body{k - 1}"
        )

    # The body: one smooth taper, flattening a little from side to side towards the tail.
    for k in range(POINTS - 1):
        y0, y1 = -LINK * k, -LINK * (k + 1)
        b.cone((0.0, y0, z), (0.0, y1, z), thick(k) * bulk, thick(k + 1) * bulk, f"body{k + 1}", 0.05)
    # The tail: on past the last point, into a paddle.
    end = -LINK * (POINTS - 1)
    b.cone(
        (0.0, end, z),
        (0.0, end - 0.24, z + 0.01),
        thick(POINTS - 1) * bulk * 0.8,
        0.006,
        f"body{POINTS - 1}",
        0.03,
    )
    b.blob((0.0, end - 0.18, z + 0.01), (0.008, 0.2, 0.085), f"body{POINTS - 1}", 0.02)
    # The fin down the back, rising from behind the head and running into the tail.
    for k in range(1, POINTS):
        h = 0.015 + 0.05 * (k / (POINTS - 1)) ** 1.5
        b.blob(
            (0.0, -LINK * (k - 0.5), z + thick(k - 0.5) * bulk * 0.92),
            (0.006, LINK * 0.6, h),
            f"body{k}",
            0.02,
        )
    # And under the tail.
    for k in range(5, POINTS):
        b.blob(
            (0.0, -LINK * (k - 0.5), z - thick(k - 0.5) * bulk * 0.9),
            (0.006, LINK * 0.6, 0.025),
            f"body{k}",
            0.02,
        )
    # Pectoral fins behind the gills.
    for s in (1.0, -1.0):
        b.blob((0.13 * s, -0.1, z - 0.035), (0.05, 0.06, 0.007), "body1", 0.012, along=(0.5 * s, -1.0, -0.3))
    _head(b, z)
    return b


def _head(b: Body, z: float) -> None:
    # A blunt skull, the snout rounding off, cheeks swelling behind the eyes; a gill slit each side.
    b.blob((0.0, 0.06, z + 0.01), (0.115, 0.17, 0.1), "head", 0.04)
    b.blob((0.0, 0.2, z + 0.005), (0.08, 0.11, 0.07), "head", 0.03)
    for s in (1.0, -1.0):
        b.blob((0.085 * s, 0.03, z - 0.01), (0.04, 0.07, 0.05), "head", 0.025)
    # The underslung jaw, and the mouth's line between it and the skull.
    b.blob((0.0, 0.16, z - 0.06), (0.075, 0.14, 0.032), "jaw", 0.012)
    b.blob((0.0, 0.2, z - 0.03), (0.07, 0.13, 0.008), "head", 0.004, carve=True)
    # Milky eyes, high and forward.
    for s in (1.0, -1.0):
        b.blob((0.068 * s, 0.19, z + 0.04), (0.017, 0.017, 0.016), "head", 0.004, carve=True)
        b.eyes.append(((0.064 * s, 0.19, z + 0.04), 0.016))
    # Needle teeth along both jaws.
    for i in range(6):
        y = 0.27 - 0.035 * i
        w = 0.035 + 0.04 * (i / 5) ** 0.7
        for s in (1.0, -1.0):
            b.teeth.append(((w * s, y, z - 0.032), (w * s * 0.95, y + 0.004, z - 0.06), 0.0045, "head"))
            b.teeth.append(
                ((w * s * 0.92, y - 0.012, z - 0.05), (w * s * 0.9, y - 0.008, z - 0.025), 0.004, "jaw")
            )


# --- The skin -----------------------------------------------------------------------------------


def hair(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The bake's grain: fine creases across the body, a slime's sheen."""
    flow = np.repeat(np.array([[0.0, -1.0, 0.0]]), len(p), axis=0)
    return hair_coords(p, 40.0, 160.0, flow), hair_coords(p, 15.0, 60.0, flow)


def fur_offsets(p: np.ndarray, n: np.ndarray, noise: Noise, length: float) -> np.ndarray:
    """Skin: only the faintest swell."""
    return length * (noise.fbm(p * 20.0, 2) - 0.5)


def coat_colours(p: np.ndarray, n: np.ndarray, noise: Noise, pal: Palette, mange: float) -> np.ndarray:
    """`coat` the flanks, `saddle` the dark back and fins, `pale` the belly, `mask` the blotches,
    `nose` the inside of the mouth and the lips, `dirt` the scars."""

    def c(rgb: tuple[float, float, float]) -> np.ndarray:
        return np.asarray(rgb, dtype=float)[None, :]

    def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
        return a + (b - a) * np.clip(t, 0.0, 1.0)[:, None]

    up = n[:, 2]
    col = np.repeat(c(pal.coat), len(p), axis=0)
    wobble = noise.fbm(p * 6.0, 3) - 0.5
    col = mix(col, c(pal.saddle), smooth(0.1, 0.6, up + 0.4 * wobble))
    col = mix(col, c(pal.pale), smooth(-0.15, -0.6, up + 0.3 * wobble))
    blot = noise.fbm(p * 14.0 + 5.0, 3)
    col = mix(col, c(pal.mask), smooth(0.6, 0.7, blot) * smooth(-0.3, 0.2, up) * 0.85)
    mouth = smooth(0.12, 0.22, p[:, 1]) * smooth(0.03, 0.0, np.abs(p[:, 2] - (SPINE - 0.035)))
    col = mix(col, c(pal.nose), mouth)
    scars = smooth(0.82, 0.86, noise.fbm(p * 30.0 + 2.0, 2)) * (1.0 - smooth(0.05, 0.25, p[:, 1]))
    col = mix(col, c(pal.dirt), scars * 0.6)
    col *= (0.92 + 0.16 * noise.fbm(p * 90.0, 2))[:, None]
    return np.clip(col, 0.0, 1.0)
