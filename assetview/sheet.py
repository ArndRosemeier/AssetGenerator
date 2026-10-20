"""The inspection sheet: nine labelled views of an asset in one PNG.

    FRONT   SIDE    TOP        orthographic, metric grid, ground line
    HERO    BACK    SCALE      perspective from front-right and back-left; front beside a 1.75 m person
    PARTS   FACING  WIRE       one colour per material; inside-out faces red, holes yellow; polygon edges

The header repeats the measurements that matter most (size, parts, floating
pieces, holes, balance), so they are read together with the picture.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

import numpy as np

from assetview.font import draw_text, text_width
from assetview.measure import measure, summary
from assetview.model import ViewModel
from assetview.paint import pixel_barycentrics
from assetview.raster import Camera, Frame, Pass, frame, rasterize

TILE = 320
HEADER = 44
BACKGROUND = np.array([0.13, 0.135, 0.145])
GRID = np.array([0.2, 0.21, 0.225])
GROUND = np.array([0.42, 0.42, 0.45])
LABEL = (0.92, 0.92, 0.92)
DIM = (0.62, 0.64, 0.68)
PERSON = np.array([0.36, 0.38, 0.42])
FLAG = (1.0, 0.55, 0.35)
# Distinct colours for the PARTS view (in display space).
PALETTE = np.array(
    [
        [0.90, 0.38, 0.32],
        [0.33, 0.63, 0.93],
        [0.95, 0.77, 0.27],
        [0.42, 0.80, 0.45],
        [0.75, 0.48, 0.90],
        [0.30, 0.85, 0.83],
        [0.97, 0.56, 0.75],
        [0.68, 0.70, 0.36],
        [0.95, 0.62, 0.30],
        [0.55, 0.60, 0.98],
    ]
)
PERSON_HEIGHT = 1.75

FRONT = Camera((0.0, 1.0, 0.0))
SIDE = Camera((-1.0, 0.0, 0.0))
TOP = Camera((0.0, 0.0, -1.0))
HERO = Camera((-1.0, 1.25, -0.75), ortho=False)
BACK = Camera((1.0, -1.25, -0.6), ortho=False)


def render_sheet(model: ViewModel, title: str) -> tuple[np.ndarray, dict[str, object]]:
    report = measure(model)
    sheet = np.empty((HEADER + 3 * TILE, 3 * TILE, 3))
    sheet[:] = BACKGROUND * 0.7
    normals = _normals(model)

    passes: dict[str, Pass] = {}
    # The orthographic views share one scale and one grid, so their proportions compare directly.
    ortho = {"front": FRONT, "side": SIDE, "top": TOP}
    scale = min(frame(camera, model.positions, TILE).scale for camera in ortho.values())
    for name, camera in ortho.items():
        passes[name] = rasterize(model, frame(camera, model.positions, TILE, scale=scale), TILE)
    for name, camera in (("hero", HERO), ("back", BACK)):
        passes[name] = rasterize(model, frame(camera, model.positions, TILE), TILE)

    tiles: list[tuple[str, np.ndarray]] = []
    step = _nice_step(TILE * 0.84 / scale / 6)
    for name in ortho:
        tile = _shaded(model, passes[name], normals, _material_colors(model), painted=True)
        _grid(tile, passes[name], model, step)
        tiles.append((f"{name}  grid {_length(step)}", tile))
    tiles.append(("hero", _shaded(model, passes["hero"], normals, _material_colors(model), painted=True)))
    tiles.append(("back", _shaded(model, passes["back"], normals, _material_colors(model), painted=True)))
    tiles.append(_scale_tile(model, normals))
    tiles.append(("parts", _parts(model, passes["hero"], normals)))
    tiles.append(("facing  red=inside out", _facing(model, passes["hero"], normals)))
    wire = _shaded(model, passes["hero"], normals, np.full((len(model.slots), 3), 0.72))
    wire[passes["hero"].wire] *= 0.35  # dense meshes read as darker, not as solid black
    tiles.append(("wire", wire))

    for index, (label, tile) in enumerate(tiles):
        row, col = divmod(index, 3)
        y, x = HEADER + row * TILE, col * TILE
        sheet[y : y + TILE, x : x + TILE] = tile
        sheet[y : y + 15, x : x + text_width(label) + 8] *= 0.55
        draw_text(sheet, label, x + 4, y + 4, LABEL)
        sheet[y : y + TILE, x] = BACKGROUND * 0.6
        sheet[y, x : x + TILE] = BACKGROUND * 0.6

    draw_text(sheet, title, 6, 6, LABEL, scale=2)
    first, second = summary(report)
    draw_text(sheet, first, 6 + text_width(title, 2) + 12, 6, DIM)
    alarming = any(word in second for word in ("floating", "open edge", "inside-out", "tips over"))
    draw_text(sheet, second, 6 + text_width(title, 2) + 12, 18, FLAG if alarming else DIM)
    draw_text(sheet, model.source, 6 + text_width(title, 2) + 12, 30, DIM)
    return sheet, report


def write_png(path: Path, image: np.ndarray) -> None:
    """RGB float image (0..1, display space) to an 8-bit PNG, standard library only."""
    pixels = (np.clip(image, 0.0, 1.0) * 255 + 0.5).astype(np.uint8)
    height, width = pixels.shape[:2]
    raw = b"".join(b"\x00" + pixels[y].tobytes() for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------------------------


def _normals(model: ViewModel) -> np.ndarray:
    p, t = model.positions, model.triangles
    n = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _to_display(linear: np.ndarray) -> np.ndarray:
    return np.clip(linear, 0.0, 1.0) ** (1 / 2.2)


def _material_colors(model: ViewModel) -> np.ndarray:
    # Lift very dark materials so their form still reads (black iron is a shape too).
    return np.maximum(_to_display(model.slot_colors), 0.16)


def _light(fr: Frame) -> np.ndarray:
    right, up, forward = fr.basis
    light = -forward * 0.55 + up * 0.65 - right * 0.5
    return light / np.linalg.norm(light)


def _lambert(normals: np.ndarray, pas: Pass) -> np.ndarray:
    """Two-sided diffuse per triangle, plus a little ambient."""
    facing = np.where(pas.front[:, None], normals, -normals)
    return 0.32 + 0.68 * np.clip(facing @ _light(pas.frame), 0.0, 1.0)


def _shaded(
    model: ViewModel, pas: Pass, normals: np.ndarray, slot_colors: np.ndarray, painted: bool = False
) -> np.ndarray:
    """Coloured by material: one colour per slot, or with `painted` (and a model whose materials
    vary over the surface) the colour at each pixel's surface point. With `painted` also lit as
    it ships, smooth across soft edges and hard at creases; otherwise flat per triangle, which
    shows the topology."""
    tile = np.empty((TILE, TILE, 3))
    tile[:] = BACKGROUND
    hit = pas.tri >= 0
    tri = pas.tri[hit]
    color = slot_colors[model.tri_slot[tri]]
    if painted and model.paint is not None:
        color = surface_colors(model, pas)
    light = smooth_light(model, pas, normals) if painted else _lambert(normals, pas)[tri]
    tile[hit] = color * light[:, None]
    return tile


CREASE = np.cos(np.radians(40.0))  # where a vertex normal leans further from its face, the edge is hard


def smooth_light(model: ViewModel, pas: Pass, normals: np.ndarray, at: ViewModel | None = None) -> np.ndarray:
    """Diffuse light per hit pixel with the normals the asset ships: blended across each
    triangle where its shading is smooth, the face's own at hard edges and on flat parts (from
    the kit's shading steps, or the normals a shipped file stores). With `at`, the pass was
    drawn from `at` (the same triangles, posed): its own normals light it."""
    source = at or model
    face = normals if at is None else _normals(at)
    _, tri, bary = pixel_barycentrics(source.positions, source.triangles, pas)
    own = face[tri]
    stored = source.corner_normals
    if stored is not None and at is None and not np.isnan(stored[tri]).any():
        corner = stored[tri]
    else:
        vertex = np.zeros_like(source.positions)
        p, t = source.positions, source.triangles
        weighted = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
        for k in range(3):
            np.add.at(vertex, t[:, k], weighted)
        vertex /= np.maximum(np.linalg.norm(vertex, axis=1, keepdims=True), 1e-12)
        corner = vertex[t[tri]]  # (N, 3, 3)
        limit = (source.crease if source.crease is not None else np.full(len(t), CREASE))[tri]
        keep = (corner * own[:, None, :]).sum(axis=2) >= limit[:, None]
        corner = np.where(keep[..., None], corner, own[:, None, :])
    n = (corner * bary[:, :, None]).sum(axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    n = np.where(pas.front[tri][:, None], n, -n)
    return 0.32 + 0.68 * np.clip(n @ _light(pas.frame), 0.0, 1.0)


def surface_colors(model: ViewModel, pas: Pass, at: ViewModel | None = None) -> np.ndarray:
    """Display colour per hit pixel of `pas` from the model's paint; with `at`, the pass was
    drawn from `at` (the same triangles, posed) and the colours come from `model` (at rest)."""
    _, tri, bary = pixel_barycentrics((at or model).positions, (at or model).triangles, pas)
    return np.maximum(_to_display(model.paint.colors(tri, bary)), 0.16)  # type: ignore[union-attr]


def _parts(model: ViewModel, pas: Pass, normals: np.ndarray) -> np.ndarray:
    colors = PALETTE[np.arange(len(model.slots)) % len(PALETTE)]
    tile = _shaded(model, pas, normals, colors)
    # Separate pieces of one material by a slight brightness step.
    islands = model.islands()
    hit = pas.tri >= 0
    jitter = 0.86 + 0.14 * ((islands * 2654435761) % 997 / 996.0)
    tile[hit] *= jitter[pas.tri[hit]][:, None]
    tile[pas.wire] *= 0.55
    y = TILE - 12 * len(model.slots) - 4
    for s, name in enumerate(model.slots):
        tile[y + 12 * s : y + 12 * s + 8, 6:14] = colors[s]
        draw_text(tile, name, 18, y + 12 * s, LABEL)
    return tile


def _facing(model: ViewModel, pas: Pass, normals: np.ndarray) -> np.ndarray:
    tile = _shaded(model, pas, normals, np.full((len(model.slots), 3), 0.7))
    hit = pas.tri >= 0
    back = np.zeros_like(hit)
    back[hit] = ~pas.front[pas.tri[hit]]
    tile[back] = np.array([0.9, 0.15, 0.12]) * (0.6 + 0.4 * tile[back][:, :1])
    _draw_open_edges(tile, model, pas)
    return tile


def _draw_open_edges(tile: np.ndarray, model: ViewModel, pas: Pass) -> None:
    counts: dict[tuple[int, int], int] = {}
    for a, b, c in model.triangles:
        for u, v in ((a, b), (b, c), (c, a)):
            key = (min(u, v), max(u, v))
            counts[key] = counts.get(key, 0) + 1
    open_edges = [key for key, n in counts.items() if n == 1]
    if not open_edges:
        return
    screen, _ = pas.frame.project(model.positions)
    for u, v in open_edges:
        _line(tile, screen[u], screen[v], (1.0, 0.85, 0.1))


def _line(tile: np.ndarray, a: np.ndarray, b: np.ndarray, color: tuple[float, float, float]) -> None:
    steps = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
    xs = np.linspace(a[0], b[0], steps).astype(int)
    ys = np.linspace(a[1], b[1], steps).astype(int)
    for dx, dy in ((0, 0), (1, 0), (0, 1)):
        x, y = xs + dx, ys + dy
        keep = (x >= 0) & (x < TILE) & (y >= 0) & (y < TILE)
        tile[y[keep], x[keep]] = color


def _grid(tile: np.ndarray, pas: Pass, model: ViewModel, step: float) -> None:
    """Metric grid every `step` metres behind an orthographic view, and the ground line."""
    fr = pas.frame
    right, up, _ = fr.basis
    eye_u, eye_v = fr.eye @ right, fr.eye @ up
    edges = np.arange(TILE + 1)
    u = (edges - fr.offset[0]) / fr.scale + eye_u
    v = -(edges - fr.offset[1]) / fr.scale + eye_v
    cols = np.nonzero(np.floor(u[:-1] / step) != np.floor(u[1:] / step))[0]
    rows = np.nonzero(np.floor(v[:-1] / step) != np.floor(v[1:] / step))[0]
    empty = pas.tri < 0
    for c in cols:
        tile[empty[:, c], c] = GRID
    for r in rows:
        tile[r, empty[r]] = GRID
    if abs(up[2]) > 0.5:  # a side view: the ground line at the lowest point
        ground = model.positions[:, 2].min()
        r = int(round(-(ground - eye_v) * fr.scale + fr.offset[1]))
        if 0 <= r < TILE:
            tile[r, empty[r]] = GROUND


def _nice_step(target: float) -> float:
    exponent = math.floor(math.log10(max(target, 1e-6)))
    for factor in (1, 2, 5, 10):
        step = factor * 10**exponent
        if step >= target:
            return step
    return 10 ** (exponent + 1)


def _length(metres: float) -> str:
    if metres >= 1:
        return f"{metres:g} m"
    if metres >= 0.01:
        return f"{metres * 100:g} cm"
    return f"{metres * 1000:g} mm"


def _scale_tile(model: ViewModel, normals: np.ndarray) -> tuple[str, np.ndarray]:
    """The front view beside a person, framed to hold both."""
    lower, upper = model.positions.min(axis=0), model.positions.max(axis=0)
    feet_x = lower[0] - 0.22 - max(0.1, 0.1 * (upper[0] - lower[0]))
    ground = lower[2]
    person = [[(feet_x + x, 0.0, ground + z) for x, z in poly] for poly in _person_outline()]
    corners = np.array([pt for poly in person for pt in poly])
    fr = frame(FRONT, np.concatenate([model.positions, corners]), TILE)
    pas = rasterize(model, fr, TILE)
    tile = _shaded(model, pas, normals, _material_colors(model))
    empty = pas.tri < 0
    for poly in person:
        screen, _ = fr.project(np.asarray(poly))
        mask = _polygon_mask(screen) & empty
        tile[mask] = PERSON
    r = int(round(fr.project(np.array([[0.0, 0.0, ground]]))[0][0, 1]))
    if 0 <= r < TILE:
        tile[r, empty[r]] = GROUND
    return f"scale  person {PERSON_HEIGHT:g} m", tile


def _person_outline() -> list[list[tuple[float, float]]]:
    """A standing person, 1.75 m, feet at (0, 0), as polygons in (x, z) metres."""
    head = [
        (0.105 * math.cos(a), 1.635 + 0.115 * math.sin(a))
        for a in np.linspace(0, math.tau, 20, endpoint=False)
    ]
    torso = [(-0.21, 1.47), (0.21, 1.47), (0.17, 0.86), (-0.17, 0.86)]
    neck = [(-0.05, 1.55), (0.05, 1.55), (0.06, 1.44), (-0.06, 1.44)]
    leg = [(-0.17, 0.9), (-0.015, 0.9), (-0.04, 0.0), (-0.16, 0.0)]
    arm = [(-0.21, 1.47), (-0.27, 1.43), (-0.29, 0.83), (-0.22, 0.83), (-0.18, 1.3)]
    mirror = lambda poly: [(-x, z) for x, z in poly]  # noqa: E731
    return [head, neck, torso, leg, mirror(leg), arm, mirror(arm)]


def _polygon_mask(poly: np.ndarray) -> np.ndarray:
    ys, xs = np.mgrid[0:TILE, 0:TILE]
    px, py = xs + 0.5, ys + 0.5
    inside = np.zeros((TILE, TILE), dtype=bool)
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        crosses = (y0 > py) != (y1 > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
        inside ^= crosses & (px < at)
    return inside
