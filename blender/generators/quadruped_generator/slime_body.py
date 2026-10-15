"""The slimes' body and skin: a heap of jelly that slumps into a skirt on the ground, a dome on top.

Same axes as the dog (anatomy.py): +Y forward, +Z up, metres. No legs: `spine1` is the slumped base
(scaled, it squashes the whole heap), `head` the dome on it, and four lobes of the skirt, `front`,
`back` and `side.#`, that flow out and draw in as it moves. It squashes and stretches
(`Body.squash`): its clips scale bones as well as turning them.

Two kinds: Lumen, smooth and pale, with glowing motes just under its skin (Body.eyes: the `eye`
material, which the game draws glowing), and Murk, black and lumpy (`lumps`).
"""

from __future__ import annotations

import math

import numpy as np

from blender.generators.quadruped_generator.anatomy import Body
from blender.generators.quadruped_generator.coat import Noise, Palette, hair_coords, smooth

SOFTNESS = {"head": 0.05}
DEFAULT_SOFTNESS = 0.035

#: Where the motes are: (angle round, height up the dome 0..1, radius).
MOTES = [
    (0.3, 0.35, 0.03),
    (1.6, 0.6, 0.026),
    (2.7, 0.2, 0.024),
    (3.9, 0.5, 0.03),
    (5.1, 0.3, 0.024),
    (0.9, 0.85, 0.022),
    (4.5, 0.75, 0.02),
]
#: Murk's lumps on the dome: (angle round, height up 0..1, radius).
LUMPS = [
    (0.4, 0.45, 0.07),
    (2.2, 0.3, 0.06),
    (3.6, 0.6, 0.055),
    (5.0, 0.35, 0.065),
    (1.3, 0.8, 0.05),
    (4.3, 0.15, 0.06),
    (2.9, 0.75, 0.045),
    (5.8, 0.6, 0.05),
    (1.0, 0.1, 0.055),
]


def slime(motes: bool, lumps: float) -> Body:
    """A slime; `lumps` (0..1.5) is how lumpy its dome is."""
    b = Body()
    b.squash = True
    b.bone("root", (0.0, -0.05, 0.0), (0.0, 0.05, 0.0), None)
    b.bone("spine1", (0.0, 0.0, 0.0), (0.0, 0.0, 0.17), "root")
    b.bone("head", (0.0, 0.0, 0.17), (0.0, 0.0, 0.46), "spine1")
    b.bone("front", (0.0, 0.0, 0.06), (0.0, 0.3, 0.06), "spine1")
    b.bone("back", (0.0, 0.0, 0.06), (0.0, -0.3, 0.06), "spine1")
    b.bone("side.#", (0.0, 0.0, 0.06), (0.3, 0.0, 0.06), "spine1", mirror=True)

    # The slumped base and the dome on it, run together.
    b.blob((0.0, 0.0, 0.1), (0.33, 0.35, 0.1), "spine1", 0.06)
    b.blob((0.0, -0.01, 0.24), (0.27, 0.28, 0.25), "head", 0.08)
    # The skirt's lobes, flowing out over the ground; the front one a little further.
    b.blob((0.0, 0.25, 0.055), (0.14, 0.13, 0.055), "front", 0.06)
    b.blob((0.0, -0.24, 0.055), (0.13, 0.12, 0.05), "back", 0.06)
    b.blob((0.23, 0.03, 0.055), (0.12, 0.13, 0.05), "side.#", 0.06, mirror=True)
    # A sag down one flank, so it is not a perfect pudding.
    b.blob((0.12, -0.12, 0.16), (0.12, 0.14, 0.1), "spine1", 0.07)
    for a, up, r in LUMPS:
        if lumps <= 0:
            break
        c, _ = _on_dome(a, up)
        b.blob(c, (r * lumps, r * lumps, r * lumps * 0.8), "head", 0.035)
    if motes:
        for a, up, r in MOTES:
            c, _ = _on_dome(a, up, 1.03)
            b.eyes.append((c, r))
    return b


def _on_dome(angle: float, up: float, out: float = 1.0) -> tuple[tuple[float, float, float], float]:
    """A point on the dome's surface (`out` < 1 just under it): `up` 0 at its foot, 1 at the top."""
    e = up * math.pi / 2
    ring = math.cos(e)
    x = math.cos(angle) * ring * 0.27 * out
    y = -0.01 + math.sin(angle) * ring * 0.28 * out
    z = 0.24 + math.sin(e) * 0.25 * out - (1 - up) * 0.06
    return (x, y, z), ring


# --- The skin -----------------------------------------------------------------------------------


def hair(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The bake's grain: a slow ripple, no strands."""
    flow = np.repeat(np.array([[0.0, 0.0, 1.0]]), len(p), axis=0)
    return hair_coords(p, 30.0, 30.0, flow), hair_coords(p, 12.0, 12.0, flow)


def fur_offsets(p: np.ndarray, n: np.ndarray, noise: Noise, length: float) -> np.ndarray:
    """Jelly: soft swells, nothing standing off it."""
    return length * (noise.fbm(p * 9.0, 2) - 0.5)


def coat_colours(p: np.ndarray, n: np.ndarray, noise: Noise, pal: Palette, mange: float) -> np.ndarray:
    """`coat` the jelly, `pale` where it thins over the top, `saddle` the clouding deep in it,
    `mask` the spots floating in it, `dirt` the grit it has picked up round its foot."""

    def c(rgb: tuple[float, float, float]) -> np.ndarray:
        return np.asarray(rgb, dtype=float)[None, :]

    def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
        return a + (b - a) * np.clip(t, 0.0, 1.0)[:, None]

    up = n[:, 2]
    col = np.repeat(c(pal.coat), len(p), axis=0)
    col = mix(col, c(pal.pale), smooth(0.3, 0.95, up) * smooth(0.2, 0.42, p[:, 2]))
    cloud = noise.fbm(p * 7.0 + 3.0, 3)
    col = mix(col, c(pal.saddle), smooth(0.45, 0.7, cloud) * 0.7)
    spots = noise.fbm(p * 45.0 + 11.0, 2)
    col = mix(col, c(pal.mask), smooth(0.72, 0.78, spots) * 0.5)
    col = mix(col, c(pal.dirt), smooth(0.05, 0.0, p[:, 2]) * (0.4 + 0.4 * noise.fbm(p * 40.0, 2)))
    col *= (0.94 + 0.12 * noise.fbm(p * 120.0, 2))[:, None]
    return np.clip(col, 0.0, 1.0)
