"""A small software rasterizer: which triangle covers each pixel, seen from a camera.

One pass gives a triangle id per pixel plus a wire mask; the sheet colours the same
pass several ways (shaded, by part, by facing). No GPU, same pixels on every machine.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from assetview.model import ViewModel


@dataclass(frozen=True)
class Camera:
    """Looks along `forward` (from the eye into the scene). Orthographic, or perspective
    with the eye `distance` radii away from the centre of the model's bounds."""

    forward: tuple[float, float, float]
    up: tuple[float, float, float] = (0.0, 0.0, 1.0)
    ortho: bool = True
    distance: float = 3.0


@dataclass
class Frame:
    """Where a camera's view lands on a tile: screen = (local * scale) + offset, y down."""

    basis: np.ndarray  # rows: right, up, forward
    eye: np.ndarray
    ortho: bool
    scale: float
    offset: np.ndarray

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pixel coordinates (N, 2) and closeness (N,) (larger is nearer the eye)."""
        local = (points - self.eye) @ self.basis.T
        if self.ortho:
            plane, closeness = local[:, :2], -local[:, 2]
        else:
            depth = np.maximum(local[:, 2], 1e-6)
            plane, closeness = local[:, :2] / depth[:, None], 1.0 / depth
        screen = plane * self.scale
        screen[:, 1] = -screen[:, 1]
        return screen + self.offset, closeness


def frame(
    camera: Camera, points: np.ndarray, size: int, margin: float = 0.08, scale: float | None = None
) -> Frame:
    """Fit the camera's view of `points` into a size x size tile (centred; at `scale` pixels per
    metre when given, so several views can share one scale)."""
    forward = np.asarray(camera.forward, dtype=np.float64)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, camera.up)
    if np.linalg.norm(right) < 1e-6:
        right = np.cross(forward, (0.0, 1.0, 0.0))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    basis = np.stack([right, up, forward])
    lower, upper = points.min(axis=0), points.max(axis=0)
    centre = (lower + upper) / 2
    radius = max(np.linalg.norm(upper - lower) / 2, 1e-6)
    eye = centre - forward * radius * (camera.distance if not camera.ortho else 4.0)
    probe = Frame(basis, eye, camera.ortho, 1.0, np.zeros(2))
    screen, _ = probe.project(points)
    low, high = screen.min(axis=0), screen.max(axis=0)
    if scale is None:
        extent = max(high[0] - low[0], high[1] - low[1], 1e-9)
        scale = size * (1.0 - 2 * margin) / extent
    mid = (low + high) / 2 * scale
    return Frame(basis, eye, camera.ortho, scale, np.array([size / 2, size / 2]) - mid)


@dataclass
class Pass:
    tri: np.ndarray  # (H, W) int64: triangle id, -1 where nothing is
    wire: np.ndarray  # (H, W) bool: within half a pixel of a polygon edge
    closeness: np.ndarray  # (H, W) float64
    front: np.ndarray  # (T,) bool: triangle faces the eye (counter-clockwise on screen)
    frame: Frame


def rasterize(model: ViewModel, fr: Frame, size: int) -> Pass:
    screen, close = fr.project(model.positions)
    tri = np.full((size, size), -1, dtype=np.int64)
    depth = np.full((size, size), -np.inf)
    wire = np.zeros((size, size), dtype=bool)

    corners = screen[model.triangles]  # (T, 3, 2)
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    # Signed area with y down: negative is counter-clockwise as seen (facing the eye).
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    front = area < 0
    lo = np.floor(corners.min(axis=1)).astype(np.int64)
    hi = np.ceil(corners.max(axis=1)).astype(np.int64)
    visible = (
        (np.abs(area) > 1e-12) & (hi[:, 0] >= 0) & (hi[:, 1] >= 0) & (lo[:, 0] < size) & (lo[:, 1] < size)
    )
    tri_close = close[model.triangles]
    edge_len = np.stack(
        [np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], axis=1
    )

    # Small triangles (nearly all of them) are drawn together, a batch per size: every candidate
    # pixel of every triangle at once, then the nearest triangle per pixel by one sort.
    span = np.maximum(hi - lo, 1).max(axis=1)
    candidates: list[tuple[np.ndarray, ...]] = []
    done = np.zeros(len(area), dtype=bool)
    for side in (2, 4, 8, 16, 32, 64):
        batch = np.nonzero(visible & ~done & (span <= side))[0]
        done[batch] = True
        if len(batch):
            candidates.append(
                _batch(batch, side, lo, corners, area, tri_close, edge_len, model.real_edges, size)
            )
    if candidates:
        pix, z, t, near = (np.concatenate(c) for c in zip(*candidates, strict=True))
        order = np.lexsort((-z, pix))
        pix, z, t, near = pix[order], z[order], t[order], near[order]
        first = np.ones(len(pix), dtype=bool)
        first[1:] = pix[1:] != pix[:-1]
        depth.flat[pix[first]] = z[first]
        tri.flat[pix[first]] = t[first]
        wire.flat[pix[first]] = near[first]

    # The few large ones, one at a time.
    for t in np.nonzero(visible & ~done)[0]:
        x0, y0 = max(lo[t, 0], 0), max(lo[t, 1], 0)
        x1, y1 = min(hi[t, 0], size - 1), min(hi[t, 1], size - 1)
        ys, xs = np.mgrid[y0 : y1 + 1, x0 : x1 + 1]
        px, py = xs + 0.5, ys + 0.5
        (ax, ay), (bx, by), (cx, cy) = corners[t]
        # Barycentric weights: w0 for corner a (opposite edge b-c), and so on.
        w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / area[t]
        w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / area[t]
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        z = w0 * tri_close[t, 0] + w1 * tri_close[t, 1] + w2 * tri_close[t, 2]
        region = depth[y0 : y1 + 1, x0 : x1 + 1]
        win = inside & (z > region)
        if not win.any():
            continue
        region[win] = z[win]
        tri[y0 : y1 + 1, x0 : x1 + 1][win] = t
        # Distance in pixels to each edge: edge k runs corner k -> k+1, opposite weight k+2.
        twice = abs(area[t])
        near = np.zeros_like(win)
        for k, weight in enumerate((w2, w0, w1)):
            if model.real_edges[t, k]:
                near |= weight * twice / max(edge_len[t, k], 1e-9) < 0.6
        wire[y0 : y1 + 1, x0 : x1 + 1][win] = near[win]
    return Pass(tri=tri, wire=wire, closeness=depth, front=front, frame=fr)


def _batch(
    batch: np.ndarray,
    side: int,
    lo: np.ndarray,
    corners: np.ndarray,
    area: np.ndarray,
    tri_close: np.ndarray,
    edge_len: np.ndarray,
    real_edges: np.ndarray,
    size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Every pixel inside one of `batch`'s triangles (each within a side x side box): flat pixel
    index, closeness, triangle id, and whether it lies on a polygon edge."""
    dy, dx = np.mgrid[0 : side + 1, 0 : side + 1]
    xs = lo[batch, 0][:, None] + dx.ravel()[None, :]
    ys = lo[batch, 1][:, None] + dy.ravel()[None, :]
    px, py = xs + 0.5, ys + 0.5
    c = corners[batch]
    ax, ay = c[:, 0, 0][:, None], c[:, 0, 1][:, None]
    bx, by = c[:, 1, 0][:, None], c[:, 1, 1][:, None]
    cx, cy = c[:, 2, 0][:, None], c[:, 2, 1][:, None]
    a = area[batch][:, None]
    w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / a
    w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / a
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9) & (xs >= 0) & (xs < size) & (ys >= 0) & (ys < size)
    tc = tri_close[batch]
    z = w0 * tc[:, 0:1] + w1 * tc[:, 1:2] + w2 * tc[:, 2:3]
    twice = np.abs(a)
    near = np.zeros_like(inside)
    for k, weight in enumerate((w2, w0, w1)):
        near |= real_edges[batch, k][:, None] & (
            weight * twice / np.maximum(edge_len[batch, k], 1e-9)[:, None] < 0.6
        )
    rows, cols = np.nonzero(inside)
    return (
        ys[rows, cols] * size + xs[rows, cols],
        z[rows, cols],
        batch[rows],
        near[rows, cols],
    )
