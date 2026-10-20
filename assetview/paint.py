"""Surface colour per pixel: material patterns (kit assets) or baked textures (shipped .glb).

The sheet's material views colour each pixel by what lies there, not by one value per
material: a kit asset evaluates its patterns at the pixel's surface point (no Blender, no
UVs); a shipped file samples its base colour texture through its UVs. Either way the sheet
shows the surface that ships.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from assetkit.material import Surface, coverage, detail_normals, evaluate
from assetkit.texbake import SlotLook, from_srgb


class PatternPaint:
    """Patterns evaluated on the model's own (welded) mesh."""

    def __init__(
        self,
        positions: np.ndarray,
        triangles: np.ndarray,
        tri_slot: np.ndarray,
        looks: Sequence[SlotLook],
        origins: Sequence[tuple[float, float, float]],
        shapes: Sequence[object] | None = None,
    ) -> None:
        self.surface = Surface(positions, triangles)
        self.tri_slot = tri_slot
        self.looks = looks
        self.origins = origins  # per slot
        self.shapes = shapes or [None] * len(looks)  # per slot: its part's exact shape, or None

    def detailed(self) -> bool:
        """Whether some slot has detail beyond the mesh (an exact shape, or relief)."""
        return any(s is not None for s in self.shapes) or any(
            look.pattern is not None and any(x.relief for x in look.pattern.layers) for look in self.looks
        )

    def normals(self, tri: np.ndarray, bary: np.ndarray, base: np.ndarray) -> np.ndarray:
        """The finished surface's normals (exact shape, relief) where the mesh's are `base`."""
        out = base.copy()
        slot = self.tri_slot[tri]
        for s, look in enumerate(self.looks):
            pick = np.nonzero(slot == s)[0]
            if len(pick) and (self.shapes[s] is not None or look.pattern is not None):
                out[pick] = detail_normals(
                    look.pattern,
                    self.surface,
                    tri[pick],
                    bary[pick],
                    base[pick],
                    self.origins[s],
                    self.shapes[s],  # type: ignore[arg-type]
                )
        return out

    def colors(self, tri: np.ndarray, bary: np.ndarray) -> np.ndarray:
        out = np.zeros((len(tri), 3))
        slot = self.tri_slot[tri]
        for s, look in enumerate(self.looks):
            pick = np.nonzero(slot == s)[0]
            if not len(pick):
                continue
            if look.pattern is None:
                out[pick] = look.base_color
            else:
                out[pick] = evaluate(
                    look.pattern,
                    self.surface,
                    tri[pick],
                    bary[pick],
                    look.base_color,
                    look.roughness,
                    self.origins[s],
                )[0]
        return out

    def report(self, slots: Sequence[str]) -> list[dict[str, object]]:
        """Per patterned slot, how much of its surface each layer paints, with what to look at:
        a layer under 1% does not show, one over 90% hides everything beneath it."""
        out: list[dict[str, object]] = []
        v, t = self.surface.vertices, self.surface.triangles
        area = 0.5 * np.sqrt((np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]) ** 2).sum(axis=1))
        # Four points per triangle (its centre and three towards its corners), weighted by area.
        points = np.array([[1, 1, 1], [4, 1, 1], [1, 4, 1], [1, 1, 4]], dtype=np.float64) / np.array(
            [[3.0], [6], [6], [6]]
        )
        for s, look in enumerate(self.looks):
            pick = np.nonzero(self.tri_slot == s)[0]
            if look.pattern is None or not len(pick):
                continue
            tri = np.repeat(pick, 4)
            bary = np.tile(points, (len(pick), 1))
            shares = coverage(
                look.pattern, self.surface, tri, bary, self.origins[s], np.repeat(area[pick], 4)
            )
            layers = [
                {"layer": layer.kind, "covers": round(c, 3)}
                for layer, c in zip(look.pattern.layers, shares, strict=True)
            ]
            flags = [
                f"{d['layer']} (layer {i + 1}) does not show ({d['covers']:.0%})"
                for i, d in enumerate(layers)
                if d["covers"] < 0.01
            ]  # type: ignore[operator]
            flags += [
                f"{d['layer']} (layer {i + 1}) covers {d['covers']:.0%}: it hides the layers beneath"
                for i, d in enumerate(layers)
                if d["covers"] > 0.9
            ]  # type: ignore[operator]
            out.append({"slot": slots[s], "layers": layers, "flags": flags})
        return out


@dataclass
class TexturePaint:
    """Base colour textures sampled through per-corner UVs (glTF convention: v down)."""

    corner_uvs: np.ndarray  # (T, 3, 2)
    tri_slot: np.ndarray  # (T,)
    textures: Sequence[np.ndarray | None]  # per slot: (H, W, 3) linear, rows top first
    factors: np.ndarray  # (S, 3) linear base colour factors

    def colors(self, tri: np.ndarray, bary: np.ndarray) -> np.ndarray:
        slot = self.tri_slot[tri]
        out = self.factors[slot].copy()
        uv = (self.corner_uvs[tri] * bary[:, :, None]).sum(axis=1)
        for s, texture in enumerate(self.textures):
            if texture is None:
                continue
            pick = np.nonzero(slot == s)[0]
            h, w = texture.shape[:2]
            col = np.clip((uv[pick, 0] % 1.0) * w, 0, w - 1).astype(np.int64)
            row = np.clip((uv[pick, 1] % 1.0) * h, 0, h - 1).astype(np.int64)
            out[pick] *= texture[row, col]
        return out


def pixel_barycentrics(positions: np.ndarray, triangles: np.ndarray, pas: object) -> tuple[np.ndarray, ...]:
    """For a raster pass: the hit mask (H, W), and per hit pixel its triangle and barycentric
    weights there (perspective-correct)."""
    hit = pas.tri >= 0  # type: ignore[attr-defined]
    tri = pas.tri[hit]  # type: ignore[attr-defined]
    ys, xs = np.nonzero(hit)
    screen, close = pas.frame.project(positions)  # type: ignore[attr-defined]
    corners = screen[triangles[tri]]
    px, py = xs + 0.5, ys + 0.5
    (ax, ay), (bx, by), (cx, cy) = (corners[:, k].T for k in range(3))
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    area = np.where(np.abs(area) < 1e-12, 1e-12, area)
    w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / area
    w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / area
    w = np.clip(np.stack([w0, w1, 1.0 - w0 - w1], axis=1), 0.0, None)
    if not pas.frame.ortho:  # type: ignore[attr-defined]
        w = w * close[triangles[tri]]
    w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-30)
    return hit, tri, w


def decode_png(data: bytes) -> np.ndarray:
    """An 8-bit RGB, RGBA, grey or grey-alpha PNG (not interlaced) as (H, W, 3) floats 0..1,
    rows top first. Standard library and numpy only."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    at, idat = 8, []
    width = height = depth = kind = interlace = 0
    while at < len(data):
        (length,) = struct.unpack_from(">I", data, at)
        tag = data[at + 4 : at + 8]
        body = data[at + 8 : at + 8 + length]
        if tag == b"IHDR":
            width, height, depth, kind, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
        at += 12 + length
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(kind)
    if depth != 8 or channels is None or interlace:
        raise ValueError(f"unsupported PNG (depth {depth}, colour type {kind}, interlace {interlace})")
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), dtype=np.uint8).reshape(height, width * channels + 1)
    filters = raw[:, 0].astype(np.int64)
    if (filters > 4).any():
        raise ValueError("bad PNG filter")
    line = raw[:, 1:].reshape(height, width, channels).astype(np.int16)
    # A pixel depends on the decoded pixels left, above and above-left of it, so all pixels of one
    # anti-diagonal (x + y = d) decode together: H + W steps, not H x W. Stored skewed,
    # skew[x + y + 1, y + 1] = pixel (y, x), each diagonal is one contiguous slice; the zero
    # first row and column stand for the pixels beyond the image's top and left edges.
    ys, xs = np.mgrid[0:height, 0:width]
    skew = np.zeros((height + width + 1, height + 1, channels), dtype=np.int16)
    raw_skew = np.zeros((height + width, height, channels), dtype=np.int16)
    raw_skew[xs + ys, ys] = line
    for d in range(height + width - 1):
        lo, hi = max(0, d - width + 1), min(height, d + 1)
        left = skew[d, lo + 1 : hi + 1]
        up = skew[d, lo:hi]
        ul = skew[d - 1, lo:hi] if d else np.zeros_like(up)
        f = filters[lo:hi, None]
        p = left + up - ul
        pa, pb, pc = np.abs(p - left), np.abs(p - up), np.abs(p - ul)
        paeth = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, up, ul))
        pred = np.select([f == 1, f == 2, f == 3, f == 4], [left, up, (left + up) >> 1, paeth], 0)
        skew[d + 1, lo + 1 : hi + 1] = (raw_skew[d, lo:hi] + pred) & 255
    out = skew[xs + ys + 1, ys + 1]
    image = out.reshape(height, width, channels).astype(np.float64) / 255.0
    if channels < 3:
        image = np.repeat(image[..., :1], 3, axis=2)
    return image[..., :3]


def glb_textures(glb: object) -> list[np.ndarray | None]:
    """Per glTF material, its base colour texture as linear (H, W, 3), or None."""
    doc = glb.doc  # type: ignore[attr-defined]
    out: list[np.ndarray | None] = []
    decoded: dict[int, np.ndarray | None] = {}  # materials of one part share one image
    for material in doc.get("materials", []):
        ref = material.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if ref is None:
            out.append(None)
            continue
        source = doc["textures"][ref["index"]]["source"]
        if source not in decoded:
            image = doc["images"][source]
            view = doc["bufferViews"][image["bufferView"]]
            start = view.get("byteOffset", 0)
            blob = glb.binary[start : start + view["byteLength"]]  # type: ignore[attr-defined]
            png = image.get("mimeType", "image/png") == "image/png"
            decoded[source] = from_srgb(decode_png(blob)) if png else None
        out.append(decoded[source])
    return out
