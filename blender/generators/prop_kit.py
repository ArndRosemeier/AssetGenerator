"""Small hand props for dungeons and mines: barrels, buckets, tools, cut stone.

One generator, `prop.kit`, with a recipe per `kind`. Each recipe composes closed
shells (blender/lib/shells.py) into one mesh with material slots, so QA's
manifold and outward-normal gates hold. Props are made to be seen up close in a
headlamp's beam: proportions follow real objects and every part has thickness.

Frame (as every asset here): metres, Z up, origin at the footprint centre on
Z=0, the front facing -Y (glTF +Z).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping

import bpy  # first: in the bpy module, bmesh only exists once bpy is loaded
import bmesh
from mathutils import Vector, noise

from blender.lib.mushroom import CAP_SHAPES, Mushroom, Part, mushroom
from blender.lib.scene import BoxBuilder, unwrap
from blender.lib.shells import Shell, circle, lathe, place, rect, ring, sweep
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
Recipe = Callable[[BoxBuilder, dict[str, float], random.Random], list[float] | None]


def _add(b: BoxBuilder, shell: Shell, slot: str) -> None:
    verts, faces = shell
    b.add_mesh(verts, faces, slot)


# ---------------------------------------------------------------------------------------------
# Barrel: staves bent round a bulge, two heads, iron hoops.
# ---------------------------------------------------------------------------------------------


def _barrel(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> None:
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


def _bucket(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> None:
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


def _handle(b: BoxBuilder, length: float, r0: float, r1: float, bend: float) -> None:
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


def _pick(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> None:
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


def _shovel(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> None:
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
    sect = [(x, y) for x, y in sect]

    def width(t: float) -> tuple[float, float]:
        # t runs from the tip (0) up to the shoulder (1).
        return (bw * max(math.sin(math.pi / 2 * min(t * 1.6, 1.0)), 0.12), 1.0)

    blade = [(0.0, 0.0, bl * i / 10) for i in range(11)]
    _add(b, sweep(blade, [(x, y) for x, y in reversed(sect)], scale=width, up=(0.0, -1.0, 0.0)), "iron")


# ---------------------------------------------------------------------------------------------
# Cut stone: a dressed block with tooled faces and knocked corners.
# ---------------------------------------------------------------------------------------------


def _cut_block(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> list[float]:
    sx, sy, sz = p["size_x"], p["size_y"], p["size_z"]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    cuts = max(2, int(max(sx, sy, sz) / 0.1))
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    seed = rng.uniform(0, 100)
    chip = p["chip"]
    shade: list[float] = []
    for v in bm.verts:
        x, y, z = v.co.x * sx, v.co.y * sy, (v.co.z + 0.5) * sz
        # Which face: the largest normalised coordinate.
        ax = max(range(3), key=lambda i: abs(v.co[i]))
        n = Vector((0.0, 0.0, 0.0))
        n[ax] = 1.0 if v.co[ax] > 0 else -1.0
        d = 0.004 * noise.noise(Vector((x * 6 + seed, y * 6, z * 6)))
        # Here and there an edge knocked off where a block was dropped: sparse, sharp chips.
        edge = sorted(abs(v.co[i]) for i in range(3))[1]  # second largest: near an edge when ~0.5
        k = noise.noise(Vector((x * 5 - seed, y * 5, z * 5)))
        knocked = edge > 0.4 and k > 0.1
        if knocked:
            d -= chip * min(1.0, (k - 0.1) * 3.0) * (edge - 0.4) / 0.1
        v.co = Vector((x, y, z)) + n * d
        # Tool marks and the fresh, paler stone where a chip came off: in the colour, not the mesh.
        along = (y if ax != 1 else x) * 18.0 + 0.6 * noise.noise(Vector((x * 2, y * 2 + seed, z * 2)))
        mark = 0.9 + 0.1 * math.sin(along * math.tau) * (
            0.5 + 0.5 * noise.noise(Vector((x * 3, y * 3, z * 3 + seed)))
        )
        shade.append(mark * (1.12 if knocked else 1.0))
    verts = [tuple(v.co) for v in bm.verts]
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    b.add_mesh(verts, faces, "stone")
    return shade


def _hexa(
    b: BoxBuilder, bottom: list[tuple[float, float, float]], top: list[tuple[float, float, float]], slot: str
) -> None:
    """A six-sided solid from four bottom and four top corners, each counter-clockwise from above."""
    faces = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    b.add_mesh(bottom + top, faces, slot)


# ---------------------------------------------------------------------------------------------
# Mine cart: a riveted steel tub on a timber chassis, flanged wheels for the narrow gauge.
# ---------------------------------------------------------------------------------------------


def _cart(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> list[float] | None:
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
    b: BoxBuilder,
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


def _shack(b: BoxBuilder, p: dict[str, float], rng: random.Random) -> None:
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
    # The door, shut, a little inside its frame: boards, two ledges and a brace.
    d0, d1, _, dh = door
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
        {"width": 4.4, "depth": 3.2, "height": 2.4},
    ),
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
}


def build(spec: AssetSpec) -> list[bpy.types.Object]:
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
    require_materials(spec.materials, slots, spec.generator)

    builder = BoxBuilder(slots)
    shade = recipe(builder, params, random.Random(seed))
    return [_finish(builder, spec, shade, smooth)]


# Counts and switches that may be 0 (no gills, no spots, no ring, no load, upright).
MAY_BE_ZERO = {"gills", "spots", "ring", "volva", "load", "lean"}


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


def _build_parts(spec: AssetSpec, kind: str) -> list[bpy.types.Object]:
    recipe, defaults, default_shape = PART_RECIPES[kind]
    params = _params(spec.params, kind, defaults)
    shape = as_str(spec.params.get("cap_shape", default_shape), "params.cap_shape")
    if shape not in CAP_SHAPES:
        raise SpecError(f"params.cap_shape: unknown '{shape}'; have {sorted(CAP_SHAPES)}")
    parts = recipe(params, shape, random.Random(as_int(spec.params.get("seed", 1), "params.seed")))
    slots = tuple(slot for slot in MUSHROOM_SLOTS if any(p[1] == slot for p in parts))
    require_materials(spec.materials, slots, spec.generator)
    builder = BoxBuilder(slots)
    for shell, slot in parts:
        _add(builder, shell, slot)
    return [_finish(builder, spec, None, as_bool(spec.params.get("smooth", True), "params.smooth"))]


def _finish(
    builder: BoxBuilder, spec: AssetSpec, shade: list[float] | None, smooth: bool
) -> bpy.types.Object:
    obj = builder.to_object(spec.asset_id, spec.materials)
    mesh = obj.data
    if shade is not None:
        attr = mesh.attributes.new("shade", "FLOAT", "POINT")
        attr.data.foreach_set("value", shade)
    # Settle on the origin: footprint centred, resting on Z=0 (tool marks and bends move it a little).
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    shift = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(v.co.z for v in mesh.vertices)))
    for v in mesh.vertices:
        v.co -= shift
    for polygon in mesh.polygons:
        polygon.use_smooth = smooth
    if smooth:
        # Keep hard edges hard: split normals where faces turn by more than ~40 degrees.
        if hasattr(mesh, "set_sharp_from_angle"):
            mesh.set_sharp_from_angle(angle=math.radians(40.0))
    unwrap(obj)
    return obj
