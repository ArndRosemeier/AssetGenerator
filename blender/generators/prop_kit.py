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


RECIPES: dict[str, tuple[Recipe, tuple[str, ...], dict[str, float]]] = {
    "barrel": (
        _barrel,
        ("staves", "ends", "iron"),
        {"height": 0.9, "radius": 0.27, "bulge": 0.05, "staves": 14, "hoops": 4},
    ),
    "bucket": (_bucket, ("tin", "iron"), {"radius_top": 0.15, "radius_bottom": 0.12, "height": 0.27}),
    "pick": (_pick, ("wood", "iron"), {"handle_length": 0.9, "head_length": 0.6}),
    "shovel": (_shovel, ("wood", "iron"), {"handle_length": 0.72, "blade_width": 0.24, "blade_length": 0.3}),
    "cut_block": (
        _cut_block,
        ("stone",),
        {"size_x": 0.8, "size_y": 0.8, "size_z": 0.4, "groove_depth": 0.006, "chip": 0.05},
    ),
}

SMOOTH = {"barrel": False, "bucket": True, "pick": True, "shovel": True, "cut_block": False}


def build(spec: AssetSpec) -> list[bpy.types.Object]:
    raw: Mapping[str, object] = spec.params
    kind = as_str(require_key(raw, "kind", "params"), "params.kind")
    if kind not in RECIPES:
        raise SpecError(f"params.kind: unknown prop '{kind}'; have {sorted(RECIPES)}")
    recipe, slots, defaults = RECIPES[kind]
    params = dict(defaults)
    for key, value in raw.items():
        if key in ("kind", "seed", "smooth"):
            continue
        if key not in defaults:
            raise SpecError(f"params.{key}: not a parameter of a {kind}; have {sorted(defaults)}")
        params[key] = as_float(value, f"params.{key}")
        if params[key] <= 0.0:
            raise SpecError(f"params.{key}: must be positive, got {params[key]}")
    seed = as_int(raw.get("seed", 1), "params.seed")
    smooth = as_bool(raw.get("smooth", SMOOTH[kind]), "params.smooth")
    require_materials(spec.materials, slots, spec.generator)

    builder = BoxBuilder(slots)
    shade = recipe(builder, params, random.Random(seed))
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
    return [obj]
