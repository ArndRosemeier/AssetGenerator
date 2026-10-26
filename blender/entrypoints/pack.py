"""Build props from their specs and pack them for an engine that draws vertex colours.

For each spec: build it (the same `build` as generate), bake ambient occlusion
(with a ground plane under it) into the vertices, multiply it into each
material's base colour with the recipe's own `shade` attribute if it has one, give each separate part (a stave, a plank) a slightly
different shade, and write all of them into one `.fmpk` file (format below).

Engines whose props are flat-shaded vertex-coloured meshes (Dunfinity) read the
pack instead of a .glb: no textures, no materials, one draw call for many props.

FMPK v1, little-endian:
    "FMPK", u32 version (1), u32 model count, then per model:
    u16 name length, name (utf-8), padding to 4 bytes,
    f32 position scale, f32 min[3], f32 max[3] (metres, Y up, front +Z),
    u32 vertex count, u32 index count,
    i16 positions[3 * n] (times the scale), padding to 4,
    i8 normals[3 * n] (/ 127), u8 colours[3 * n] (linear = (v / 255)^2), padding to 4,
    u16 indices (u32 when vertex count > 65535), padding to 4.

FMPK v2 (`ag.py pack --slots`) is v1 plus the material each vertex comes from, so an
engine can give wood, iron and cloth their own surface: after the name's padding
    u16 slot count, per slot u16 name length and name (utf-8, the spec's material name),
    padding to 4;
and after the colours (before their padding) u8 slot[n].
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import importlib
import math
import struct
from collections.abc import Mapping

import bpy  # first: in the bpy module, bmesh only exists once bpy is loaded
import bmesh

from blender.backend import build
from blender.lib.registry import resolve_generator_module
from blender.lib.report import Report
from blender.lib.runner import execute
from blender.lib.scene import activate, reset_scene
from blender.lib.spec import load_spec

AO_DISTANCE = 0.6  # metres: crevices and the ground under a prop, not the room
SHADE_JITTER = 0.09  # each separate part ± this much brighter or darker


def _joined(objects: list[bpy.types.Object]) -> bpy.types.Object:
    meshes = [o for o in objects if o.type == "MESH"]
    activate(meshes[0])
    for o in meshes:
        o.select_set(True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def _bake_ao(obj: bpy.types.Object, samples: int) -> bpy.types.Attribute:
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.light_settings.distance = AO_DISTANCE
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.render.bake.target = "VERTEX_COLORS"
    # The floor the prop stands on darkens its foot.
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, -0.001))
    ground = bpy.context.view_layer.objects.active
    attr = obj.data.color_attributes.new("AO", "FLOAT_COLOR", "CORNER")
    obj.data.color_attributes.active_color = attr
    activate(obj)
    bpy.ops.object.bake(type="AO")
    bpy.data.objects.remove(ground, do_unlink=True)
    return obj.data.color_attributes["AO"]


def _islands(mesh: bpy.types.Mesh) -> list[int]:
    parent = list(range(len(mesh.vertices)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in mesh.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    return [find(i) for i in range(len(mesh.vertices))]


def _pattern_colors(mesh: bpy.types.Mesh, asset: object) -> list[tuple[float, float, float]] | None:
    """Per loop-triangle corner, the colour a kit material's pattern has there (the same
    evaluation the textures are baked from), or None when no material has a pattern: so a
    pack shows the bark, rust and moss a .glb carries in its textures."""
    if asset is None:
        return None
    import numpy as np

    from assetkit.asset import pattern_of
    from assetkit.material import Surface, evaluate

    by_slot: dict[str, tuple[object, tuple[float, float, float]]] = {}
    for part in asset.parts:  # type: ignore[attr-defined]
        for slot, material in part.materials.items():
            by_slot.setdefault(slot, (material, part.pattern_origin))
    looks = []
    for material in mesh.materials:
        found = by_slot.get(material.name.split(".")[0])
        looks.append(found if found is not None and pattern_of(found[0]) is not None else None)
    if not any(looks):
        return None
    count = len(mesh.loop_triangles)
    verts = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", verts)
    tris = np.empty(count * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", tris)
    slots = np.empty(count, dtype=np.int64)
    mesh.loop_triangles.foreach_get("material_index", slots)
    surface = Surface(verts.reshape(-1, 3), tris.reshape(-1, 3))
    out = np.zeros((count * 3, 3))
    corner_tri = np.repeat(np.arange(count), 3)
    corner_bary = np.tile(np.eye(3), (count, 1))
    for s, found in enumerate(looks):
        pick = np.nonzero(slots[corner_tri] == s)[0]
        if not len(pick):
            continue
        if found is None:
            node = mesh.materials[s].node_tree.nodes["Principled BSDF"]
            out[pick] = tuple(node.inputs["Base Color"].default_value)[:3]
            continue
        material, origin = found
        color, _ = evaluate(
            pattern_of(material),
            surface,
            corner_tri[pick],
            corner_bary[pick],  # type: ignore[arg-type]
            tuple(material.base_color[:3]),
            material.roughness,
            origin,  # type: ignore[attr-defined]
        )
        out[pick] = color
    return [tuple(c) for c in out.tolist()]


def _image_colors(mesh: bpy.types.Mesh) -> list[tuple[float, float, float]] | None:
    """Per loop-triangle corner, the colour of the baked albedo where a material's base colour
    is an image (generators that bake their looks into textures), or None."""
    import numpy as np

    images = []
    for material in mesh.materials:
        node = material.node_tree.nodes.get("Principled BSDF") if material and material.node_tree else None
        link = node.inputs["Base Color"].links[0] if node and node.inputs["Base Color"].links else None
        image = link.from_node.image if link and link.from_node.type == "TEX_IMAGE" else None
        if image is None:
            images.append(None)
            continue
        w, h = image.size
        px = np.empty(w * h * 4, dtype=np.float32)
        image.pixels.foreach_get(px)
        images.append((w, h, px.reshape(h, w, 4)))
    if not any(images) or not mesh.uv_layers:
        return None
    uv = mesh.uv_layers.active.data
    out = []
    for tri in mesh.loop_triangles:
        img = images[tri.material_index]
        for loop in tri.loops:
            if img is None:
                node = mesh.materials[tri.material_index].node_tree.nodes["Principled BSDF"]
                out.append(tuple(node.inputs["Base Color"].default_value)[:3])
                continue
            w, h, px = img
            u, v = uv[loop].uv
            c = px[min(h - 1, max(0, int(v * h))), min(w - 1, max(0, int(u * w)))]
            out.append((float(c[0]), float(c[1]), float(c[2])))
    return out


def _shade(island: int, seed: int) -> float:
    h = (island * 2654435761 + seed * 40503) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    return 1.0 + SHADE_JITTER * (2.0 * (h / 0xFFFFFFFF) - 1.0)


def _slot_name(material: bpy.types.Material) -> str:
    return material.name.split(".")[0]


def _model(spec_path: Path, samples: int, slots: bool = False) -> tuple[str, bytes, dict[str, object]]:
    spec = load_spec(spec_path)
    module = importlib.import_module(resolve_generator_module(spec.generator))
    reset_scene()
    objects, asset = build(module, spec)
    obj = _joined(objects)
    ao = _bake_ao(obj, samples)
    mesh = obj.data
    mesh.calc_loop_triangles()
    base = [
        tuple(m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value)[:3]
        for m in mesh.materials
    ]
    patterned = _pattern_colors(mesh, asset) or _image_colors(mesh)
    # Slots a texture bake merged into one material (blender/lib/bake.py keeps them).
    face_slot = mesh.attributes.get("slot")
    slot_names = [str(n) for n in mesh.get("slot_names", [])] if face_slot is not None else [_slot_name(m) for m in mesh.materials]
    island = _islands(mesh)
    # A recipe's own shading (tool marks, grime) per vertex, when it has one.
    shade = mesh.attributes.get("shade")
    marks = [d.value for d in shade.data] if shade is not None else None
    seed = sum(spec.asset_id.encode())
    normals = mesh.corner_normals

    keys: dict[tuple, int] = {}
    pos: list[tuple[float, float, float]] = []
    nor: list[tuple[int, int, int]] = []
    col: list[tuple[int, int, int]] = []
    slot: list[int] = []
    idx: list[int] = []
    for t, tri in enumerate(mesh.loop_triangles):
        color = base[tri.material_index]
        tri_slot = face_slot.data[tri.polygon_index].value if face_slot is not None else tri.material_index
        for corner, loop in enumerate(tri.loops):
            if patterned is not None:
                color = patterned[3 * t + corner]
            v = mesh.loops[loop].vertex_index
            x, y, z = mesh.vertices[v].co
            nx, ny, nz = normals[loop].vector
            occ = ao.data[loop].color[0]
            k = _shade(island[v], seed) * (0.22 + 0.78 * occ) * (marks[v] if marks else 1.0)
            # Blender Z up, front -Y  →  Y up, front +Z.
            p = (x, z, -y)
            n = (round(nx * 127), round(nz * 127), round(-ny * 127))
            c = tuple(min(255, round(math.sqrt(max(0.0, ch * k)) * 255)) for ch in color)
            key = (p, n, c, tri_slot if slots else 0)
            if key not in keys:
                keys[key] = len(pos)
                pos.append(p)
                nor.append(n)
                col.append(c)
                slot.append(tri_slot)
            idx.append(keys[key])

    lo = [min(p[i] for p in pos) for i in range(3)]
    hi = [max(p[i] for p in pos) for i in range(3)]
    scale = max(max(abs(v) for v in lo + hi), 1e-6) / 32767.0
    out = bytearray()
    name = spec.asset_id.encode()
    out += struct.pack("<H", len(name)) + name
    out += b"\0" * (-len(out) % 4)
    if slots:
        names = [nm.encode() for nm in slot_names]
        out += struct.pack("<H", len(names))
        for nm in names:
            out += struct.pack("<H", len(nm)) + nm
        out += b"\0" * (-len(out) % 4)
    out += struct.pack("<f3f3fII", scale, *lo, *hi, len(pos), len(idx))
    out += struct.pack(f"<{3 * len(pos)}h", *(round(c / scale) for p in pos for c in p))
    out += b"\0" * (-len(out) % 4)
    out += struct.pack(f"<{3 * len(nor)}b", *(c for n in nor for c in n))
    out += bytes(c for cc in col for c in cc)
    if slots:
        out += bytes(slot)
    out += b"\0" * (-len(out) % 4)
    out += struct.pack(f"<{len(idx)}{'H' if len(pos) <= 65535 else 'I'}", *idx)
    out += b"\0" * (-len(out) % 4)
    stats = {
        "vertices": len(pos),
        "triangles": len(idx) // 3,
        "size_m": [round(hi[i] - lo[i], 3) for i in range(3)],
    }
    return spec.asset_id, bytes(out), stats


def handle(payload: Mapping[str, object]) -> Report:
    specs = [Path(str(p)) for p in payload["specs"]]  # type: ignore[union-attr]
    out_path = Path(str(payload["out"]))
    samples = int(payload.get("samples", 32))  # type: ignore[arg-type]
    slots = bool(payload.get("slots", False))
    blobs: list[bytes] = []
    models: dict[str, object] = {}
    for spec_path in specs:
        name, blob, stats = _model(spec_path, samples, slots)
        blobs.append(blob)
        models[name] = stats
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"FMPK" + struct.pack("<II", 2 if slots else 1, len(blobs)) + b"".join(blobs))
    return {
        "ok": True,
        "command": "pack",
        "outputs": {"pack": str(out_path)},
        "models": models,
        "checks": [],
        "errors": [],
    }


execute("pack", handle)
