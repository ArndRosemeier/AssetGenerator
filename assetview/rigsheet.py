"""The rig sheet: a rigged asset's skeleton, skin weights and every clip, in one PNG.

    BONES        WEIGHTS          WEIGHTS (side)
    clip 1:  six frames across the clip
    clip 2:  ...

BONES draws each bone (head dot, line to its tail) over the body; WEIGHTS colours the body by
its bones' colours mixed by weight, so a joint's blend is visible as a gradient and a vertex
pulled by the wrong bone stands out. Each clip row shows the body at six moments, framed alike,
with the clip's measurements: how far it sinks into the ground, how much the skin stretches or
collapses, whether anything moves. The frames come from the same skinning sum Blender runs.
"""

from __future__ import annotations

import numpy as np

from assetkit import Asset
from assetkit.asset import pattern_of
from assetkit.skinning import clip_flags, clip_report, deform, glued_limbs, shared_skin
from assetkit.texbake import SlotLook
from assetview.font import draw_text, text_width
from assetview.model import ViewModel, shading_crease
from assetview.paint import PatternPaint
from assetview.raster import Camera, Pass, frame, rasterize
from assetview.sheet import (
    BACKGROUND,
    DIM,
    FLAG,
    HEADER,
    LABEL,
    _lambert,
    _normals,
    smooth_light,
    surface_colors,
)

BIG = 320
SMALL = 160
ROW_LABEL = 14
HERO = Camera((-1.0, 1.25, -0.75), ortho=False)
SIDE = Camera((-1.0, 0.0, 0.0))
FILM = Camera((-1.0, 0.4, -0.3), ortho=False)  # mostly from the side: legs and bobbing read best


def _model(asset: Asset, positions: np.ndarray, painted: bool = True) -> ViewModel:
    """The skinned part as a view model with `positions` (no welding: skin indices stay valid).
    Its paint, if any, evaluates patterns at rest, so they move with the skin."""
    part = next(p for p in asset.parts if p.skin is not None)
    mesh = part.mesh
    tris, real, tri_slot = [], [], []
    for face, slot in zip(mesh.faces, mesh.face_slots, strict=True):
        n = len(face)
        for k in range(1, n - 1):
            tris.append((face[0], face[k], face[k + 1]))
            real.append((k == 1, True, k == n - 2))
            tri_slot.append(slot)
    colors = [tuple(part.materials[s].base_color[:3]) for s in mesh.slots]
    looks = [
        SlotLook(pattern_of(part.materials[s]), colors[i], part.materials[s].roughness)  # type: ignore[arg-type]
        for i, s in enumerate(mesh.slots)
    ]
    triangles = np.asarray(tris, dtype=np.int64)
    slot_of = np.asarray(tri_slot, dtype=np.int64)
    paint = None
    if painted and any(look.pattern is not None for look in looks):
        origins = [part.pattern_origin] * len(looks)
        paint = PatternPaint(np.asarray(mesh.vertices, dtype=np.float64), triangles, slot_of, looks, origins)
    return ViewModel(
        positions=np.asarray(positions, dtype=np.float64),
        triangles=triangles,
        tri_slot=slot_of,
        slots=list(mesh.slots),
        slot_colors=np.asarray(colors, dtype=np.float64),
        real_edges=np.asarray(real, dtype=bool),
        source="kit asset",
        paint=paint,
        crease=np.full(len(triangles), shading_crease(part.finish)),
    )


def _bone_colors(names: tuple[str, ...]) -> dict[str, np.ndarray]:
    """A distinct colour per bone: hues a golden angle apart, so neighbours in the list differ."""
    colors = {}
    for i, name in enumerate(names):
        hue = (i * 0.381966) % 1.0
        colors[name] = _hsv(hue, 0.62, 0.95)
    return colors


def _hsv(h: float, s: float, v: float) -> np.ndarray:
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return np.array([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i])


def _shade(
    model: ViewModel, pas: Pass, size: int, vertex_colors: np.ndarray | None, flat: np.ndarray | None
) -> np.ndarray:
    tile = np.empty((size, size, 3))
    tile[:] = BACKGROUND
    hit = pas.tri >= 0
    tri = pas.tri[hit]
    light = _lambert(_normals(model), pas)[tri][:, None]
    if vertex_colors is not None:
        color = vertex_colors[model.triangles[tri]].mean(axis=1)
    else:
        color = flat[model.tri_slot[tri]]  # type: ignore[index]
    tile[hit] = color * light
    return tile


def _line(tile: np.ndarray, a: np.ndarray, b: np.ndarray, color: np.ndarray, width: int = 2) -> None:
    size = tile.shape[0]
    steps = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
    xs = np.linspace(a[0], b[0], steps).astype(int)
    ys = np.linspace(a[1], b[1], steps).astype(int)
    for dx in range(width):
        for dy in range(width):
            x, y = xs + dx, ys + dy
            keep = (x >= 0) & (x < size) & (y >= 0) & (y < size)
            tile[y[keep], x[keep]] = color


def _dot(tile: np.ndarray, p: np.ndarray, color: np.ndarray, radius: int = 3) -> None:
    size = tile.shape[0]
    ys, xs = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    mask = xs * xs + ys * ys <= radius * radius
    x, y = (int(p[0]) + xs[mask]), (int(p[1]) + ys[mask])
    keep = (x >= 0) & (x < size) & (y >= 0) & (y < size)
    tile[y[keep], x[keep]] = color


def render_rig_sheet(asset: Asset, title: str) -> tuple[np.ndarray, list[dict[str, object]], list[str]]:
    """The sheet, one measurement report per clip (with `flags`), and rig-wide warnings."""
    if asset.skeleton is None:
        raise ValueError("render_rig_sheet: the asset has no skeleton")
    part = next(p for p in asset.parts if p.skin is not None)
    skin = part.skin
    rest = np.asarray(part.mesh.vertices, dtype=np.float64)
    model = _model(asset, rest)
    bones = asset.skeleton.bones
    colors = _bone_colors(asset.skeleton.names)
    weight_colors = np.zeros((len(rest), 3))
    for v, (idx, w) in enumerate(zip(skin.indices, skin.weights, strict=True)):
        for i, wi in zip(idx, w, strict=True):
            weight_colors[v] += wi * colors[skin.bones[i]]
    ground = float(rest[:, 2].min())

    rows = len(asset.clips)
    sheet = np.empty((HEADER + BIG + rows * (SMALL + ROW_LABEL), 3 * BIG, 3))
    sheet[:] = BACKGROUND * 0.7

    # Row 1: bones, weights from the hero view, weights from the side.
    hero = rasterize(model, frame(HERO, rest, BIG), BIG)
    tile = _shade(model, hero, BIG, None, np.full((len(model.slots), 3), 0.55))
    for bone in bones:
        a, _ = hero.frame.project(np.array([bone.head, bone.tail]))
        _line(tile, a[0], a[1], colors[bone.name])
        _dot(tile, a[0], colors[bone.name])
    _place(sheet, tile, 0, HEADER, f"bones  {len(bones)}")
    tile = _shade(model, hero, BIG, weight_colors, None)
    y = BIG - 12 * len(bones) - 4
    for i, bone in enumerate(bones):
        tile[y + 12 * i : y + 12 * i + 8, 6:14] = colors[bone.name]
        draw_text(tile, bone.name, 18, y + 12 * i, LABEL)
    _place(sheet, tile, BIG, HEADER, "weights")
    side = rasterize(model, frame(SIDE, rest, BIG), BIG)
    _place(sheet, _shade(model, side, BIG, weight_colors, None), 2 * BIG, HEADER, "weights  side")

    # One row per clip: six moments, framed alike.
    faces = model.triangles
    reports = []
    material = np.maximum(np.clip(model.slot_colors, 0, 1) ** (1 / 2.2), 0.16)
    for row, clip in enumerate(asset.clips):
        report = clip_report(rest, faces, skin, clip, ground)
        report["flags"] = clip_flags(report)
        reports.append(report)
        picks = (
            [round(k * (len(clip.frames) - 1) / 5) for k in range(6)]
            if not clip.loop
            else [round(k * len(clip.frames) / 6) % len(clip.frames) for k in range(6)]
        )
        posed = [deform(rest, skin, clip.frames[i]) for i in picks]
        everything = np.concatenate(posed)
        fr = frame(FILM, everything, SMALL)
        y0 = HEADER + BIG + row * (SMALL + ROW_LABEL)
        flags = report["flags"]
        label = f"{clip.name}  {clip.seconds:.2f} s {'loop' if clip.loop else 'once'}"
        sheet[y0 : y0 + ROW_LABEL, :] = BACKGROUND * 0.5
        draw_text(sheet, label, 4, y0 + 4, LABEL)
        draw_text(
            sheet, "; ".join(flags) if flags else "ok", 12 + text_width(label), y0 + 4, FLAG if flags else DIM
        )
        for k, positions in enumerate(posed):
            m = _model(asset, positions, painted=False)
            pas = rasterize(m, fr, SMALL)
            tile = _shade(m, pas, SMALL, None, material)
            hit = pas.tri >= 0
            color = (
                surface_colors(model, pas, at=m)
                if model.paint is not None
                else material[m.tri_slot[pas.tri[hit]]]
            )
            tile[hit] = color * smooth_light(m, pas, _normals(m))[:, None]
            ground_row = int(round(fr.project(np.array([[0.0, 0.0, ground]]))[0][0, 1]))
            if 0 <= ground_row < SMALL:
                empty = pas.tri[ground_row] < 0
                tile[ground_row, empty] = (0.42, 0.42, 0.45)
            sheet[y0 + ROW_LABEL : y0 + ROW_LABEL + SMALL, k * SMALL : (k + 1) * SMALL] = tile
            sheet[y0 + ROW_LABEL : y0 + ROW_LABEL + SMALL, k * SMALL] = BACKGROUND * 0.6

    parents = {b.name: b.parent for b in bones}
    warnings = [
        f"{a} shares skin with {b} ({n} vertices): model them apart" for a, b, n in shared_skin(skin, parents)
    ]
    warnings += [
        f"{limb} is fused to {body} along {share:.0%} of its length: it reads as part of the body;"
        " model it further out"
        for limb, body, share in glued_limbs(rest, faces, skin, bones)
    ]
    x = 6 + text_width(title, 2) + 12
    draw_text(sheet, title, 6, 6, LABEL, scale=2)
    draw_text(sheet, f"rig: {len(bones)} bones, {len(asset.clips)} clip(s)", x, 6, DIM)
    worst = [f"{r['clip']}: {', '.join(r['flags'])}" for r in reports if r["flags"]]
    draw_text(sheet, "; ".join(worst) if worst else "clips ok", x, 18, FLAG if worst else DIM)
    draw_text(
        sheet, "; ".join(warnings[:2]) if warnings else "no fused limbs", x, 30, FLAG if warnings else DIM
    )
    return sheet, reports, warnings


def _place(sheet: np.ndarray, tile: np.ndarray, x: int, y: int, label: str) -> None:
    size = tile.shape[0]
    sheet[y : y + size, x : x + size] = tile
    sheet[y : y + 15, x : x + text_width(label) + 8] *= 0.55
    draw_text(sheet, label, x + 4, y + 4, LABEL)
    sheet[y : y + size, x] = BACKGROUND * 0.6
