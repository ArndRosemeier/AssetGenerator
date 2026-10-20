"""Bake material patterns into textures on a mesh's UV layout. Needs numpy.

The backend unwraps; this fills every texel inside a UV triangle with the pattern of that
triangle's material, evaluated at the 3D point the texel maps to, and then grows each island a
few texels outward so a texture sampled at an island's border never picks up the empty gap
around it. Nothing here is Blender's: the same maps on every Blender version.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from assetkit.material import Color, Pattern, Surface, evaluate

TEXELS_PER_METRE = 512.0
MIN_SIZE, MAX_SIZE = 256, 2048
GROW = 8  # texels each island is grown outward


@dataclass(frozen=True)
class SlotLook:
    """What one material slot looks like: its pattern (None: plain) over its base values."""

    pattern: Pattern | None
    base_color: Color
    roughness: float


@dataclass
class Maps:
    """Baked textures, rows from the bottom (v = 0) up, as Blender and UV space count."""

    color: np.ndarray  # (H, W, 3) linear RGB
    roughness: np.ndarray  # (H, W)
    covered: float  # share of texels inside some UV triangle


def texture_size(vertices: np.ndarray, triangles: np.ndarray, uvs: np.ndarray) -> int:
    """The power of two nearest to TEXELS_PER_METRE across the surface on this UV layout."""
    v = np.asarray(vertices, dtype=np.float64)
    a, b, c = v[triangles[:, 0]], v[triangles[:, 1]], v[triangles[:, 2]]
    area = 0.5 * np.sqrt((np.cross(b - a, c - a) ** 2).sum(axis=1)).sum()
    u = np.asarray(uvs, dtype=np.float64)
    e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
    uv_area = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
    wanted = TEXELS_PER_METRE * math.sqrt(area / max(uv_area, 1e-9))
    # The nearest power of two (by ratio): 1100 texels wanted gives 1024, not 2048.
    size = 2 ** round(math.log2(max(wanted, 1.0)))
    return int(min(max(size, MIN_SIZE), MAX_SIZE))


def bake(
    vertices: np.ndarray,
    triangles: np.ndarray,
    uvs: np.ndarray,
    tri_slot: np.ndarray,
    looks: Sequence[SlotLook],
    size: int | None = None,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Maps:
    """Maps for a mesh: `triangles` (T, 3) into `vertices`, `uvs` (T, 3, 2) per corner,
    `tri_slot` (T,) into `looks`; patterns are written with their origin at `origin`."""
    v = np.asarray(vertices, dtype=np.float64)
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    uv = np.asarray(uvs, dtype=np.float64).reshape(-1, 3, 2)
    slots = np.asarray(tri_slot, dtype=np.int64)
    if size is None:
        size = texture_size(v, t, uv)
    tri, bary = _rasterize(uv, size)
    surface = Surface(v, t)
    color = np.zeros((size * size, 3))
    rough = np.zeros(size * size)
    hit = np.nonzero(tri >= 0)[0]
    for s, look in enumerate(looks):
        pick = hit[slots[tri[hit]] == s]
        if not len(pick):
            continue
        if look.pattern is None:
            color[pick] = look.base_color
            rough[pick] = look.roughness
        else:
            c, r = evaluate(
                look.pattern, surface, tri[pick], bary[pick], look.base_color, look.roughness, origin
            )
            color[pick], rough[pick] = c, r
    covered = tri >= 0
    color, rough = _grow(color.reshape(size, size, 3), rough.reshape(size, size), covered.reshape(size, size))
    return Maps(color=color, roughness=rough, covered=float(covered.mean()))


def _rasterize(uv: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Per texel (flat, rows from v = 0): the UV triangle its centre lies in (-1: none) and the
    barycentric weights there. A texel whose centre falls just outside every triangle (within
    half a texel of an edge) takes the nearest one, clamped onto it, so islands have no gaps."""
    tri = np.full(size * size, -1, dtype=np.int64)
    best = np.full(size * size, -np.inf)
    bary = np.zeros((size * size, 3))
    p = uv * size  # texel units; texel (i, j) has its centre at (j + 0.5, i + 0.5)
    a, b, c = p[:, 0], p[:, 1], p[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    lo = np.floor(p.min(axis=1) - 0.5).astype(np.int64)
    hi = np.ceil(p.max(axis=1) + 0.5).astype(np.int64)
    lo, hi = np.clip(lo, 0, size - 1), np.clip(hi, 0, size - 1)
    edge = np.stack(
        [
            np.sqrt(((c - b) ** 2).sum(axis=1)),  # opposite corner a
            np.sqrt(((a - c) ** 2).sum(axis=1)),
            np.sqrt(((b - a) ** 2).sum(axis=1)),
        ],
        axis=1,
    )
    for k in np.nonzero(np.abs(area) > 1e-12)[0]:
        ys, xs = np.mgrid[lo[k, 1] : hi[k, 1] + 1, lo[k, 0] : hi[k, 0] + 1]
        px, py = xs.ravel() + 0.5, ys.ravel() + 0.5
        (ax, ay), (bx, by), (cx, cy) = p[k]
        w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / area[k]
        w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / area[k]
        w2 = 1.0 - w0 - w1
        w = np.stack([w0, w1, w2], axis=1)
        # How far inside the triangle, in texels (negative: outside by that much).
        score = (w * np.abs(area[k]) / np.maximum(edge[k], 1e-12)).min(axis=1)
        flat = ys.ravel() * size + xs.ravel()
        take = (score > -0.75) & (score > best[flat])
        if not take.any():
            continue
        flat, w = flat[take], np.clip(w[take], 0.0, None)
        best[flat] = score[take]
        tri[flat] = k
        bary[flat] = w / w.sum(axis=1, keepdims=True)
    return tri, bary


def _grow(color: np.ndarray, rough: np.ndarray, covered: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Spread each island's border texels GROW texels outward into the empty space: every empty
    texel near an island copies a nearby border texel."""
    h, w = covered.shape
    source = np.where(covered.ravel(), np.arange(h * w), -1).reshape(h, w)
    for _ in range(GROW):
        before = source
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            shifted = np.full_like(source, -1)
            shifted[max(dy, 0) : h + min(dy, 0), max(dx, 0) : w + min(dx, 0)] = before[
                max(-dy, 0) : h + min(-dy, 0), max(-dx, 0) : w + min(-dx, 0)
            ]
            take = (source < 0) & (shifted >= 0)
            source = np.where(take, shifted, source)
        if (source == before).all():
            break
    flat = source.ravel()
    color = color.reshape(-1, 3)[np.maximum(flat, 0)].reshape(h, w, 3)
    rough = rough.ravel()[np.maximum(flat, 0)].reshape(h, w)
    empty = (flat < 0).reshape(h, w)
    # Whatever is still empty takes the mean, so no texel is black.
    if empty.any() and covered.any():
        color[empty] = color[~empty].mean(axis=0)
        rough[empty] = rough[~empty].mean()
    return color, rough


def to_srgb(linear: np.ndarray) -> np.ndarray:
    """Linear 0..1 to sRGB-encoded 0..1 (what an 8-bit colour texture stores)."""
    x = np.clip(linear, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def from_srgb(encoded: np.ndarray) -> np.ndarray:
    x = np.clip(encoded, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))
