"""Small hand props for dungeons and mines: barrels, buckets, tools, cut stone.

One generator, `prop.kit`, with a recipe per `kind`. Each recipe composes closed
shells (assetkit/shells.py) into one mesh with material slots, so QA's
manifold and outward-normal gates hold. Props are made to be seen up close in a
headlamp's beam: proportions follow real objects and every part has thickness.

Frame (as every asset here): metres, Z up, origin at the footprint centre on
Z=0, the front facing -Y (glTF +Z).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping

from assetkit import Asset, MeshBuilder, ShadeFlat, ShadeSmooth, Unwrap, noise
from assetkit import Part as KitPart
from assetkit.shells import Shell, Vec, circle, grid_cube, lathe, place, rect, ring, sweep, transform
from blender.lib.mushroom import CAP_SHAPES, Mushroom, Part, mushroom
from blender.lib.spec import (
    AssetSpec,
    SpecError,
    as_bool,
    as_float,
    as_int,
    as_str,
    require_key,
    require_materials,
)

# A recipe may return a shade per vertex (a colour multiplier the pack bakes in: tool marks, grime).
Recipe = Callable[[MeshBuilder, dict[str, float], random.Random], list[float] | None]


def _add(b: MeshBuilder, shell: Shell, slot: str) -> None:
    b.add(shell, slot)


# ---------------------------------------------------------------------------------------------
# Barrel: staves bent round a bulge, two heads, iron hoops.
# ---------------------------------------------------------------------------------------------


def _barrel(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    h, r0, bulge = p["height"], p["radius"], p["bulge"]
    staves, thick = int(p["staves"]), 0.022
    rows = 5

    def radius(z: float) -> float:
        return r0 + bulge * math.sin(math.pi * z / h)

    gap = 0.012 / r0  # radians between staves
    for k in range(staves):
        a0 = math.tau * k / staves + gap / 2
        a1 = math.tau * (k + 1) / staves - gap / 2
        top = h + rng.uniform(-0.006, 0.004)
        out = rng.uniform(-0.002, 0.002)
        outer = [(radius(top * i / rows) + out, top * i / rows) for i in range(rows + 1)]
        inner = [(r - thick, z) for r, z in reversed(outer)]
        _add(b, lathe(outer + inner, 2, start=a0, end=a1), "staves")
    # The heads sit in the croze a little below each end.
    for z0 in (0.03, h - 0.05):
        r = radius(z0) - thick * 0.6
        _add(b, lathe([(0.0, z0), (r, z0), (r, z0 + 0.02), (0.0, z0 + 0.02)], 24), "ends")
    hoops = int(p["hoops"])
    marks = [0.07, 0.24, h - 0.24, h - 0.07] if hoops >= 4 else [0.08, h * 0.5, h - 0.08][: max(hoops, 2)]
    if hoops == 2:
        marks = [0.08, h - 0.08]
    for z in marks:
        r = radius(z) + 0.001
        w, t = 0.018, 0.005
        _add(b, ring([(r, z - w), (r + t, z - w), (r + t, z + w), (r, z + w)], 28), "iron")


# ---------------------------------------------------------------------------------------------
# Bucket: a tapered pail with a rolled rim and a wire bail.
# ---------------------------------------------------------------------------------------------


def _bucket(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    rt, rb, h, w = p["radius_top"], p["radius_bottom"], p["height"], 0.006
    _add(b, lathe([(0.0, 0.0), (rb, 0.0), (rt, h), (rt - w, h), (rb - w, w), (0.0, w)], 24), "tin")
    _add(
        b,
        ring(
            [
                (rt - 0.004, h - 0.006),
                (rt + 0.006, h - 0.006),
                (rt + 0.006, h + 0.004),
                (rt - 0.004, h + 0.004),
            ],
            24,
        ),
        "tin",
    )
    for s in (-1.0, 1.0):
        _add(
            b,
            place(
                lathe([(0.0, 0.0), (0.018, 0.0), (0.018, 0.008), (0.0, 0.008)], 8),
                (s * (rt - 0.004), 0.0, h - 0.04),
                roll=s * math.pi / 2,
            ),
            "iron",
        )
    # The bail lies over to one side, as a dropped handle does.
    tilt = math.radians(rng.uniform(55, 75))
    arc = []
    for i in range(13):
        t = math.pi * i / 12
        x = math.cos(t) * (rt + 0.008)
        up = math.sin(t) * (rt * 1.05)
        arc.append((x, -math.sin(tilt) * up, h - 0.04 + math.cos(tilt) * up))
    _add(b, sweep(arc, circle(0.0035, 6)), "iron")


# ---------------------------------------------------------------------------------------------
# Pick and shovel: ash handles, forged heads.
# ---------------------------------------------------------------------------------------------


def _handle(b: MeshBuilder, length: float, r0: float, r1: float, bend: float) -> None:
    path = [(bend * math.sin(math.pi * i / 10), 0.0, length * i / 10) for i in range(11)]
    _add(
        b,
        sweep(
            path,
            [(x * 1.0, y * 0.8) for x, y in circle(1.0, 10)],
            scale=lambda t: (r0 + (r1 - r0) * t,) * 2,
            up=(0.0, 1.0, 0.0),
        ),
        "wood",
    )


def _pick(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    L, reach = p["handle_length"], p["head_length"] / 2
    _handle(b, L + 0.03, 0.016, 0.021, rng.uniform(-0.006, 0.006))
    z = L - 0.035
    # The head: a curved bar drooping to a point on one side and a narrow chisel on the other.
    path = []
    for i in range(17):
        t = -1.0 + 2.0 * i / 16
        path.append((t * reach, 0.0, z - 0.09 * t * t))

    def taper(t: float) -> tuple[float, float]:
        d = abs(2.0 * t - 1.0)
        fall = max(0.0, 1.0 - d) ** 0.5 if d > 0.25 else 1.0
        if t < 0.5:  # the point
            return (0.024 * max(fall, 0.08), 0.024 * max(fall, 0.08))
        return (0.024 * max(fall, 0.25), 0.03 * max(1.0 - 0.6 * d, 0.3))

    _add(b, sweep(path, rect(1.0, 1.0), scale=taper, up=(0.0, 1.0, 0.0)), "iron")
    # The eye's collar round the handle.
    _add(
        b,
        place(lathe([(0.0, -0.045), (0.03, -0.045), (0.03, 0.045), (0.0, 0.045)], 8), (0.0, 0.0, z)),
        "iron",
    )


def _shovel(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    L, bw, bl = p["handle_length"], p["blade_width"] / 2, p["blade_length"]
    base = bl * 0.95
    # The handle starts in the socket and ends in a T grip.
    path = [(0.0, 0.0, base + (L) * i / 8) for i in range(9)]
    _add(b, sweep(path, circle(0.017, 10), up=(0.0, 1.0, 0.0)), "wood")
    _add(b, sweep([(-0.065, 0.0, base + L), (0.065, 0.0, base + L)], circle(0.016, 8)), "wood")
    # The socket tapers from the blade up round the handle.
    _add(
        b,
        sweep(
            [(0.0, 0.0, bl * 0.75), (0.0, 0.0, base + 0.16)],
            circle(1.0, 10),
            scale=lambda t: (0.04 - 0.018 * t,) * 2,
            up=(0.0, 1.0, 0.0),
        ),
        "iron",
    )
    # The blade: a dished plate, round-pointed, its face to -Y.
    dish = 0.028
    sect: list[tuple[float, float]] = []
    n = 9
    for i in range(n):  # front face, left to right
        u = -1.0 + 2.0 * i / (n - 1)
        sect.append((u, dish * u * u))
    for i in reversed(range(n)):  # back face
        u = -1.0 + 2.0 * i / (n - 1)
        sect.append((u, dish * u * u + 0.004))

    def width(t: float) -> tuple[float, float]:
        # t runs from the tip (0) up to the shoulder (1).
        return (bw * max(math.sin(math.pi / 2 * min(t * 1.6, 1.0)), 0.12), 1.0)

    blade = [(0.0, 0.0, bl * i / 10) for i in range(11)]
    _add(b, sweep(blade, sect, scale=width, up=(0.0, -1.0, 0.0)), "iron")


# ---------------------------------------------------------------------------------------------
# Cut stone: a dressed block with tooled faces and knocked corners.
# ---------------------------------------------------------------------------------------------


def _cut_block(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> list[float]:
    sx, sy, sz = p["size_x"], p["size_y"], p["size_z"]
    cube, faces = grid_cube(max(2, int(max(sx, sy, sz) / 0.1)))
    seed = rng.uniform(0, 100)
    chip = p["chip"]
    shade: list[float] = []
    verts: list[Vec] = []
    for co in cube:
        x, y, z = co[0] * sx, co[1] * sy, (co[2] + 0.5) * sz
        # Which face: the largest normalised coordinate.
        ax = max(range(3), key=lambda i: abs(co[i]))
        n = [0.0, 0.0, 0.0]
        n[ax] = 1.0 if co[ax] > 0 else -1.0
        d = 0.004 * noise.noise(x * 6 + seed, y * 6, z * 6)
        # Here and there an edge knocked off where a block was dropped: sparse, sharp chips.
        edge = sorted(abs(co[i]) for i in range(3))[1]  # second largest: near an edge when ~0.5
        k = noise.noise(x * 5 - seed, y * 5, z * 5)
        knocked = edge > 0.4 and k > 0.1
        if knocked:
            d -= chip * min(1.0, (k - 0.1) * 3.0) * (edge - 0.4) / 0.1
        verts.append((x + n[0] * d, y + n[1] * d, z + n[2] * d))
        # Tool marks and the fresh, paler stone where a chip came off: in the colour, not the mesh.
        along = (y if ax != 1 else x) * 18.0 + 0.6 * noise.noise(x * 2, y * 2 + seed, z * 2)
        mark = 0.9 + 0.1 * math.sin(along * math.tau) * (0.5 + 0.5 * noise.noise(x * 3, y * 3, z * 3 + seed))
        shade.append(mark * (1.12 if knocked else 1.0))
    b.add_shell(verts, faces, "stone")
    return shade


def _hexa(
    b: MeshBuilder, bottom: list[tuple[float, float, float]], top: list[tuple[float, float, float]], slot: str
) -> None:
    """A six-sided solid from four bottom and four top corners, each counter-clockwise from above."""
    faces = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    b.add_shell(bottom + top, faces, slot)


# ---------------------------------------------------------------------------------------------
# Mine cart: a riveted steel tub on a timber chassis, flanged wheels for the narrow gauge.
# ---------------------------------------------------------------------------------------------


def _cart(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> list[float] | None:
    gauge, wr = p["gauge"] / 2, p["wheel_radius"]
    axle_z = p["rail_top"] + wr
    hx0, hy0, hx1, hy1 = 0.4, 0.66, 0.52, 0.82  # half width and length at the bottom and the top
    z0, z1, t = axle_z + wr * 0.55, axle_z + wr * 0.55 + 0.82, 0.03
    # Wheels: a tread and an inner flange, an axle across.
    for sy in (-0.45, 0.45):
        for sx in (-1.0, 1.0):
            prof = [
                (0.0, -0.035),
                (wr, -0.035),
                (wr, 0.02),
                (wr + 0.025, 0.02),
                (wr + 0.025, 0.035),
                (0.0, 0.035),
            ]
            _add(b, place(lathe(prof, 14), (sx * gauge, sy, axle_z), roll=sx * math.pi / 2), "iron")
        _add(b, sweep([(-gauge - 0.06, sy, axle_z), (gauge + 0.06, sy, axle_z)], circle(0.025, 8)), "iron")
    # The chassis: two beams along, buffers at the ends.
    for sx in (-0.3, 0.3):
        b.add_box((sx, 0.0, axle_z + 0.05), (0.1, 1.5, 0.12), "wood")
    for sy in (-1.0, 1.0):
        b.add_box((0.0, sy * 0.78, axle_z + 0.08), (0.75, 0.1, 0.14), "wood")
        b.add_box((0.0, sy * 0.86, axle_z + 0.08), (0.1, 0.08, 0.08), "iron")

    # The tub: four flared walls and a floor, a rim round the top, straps down the sides.
    def corner(hx: float, hy: float, z: float) -> list[tuple[float, float, float]]:
        return [(-hx, -hy, z), (hx, -hy, z), (hx, hy, z), (-hx, hy, z)]

    _hexa(b, corner(hx0, hy0, z0), corner(hx0, hy0, z0 + t), "steel")
    for k in range(4):
        ob, ot = corner(hx0, hy0, z0), corner(hx1, hy1, z1)
        a, c = k, (k + 1) % 4

        def inset(
            q: tuple[float, float, float], z: float, hx: float, hy: float
        ) -> tuple[float, float, float]:
            return (
                q[0] - math.copysign(t, q[0]) * (1 if k % 2 == 1 else 0),
                q[1] - math.copysign(t, q[1]) * (1 if k % 2 == 0 else 0),
                z,
            )

        bottom = [ob[a], ob[c], inset(ob[c], z0, hx0, hy0), inset(ob[a], z0, hx0, hy0)]
        top = [ot[a], ot[c], inset(ot[c], z1, hx1, hy1), inset(ot[a], z1, hx1, hy1)]
        # Wind the bottom counter-clockwise from above whichever way the wall runs.
        area = sum(
            bottom[i][0] * bottom[(i + 1) % 4][1] - bottom[(i + 1) % 4][0] * bottom[i][1] for i in range(4)
        )
        if area < 0:
            bottom.reverse()
            top.reverse()
        _hexa(b, bottom, top, "steel")
    rim = [(-hx1, -hy1, z1), (hx1, -hy1, z1), (hx1, hy1, z1), (-hx1, hy1, z1)]
    for k in range(4):
        q0, q1 = rim[k], rim[(k + 1) % 4]
        d = (q1[0] - q0[0], q1[1] - q0[1])
        n = math.hypot(*d)
        ext = 0.02
        a0 = (q0[0] - d[0] / n * ext, q0[1] - d[1] / n * ext, z1)
        a1 = (q1[0] + d[0] / n * ext, q1[1] + d[1] / n * ext, z1)
        _add(b, sweep([a0, a1], circle(0.022, 6)), "iron")
    for sx in (-1.0, 1.0):
        for fy in (-0.45, 0.0, 0.45):
            lo = (sx * (hx0 + 0.008), fy * hy0 / hy1 * hy0, z0 + 0.02)
            hi = (sx * (hx1 + 0.008), fy * hy0, z1 - 0.02)
            _add(b, sweep([lo, hi], rect(0.006, 0.03), up=(sx, 0.0, 0.0)), "iron")
    if p["load"] > 0.5:
        # Broken stone heaped above the rim.
        for _ in range(26):
            u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
            h = (1 - 0.5 * (u * u + v * v)) * 0.18
            size = rng.uniform(0.08, 0.2)
            b.add_box(
                (u * (hx1 - 0.14), v * (hy1 - 0.16), z1 - 0.12 + h),
                (size, size * rng.uniform(0.7, 1.2), size * rng.uniform(0.5, 0.9)),
                "load",
                rotation=(rng.uniform(0, 3), rng.uniform(0, 3), rng.uniform(0, 3)),
            )
        zf = (z1 - 0.26 - z0) / (z1 - z0)  # the fill's floor, between the flared walls
        b.add_box(
            (0.0, 0.0, z1 - 0.18),
            ((hx0 + (hx1 - hx0) * zf - t) * 2, (hy0 + (hy1 - hy0) * zf - t) * 2, 0.16),
            "load",
        )
    return None


# ---------------------------------------------------------------------------------------------
# Shack: a plank hut on a frame, a door and a window on its sides, a tarred roof.
# ---------------------------------------------------------------------------------------------


def _planks(
    b: MeshBuilder,
    rng: random.Random,
    x0: float,
    x1: float,
    z0: float,
    z1: float,
    holes: list[tuple[float, float, float, float]],
    wall: Callable[
        [float, float, float, float], tuple[tuple[float, float, float], tuple[float, float, float]]
    ],
) -> None:
    """Upright boards across [x0, x1] from z0 to z1, broken round `holes` (u0, u1, v0, v1);
    `wall(u, v, w, h)` gives a board's centre and size in the shack's frame."""
    u = x0
    while u < x1 - 0.02:
        w = min(rng.uniform(0.16, 0.22), x1 - u)
        c = u + w / 2
        spans = [(z0, z1 + rng.uniform(-0.02, 0.0))]
        for h0, h1, v0, v1 in holes:
            if h0 < c < h1:
                spans = [(a, min(e, v0)) for a, e in spans if a < v0] + [
                    (max(a, v1), e) for a, e in spans if e > v1
                ]
        for a, e in spans:
            if e - a > 0.05:
                centre, size = wall(c, (a + e) / 2, w - 0.012, e - a)
                b.add_box(centre, size, "boards")
        u += w


def _door_leaf(b: MeshBuilder, d0: float, d1: float, dh: float, hy: float) -> None:
    """The shack's plank door, shut in its doorway: five boards, two ledges, a brace, hinges, a handle."""
    dc, dw = (d0 + d1) / 2, d1 - d0
    for k in range(5):
        b.add_box((d0 + dw * (k + 0.5) / 5, -hy + 0.01, dh / 2), (dw / 5 - 0.008, 0.03, dh - 0.02), "door")
    for z in (0.3, dh - 0.3):
        b.add_box((dc, -hy - 0.02, z), (dw - 0.06, 0.03, 0.1), "door")
    brace = math.atan2(dh - 0.6, dw - 0.1)
    b.add_box(
        (dc, -hy - 0.02, dh / 2),
        (math.hypot(dw - 0.1, dh - 0.6), 0.025, 0.09),
        "door",
        rotation=(0.0, -brace, 0.0),
    )
    for z in (0.3, dh - 0.3):  # hinges
        b.add_box((d0 + 0.12, -hy - 0.04, z), (0.22, 0.012, 0.04), "iron")
    b.add_box((d1 - 0.1, -hy - 0.045, 1.0), (0.04, 0.02, 0.12), "iron")


def _shack(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    hx, hy, h = p["width"] / 2, p["depth"] / 2, p["height"]
    door = (0.15, 1.05, 0.0, 1.9)  # in the front wall: (x0, x1, z0, z1)
    window = (-0.4, 0.4, 1.25, 1.85)  # in the right side wall: (y0, y1, z0, z1)
    t, post = 0.035, 0.1
    # Frame: corner posts, sills, the plate under the roof.
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            b.add_box((sx * (hx - post / 2), sy * (hy - post / 2), h / 2), (post, post, h), "frame")
    for sy in (-1.0, 1.0):
        b.add_box((0.0, sy * (hy - post / 2), 0.06), (hx * 2, post, 0.12), "frame")
        b.add_box((0.0, sy * (hy - post / 2), h - 0.06), (hx * 2, post, 0.12), "frame")
    for sx in (-1.0, 1.0):
        b.add_box((sx * (hx - post / 2), 0.0, 0.06), (post, hy * 2, 0.12), "frame")
        b.add_box((sx * (hx - post / 2), 0.0, h - 0.06), (post, hy * 2, 0.12), "frame")
    # Boards on the outside of the frame.
    _planks(b, rng, -hx, hx, 0.02, h, [door], lambda u, v, w, hh: ((u, -hy - t / 2, v), (w, t, hh)))
    _planks(b, rng, -hx, hx, 0.02, h, [], lambda u, v, w, hh: ((u, hy + t / 2, v), (w, t, hh)))
    _planks(b, rng, -hy, hy, 0.02, h, [], lambda u, v, w, hh: ((-hx - t / 2, u, v), (t, w, hh)))
    _planks(b, rng, -hy, hy, 0.02, h, [window], lambda u, v, w, hh: ((hx + t / 2, u, v), (t, w, hh)))
    # The door, shut, a little inside its frame: boards, two ledges and a brace. Without it
    # (door = 0) the doorway stands open, for a game that hangs and swings its own leaf.
    d0, d1, _, dh = door
    dc, dw = (d0 + d1) / 2, d1 - d0
    if p["door"] > 0.5:
        _door_leaf(b, d0, d1, dh, hy)
    # Door and window frames.
    for x in (d0 - 0.04, d1 + 0.04):
        b.add_box((x, -hy - t - 0.01, dh / 2), (0.08, 0.04, dh + 0.04), "frame")
    b.add_box((dc, -hy - t - 0.01, dh + 0.04), (dw + 0.16, 0.04, 0.08), "frame")
    w0, w1, v0, v1 = window
    for y in (w0 - 0.04, w1 + 0.04):
        b.add_box((hx + t + 0.01, y, (v0 + v1) / 2), (0.04, 0.08, v1 - v0 + 0.16), "frame")
    for z in (v0 - 0.04, v1 + 0.04):
        b.add_box((hx + t + 0.01, (w0 + w1) / 2, z), (0.04, w1 - w0 + 0.16, 0.08), "frame")
    b.add_box((hx + 0.01, (w0 + w1) / 2, (v0 + v1) / 2), (0.02, 0.03, v1 - v0), "frame")  # the cross bar
    # The roof: rafters falling to the back, boards on them, tar paper over, battens on the tar.
    over, fall = 0.25, 0.25
    pitch = math.atan2(fall, hy * 2 + over * 2)
    for x in [-hx + 0.05 + k * (hx * 2 - 0.1) / 4 for k in range(5)]:
        b.add_box((x, 0.0, h + 0.07), (0.07, hy * 2 + over * 2, 0.1), "frame", rotation=(-pitch, 0.0, 0.0))
    b.add_box(
        (0.0, 0.0, h + 0.15),
        (hx * 2 + over * 2, hy * 2 + over * 2, 0.05),
        "roof",
        rotation=(-pitch, 0.0, 0.0),
    )
    for k in range(6):
        x = -hx - over + 0.1 + k * (hx * 2 + over * 2 - 0.2) / 5
        b.add_box((x, 0.0, h + 0.19), (0.04, hy * 2 + over * 2, 0.03), "roof", rotation=(-pitch, 0.0, 0.0))
    # The stovepipe through the roof at the back, a step under the door.
    _add(
        b,
        sweep(
            [(-hx + 0.5, hy - 0.4, h - 0.3), (-hx + 0.5, hy - 0.4, h + 0.9)],
            circle(0.07, 10),
            up=(0.0, 1.0, 0.0),
        ),
        "iron",
    )
    b.add_box((dc, -hy - 0.25, 0.08), (dw + 0.2, 0.36, 0.16), "frame")


# ---------------------------------------------------------------------------------------------
# Mushrooms (blender/lib/mushroom.py, shared with mushroom creatures): one, a cluster, or
# brackets on a wall. Their slots are the parts they have: cap, gills, stalk, ring, spots.
# ---------------------------------------------------------------------------------------------

MUSHROOM_SLOTS = ("cap", "gills", "stalk", "ring", "spots")


def _mushrooms(p: dict[str, float], shape: str, rng: random.Random) -> list[Part]:
    count = int(p["count"])
    parts: list[Part] = []
    for k in range(count):
        # The first is the biggest, in the middle; the rest round it, smaller, leaning out.
        size = 1.0 if k == 0 else rng.uniform(0.45, 0.85)
        a = rng.uniform(0, math.tau)
        d = 0.0 if k == 0 else p["spread"] * rng.uniform(0.5, 1.0)
        m = Mushroom(
            cap_radius=p["cap_radius"] * size * rng.uniform(0.9, 1.1),
            cap_height=p["cap_height"] * size * rng.uniform(0.85, 1.15),
            cap_shape=shape,
            stalk_height=p["stalk_height"] * size * rng.uniform(0.8, 1.15),
            stalk_radius=p["stalk_radius"] * (0.6 + 0.4 * size),
            bulb=p["bulb"],
            lean=(p["lean"] + (p["spread"] * 0.5 if k else 0.0)) * size * rng.uniform(0.5, 1.0),
            gills=int(p["gills"]),
            ring=p["ring"] > 0.5,
            volva=p["volva"] > 0.5,
            spots=int(p["spots"] * size),
            spot_radius=p["cap_radius"] * 0.12 * size,
            seed=rng.randrange(1 << 30),
            yaw=a,
            at=(d * math.cos(a), d * math.sin(a), 0.0),
            segments=int(p["segments"]),
        )
        parts.extend(mushroom(m))
    return parts


def _brackets(p: dict[str, float], shape: str, rng: random.Random) -> list[Part]:
    """Shelf fungi stepped up a wall at +Y: half caps, flat on top, ridged underneath."""
    parts: list[Part] = []
    for k in range(int(p["count"])):
        R = p["cap_radius"] * rng.uniform(0.6, 1.0) * (1.0 - 0.08 * k)
        H = R * 0.3
        z = 0.05 + k * p["spread"] * rng.uniform(0.8, 1.2)
        x = rng.uniform(-1, 1) * p["spread"]
        prof = [(R * 0.02, 0.0), (R, H * 0.1), (R * 0.98, H * 0.5), (R * 0.7, H), (R * 0.02, H * 1.05)]
        shell = lathe(prof, 10, start=math.pi, end=math.tau)
        # Bands of growth: a second, thinner lip under the first.
        lip = lathe(
            [(R * 0.02, -H * 0.25), (R * 0.85, -H * 0.15), (R * 0.85, -H * 0.05), (R * 0.02, 0.0)],
            10,
            start=math.pi,
            end=math.tau,
        )
        for sh, slot in ((shell, "cap"), (lip, "gills")):
            parts.append((place(sh, (x, 0.0, z)), slot))
    return parts


# ---------------------------------------------------------------------------------------------
# The crypts: skulls and long bones, heaped; candles on their own wax.
# ---------------------------------------------------------------------------------------------


def _blob(
    rx: float, ry: float, rz: float, at: tuple[float, float, float], steps: int = 8, seg: int = 12
) -> Shell:
    """An ellipsoid with half-axes rx, ry, rz, centred at `at`."""
    prof = [(math.sin(math.pi * i / steps), -math.cos(math.pi * i / steps)) for i in range(steps + 1)]
    prof[0], prof[-1] = (0.0, -1.0), (0.0, 1.0)
    return transform(lathe(prof, seg), lambda v: (at[0] + v[0] * rx, at[1] + v[1] * ry, at[2] + v[2] * rz))


def _skull(s: float) -> list[tuple[Shell, str]]:
    """A skull resting on its jaw, facing -Y, `s` = 1 for a man's (about 0.2 m long)."""
    parts = [
        (_blob(0.068 * s, 0.09 * s, 0.075 * s, (0.0, 0.012 * s, 0.09 * s), 10, 16), "bone"),
        # The face: brow, cheekbones and upper jaw, narrower and lower than the brain case.
        (_blob(0.054 * s, 0.05 * s, 0.05 * s, (0.0, -0.048 * s, 0.06 * s), 8, 14), "bone"),
    ]
    for side in (-1.0, 1.0):
        # Deep round sockets under the brow, and the cheekbones running back under them.
        parts.append(
            (_blob(0.021 * s, 0.012 * s, 0.019 * s, (side * 0.026 * s, -0.089 * s, 0.07 * s), 5, 10), "dark")
        )
        parts.append(
            (_blob(0.009 * s, 0.026 * s, 0.01 * s, (side * 0.047 * s, -0.06 * s, 0.047 * s), 4, 8), "bone")
        )
    parts.append((_blob(0.008 * s, 0.008 * s, 0.013 * s, (0.0, -0.1 * s, 0.045 * s), 4, 6), "dark"))
    # The lower jaw: a U of bone under the face, its teeth a dark line.
    jaw = [
        (0.045 * s * math.cos(a), -0.085 * s * math.sin(a), 0.016 * s)
        for a in [math.pi * i / 10 for i in range(11)]
    ]
    parts.append((sweep(jaw, rect(0.007 * s, 0.013 * s), up=(0.0, 0.0, 1.0)), "bone"))
    teeth = [
        (0.03 * s * math.cos(a), -0.084 * s * math.sin(a), 0.032 * s)
        for a in [math.pi * (0.2 + 0.6 * i / 6) for i in range(7)]
    ]
    parts.append((sweep(teeth, rect(0.003 * s, 0.004 * s), up=(0.0, 0.0, 1.0)), "dark"))
    return parts


def _long_bone(length: float, r: float) -> Shell:
    """A thigh or arm bone along X, lying on Z = 0: a shaft between two knuckled ends."""
    path = [(length * (i / 10 - 0.5), 0.0, r * 2.0) for i in range(11)]

    def girth(t: float) -> tuple[float, float]:
        end = max(0.0, 1.0 - min(t, 1.0 - t) * 6.0)
        k = r * (1.0 + 1.1 * end**2)
        return (k * (1.0 + 0.35 * end), k)

    return sweep(path, circle(1.0, 8), scale=girth, up=(0.0, 0.0, 1.0))


def _bones(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A heap of long bones with skulls set on and round it, as an ossuary stacks them."""
    for k in range(int(p["bones"])):
        length = rng.uniform(0.3, 0.46)
        layer = k // 4
        z = layer * 0.045
        y = rng.uniform(-0.5, 0.5) * p["spread"] * (1.0 - 0.25 * layer)
        x = rng.uniform(-0.3, 0.3) * p["spread"]
        _add(
            b,
            place(
                _long_bone(length, rng.uniform(0.011, 0.015)),
                (x, y, z),
                yaw=rng.uniform(-0.5, 0.5) + (0.0 if layer % 2 == 0 else 0.35),
            ),
            "bone",
        )
    top = (int(p["bones"]) - 1) // 4 * 0.045 + 0.05 if p["bones"] else 0.0
    for k in range(int(p["skulls"])):
        s = rng.uniform(0.9, 1.05)
        on = k == 0 and p["bones"] > 0
        a = rng.uniform(0, math.tau)
        d = 0.0 if on else p["spread"] * rng.uniform(0.45, 0.65)
        at = (d * math.cos(a), d * math.sin(a), top if on else 0.0)
        yaw = rng.uniform(-0.6, 0.6) + (0.0 if on else rng.choice((0.0, math.pi * 0.5, -math.pi * 0.5)))
        tilt = rng.uniform(-0.15, 0.15)
        for shell, slot in _skull(s):
            _add(b, place(shell, at, yaw=yaw, roll=tilt), slot)


def _candles(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Candles of several heights standing in a pool of their own spilt wax."""
    spread = p["spread"]
    _add(
        b,
        lathe(
            [(0.0, 0.0), (spread * 1.25, 0.0), (spread * 1.15, 0.008), (spread * 0.6, 0.014), (0.0, 0.016)],
            18,
        ),
        "wax",
    )
    for k in range(int(p["count"])):
        a = rng.uniform(0, math.tau)
        d = 0.0 if k == 0 else spread * rng.uniform(0.35, 0.9)
        h = p["height"] * (1.0 if k == 0 else rng.uniform(0.3, 0.85))
        r = rng.uniform(0.011, 0.018) * (1.25 if k == 0 else 1.0)
        at = (d * math.cos(a), d * math.sin(a), 0.0)
        # Burnt down: the top dished round the wick, a lip of wax run over one side.
        body = lathe([(0.0, 0.0), (r, 0.0), (r, h), (r * 0.8, h - 0.004), (0.0, h - 0.006)], 10)
        _add(b, place(body, at), "wax")
        drip = rng.uniform(0, math.tau)
        _add(
            b,
            _blob(
                r * 0.35,
                r * 0.35,
                h * 0.3,
                (at[0] + r * math.cos(drip), at[1] + r * math.sin(drip), h * 0.72),
                4,
                6,
            ),
            "wax",
        )
        _add(
            b,
            place(
                lathe([(0.0, 0.0), (0.0015, 0.0), (0.0012, 0.012), (0.0, 0.013)], 5),
                (at[0], at[1], h - 0.006),
            ),
            "wick",
        )


# ---------------------------------------------------------------------------------------------
# The rifts: a coil of old rope on its piton, a plank bridge across a slot.
# ---------------------------------------------------------------------------------------------


def _rope(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A coil of rope lying flat, its end run off to a piton driven into the floor at +Y."""
    R, rr, turns = p["radius"], p["thickness"] / 2, p["turns"]
    n = int(turns * 16)
    path = []
    for i in range(n + 1):
        t = i / n
        a = math.tau * turns * t
        # Each turn lies a little in from and over the one before, as a coil drops.
        rad = R * (1.0 + 0.06 * math.sin(a * 0.5 + 1.0)) - rr * 0.6 * turns * t
        path.append((rad * math.cos(a), rad * math.sin(a), rr + rr * 1.3 * turns * t))
    # The free end runs out to the piton.
    end = path[-1]
    tail = [
        (end[0] + (0.0 - end[0]) * t, end[1] + (R + 0.25 - end[1]) * t, end[2] * (1.0 - t) + 0.03 * t)
        for t in (0.33, 0.66, 1.0)
    ]
    _add(b, sweep(path + tail, circle(rr, 6), up=(0.0, 0.0, 1.0)), "rope")
    # The piton: a flat iron spike with an eye, standing a hand above the floor.
    px, py = 0.0, R + 0.28
    _add(b, sweep([(px, py, 0.0), (px, py, 0.09)], rect(0.008, 0.004), up=(0.0, 1.0, 0.0)), "iron")
    _add(
        b,
        place(
            ring([(0.012, -0.004), (0.018, -0.004), (0.018, 0.004), (0.012, 0.004)], 10),
            (px, py, 0.1),
            pitch=math.pi / 2,
        ),
        "iron",
    )


def _plank_bridge(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Planks nailed across two beams spanning X, a rope rail on posts along each side."""
    L, W = p["length"], p["width"]
    # The beams: rough baulks running the full span.
    for side in (-1.0, 1.0):
        y = side * (W / 2 - 0.08)
        _hexa(
            b,
            [
                (-L / 2, y - 0.07, 0.0),
                (L / 2, y - 0.07, 0.0),
                (L / 2, y + 0.07, 0.0),
                (-L / 2, y + 0.07, 0.0),
            ],
            [
                (-L / 2, y - 0.07, 0.16),
                (L / 2, y - 0.07, 0.16),
                (L / 2, y + 0.07, 0.16),
                (-L / 2, y + 0.07, 0.16),
            ],
            "beam",
        )
    # Planks: odd widths, a finger's gap between, each a little askew.
    x = -L / 2 + 0.02
    while x < L / 2 - 0.08:
        w = min(rng.uniform(0.18, 0.28), L / 2 - 0.02 - x)
        skew = rng.uniform(-0.015, 0.015)
        lift = rng.uniform(0.0, 0.006)
        y0, y1 = -W / 2, W / 2
        bottom = [
            (x + skew, y0, 0.16),
            (x + w + skew, y0, 0.16),
            (x + w - skew, y1, 0.16),
            (x - skew, y1, 0.16),
        ]
        top = [(q[0], q[1], 0.2 + lift) for q in bottom]
        _hexa(b, bottom, top, "planks")
        x += w + rng.uniform(0.01, 0.025)
    # Posts at the ends and the middle; a rope sagging between them.
    posts = [-L / 2 + 0.06, 0.0, L / 2 - 0.06] if L > 2.5 else [-L / 2 + 0.06, L / 2 - 0.06]
    for side in (-1.0, 1.0):
        y = side * (W / 2 - 0.04)
        for px in posts:
            _add(b, sweep([(px, y, 0.0), (px, y, 1.0)], rect(0.04, 0.04), up=(0.0, 1.0, 0.0)), "beam")
        rail = []
        for a, c in zip(posts, posts[1:], strict=False):
            for i in range(0 if not rail else 1, 9):
                t = i / 8
                rail.append((a + (c - a) * t, y, 0.95 - 0.12 * math.sin(math.pi * t)))
        _add(b, sweep(rail, circle(0.013, 6), up=(0.0, 0.0, 1.0)), "rope")


# ---------------------------------------------------------------------------------------------
# Root hollows: ferns, moss, hanging vines and pale flowers. Leaves are thin closed slabs.
# ---------------------------------------------------------------------------------------------

V3 = tuple[float, float, float]


def _leaf(b: MeshBuilder, base: V3, tip: V3, width: float, slot: str, thick: float = 0.003) -> None:
    """A flat leaf from `base` to `tip`, widest a third of the way, lying across the horizontal."""
    dx, dy, dz = tip[0] - base[0], tip[1] - base[1], tip[2] - base[2]
    flat = math.hypot(dx, dy) or 1.0
    # Across the leaf, level: perpendicular to its run in plan.
    ax, ay = -dy / flat * width / 2, dx / flat * width / 2
    mid = (base[0] + dx * 0.35, base[1] + dy * 0.35, base[2] + dz * 0.35)
    ring_ = [base, (mid[0] - ax, mid[1] - ay, mid[2]), tip, (mid[0] + ax, mid[1] + ay, mid[2])]
    area = sum(ring_[i][0] * ring_[(i + 1) % 4][1] - ring_[(i + 1) % 4][0] * ring_[i][1] for i in range(4))
    if area < 0:
        ring_.reverse()
    _hexa(b, ring_, [(x, y, z + thick) for x, y, z in ring_], slot)


def _frond(b: MeshBuilder, length: float, yaw: float, rise: float, rng: random.Random) -> None:
    """One fern frond: an arching stem with paired leaflets, shrinking to the tip."""
    n = 14
    cy, sy = math.cos(yaw), math.sin(yaw)

    def at(t: float) -> V3:
        d = length * t * 0.9
        z = length * rise * math.sin(math.pi * min(t * 1.1, 1.0) * 0.75) - length * 0.15 * t * t
        return (d * cy, d * sy, max(z, 0.01) if t > 0 else 0.0)

    path = [at(i / n) for i in range(n + 1)]
    _add(b, sweep(path, circle(1.0, 4), scale=lambda t: (0.005 * (1 - 0.7 * t),) * 2), "stem")
    for i in range(1, n):
        t = i / n
        x, y, z = at(t)
        size = length * 0.28 * math.sin(math.pi * (0.15 + 0.85 * t)) * rng.uniform(0.85, 1.05)
        for side in (-1.0, 1.0):
            # Leaflets point out and forward, drooping a little at their tips.
            ox, oy = -sy * side + cy * 0.45, cy * side + sy * 0.45
            tip = (x + ox * size, y + oy * size, z - size * 0.25)
            _leaf(b, (x, y, z), tip, size * 0.42, "leaf")


def _fern(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    for k in range(int(p["fronds"])):
        yaw = math.tau * k / p["fronds"] + rng.uniform(-0.25, 0.25)
        _frond(b, p["length"] * rng.uniform(0.75, 1.1), yaw, rng.uniform(0.75, 1.1), rng)


def _moss(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Cushions of moss: low lumpy domes run together."""
    seed = rng.uniform(0, 100)
    for k in range(int(p["tufts"])):
        r = p["radius"] * (1.0 if k == 0 else rng.uniform(0.4, 0.8))
        a, d = rng.uniform(0, math.tau), 0.0 if k == 0 else p["radius"] * rng.uniform(0.6, 1.1)
        cx, cy = d * math.cos(a), d * math.sin(a)
        h = r * rng.uniform(0.35, 0.5)
        prof = [(r * math.cos(math.pi / 2 * i / 8), h * math.sin(math.pi / 2 * i / 8)) for i in range(9)]
        dome = lathe([(0.0, -0.01), *prof[:-1], (0.0, h)], 20)

        def lump(v: V3, cx: float = cx, cy: float = cy, h: float = h) -> V3:
            x, y, z = v
            swell = 1.0 + 0.3 * noise.noise(x * 22 + seed, y * 22, z * 22)
            return (cx + x * swell, cy + y * swell, z * swell if z > 0 else z)

        _add(b, transform(dome, lump), "moss")


def _vines(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Strands of vine hanging from a knot of roots overhead, leaves all down them."""
    H, spread = p["length"], p["spread"]
    for k in range(int(p["strands"])):
        x0 = spread * (2.0 * k / max(1, p["strands"] - 1) - 1.0) * 0.8 + rng.uniform(-0.04, 0.04)
        y0 = rng.uniform(-0.3, 0.3) * spread
        L = H * rng.uniform(0.45, 1.0)
        phase = rng.uniform(0, math.tau)
        n = max(5, int(L / 0.09))
        path = [
            (
                x0 + 0.06 * math.sin(phase + 4.0 * i / n),
                y0 + 0.04 * math.cos(phase + 3.0 * i / n),
                H - L * i / n,
            )
            for i in range(n + 1)
        ]
        _add(b, sweep(path, circle(0.006, 5), up=(1.0, 0.0, 0.0)), "stem")
        # Each strand comes out of a knot of root where it clings overhead.
        _add(b, _blob(0.05, 0.04, 0.035, (x0, y0, H), 4, 7), "stem")
        for i in range(1, n + 1):
            x, y, z = path[i]
            a = phase + i * 2.4
            size = 0.09 * rng.uniform(0.7, 1.1) * (0.6 + 0.4 * i / n)
            tip = (x + size * math.cos(a), y + size * math.sin(a), z - size * 0.7)
            _leaf(b, (x, y, z), tip, size * 0.75, "leaf")


def _flowers(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A clump of pale flowers reaching for the light: stems, a few leaves, five-petalled heads."""
    for k in range(int(p["count"])):
        a = rng.uniform(0, math.tau)
        d = 0.0 if k == 0 else p["spread"] * rng.uniform(0.3, 1.0)
        h = p["height"] * (1.0 if k == 0 else rng.uniform(0.55, 0.95))
        lean = rng.uniform(0.0, 0.25) * h
        bx, by = d * math.cos(a), d * math.sin(a)
        path = [
            (bx + lean * (i / 6) ** 2 * math.cos(a), by + lean * (i / 6) ** 2 * math.sin(a), h * i / 6)
            for i in range(7)
        ]
        _add(b, sweep(path, circle(0.003, 4), up=(1.0, 0.0, 0.0)), "stem")
        for j in range(2):
            la = a + math.pi * (j + rng.uniform(-0.2, 0.2))
            base = (bx, by, 0.01 + j * 0.02)
            size = h * rng.uniform(0.3, 0.45)
            _leaf(
                b, base, (bx + size * math.cos(la), by + size * math.sin(la), size * 0.3), size * 0.35, "leaf"
            )
        top = path[-1]
        r = p["petal"] * rng.uniform(0.8, 1.1)
        spin = rng.uniform(0, math.tau)
        for j in range(5):
            pa = spin + math.tau * j / 5
            tip = (top[0] + r * math.cos(pa), top[1] + r * math.sin(pa), top[2] + r * 0.35)
            _leaf(b, top, tip, r * 0.8, "petal", 0.002)
        _add(b, _blob(r * 0.25, r * 0.25, r * 0.18, (top[0], top[1], top[2] + 0.004), 4, 8), "heart")


# ---------------------------------------------------------------------------------------------
# Gates, crystals and lava: an iron grille, hexagonal spars, drips of cooled lava, fallen rock.
# ---------------------------------------------------------------------------------------------


def _gate(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """An iron grille gate across X: a frame, round bars with spear tips, flat cross bands."""
    W, H = p["width"], p["height"]
    for x in (-W / 2 + 0.05, W / 2 - 0.05):
        _add(b, sweep([(x, 0.0, 0.0), (x, 0.0, H)], rect(0.05, 0.05), up=(0.0, 1.0, 0.0)), "iron")
    _add(
        b,
        sweep([(-W / 2, 0.0, H - 0.05), (W / 2, 0.0, H - 0.05)], rect(0.05, 0.05), up=(0.0, 0.0, 1.0)),
        "iron",
    )
    bars = max(2, round((W - 0.1) / p["spacing"]))
    for k in range(1, bars):
        x = -W / 2 + 0.05 + (W - 0.1) * k / bars
        # Bent a little, as old iron is; the tip pokes through the top beam.
        bend = rng.uniform(-0.012, 0.012)
        path = [(x + bend * math.sin(math.pi * i / 4), 0.0, 0.02 + (H - 0.12) * i / 4) for i in range(5)]
        _add(b, sweep(path, circle(0.016, 6), up=(0.0, 1.0, 0.0)), "iron")
        _add(b, place(lathe([(0.0, 0.0), (0.03, 0.0), (0.0, 0.11)], 4), (x, 0.0, H - 0.005)), "iron")
    for z in (0.35, H * 0.55):
        _add(
            b,
            sweep([(-W / 2 + 0.05, 0.0, z), (W / 2 - 0.05, 0.0, z)], rect(0.03, 0.012), up=(0.0, 0.0, 1.0)),
            "iron",
        )
    # A ring handle and a lock box in the middle.
    _add(b, _blob(0.07, 0.05, 0.09, (0.0, -0.03, H * 0.42), 3, 4), "iron")
    _add(
        b,
        place(
            ring([(0.04, -0.006), (0.052, -0.006), (0.052, 0.006), (0.04, 0.006)], 10),
            (0.0, -0.09, H * 0.36),
            pitch=math.pi / 2,
        ),
        "iron",
    )


def _crystals(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Hexagonal spars with pyramid tips, sprouting from one root and leaning outwards."""
    for k in range(int(p["count"])):
        size = 1.0 if k == 0 else rng.uniform(0.3, 0.75)
        L = p["length"] * size
        r = p["radius"] * size * rng.uniform(0.85, 1.15)
        tip = r * rng.uniform(1.2, 1.8)
        spar = lathe([(0.0, -r), (r, -r), (r, L - tip), (0.0, L)], 6)
        a = rng.uniform(0, math.tau)
        lean = 0.0 if k == 0 else rng.uniform(0.25, 0.75)
        d = 0.0 if k == 0 else p["radius"] * rng.uniform(0.3, 1.0)
        spar = place(spar, (0.0, 0.0, 0.0), yaw=rng.uniform(0, math.tau))
        _add(b, place(spar, (d * math.cos(a), d * math.sin(a), 0.0), roll=lean, yaw=a), "crystal")


def _drips(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Cooled lava hanging from a crust overhead: knobbly cones run together at the root."""
    L0 = p["length"]
    _add(b, _blob(L0 * 0.24, L0 * 0.2, L0 * 0.05, (0.0, 0.0, L0), 4, 10), "rock")
    for k in range(int(p["count"])):
        L = L0 * (1.0 if k == 0 else rng.uniform(0.3, 0.75))
        r = L * rng.uniform(0.14, 0.2)
        a, d = rng.uniform(0, math.tau), 0.0 if k == 0 else L0 * rng.uniform(0.08, 0.25)
        prof = [(0.0, L0 - L)]
        for i in range(1, 8):
            t = i / 7  # 0 at the point, 1 at the root
            knob = 1.0 + 0.18 * math.sin(t * 13.0 + k)
            prof.append((r * t**0.8 * knob, L0 - L + L * t))
        prof.append((0.0, L0 + 0.02))
        _add(b, place(lathe(prof, 8), (d * math.cos(a), d * math.sin(a), 0.0), yaw=rng.uniform(0, 1)), "rock")


def _boulder(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> list[float]:
    """A fallen block: a squared lump with broken faces, flat where it landed."""
    sx, sy, sz = p["size_x"], p["size_y"], p["size_z"]
    cube, faces = grid_cube(3)
    seed = rng.uniform(0, 100)
    shade: list[float] = []
    verts: list[Vec] = []
    for co in cube:
        # Round the corners a little towards a sphere, then break the faces with coarse noise.
        length = math.sqrt(co[0] ** 2 + co[1] ** 2 + co[2] ** 2)
        qx, qy, qz = (c + (c / length * 0.62 - c) * 0.35 for c in co)
        swell = 1.0 + 0.16 * noise.noise(qx * 2.2 + seed, qy * 2.2, qz * 2.2)
        x, y, z = qx * swell * sx, qy * swell * sy, (qz * swell + 0.5) * sz
        verts.append((x, y, max(z, 0.0)))
        shade.append(0.85 + 0.15 * noise.noise(x * 3, y * 3 + seed, z * 3))
    b.add_shell(verts, faces, "rock")
    return shade


# ---------------------------------------------------------------------------------------------
# Dwarven halls: a forge with its anvil, a king in granite, a brazier, a hanging chain.
# ---------------------------------------------------------------------------------------------


def _box(b: MeshBuilder, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, slot: str) -> None:
    _hexa(
        b,
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
        [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        slot,
    )


def _forge(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A squat stone hearth with a chimney hood, its firebox open to the front (-Y), an anvil
    beside it. With `fire_only` it is just the glowing coals in the firebox, for the glow pass."""
    if p["fire_only"] > 0.5:
        _box(b, -0.42, 0.42, -0.5, 0.0, 0.62, 0.7, "fire")
        for _ in range(9):
            at = (rng.uniform(-0.35, 0.35), rng.uniform(-0.42, -0.08), 0.7)
            _add(b, _blob(0.06, 0.05, 0.035, at, 3, 6), "fire")
        return
    # The hearth: a stone block with the firebox as a deep notch in its front.
    _box(b, -0.7, 0.7, -0.55, 0.55, 0.0, 0.62, "stone")
    _box(b, -0.7, -0.45, -0.55, 0.55, 0.62, 1.05, "stone")
    _box(b, 0.45, 0.7, -0.55, 0.55, 0.62, 1.05, "stone")
    _box(b, -0.45, 0.45, 0.0, 0.55, 0.62, 1.05, "stone")
    # The hood narrowing up into a flue.
    _hexa(
        b,
        [(-0.72, -0.57, 1.05), (0.72, -0.57, 1.05), (0.72, 0.57, 1.05), (-0.72, 0.57, 1.05)],
        [(-0.3, -0.12, 1.45), (0.3, -0.12, 1.45), (0.3, 0.42, 1.45), (-0.3, 0.42, 1.45)],
        "stone",
    )
    _box(b, -0.25, 0.25, -0.08, 0.38, 1.45, 1.6, "stone")
    # A bellows' iron nozzle into the side, and the anvil on its block.
    _add(b, sweep([(0.95, 0.15, 0.4), (0.7, 0.15, 0.4)], circle(0.05, 8)), "iron")
    ax, ay = -1.15, -0.25
    _box(b, ax - 0.2, ax + 0.2, ay - 0.2, ay + 0.2, 0.0, 0.45, "wood")
    _box(b, ax - 0.12, ax + 0.12, ay - 0.1, ay + 0.1, 0.45, 0.62, "iron")
    _box(b, ax - 0.2, ax + 0.2, ay - 0.13, ay + 0.13, 0.62, 0.74, "iron")
    _add(
        b,
        place(lathe([(0.0, 0.0), (0.065, 0.0), (0.0, 0.22)], 8), (ax + 0.2, ay, 0.69), roll=math.pi / 2),
        "iron",
    )


def _statue(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A dwarf king carved in one stone, facing -Y: broad robed body, a beard to his belt,
    a crown, and both hands on the haft of a hammer stood before him. On a stepped plinth."""
    H = p["height"]
    s = H / 4.0
    _box(b, -0.9 * s, 0.9 * s, -0.8 * s, 0.8 * s, 0.0, 0.35 * s, "stone")
    _box(b, -0.75 * s, 0.75 * s, -0.65 * s, 0.65 * s, 0.35 * s, 0.75 * s, "stone")
    z0 = 0.75 * s
    # Robe and body: a broad squat cone, then shoulders.
    body = [
        (0.0, z0),
        (0.68 * s, z0),
        (0.62 * s, z0 + 0.6 * s),
        (0.58 * s, z0 + 1.45 * s),
        (0.72 * s, z0 + 1.85 * s),
        (0.45 * s, z0 + 2.1 * s),
        (0.0, z0 + 2.15 * s),
    ]
    _add(b, transform(lathe(body, 16), lambda v: (v[0], v[1] * 0.75, v[2])), "stone")
    head_z = z0 + 2.45 * s
    _add(b, _blob(0.34 * s, 0.33 * s, 0.38 * s, (0.0, 0.0, head_z), 8, 14), "stone")
    # Heavy brow and nose, then the beard falling broad and thick to below the belt.
    _add(b, _blob(0.27 * s, 0.1 * s, 0.07 * s, (0.0, -0.27 * s, head_z + 0.1 * s), 4, 8), "stone")
    _add(b, _blob(0.07 * s, 0.1 * s, 0.11 * s, (0.0, -0.34 * s, head_z - 0.02 * s), 4, 6), "stone")
    zt, zb = head_z - 0.05 * s, z0 + 0.85 * s
    beard = lathe(
        [(0.0, zb), (0.1 * s, zb), (0.3 * s, zb + 0.5 * s), (0.36 * s, zt), (0.0, zt + 0.06 * s)], 14
    )
    _add(b, transform(beard, lambda v: (v[0], v[1] * 0.55 - 0.36 * s, v[2])), "stone")
    # The crown: a band with five points.
    cz = head_z + 0.24 * s
    _add(
        b,
        ring([(0.31 * s, cz), (0.36 * s, cz), (0.36 * s, cz + 0.14 * s), (0.31 * s, cz + 0.14 * s)], 14),
        "gold",
    )
    for k in range(5):
        a = -math.pi / 2 + math.tau * k / 5
        at = (0.335 * s * math.cos(a), 0.335 * s * math.sin(a), cz + 0.12 * s)
        _add(b, place(lathe([(0.0, 0.0), (0.05 * s, 0.0), (0.0, 0.16 * s)], 4), at), "gold")
    # Arms from the shoulders to the hands on the haft; the hammer's head on the plinth.
    hx, hy = 0.0, -0.75 * s
    for side in (-1.0, 1.0):
        arm = [
            (side * 0.55 * s, -0.05 * s, z0 + 1.85 * s),
            (side * 0.5 * s, -0.4 * s, z0 + 1.25 * s),
            (side * 0.12 * s, -0.68 * s, z0 + 1.15 * s),
        ]
        _add(b, sweep(arm, circle(0.13 * s, 8), up=(0.0, 0.0, 1.0)), "stone")
        _add(b, _blob(0.11 * s, 0.1 * s, 0.1 * s, (side * 0.09 * s, -0.7 * s, z0 + 1.15 * s), 4, 8), "stone")
    _add(
        b,
        sweep([(hx, hy, z0 + 0.25 * s), (hx, hy, z0 + 1.4 * s)], circle(0.05 * s, 8), up=(0.0, 1.0, 0.0)),
        "stone",
    )
    _box(b, hx - 0.32 * s, hx + 0.32 * s, hy - 0.15 * s, hy + 0.15 * s, z0, z0 + 0.3 * s, "stone")


def _brazier(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A wide iron bowl on three splayed legs, a ring joining them, dead coals in the bowl."""
    H, R = p["height"], p["radius"]
    bowl = [
        (0.0, H - 0.18),
        (R * 0.55, H - 0.18),
        (R, H),
        (R * 1.04, H + 0.02),
        (R * 0.97, H + 0.02),
        (R * 0.52, H - 0.15),
        (0.0, H - 0.15),
    ]
    _add(b, lathe(bowl, 16), "iron")
    for k in range(3):
        a = math.tau * k / 3
        c, sn = math.cos(a), math.sin(a)
        leg = [
            (R * 0.5 * c, R * 0.5 * sn, H - 0.16),
            (R * 0.75 * c, R * 0.75 * sn, H * 0.45),
            (R * 1.0 * c, R * 1.0 * sn, 0.0),
        ]
        _add(b, sweep(leg, rect(0.022, 0.022), up=(0.0, 0.0, 1.0)), "iron")
    _add(
        b,
        place(
            ring([(R * 0.74, -0.012), (R * 0.79, -0.012), (R * 0.79, 0.012), (R * 0.74, 0.012)], 16),
            (0.0, 0.0, H * 0.42),
        ),
        "iron",
    )
    for _ in range(7):
        a, d = rng.uniform(0, math.tau), rng.uniform(0, R * 0.5)
        _add(b, _blob(0.06, 0.05, 0.035, (d * math.cos(a), d * math.sin(a), H - 0.1), 3, 6), "coal")


def _chain(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Heavy oval links hanging straight, each turned a quarter to the last, from a ceiling plate."""
    L, w = p["length"], p["link"]
    t = w * 0.16  # bar thickness
    n = max(2, int(L / (w * 1.25)))
    pitch = L / n
    for k in range(n):
        z = k * pitch + w * 0.7
        oval = []
        for i in range(12):
            a = math.tau * i / 12
            oval.append((w * 0.4 * math.cos(a), 0.0, z + w * 0.7 * math.sin(a)))
        oval.append(oval[0])
        link = sweep(oval, circle(t, 5), up=(0.0, 1.0, 0.0))
        _add(b, place(link, (0.0, 0.0, 0.0), yaw=(math.pi / 2) * (k % 2)), "iron")
    _box(b, -0.15, 0.15, -0.15, 0.15, L + w * 0.6, L + w * 0.75, "iron")


def _hatchet(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A one-hand hatchet standing on its butt: a slim ash handle swelling to the grip, the iron
    head on top with a bearded blade out along +X, its edge ground bright, and a short poll."""
    L, reach = p["handle_length"], p["blade"]
    _handle(b, L + 0.02, 0.015, 0.012, rng.uniform(-0.004, 0.004))
    z = L - 0.03

    def blade(t: float) -> tuple[float, float]:
        # t runs from the eye (0) to the edge (1): thinner in Y, deeper in Z (the beard drops).
        return (0.011 * (1.0 - 0.85 * t), 0.024 + 0.034 * t * t)

    path = [(reach * i / 8, 0.0, z - 0.012 * (i / 8) ** 2) for i in range(9)]
    _add(b, sweep(path, rect(1.0, 1.0), scale=blade, up=(0.0, 0.0, 1.0)), "iron")
    edge = [(reach - 0.014, 0.0, z - 0.012), (reach, 0.0, z - 0.012)]
    _add(b, sweep(edge, rect(0.003, 0.056), up=(0.0, 0.0, 1.0)), "edge")
    # The eye round the handle and the poll behind it.
    _add(
        b,
        place(lathe([(0.0, -0.028), (0.021, -0.028), (0.021, 0.028), (0.0, 0.028)], 8), (0.0, 0.0, z)),
        "iron",
    )
    _box(b, -0.045, -0.012, -0.012, 0.012, z - 0.022, z + 0.022, "iron")


def _crowbar(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A crowbar standing on its chisel end: a straight bar, bent over at the top into a
    goose-neck whose split claw points back down; both working ends worn bright."""
    L, r = p["length"], p["radius"]
    hook = 0.042 * L / 0.6
    bar = [(0.0, 0.0, 0.04 + (L - 0.04) * i / 8) for i in range(9)]
    for i in range(1, 10):
        a = math.pi * i / 9
        bar.append((-hook + hook * math.cos(a), 0.0, L + hook * 0.9 * math.sin(a)))
    bar.append((-2 * hook - 0.004, 0.0, L - 0.02))
    _add(b, sweep(bar, circle(r, 6), up=(0.0, 1.0, 0.0)), "iron")
    # The claw: flattened and split, and the chisel at the foot: both bright from use.
    tip = [(-2 * hook - 0.004, 0.0, L - 0.005), (-2 * hook - 0.008, 0.0, L - 0.05)]
    for side in (-1.0, 1.0):
        claw = [(x, side * r * 0.5, z) for x, _, z in tip]
        _add(
            b,
            sweep(claw, rect(r * 0.5, r * 0.42), scale=lambda t: (1.0 - 0.5 * t, 1.0), up=(1.0, 0.0, 0.0)),
            "worn",
        )
    chisel = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.05)]
    _add(
        b,
        sweep(chisel, rect(r * 0.95, r * 1.25), scale=lambda t: (0.35 + 0.65 * t, 1.0), up=(1.0, 0.0, 0.0)),
        "worn",
    )


def _hard_hat(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A miner's hard hat for a head of radius `head` (the humanoid's headRadius): an enamel dome,
    longer front to back, a ridge over the crown, a brim turned down at the edge, a few dents, and
    a lamp on an iron bracket at the front (-Y). Origin under the brim's centre, so a rigid part
    places it on the head socket."""
    s = p["head"] / 0.1
    a, c, t, rb = 0.098 * s, 0.115 * s, 0.006 * s, 0.132 * s
    long = 1.12  # the dome's stretch front to back
    arc = [math.radians(d) for d in range(90, -1, -5)]
    inner = [(a * math.cos(q), c * math.sin(q)) for q in arc]
    outer = [((a + t) * math.cos(q), 0.008 * s + (c + t - 0.008 * s) * math.sin(q)) for q in reversed(arc)]
    brim = [
        (rb - 0.012 * s, -0.001 * s),
        (rb, -0.009 * s),
        (rb + 0.004 * s, -0.006 * s),
        (rb - 0.01 * s, 0.007 * s),
    ]
    dome = lathe([(0.0, inner[0][1]), *inner[1:], *brim, *outer[:-1], (0.0, outer[-1][1])], 32)

    # Dents: shallow dimples pushed in along the radius, both skins together, never on the lamp.
    dents = []
    for _ in range(int(p["dents"])):
        yaw = rng.uniform(-math.pi * 0.25, math.pi * 1.25)  # anywhere but the front quarter
        tilt = rng.uniform(0.35, 1.2)
        dents.append(
            (
                (math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), math.sin(tilt)),
                rng.uniform(0.006, 0.01) * s,
            )
        )

    def dented(v: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = v
        n = math.sqrt(x * x + y * y + z * z) or 1.0
        if z < 0.012 * s:
            return (x, y * long, z)
        d = 0.0
        for (dx, dy, dz), depth in dents:
            dot = (x * dx + y * dy + z * dz) / n
            d += depth * math.exp(-(((1.0 - dot) / 0.035) ** 2))
        k = 1.0 - d / n
        return (x * k, y * k * long, z * k)

    _add(b, transform(dome, dented), "enamel")
    ridge = [
        (0.0, (a + t * 0.5) * math.cos(q), 0.008 * s + (c + t * 0.5 - 0.008 * s) * math.sin(q))
        for q in [math.radians(d) for d in range(25, 146, 10)]
    ]
    _add(b, transform(sweep(ridge, rect(0.009 * s, 0.006 * s), up=(1.0, 0.0, 0.0)), dented), "enamel")

    # The lamp: an iron clip on the front of the dome, a short barrel looking forward, a pale lens.
    q = math.asin(0.55)
    zl, yl = 0.072 * s, -(a + t) * math.cos(q) * long
    _box(b, -0.014 * s, 0.014 * s, yl - 0.004 * s, yl + 0.012 * s, zl - 0.03 * s, zl + 0.022 * s, "iron")
    lr, ll = 0.021 * s, 0.026 * s
    barrel = lathe([(0.0, 0.0), (lr * 0.8, 0.0), (lr, ll * 0.4), (lr, ll), (lr * 0.82, ll), (0.0, ll)], 14)
    _add(b, place(barrel, (0.0, yl - 0.003 * s, zl), pitch=math.pi / 2), "iron")
    lens = lathe([(0.0, 0.0), (lr * 0.84, 0.0), (lr * 0.84, 0.004 * s), (0.0, 0.004 * s)], 14)
    _add(b, place(lens, (0.0, yl - 0.003 * s - ll + 0.002 * s, zl), pitch=math.pi / 2), "lens")


# ---------------------------------------------------------------------------------------------
# Grandma's furniture: upholstery as rounded pillows, turned legs, joinery with real thickness.
# ---------------------------------------------------------------------------------------------


def _pillow(
    hx: float, hy: float, hz: float, at: tuple[float, float, float], e: float = 0.45, tilt: float = 0.0
) -> Shell:
    """A rounded box (a superellipsoid) of half sizes hx, hy, hz at `at`, tipped back by `tilt`
    radians about X: a cushion when `e` is near 0.5, a board with eased edges when it is small."""

    def f(v: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = (math.copysign(abs(c) ** e, c) for c in v)
        x, y, z = x * hx, y * hy, z * hz
        y, z = y * math.cos(tilt) + z * math.sin(tilt), -y * math.sin(tilt) + z * math.cos(tilt)
        return (at[0] + x, at[1] + y, at[2] + z)

    return transform(_blob(1.0, 1.0, 1.0, (0.0, 0.0, 0.0), 10, 16), f)


def _turned(profile: list[tuple[float, float]], at: tuple[float, float, float], seg: int = 12) -> Shell:
    """A turned part (a leg, a column) from its outline [(radius, z), ...], closed at both ends."""
    z0, z1 = profile[0][1], profile[-1][1]
    return place(lathe([(0.0, z0), *profile, (0.0, z1)], seg), at)


def _armchair(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """Grandma's wing armchair (or, wider and without wings, her sofa): a deep sprung seat with
    loose cushions, a buttoned back tipped a little, wings at the head, rolled arms, short turned
    legs. The front faces -Y."""
    w, seat, n = p["width"] / 2, p["seat"], max(1, int(p["cushions"]))
    tilt = 0.17
    _add(b, _pillow(w - 0.05, 0.37, 0.11, (0.0, 0.0, seat - 0.2)), "plush")
    inner = w - 0.12
    for k in range(n):
        cx = -inner + inner * (2 * k + 1) / n
        _add(b, _pillow(inner / n - 0.01, 0.31, 0.06, (cx, -0.05, seat - 0.055), e=0.5), "plush")
    back = (0.0, 0.3, seat + 0.33)
    _add(b, _pillow(w - 0.06, 0.08, 0.38, back, tilt=tilt), "plush")
    for side in (-1.0, 1.0):
        # The wings, the arms and the scroll rolled over at the top of each arm.
        if p["wings"] > 0.5:
            _add(b, _pillow(0.06, 0.13, 0.17, (side * (w - 0.08), 0.24, seat + 0.38), tilt=tilt), "plush")
        _add(b, _pillow(0.07, 0.36, 0.14, (side * (w - 0.06), -0.01, seat - 0.05)), "plush")
        roll = [(side * (w - 0.055), -0.38, seat + 0.1), (side * (w - 0.055), 0.28, seat + 0.1)]
        _add(b, sweep(roll, circle(0.075, 12), up=(0.0, 0.0, 1.0)), "plush")
        for fy in (-1.0, 1.0):
            leg = [(0.03, 0.0), (0.024, 0.04), (0.028, 0.1), (0.036, 0.16), (0.036, seat - 0.26)]
            _add(b, _turned(leg, (side * (w - 0.08), fy * 0.3, 0.0), 10), "wood")
    # Buttons in diamonds across the back, sunk into its front face.
    c, sn = math.cos(tilt), math.sin(tilt)
    for k in range(n):
        cx = -inner + inner * (2 * k + 1) / n
        for bx, bz in ((-0.12, 0.08), (0.12, 0.08), (0.0, 0.2), (-0.12, 0.32), (0.12, 0.32), (0.0, -0.04)):
            ly = -0.072
            at = (cx + bx * min(1.0, inner / n / 0.3), back[1] + ly * c + bz * sn, back[2] - ly * sn + bz * c)
            _add(b, _blob(0.016, 0.012, 0.016, at, 4, 8), "button")


def _side_table(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A round lamp table on one turned column and a round foot."""
    H, R = p["height"], p["radius"]
    k = H / 0.62
    prof = [
        (0.16, 0.0),
        (0.16, 0.016),
        (0.12, 0.034),
        (0.06, 0.05 * k),
        (0.036, 0.08 * k),
        (0.032, 0.12 * k),
        (0.044, 0.18 * k),
        (0.046, 0.22 * k),
        (0.03, 0.28 * k),
        (0.026, 0.34 * k),
        (0.036, 0.42 * k),
        (0.036, 0.46 * k),
        (0.024, 0.52 * k),
        (0.04, H - 0.06),
        (0.07, H - 0.03),
        (R, H - 0.026),
        (R + 0.006, H - 0.013),
        (R, H),
    ]
    _add(b, _turned(prof, (0.0, 0.0, 0.0), 24), "wood")


def _chair(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A plain kitchen chair: a board seat, square legs tapering to the floor, the back legs
    running on up into posts with a top rail, a middle rail and three spindles; stretchers low."""
    seat, back = p["seat"], p["back"]
    hx, hy = 0.2, 0.19
    _add(b, _pillow(hx + 0.015, hy + 0.02, 0.016, (0.0, 0.0, seat - 0.016), e=0.15), "wood")

    def taper(t: float) -> tuple[float, float]:
        return (0.013 + 0.006 * t, 0.013 + 0.006 * t)

    for side in (-1.0, 1.0):
        x = side * (hx - 0.02)
        _add(
            b,
            sweep([(x, -hy + 0.02, 0.0), (x, -hy + 0.02, seat - 0.03)], rect(1.0, 1.0), scale=taper),
            "wood",
        )
        post = [(x, hy - 0.02, 0.0), (x, hy - 0.02, seat - 0.03), (x * 0.96, hy + 0.03, back)]
        _add(b, sweep(post, rect(0.019, 0.019), up=(1.0, 0.0, 0.0)), "wood")
        _add(b, sweep([(x, -hy + 0.02, 0.14), (x, hy - 0.02, 0.14)], circle(0.009, 6)), "wood")
    _add(b, sweep([(-hx + 0.02, -hy + 0.02, 0.2), (hx - 0.02, -hy + 0.02, 0.2)], circle(0.009, 6)), "wood")
    lean = 0.05 / (back - seat)
    for z, h in ((back - 0.05, 0.045), (seat + 0.2, 0.02)):
        y = hy - 0.02 + (z - seat) * lean
        _add(b, _pillow(hx - 0.01, 0.012, h, (0.0, y, z), e=0.2, tilt=-math.atan(lean)), "wood")
    for k in (-1, 0, 1):
        z0, z1 = seat + 0.2, back - 0.05
        rail = [
            (k * 0.08, hy - 0.02 + (z0 - seat) * lean, z0),
            (k * 0.08, hy - 0.02 + (z1 - seat) * lean, z1),
        ]
        _add(b, sweep(rail, circle(0.009, 6)), "wood")


def _table(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A kitchen table: a scrubbed top with eased edges on an apron, four turned legs."""
    H, hx, hy = p["height"], p["length"] / 2, p["width"] / 2
    _add(b, _pillow(hx, hy, 0.016, (0.0, 0.0, H - 0.016), e=0.12), "top")
    lx, ly = hx - 0.07, hy - 0.07
    for side in (-1.0, 1.0):
        _box(b, side * lx - 0.012, side * lx + 0.012, -ly, ly, H - 0.12, H - 0.032, "wood")
        _box(b, -lx, lx, side * ly - 0.012, side * ly + 0.012, H - 0.12, H - 0.032, "wood")
        for fy in (-1.0, 1.0):
            leg = [(0.018, 0.0), (0.022, 0.03), (0.02, 0.06), (0.03, 0.4), (0.024, 0.5), (0.03, 0.56)]
            leg += [(0.032, 0.6), (0.032, H - 0.032)]
            _add(b, _turned(leg, (side * lx, fy * ly, 0.0), 10), "wood")


def _cabinet(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A case piece (wardrobe, sideboard, cupboard) facing -Y: a carcass on short turned feet or a
    plinth, a row of drawers over panelled doors, a top that overhangs, a cornice when tall,
    brass knobs."""
    W, D, H = p["width"] / 2, p["depth"] / 2, p["height"]
    foot, n, drawers = p["feet"], max(1, int(p["doors"])), p["drawers"] > 0.5
    _box(b, -W + 0.02, W - 0.02, -D + 0.02, D - 0.02, foot, H - 0.03, "wood")
    _add(b, _pillow(W + 0.02, D + 0.02, 0.015, (0.0, -0.01, H - 0.015), e=0.15), "wood")
    if p["cornice"] > 0.5:
        _add(b, _pillow(W + 0.05, D + 0.04, 0.035, (0.0, -0.02, H + 0.025), e=0.2), "wood")
    if foot > 0.0:
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                f = [(0.022, 0.0), (0.03, foot * 0.5), (0.034, foot + 0.01)]
                _add(b, _turned(f, (sx * (W - 0.06), sy * (D - 0.06), 0.0), 10), "wood")
    else:
        _box(b, -W + 0.03, W - 0.03, -D + 0.03, D - 0.03, 0.0, 0.08, "wood")
    z0, z1 = max(foot, 0.08) + 0.03, H - 0.06
    face = -D + 0.02
    if drawers:
        dz = min(0.16, (z1 - z0) * 0.2)
        for k in range(n):
            x0 = -W + 0.05 + (2 * W - 0.1) * k / n
            x1 = -W + 0.05 + (2 * W - 0.1) * (k + 1) / n
            _box(b, x0 + 0.01, x1 - 0.01, face - 0.018, face, z1 - dz, z1, "panel")
            _add(b, _blob(0.014, 0.018, 0.014, ((x0 + x1) / 2, face - 0.03, z1 - dz / 2), 4, 8), "brass")
        z1 -= dz + 0.03
    for k in range(n):
        x0 = -W + 0.05 + (2 * W - 0.1) * k / n
        x1 = -W + 0.05 + (2 * W - 0.1) * (k + 1) / n
        _box(b, x0 + 0.01, x1 - 0.01, face - 0.012, face, z0, z1, "wood")
        # The raised panel in the door.
        _box(b, x0 + 0.06, x1 - 0.06, face - 0.024, face - 0.012, z0 + 0.06, z1 - 0.06, "panel")
        kx = x1 - 0.05 if k % 2 == 0 else x0 + 0.05
        _add(b, _blob(0.013, 0.016, 0.013, (kx, face - 0.03, (z0 + z1) / 2), 4, 8), "brass")


def _bed(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A made double bed, its head to -Y: a wooden frame with a tall headboard and a low
    footboard between turned posts, the mattress, the eiderdown folded back, two pillows."""
    W, L = p["width"] / 2, p["length"] / 2
    for y, top in ((-L, 1.0), (L, 0.62)):
        for sx in (-1.0, 1.0):
            post = [
                (0.03, 0.0),
                (0.034, 0.05),
                (0.03, 0.12),
                (0.032, top - 0.06),
                (0.042, top - 0.03),
                (0.02, top),
            ]
            _add(b, _turned(post, (sx * W, y, 0.0), 10), "wood")
        _box(b, -W + 0.02, W - 0.02, y - 0.018, y + 0.018, 0.22, top - 0.08, "wood")
    for sx in (-1.0, 1.0):
        _box(b, sx * W - 0.02, sx * W + 0.02, -L, L, 0.2, 0.36, "wood")
    _add(b, _pillow(W - 0.03, L - 0.04, 0.09, (0.0, 0.0, 0.43), e=0.3), "linen")
    _add(b, _pillow(W - 0.01, L * 0.62, 0.035, (0.0, L * 0.34, 0.53), e=0.35), "blanket")
    _add(b, _pillow(W - 0.01, 0.12, 0.05, (0.0, -L + L * 0.76, 0.53), e=0.45), "blanket")
    for sx in (-1.0, 1.0):
        _add(b, _pillow(W * 0.42, 0.17, 0.06, (sx * W * 0.47, -L + 0.26, 0.56), e=0.5, tilt=-0.25), "linen")


def _stove(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """An enamelled kitchen range on legs, facing -Y: an oven door with a handle bar, a black
    hob with two plates, a back splash, knobs along the top front."""
    W, D, H = 0.32, 0.31, p["height"]
    _add(b, _pillow(W, D, (H - 0.12) / 2, (0.0, 0.0, 0.12 + (H - 0.12) / 2), e=0.12), "enamel")
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            _box(
                b,
                sx * (W - 0.03) - 0.015,
                sx * (W - 0.03) + 0.015,
                sy * (D - 0.03) - 0.015,
                sy * (D - 0.03) + 0.015,
                0.0,
                0.13,
                "iron",
            )
    _box(b, -W + 0.01, W - 0.01, -D + 0.01, D - 0.01, H, H + 0.012, "iron")
    for x in (-0.13, 0.13):
        _add(
            b,
            place(lathe([(0.0, 0.0), (0.085, 0.0), (0.085, 0.012), (0.0, 0.012)], 16), (x, -0.02, H + 0.01)),
            "iron",
        )
    _box(b, -W, W, D - 0.02, D + 0.01, H, H + 0.22, "enamel")
    _add(b, _pillow(W - 0.05, 0.012, 0.21, (0.0, -D - 0.004, 0.42), e=0.15), "enamel")
    _add(b, sweep([(-0.2, -D - 0.05, 0.66), (0.2, -D - 0.05, 0.66)], circle(0.009, 6)), "chrome")
    for x in (-0.2, 0.2):
        _box(b, x - 0.008, x + 0.008, -D - 0.05, -D - 0.005, 0.655, 0.665, "chrome")
    for k in range(4):
        _add(
            b,
            place(
                lathe([(0.0, 0.0), (0.018, 0.0), (0.016, 0.02), (0.0, 0.02)], 8),
                (-0.18 + 0.12 * k, -D, H - 0.06),
                pitch=math.pi / 2,
            ),
            "iron",
        )


def _shelf(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A cellar shelf unit: three uprights, boards at the given heights, a back rail."""
    W, D, H = p["width"] / 2, p["depth"] / 2, p["height"]
    for x in (-W, 0.0, W):
        _box(b, x - 0.02, x + 0.02, -D, D, 0.0, H, "wood")
    for z in (p["board1"], p["board2"], p["board3"]):
        _box(b, -W, W, -D, D, z - 0.015, z + 0.015, "wood")
        _box(b, -W, W, D - 0.025, D, z + 0.015, z + 0.07, "wood")
    _box(b, -W, W, D - 0.02, D, H - 0.1, H, "wood")


def _coat_stand(b: MeshBuilder, p: dict[str, float], rng: random.Random) -> None:
    """A turned coat stand on a round foot, hooks curling out at the top."""
    H = p["height"]
    pole = [
        (0.16, 0.0),
        (0.16, 0.02),
        (0.05, 0.05),
        (0.022, 0.12),
        (0.02, H - 0.15),
        (0.03, H - 0.1),
        (0.018, H - 0.02),
        (0.03, H),
    ]
    _add(b, _turned(pole, (0.0, 0.0, 0.0), 14), "wood")
    for k in range(4):
        a = math.tau * k / 4 + 0.4
        c, sn = math.cos(a), math.sin(a)
        hook = [
            (0.015 * c, 0.015 * sn, H - 0.16),
            (0.1 * c, 0.1 * sn, H - 0.13),
            (0.14 * c, 0.14 * sn, H - 0.07),
        ]
        _add(b, sweep(hook, circle(0.009, 6), up=(0.0, 0.0, 1.0)), "brass")


PART_RECIPES: dict[
    str, tuple[Callable[[dict[str, float], str, random.Random], list[Part]], dict[str, float], str]
] = {
    "mushroom": (
        _mushrooms,
        {
            "count": 1,
            "spread": 0.1,
            "cap_radius": 0.1,
            "cap_height": 0.07,
            "stalk_height": 0.12,
            "stalk_radius": 0.016,
            "bulb": 0.2,
            "lean": 0.0,
            "gills": 24,
            "ring": 0.0,
            "volva": 0.0,
            "spots": 0.0,
            "segments": 16,
        },
        "dome",
    ),
    "bracket": (_brackets, {"count": 3, "spread": 0.12, "cap_radius": 0.16}, "flat"),
}


RECIPES: dict[str, tuple[Recipe, tuple[str, ...], dict[str, float]]] = {
    "barrel": (
        _barrel,
        ("staves", "ends", "iron"),
        {"height": 0.9, "radius": 0.27, "bulge": 0.05, "staves": 14, "hoops": 4},
    ),
    "bucket": (_bucket, ("tin", "iron"), {"radius_top": 0.15, "radius_bottom": 0.12, "height": 0.27}),
    "pick": (_pick, ("wood", "iron"), {"handle_length": 0.9, "head_length": 0.6}),
    "shovel": (_shovel, ("wood", "iron"), {"handle_length": 0.72, "blade_width": 0.24, "blade_length": 0.3}),
    "cart": (
        _cart,
        ("steel", "iron", "wood"),
        {"gauge": 0.6, "wheel_radius": 0.17, "rail_top": 0.265, "load": 0.0},
    ),
    "shack": (
        _shack,
        ("boards", "frame", "door", "roof", "iron"),
        {"width": 4.4, "depth": 3.2, "height": 2.4, "door": 1.0},
    ),
    "bones": (_bones, ("bone", "dark"), {"bones": 8, "skulls": 3, "spread": 0.5}),
    "candles": (_candles, ("wax", "wick"), {"count": 5, "height": 0.22, "spread": 0.09}),
    "rope": (_rope, ("rope", "iron"), {"radius": 0.17, "thickness": 0.022, "turns": 4}),
    "plank_bridge": (_plank_bridge, ("planks", "beam", "rope"), {"length": 4.0, "width": 1.1}),
    "fern": (_fern, ("stem", "leaf"), {"fronds": 9, "length": 0.6}),
    "moss": (_moss, ("moss",), {"tufts": 5, "radius": 0.18}),
    "vines": (_vines, ("stem", "leaf"), {"strands": 6, "length": 1.8, "spread": 0.35}),
    "flowers": (
        _flowers,
        ("stem", "leaf", "petal", "heart"),
        {"count": 6, "height": 0.32, "spread": 0.12, "petal": 0.035},
    ),
    "gate": (_gate, ("iron",), {"width": 3.0, "height": 2.7, "spacing": 0.16}),
    "crystals": (_crystals, ("crystal",), {"count": 7, "length": 1.2, "radius": 0.12}),
    "drips": (_drips, ("rock",), {"count": 4, "length": 0.9}),
    "boulder": (_boulder, ("rock",), {"size_x": 3.0, "size_y": 2.4, "size_z": 1.8}),
    "forge": (_forge, ("stone", "iron", "wood"), {"fire_only": 0.0}),
    "statue": (_statue, ("stone", "gold"), {"height": 4.0}),
    "brazier": (_brazier, ("iron", "coal"), {"height": 1.2, "radius": 0.4}),
    "chain": (_chain, ("iron",), {"length": 4.0, "link": 0.16}),
    "armchair": (
        _armchair,
        ("plush", "wood", "button"),
        {"width": 0.86, "seat": 0.46, "cushions": 1, "wings": 1.0},
    ),
    "side_table": (_side_table, ("wood",), {"height": 0.62, "radius": 0.25}),
    "cabinet": (
        _cabinet,
        ("wood", "panel", "brass"),
        {"width": 1.1, "depth": 0.6, "height": 2.0, "doors": 2, "drawers": 0.0, "cornice": 1.0, "feet": 0.0},
    ),
    "bed": (_bed, ("wood", "linen", "blanket"), {"width": 1.5, "length": 2.0}),
    "stove": (_stove, ("enamel", "iron", "chrome"), {"height": 0.9}),
    "shelf": (
        _shelf,
        ("wood",),
        {"width": 1.56, "depth": 0.42, "height": 1.9, "board1": 0.35, "board2": 0.95, "board3": 1.55},
    ),
    "coat_stand": (_coat_stand, ("wood", "brass"), {"height": 1.8}),
    "chair": (_chair, ("wood",), {"seat": 0.45, "back": 0.9}),
    "table": (_table, ("top", "wood"), {"height": 0.77, "length": 1.1, "width": 0.8}),
    "hatchet": (_hatchet, ("wood", "iron", "edge"), {"handle_length": 0.4, "blade": 0.1}),
    "crowbar": (_crowbar, ("iron", "worn"), {"length": 0.6, "radius": 0.013}),
    "hard_hat": (_hard_hat, ("enamel", "iron", "lens"), {"head": 0.1, "dents": 4}),
    "cut_block": (
        _cut_block,
        ("stone",),
        {"size_x": 0.8, "size_y": 0.8, "size_z": 0.4, "groove_depth": 0.006, "chip": 0.05},
    ),
}

SMOOTH = {
    "barrel": False,
    "bucket": True,
    "pick": True,
    "shovel": True,
    "cut_block": False,
    "cart": False,
    "shack": False,
    "bones": True,
    "candles": True,
    "rope": True,
    "plank_bridge": False,
    "fern": False,
    "moss": True,
    "vines": False,
    "flowers": False,
    "gate": True,
    "crystals": False,
    "drips": True,
    "boulder": False,
    "forge": False,
    "statue": True,
    "brazier": True,
    "chain": True,
    "hard_hat": True,
    "hatchet": True,
    "crowbar": True,
    "armchair": True,
    "side_table": True,
    "chair": True,
    "cabinet": False,
    "bed": True,
    "stove": True,
    "shelf": False,
    "coat_stand": True,
    "table": True,
}


def build(spec: AssetSpec) -> Asset:
    raw: Mapping[str, object] = spec.params
    kind = as_str(require_key(raw, "kind", "params"), "params.kind")
    if kind in PART_RECIPES:
        return _build_parts(spec, kind)
    if kind not in RECIPES:
        raise SpecError(f"params.kind: unknown prop '{kind}'; have {sorted([*RECIPES, *PART_RECIPES])}")
    recipe, slots, defaults = RECIPES[kind]
    params = _params(raw, kind, defaults)
    seed = as_int(raw.get("seed", 1), "params.seed")
    smooth = as_bool(raw.get("smooth", SMOOTH[kind]), "params.smooth")
    if kind == "cart" and params["load"] > 0.5:
        slots = (*slots, "load")
    if kind == "shack" and params["door"] <= 0.5:
        slots = tuple(slot for slot in slots if slot != "door")
    if kind == "forge" and params["fire_only"] > 0.5:
        slots = ("fire",)
    require_materials(spec.materials, slots, spec.generator)

    builder = MeshBuilder(slots)
    shade = recipe(builder, params, random.Random(seed))
    return _finish(builder, spec, shade, smooth)


# Counts and switches that may be 0 (no gills, no spots, no ring, no load, upright).
MAY_BE_ZERO = {
    "gills",
    "spots",
    "ring",
    "volva",
    "load",
    "lean",
    "bones",
    "fire_only",
    "door",
    "dents",
    "wings",
    "drawers",
    "cornice",
    "feet",
}


def _params(raw: Mapping[str, object], kind: str, defaults: dict[str, float]) -> dict[str, float]:
    params = dict(defaults)
    for key, value in raw.items():
        if key in ("kind", "seed", "smooth", "cap_shape"):
            continue
        if key not in defaults:
            raise SpecError(f"params.{key}: not a parameter of a {kind}; have {sorted(defaults)}")
        params[key] = as_float(value, f"params.{key}")
        if params[key] < 0.0 or (params[key] == 0.0 and key not in MAY_BE_ZERO):
            raise SpecError(f"params.{key}: must be positive, got {params[key]}")
    return params


def _build_parts(spec: AssetSpec, kind: str) -> Asset:
    recipe, defaults, default_shape = PART_RECIPES[kind]
    params = _params(spec.params, kind, defaults)
    shape = as_str(spec.params.get("cap_shape", default_shape), "params.cap_shape")
    if shape not in CAP_SHAPES:
        raise SpecError(f"params.cap_shape: unknown '{shape}'; have {sorted(CAP_SHAPES)}")
    parts = recipe(params, shape, random.Random(as_int(spec.params.get("seed", 1), "params.seed")))
    slots = tuple(slot for slot in MUSHROOM_SLOTS if any(p[1] == slot for p in parts))
    require_materials(spec.materials, slots, spec.generator)
    builder = MeshBuilder(slots)
    for shell, slot in parts:
        _add(builder, shell, slot)
    return _finish(builder, spec, None, as_bool(spec.params.get("smooth", True), "params.smooth"))


def _finish(builder: MeshBuilder, spec: AssetSpec, shade: list[float] | None, smooth: bool) -> Asset:
    if shade is not None:
        builder.set_point_attribute("shade", shade)
    # Settle on the origin: footprint centred, resting on Z=0 (tool marks and bends move it a little).
    mesh = builder.build().settled()
    # Smooth keeps hard edges hard: normals split where faces turn by more than ~40 degrees.
    shading = ShadeSmooth(sharp_angle_deg=40.0) if smooth else ShadeFlat()
    return Asset((KitPart(spec.asset_id, mesh, spec.materials, (shading, Unwrap())),))
