"""The coat: rough fur pushed out of the sculpted skin, and its colours painted into the vertices.

Both are worked out from where a point sits on the dog (its height, which way the
skin faces, how far along the head it is) plus seeded noise, so a new seed is a
new dog of the same breed. Numpy only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from blender.generators.quadruped_generator.anatomy import ATLAS, HEAD_PITCH

Rgb = tuple[float, float, float]


class Noise:
    """Seeded smooth value noise in 3D, and fbm of it."""

    def __init__(self, seed: int) -> None:
        rng = np.random.default_rng(seed)
        self.perm = rng.permutation(256)
        self.vals = rng.random(256)

    def _h(self, ix: np.ndarray, iy: np.ndarray, iz: np.ndarray) -> np.ndarray:
        p = self.perm
        return self.vals[p[(p[(p[ix & 255] + iy) & 255] + iz) & 255]]

    def __call__(self, p: np.ndarray) -> np.ndarray:
        f = np.floor(p)
        i = f.astype(np.int64)
        t = p - f
        t = t * t * (3.0 - 2.0 * t)
        x, y, z = i[:, 0], i[:, 1], i[:, 2]
        tx, ty, tz = t[:, 0], t[:, 1], t[:, 2]

        def lerp(a: np.ndarray, b: np.ndarray, u: np.ndarray) -> np.ndarray:
            return a + (b - a) * u

        c00 = lerp(self._h(x, y, z), self._h(x + 1, y, z), tx)
        c10 = lerp(self._h(x, y + 1, z), self._h(x + 1, y + 1, z), tx)
        c01 = lerp(self._h(x, y, z + 1), self._h(x + 1, y, z + 1), tx)
        c11 = lerp(self._h(x, y + 1, z + 1), self._h(x + 1, y + 1, z + 1), tx)
        return lerp(lerp(c00, c10, ty), lerp(c01, c11, ty), tz)

    def fbm(self, p: np.ndarray, octaves: int = 4) -> np.ndarray:
        out = np.zeros(len(p))
        amp, tot = 1.0, 0.0
        for o in range(octaves):
            out += amp * self(p * (2.0**o) + o * 17.3)
            tot += amp
            amp *= 0.5
        return out / tot


def _smooth(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def head_local(p: np.ndarray) -> np.ndarray:
    """Points in the head's frame (origin at the atlas, +Y to the nose)."""
    q = p - np.asarray(ATLAS)
    c, s = np.cos(-HEAD_PITCH), np.sin(-HEAD_PITCH)
    return np.stack([q[:, 0], q[:, 1] * c - q[:, 2] * s, q[:, 1] * s + q[:, 2] * c], axis=1)


@dataclass(frozen=True)
class Regions:
    """Soft masks (0..1) of where on the dog each point is."""

    on_head: np.ndarray
    muzzle: np.ndarray
    nose: np.ndarray
    lips: np.ndarray
    back: np.ndarray
    belly: np.ndarray
    hackles: np.ndarray
    tail: np.ndarray
    trousers: np.ndarray
    ruff: np.ndarray
    low_leg: np.ndarray
    ear: np.ndarray


def regions(p: np.ndarray, n: np.ndarray) -> Regions:
    h = head_local(p)
    on_head = _smooth(-0.01, 0.03, h[:, 1]) * _smooth(0.11, 0.06, np.abs(h[:, 0]))
    muzzle = on_head * _smooth(0.11, 0.15, h[:, 1])
    nose = on_head * _smooth(0.205, 0.218, h[:, 1]) * _smooth(-0.025, -0.015, h[:, 2])
    lips = on_head * _smooth(0.09, 0.11, h[:, 1]) * _smooth(0.012, 0.0, np.abs(h[:, 2] + 0.036))
    ear = on_head * _smooth(0.06, 0.075, h[:, 2]) * _smooth(0.02, 0.03, np.abs(h[:, 0]))
    up = n[:, 2]
    body = 1.0 - on_head
    back = body * _smooth(0.1, 0.7, up) * _smooth(0.48, 0.56, p[:, 2])
    belly = body * _smooth(-0.15, -0.65, up) * _smooth(0.25, 0.35, p[:, 2])
    neck_top = (
        _smooth(0.12, 0.2, p[:, 1])
        * _smooth(0.4, 0.33, p[:, 1])
        * _smooth(0.62, 0.7, p[:, 2] + 0.25 * (0.3 - p[:, 1]))
    )
    withers = _smooth(0.0, 0.1, p[:, 1]) * _smooth(0.25, 0.15, p[:, 1]) * _smooth(0.58, 0.62, p[:, 2])
    hackles = body * np.maximum(neck_top, withers * 0.7) * _smooth(0.0, 0.5, up)
    tail = _smooth(-0.38, -0.42, p[:, 1]) * _smooth(0.2, 0.25, p[:, 2]) * _smooth(0.06, 0.03, np.abs(p[:, 0]))
    trousers = (
        body
        * _smooth(-0.25, -0.34, p[:, 1])
        * _smooth(0.22, 0.3, p[:, 2])
        * _smooth(0.52, 0.45, p[:, 2])
        * _smooth(-0.1, -0.6, n[:, 1])
    )
    ruff = np.clip(
        on_head * _smooth(0.075, 0.02, h[:, 1]) * _smooth(0.0, -0.03, h[:, 2])
        + body * _smooth(0.22, 0.3, p[:, 1]) * _smooth(0.0, -0.4, up),
        0.0,
        1.0,
    )
    low_leg = body * _smooth(0.2, 0.06, p[:, 2])
    return Regions(on_head, muzzle, nose, lips, back, belly, hackles, tail, trousers, ruff, low_leg, ear)


def hair_flow(p: np.ndarray) -> np.ndarray:
    """Which way the hair lies: back and a little down on the body and head, down the legs."""
    leg = _smooth(0.4, 0.3, p[:, 2])[:, None]
    body = np.array([0.0, -1.0, -0.45])[None, :]
    legs = np.array([0.0, -0.25, -1.0])[None, :]
    flow = body + (legs - body) * leg
    return flow / np.linalg.norm(flow, axis=1, keepdims=True)


def hair_coords(p: np.ndarray, along_scale: float, across_scale: float) -> np.ndarray:
    """Space stretched along the lie of the hair: noise in it reads as strands (long along, thin across)."""
    flow = hair_flow(p)
    along = np.einsum("ij,ij->i", p, flow)[:, None] * flow
    return (p - along) * across_scale + along * along_scale


def fur_offsets(p: np.ndarray, n: np.ndarray, noise: Noise, length: float) -> np.ndarray:
    """How far to push each point out along its normal, where a feral dog's coat stands off its outline:
    the hackles, the brush of the tail, the trousers, the ruff. The short coat elsewhere is left to
    the baked maps. Ridged noise stretched along the hair, so it reads as clumps, not lumps.
    """
    r = regions(p, n)
    ridged = 1.0 - np.abs(2.0 * noise.fbm(hair_coords(p, 13.0, 55.0), 3) - 1.0)
    clumps = ridged**3.0
    coarse = noise.fbm(p * 18.0 + 5.0, 2)
    reach = 0.05 * r.back + 1.2 * r.hackles + 1.0 * r.tail + 1.0 * r.trousers + 0.8 * r.ruff + 0.35 * r.belly
    reach *= 1.0 - r.muzzle - r.low_leg - r.ear
    return length * np.clip(reach, 0.0, None) * (0.15 + 0.85 * clumps) * (0.6 + 0.8 * coarse)


@dataclass(frozen=True)
class Palette:
    coat: Rgb
    saddle: Rgb
    pale: Rgb
    mask: Rgb
    nose: Rgb
    mange: Rgb
    dirt: Rgb


def coat_colours(p: np.ndarray, n: np.ndarray, noise: Noise, pal: Palette, mange: float) -> np.ndarray:
    """A sable street dog: a dark saddle, pale underneath, a black mask, brindle on the flanks, mud on the legs."""
    r = regions(p, n)

    def c(rgb: Rgb) -> np.ndarray:
        return np.asarray(rgb, dtype=float)[None, :]

    def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
        return a + (b - a) * np.clip(t, 0.0, 1.0)[:, None]

    wobble = noise.fbm(p * 9.0, 3)
    col = np.repeat(c(pal.coat), len(p), axis=0)
    col = mix(col, c(pal.pale), _smooth(0.45, 0.85, r.belly + r.ruff * 0.25 + 0.4 * (wobble - 0.5)))
    saddle = np.maximum(r.back, r.hackles) + 0.5 * r.tail * _smooth(0.0, 0.5, n[:, 2])
    col = mix(col, c(pal.saddle), _smooth(0.35, 0.75, saddle + 0.5 * (wobble - 0.5)))
    # Brindle: dark streaks running down the flanks and haunches.
    streak = noise.fbm(hair_coords(p, 5.0, 45.0) + 11.0, 3)
    flank = (1.0 - r.on_head) * _smooth(0.3, 0.42, p[:, 2]) * (1.0 - r.belly)
    col = mix(col, col * 0.6, flank * _smooth(0.5, 0.7, streak) * 0.5)
    # The mask: muzzle dark, the ears' backs and tips dark, the tail tip dark.
    col = mix(col, c(pal.mask), 0.85 * _smooth(0.1, 0.9, r.muzzle + 0.3 * (wobble - 0.5)))
    col = mix(col, c(pal.mask), r.ear * 0.8)
    col = mix(col, c(pal.mask), _smooth(-0.53, -0.56, p[:, 1]) * r.tail)
    col = mix(col, c(pal.nose), np.maximum(r.nose, r.lips))
    # Mange: a few bald, greyish patches where the coat has gone.
    if mange > 0:
        bald = _smooth(0.66, 0.74, noise.fbm(p * 7.0 + 31.0, 3)) * (1.0 - r.on_head) * mange
        col = mix(col, c(pal.mange), bald)
    # Mud up the legs and the underside of the paws.
    col = mix(col, c(pal.dirt), _smooth(0.16, 0.03, p[:, 2]) * (0.6 + 0.4 * wobble))
    # Hair clumps: the fur's own light and dark.
    col *= (0.82 + 0.36 * noise.fbm(p * 120.0, 2))[:, None]
    return np.clip(col, 0.0, 1.0)
