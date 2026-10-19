"""Seeded gradient noise in plain Python.

Generators used `mathutils.noise`, which ties their geometry to Blender's C code.
This is improved Perlin noise (Perlin 2002) over a fixed permutation, so a shape
is the same on every Blender version and without Blender. Output lies in about
[-1, 1] and is 0 on integer lattice points.
"""

from __future__ import annotations

import math


def _permutation() -> list[int]:
    """A fixed shuffle of 0..255 (xorshift32 Fisher-Yates), doubled to skip index wrapping."""
    state = 0x9E3779B9
    table = list(range(256))
    for i in range(255, 0, -1):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        j = state % (i + 1)
        table[i], table[j] = table[j], table[i]
    return table + table


_P = _permutation()


def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _grad(h: int, x: float, y: float, z: float) -> float:
    h &= 15
    u = x if h < 8 else y
    v = y if h < 4 else (x if h in (12, 14) else z)
    return (u if h & 1 == 0 else -u) + (v if h & 2 == 0 else -v)


def _lerp(t: float, a: float, b: float) -> float:
    return a + t * (b - a)


def noise(x: float, y: float, z: float) -> float:
    """Gradient noise at (x, y, z), in about [-1, 1]."""
    fx, fy, fz = math.floor(x), math.floor(y), math.floor(z)
    xi, yi, zi = int(fx) & 255, int(fy) & 255, int(fz) & 255
    x, y, z = x - fx, y - fy, z - fz
    u, v, w = _fade(x), _fade(y), _fade(z)
    p = _P
    a = p[xi] + yi
    aa, ab = p[a] + zi, p[a + 1] + zi
    b = p[xi + 1] + yi
    ba, bb = p[b] + zi, p[b + 1] + zi
    return _lerp(
        w,
        _lerp(
            v,
            _lerp(u, _grad(p[aa], x, y, z), _grad(p[ba], x - 1, y, z)),
            _lerp(u, _grad(p[ab], x, y - 1, z), _grad(p[bb], x - 1, y - 1, z)),
        ),
        _lerp(
            v,
            _lerp(u, _grad(p[aa + 1], x, y, z - 1), _grad(p[ba + 1], x - 1, y, z - 1)),
            _lerp(u, _grad(p[ab + 1], x, y - 1, z - 1), _grad(p[bb + 1], x - 1, y - 1, z - 1)),
        ),
    )


def noise_array(x: object, y: object, z: object) -> object:
    """`noise` over numpy arrays, value for value (the SDF shapes displace with it). Needs numpy."""
    import numpy as np

    x, y, z = (np.asarray(v, dtype=np.float64) for v in (x, y, z))
    p = np.asarray(_P, dtype=np.int64)
    fx, fy, fz = np.floor(x), np.floor(y), np.floor(z)
    xi, yi, zi = fx.astype(np.int64) & 255, fy.astype(np.int64) & 255, fz.astype(np.int64) & 255
    x, y, z = x - fx, y - fy, z - fz
    u, v, w = (t * t * t * (t * (t * 6.0 - 15.0) + 10.0) for t in (x, y, z))

    def grad(h: object, gx: object, gy: object, gz: object) -> object:
        h = h & 15
        a = np.where(h < 8, gx, gy)
        b = np.where(h < 4, gy, np.where((h == 12) | (h == 14), gx, gz))
        return np.where(h & 1 == 0, a, -a) + np.where(h & 2 == 0, b, -b)

    a = p[xi] + yi
    aa, ab = p[a] + zi, p[a + 1] + zi
    b = p[xi + 1] + yi
    ba, bb = p[b] + zi, p[b + 1] + zi

    def lerp(t: object, lo: object, hi: object) -> object:
        return lo + t * (hi - lo)

    return lerp(
        w,
        lerp(
            v,
            lerp(u, grad(p[aa], x, y, z), grad(p[ba], x - 1, y, z)),
            lerp(u, grad(p[ab], x, y - 1, z), grad(p[bb], x - 1, y - 1, z)),
        ),
        lerp(
            v,
            lerp(u, grad(p[aa + 1], x, y, z - 1), grad(p[ba + 1], x - 1, y, z - 1)),
            lerp(u, grad(p[ab + 1], x, y - 1, z - 1), grad(p[bb + 1], x - 1, y - 1, z - 1)),
        ),
    )
