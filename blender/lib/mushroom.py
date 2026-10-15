"""One mushroom, as closed shells: cap, gills, stalk, ring, volva and spots.

Shared by every mushroom made here (prop.kit's mushroom kinds, and creatures that are
mushrooms until they move), so a disguised monster and the props around it look the
same. Free of `bpy`: `mushroom()` returns its parts as `(shell, slot)` lists, which a
generator adds to a BoxBuilder, or keeps apart to animate.

Frame: metres, Z up, the stalk's foot at the origin.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field

from blender.lib.shells import Shell, Vec, circle, lathe, place, ring, sweep

Part = tuple[Shell, str]

# Cap shapes: (r, z) from the rim (s = 0) to the crown (s = 1), for a cap of radius 1, height 1.
CAP_SHAPES: dict[str, Callable[[float], tuple[float, float]]] = {
    # A round dome whose rim curls under a little (penny bun, fly agaric).
    "dome": lambda s: (math.cos(math.pi / 2 * s), math.sin(math.pi / 2 * s) * 1.08 - 0.08),
    # A bell: steep sides, rounded top (inkcaps, liberty caps).
    "bell": lambda s: ((1 - s) ** 0.55 * (1 - 0.15 * s), 1 - (1 - s) ** 2.2),
    # A cone to a point (morels, witch's hats).
    "cone": lambda s: ((1 - s) * (1 - 0.1 * math.sin(math.pi * s)), s**0.9),
    # Flat with a knob in the middle (parasols, cave flats).
    "flat": lambda s: (
        math.cos(math.pi / 2 * s),
        0.35 * math.sin(math.pi / 2 * min(1.0, s * 1.6)) + 0.65 * max(0.0, s - 0.7) / 0.3 * (s > 0.7),
    ),
    # A funnel: the rim highest, the middle sunk (chanterelles).
    "funnel": lambda s: ((1 - s) ** 0.9, 1 - 0.55 * s**1.5),
    # A ball (puffballs): the cap is the whole fruit (built apart in `mushroom`; this is its top).
    "ball": lambda s: (math.cos(math.pi / 2 * s), math.sin(math.pi / 2 * s)),
}


@dataclass
class Mushroom:
    cap_radius: float = 0.1
    cap_height: float = 0.07
    cap_shape: str = "dome"
    stalk_height: float = 0.12
    stalk_radius: float = 0.018
    # The stalk's foot swells by this share of its radius (porcini 1.0+, most 0.2).
    bulb: float = 0.2
    # How far the top of the stalk leans off the foot, metres (sideways in x).
    lean: float = 0.0
    gills: int = 24
    ring: bool = False
    volva: bool = False
    spots: int = 0
    spot_radius: float = 0.012
    seed: int = 1
    # Turned round the vertical, radians (so a cluster's mushrooms differ).
    yaw: float = 0.0
    at: Vec = (0.0, 0.0, 0.0)
    segments: int = 16
    _parts: list[Part] = field(default_factory=list, repr=False)


def mushroom(m: Mushroom) -> list[Part]:
    """The mushroom's shells with their slots: 'cap', 'gills', 'stalk', 'ring' (ring and volva),
    'spots'. All placed at `m.at`, turned by `m.yaw`."""
    rng = random.Random(m.seed)
    shape = CAP_SHAPES[m.cap_shape]
    R, H, seg = m.cap_radius, m.cap_height, m.segments
    parts: list[Part] = []

    # The stalk: a bent tube, swollen at the foot, narrowing a little to the cap.
    h, sr = m.stalk_height, m.stalk_radius
    # Detail by size: a thumb-sized mushroom needs few sides and rings.
    n = max(3, min(8, round(h * 30)))
    sides = max(6, min(12, round(sr * 400)))
    path: list[Vec] = []
    for i in range(n + 1):
        t = i / n
        path.append((m.lean * t * t, 0.0, -0.01 + (h + 0.01) * t))

    def girth(t: float) -> tuple[float, float]:
        k = sr * (1.0 + m.bulb * max(0.0, 1.0 - t * 3.0) ** 2) * (1.0 - 0.12 * t)
        return (k, k)

    parts.append((sweep(path, circle(1.0, sides), scale=girth, up=(0.0, 1.0, 0.0)), "stalk"))

    # The cap sits on the stalk's top, tipped the way the stalk leans.
    top = path[-1]
    tip = min(math.atan2(2 * m.lean, h), 0.4) if h > 0 else 0.0
    rim_drop = 0.0 if m.cap_shape in ("ball", "funnel") else -0.04 * H
    # The underside: where it meets the stalk and where it meets the rim. A funnel's gills run
    # down the stalk and its rim is high; other caps rise a little from the rim to the stalk.
    funnel = m.cap_shape == "funnel"
    under_rise = -0.45 * H if funnel else 0.12 * H
    rim_under = 0.8 * H if funnel else rim_drop
    steps = 10 if R > 0.08 else 6
    outer = [(R * shape(i / steps)[0], H * shape(i / steps)[1]) for i in range(steps + 1)]
    outer[-1] = (0.0, outer[-1][1])
    if m.cap_shape == "ball":
        # A whole ball, a little squat, sunk onto a stub of a stalk.
        prof = [(R * math.sin(math.pi * i / steps), H - H * math.cos(math.pi * i / steps)) for i in range(steps + 1)]
        prof[0], prof[-1] = (0.0, 0.0), (0.0, 2 * H)
        base_z = -0.25 * H
    else:
        under = [(0.0, under_rise - 0.04 * H), (sr * 1.05, under_rise), (R * 0.97, rim_under)]
        prof = under + [(r, z + rim_drop * (1 - i / steps)) for i, (r, z) in enumerate(outer)]
        base_z = 0.0
    cap = lathe(prof, seg)
    cap = place(cap, (0.0, 0.0, base_z), roll=0.0)
    parts.append((place(cap, top, roll=tip), "cap"))

    # Gills: thin radial fins under the cap, from the stalk out to near the rim.
    if m.gills and m.cap_shape not in ("ball", "cone"):
        for k in range(m.gills):
            a = math.tau * (k + 0.5) / m.gills
            r0 = sr * 1.1 if k % 2 == 0 else R * 0.45
            r1 = R * 0.92
            depth = min(0.35 * H, 0.03 + 0.0 * R)
            fin_t = max(0.0012, R * 0.008)

            def under_z(r: float) -> float:
                return under_rise + (rim_under - under_rise) * (r - sr) / (R * 0.97 - sr)

            bottom = [
                (r0, -fin_t, under_z(r0) - depth * 0.6),
                (r1, -fin_t, under_z(r1) - depth * 0.1),
                (r1, fin_t, under_z(r1) - depth * 0.1),
                (r0, fin_t, under_z(r0) - depth * 0.6),
            ]
            topq = [
                (r0, -fin_t, under_z(r0) + 0.004),
                (r1, -fin_t, under_z(r1) + 0.004),
                (r1, fin_t, under_z(r1) + 0.004),
                (r0, fin_t, under_z(r0) + 0.004),
            ]
            verts = bottom + topq
            faces = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
            fin = place((verts, faces), (0.0, 0.0, 0.0), yaw=a)
            parts.append((place(fin, top, roll=tip), "gills"))

    # A ring (the remains of the veil) hanging round the upper stalk; a cup round the foot.
    if m.ring:
        z = h * 0.78
        rr = girth(0.78)[0]
        prof = [
            (rr * 0.95, z),
            (rr * 0.95, z + 0.006),
            (rr + R * 0.28, z - 0.012),
            (rr + R * 0.28, z - 0.018),
        ]
        parts.append((place(ring(list(reversed(prof)), seg), (m.lean * 0.78**2, 0.0, 0.0)), "ring"))
    if m.volva:
        rb = girth(0.0)[0]
        prof = [
            (0.0, -0.01),
            (rb * 1.35, -0.01),
            (rb * 1.6, h * 0.06),
            (rb * 1.45, h * 0.1),
            (rb * 1.05, h * 0.02),
            (0.0, h * 0.02),
        ]
        parts.append((lathe(prof, seg), "ring"))

    # Spots: flat warts on the cap's top, set into its surface.
    for _ in range(m.spots):
        s = rng.uniform(0.15, 0.85)
        phi = rng.uniform(0, math.tau)
        r, z = shape(s)
        r2, z2 = shape(min(1.0, s + 0.02))
        # The surface normal in (r, z): perpendicular to the profile's direction.
        dr, dz = r2 - r, (z2 - z) * H / R
        nl = math.hypot(dr, dz) or 1.0
        nr, nz = dz / nl, -dr / nl
        if nz < 0:
            nr, nz = -nr, -nz
        size = m.spot_radius * rng.uniform(0.6, 1.3) * (1 - 0.4 * s)
        wart = lathe([(0.0, -0.004), (size, -0.004), (size * 0.8, size * 0.35), (0.0, size * 0.45)], 7)
        pitch = math.atan2(nr, nz)
        wart = place(wart, (0.0, 0.0, 0.0), roll=pitch)
        wart = place(
            wart, (R * r * math.cos(phi), R * r * math.sin(phi), H * z + rim_drop * (1 - s)), yaw=phi
        )
        parts.append((place(wart, top, roll=tip), "spots"))

    return [(place(shell, m.at, yaw=m.yaw), slot) for shell, slot in parts]
