# -*- coding: utf-8 -*-
"""Bake a distinct Quaternius tribal veteran body (art only).

Source (read-only): assets/monsters/quaternius/big/Tribal.glb
Dest:               assets/monsters/quaternius/big/Tribal_Veteran.glb

Does not overwrite Tribal.glb, does not write engine/Orrun JSON,
does not touch music beds, does not vendor into Orrun.
"""
from __future__ import annotations

import json
import math
import shutil
import struct
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

AG = Path(r"C:\Projekte\AssetGenerator")
SRC = AG / "assets" / "monsters" / "quaternius" / "big" / "Tribal.glb"
DEST = AG / "assets" / "monsters" / "quaternius" / "big" / "Tribal_Veteran.glb"
PREVIEW = AG / "assets" / "monsters" / "quaternius" / "big" / "Tribal_Veteran_preview.png"
PREVIEW_PUNCH = AG / "assets" / "monsters" / "quaternius" / "big" / "Tribal_Veteran_punch.png"
PREVIEW_COPY_DIR = Path(r"C:\Users\windo\agent-previews")
SCRATCH_DIR = AG / "tools" / "_tribal_veteran_bake"
SCRATCH_SRC = SCRATCH_DIR / "Tribal_src_copy.glb"
ATLAS_PNG = AG / "assets" / "monsters" / "quaternius" / "Atlas_Monsters.png"

REQUIRED_CLIPS = ("Idle", "Walk", "Punch")
GUARD_PATHS = [
    Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\monsters\big\Tribal.glb"),
    AG / "assets" / "monsters" / "quaternius" / "big" / "Tribal.glb",
    AG / "assets" / "monsters" / "quaternius" / "flying" / "Tribal.glb",
]

SKIN_UV = (0.0786, 0.5788)
HAIR_UV = (0.0471, 0.5775)
GOLD_UV = (0.1408, 0.5775)
GREEN_UV = (0.1097, 0.5777)
EYE_UV = (0.0156, 0.5771)

SKIN = (0.38, 0.135, 0.090)
HAIR = (0.50, 0.51, 0.54)
LEATHER = (0.24, 0.15, 0.07)
CLOTH = (0.16, 0.28, 0.13)
EYE = (0.09, 0.09, 0.10)
OCHRE = (0.82, 0.54, 0.12)
WHITE = (0.94, 0.91, 0.82)
SOOT = (0.07, 0.06, 0.055)
BONE = (0.88, 0.82, 0.62)
CORD = (0.14, 0.09, 0.05)
FUR = (0.13, 0.11, 0.09)
FUR_TIP = (0.42, 0.34, 0.24)

TEX_SIZE = 1024
JSON_FOURCC = 0x4E4F534A
BIN_FOURCC = 0x004E4942


def log(msg: str) -> None:
    print(f"[tribal-veteran] {msg}", flush=True)


def snapshot(paths):
    out = {}
    for p in paths:
        if p.is_file():
            st = p.stat()
            out[str(p)] = (st.st_size, int(st.st_mtime_ns))
        else:
            out[str(p)] = None
    return out


def assert_untouched(before, label):
    after = snapshot([Path(k) for k in before])
    dirty = []
    for k, v in before.items():
        if after.get(k) != v:
            dirty.append((k, v, after.get(k)))
    if dirty:
        raise RuntimeError(f"{label} files changed: {dirty}")
    log(f"{label} untouched ({len(before)} paths)")


def glb_chunks(path: Path):
    data = Path(path).read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError(f"{path} is not a GLB")
    _magic, _version, length = struct.unpack_from("<III", data, 0)
    offset = 12
    doc = None
    blob = b""
    unknown = []
    while offset + 8 <= min(length, len(data)):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        fourcc = data[offset + 4 : offset + 8]
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == JSON_FOURCC or fourcc == b"JSON":
            doc = json.loads(chunk)
        elif chunk_type == BIN_FOURCC or fourcc[:3] == b"BIN":
            blob = chunk
            if fourcc != b"BIN\x00":
                unknown.append(fourcc)
        else:
            unknown.append(fourcc)
    if doc is None:
        raise RuntimeError(f"{path}: no JSON chunk")
    return doc, blob, unknown, data


def write_glb(path: Path, doc: dict, blob: bytes) -> None:
    json_bytes = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_pad = (4 - (len(json_bytes) % 4)) % 4
    json_bytes = json_bytes + (b" " * json_pad)
    bin_pad = (4 - (len(blob) % 4)) % 4
    blob_padded = blob + (b"\x00" * bin_pad)
    total = 12 + 8 + len(json_bytes) + 8 + len(blob_padded)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(json_bytes), JSON_FOURCC)
    out += json_bytes
    out += struct.pack("<II", len(blob_padded), BIN_FOURCC)
    out += blob_padded
    path.write_bytes(bytes(out))


def verify_fourcc(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise RuntimeError(f"{path} is not a GLB")
    offset = 12
    found = []
    while offset + 8 <= len(data):
        chunk_len, _chunk_type = struct.unpack_from("<II", data, offset)
        fourcc = data[offset + 4 : offset + 8]
        found.append(fourcc)
        offset += 8 + chunk_len
    if found != [b"JSON", b"BIN\x00"]:
        raise RuntimeError(f"{path}: bad chunks {found!r}, want JSON + BIN\\0")
    return found


def inspect_source_bytes(path: Path) -> dict:
    doc, _blob, unknown, raw = glb_chunks(path)
    anims = [a.get("name") for a in doc.get("animations", [])]
    meshes = [m.get("name") for m in doc.get("meshes", [])]
    mats = []
    for m in doc.get("materials", []):
        mats.append(
            {
                "name": m.get("name"),
                "alphaMode": m.get("alphaMode", "OPAQUE"),
                "doubleSided": m.get("doubleSided"),
            }
        )
    images = [(i.get("name"), i.get("mimeType")) for i in doc.get("images", [])]
    info = {
        "size": len(raw),
        "anims": anims,
        "meshes": meshes,
        "materials": mats,
        "images": images,
        "unknown_chunks": [repr(u) for u in unknown],
    }
    log(f"SOURCE {path} size={info['size']}")
    log(f"  clips={anims}")
    log(f"  meshes={meshes}")
    log(f"  materials={mats}")
    log(f"  images={images}")
    missing = [c for c in REQUIRED_CLIPS if c not in anims]
    if missing:
        raise RuntimeError(f"source missing required clips: {missing}")
    return info


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for coll in (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.images,
        bpy.data.materials,
        bpy.data.actions,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(coll):
            try:
                coll.remove(block)
            except Exception:
                pass


def import_gltf(path: Path) -> None:
    bpy.ops.import_scene.gltf(
        filepath=str(path),
        bone_heuristic="BLENDER",
        guess_original_bind_pose=True,
    )


def find_armature():
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not arms:
        raise RuntimeError("no armature after import")
    for o in arms:
        if "CharacterArmature" in o.name or "Armature" in o.name:
            return o
    return arms[0]


def find_body():
    for o in bpy.data.objects:
        if o.type == "MESH" and o.vertex_groups and o.parent and o.parent.type == "ARMATURE":
            return o
    for o in bpy.data.objects:
        if o.type == "MESH" and "Tribal" in o.name:
            return o
    raise RuntimeError("Tribal mesh not found")


def rest_pose(arm) -> None:
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()


def force_opaque(mat) -> None:
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = "OPAQUE"
        except Exception:
            pass
    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = "OPAQUE"
        except Exception:
            pass
    if mat.use_nodes and mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED" and "Alpha" in node.inputs:
                node.inputs["Alpha"].default_value = 1.0


def make_opaque_mat(name: str, color, roughness: float = 0.85):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 1.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    force_opaque(mat)
    return mat


def uv_close(uv, target, tol=0.008) -> bool:
    return abs(uv[0] - target[0]) < tol and abs(uv[1] - target[1]) < tol


def island_color(uv):
    if uv_close(uv, SKIN_UV):
        return SKIN
    if uv_close(uv, HAIR_UV):
        return HAIR
    if uv_close(uv, GOLD_UV):
        return LEATHER
    if uv_close(uv, GREEN_UV):
        return CLOTH
    if uv_close(uv, EYE_UV):
        return EYE
    return None


def sample_src(px, w, h, u, v):
    x = int(max(0, min(w - 1, u * w)))
    y = int(max(0, min(h - 1, v * h)))
    i = (y * w + x) * 4
    return (px[i], px[i + 1], px[i + 2], px[i + 3])


def rasterize_tri(px, w, h, uv0, uv1, uv2, color):
    pts = [
        (uv0[0] * w, uv0[1] * h),
        (uv1[0] * w, uv1[1] * h),
        (uv2[0] * w, uv2[1] * h),
    ]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx = max(0, int(math.floor(min(xs) - 1)))
    maxx = min(w - 1, int(math.ceil(max(xs) + 1)))
    miny = max(0, int(math.floor(min(ys) - 1)))
    maxy = min(h - 1, int(math.ceil(max(ys) + 1)))

    def edge(a, b, c):
        return (c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])

    area = edge(pts[0], pts[1], pts[2])
    if abs(area) < 1e-6:
        cx = int(sum(xs) / 3.0)
        cy = int(sum(ys) / 3.0)
        if 0 <= cx < w and 0 <= cy < h:
            i = (cy * w + cx) * 4
            px[i : i + 4] = [color[0], color[1], color[2], 1.0]
        return
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            p = (x + 0.5, y + 0.5)
            w0 = edge(pts[1], pts[2], p)
            w1 = edge(pts[2], pts[0], p)
            w2 = edge(pts[0], pts[1], p)
            if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                i = (y * w + x) * 4
                px[i : i + 4] = [color[0], color[1], color[2], 1.0]


def dilate_rgba(px, w, h, times=3):
    for _ in range(times):
        src = px[:]
        for y in range(h):
            for x in range(w):
                i = (y * w + x) * 4
                if src[i + 3] > 0.5:
                    continue
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        j = (ny * w + nx) * 4
                        if src[j + 3] > 0.5:
                            px[i : i + 4] = src[j : j + 4]
                            break


def vg_weight(vert, vg_index):
    if vg_index is None:
        return 0.0
    for g in vert.groups:
        if g.group == vg_index:
            return g.weight
    return 0.0


def stripe_color_face(z, x):
    """Graphic ochre/white/soot bands across the tiki mask."""
    rel = (z - 2.08) / 0.50
    if rel < 0.0 or rel > 1.0:
        return None
    band = rel * 5.0
    bi = int(math.floor(band))
    frac = band - bi
    if frac > 0.72:
        return None
    palette = (OCHRE, WHITE, SOOT, OCHRE, WHITE)
    col = palette[max(0, min(len(palette) - 1, bi))]
    if abs(x) > 0.28 and 2.18 < z < 2.32:
        return SOOT
    return col


def stripe_color_chest(z, x):
    rel = (z - 1.38) / 0.58
    if rel < 0.0 or rel > 1.0:
        return None
    band = rel * 4.0
    bi = int(math.floor(band))
    frac = band - bi
    if frac > 0.70:
        return None
    palette = (SOOT, OCHRE, WHITE, SOOT)
    col = palette[max(0, min(len(palette) - 1, bi))]
    if abs(x) < 0.12 + 0.28 * max(0.0, z - 1.45) and 1.48 < z < 1.78:
        return OCHRE
    return col


def rebuild_albedo(body) -> None:
    mesh = body.data
    if not mesh.uv_layers:
        raise RuntimeError("body has no UV layer")
    src_uv = mesh.uv_layers[0]
    src_uv.name = "AtlasUV"
    dst_uv = mesh.uv_layers.new(name="VeteranUV")
    mesh.uv_layers.active = dst_uv
    dst_uv.active_render = True

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=66.0,
        island_margin=0.018,
        correct_aspect=True,
        scale_to_bounds=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")

    src_img = None
    for img in bpy.data.images:
        if img.size[0] >= 64:
            src_img = img
            break
    if src_img is None:
        if not ATLAS_PNG.is_file():
            raise RuntimeError(f"no source atlas image and missing {ATLAS_PNG}")
        src_img = bpy.data.images.load(str(ATLAS_PNG))
        log(f"loaded atlas fallback {ATLAS_PNG} size={tuple(src_img.size)}")
    log(f"atlas image {src_img.name!r} size={tuple(src_img.size)}")

    src_px = list(src_img.pixels)
    sw, sh = int(src_img.size[0]), int(src_img.size[1])

    dst_img = bpy.data.images.new("TribalVeteranAtlas", width=TEX_SIZE, height=TEX_SIZE, alpha=True)
    dst_img.colorspace_settings.name = "sRGB"
    w = h = TEX_SIZE
    dst_px = [0.0] * (w * h * 4)

    src_uv = mesh.uv_layers["AtlasUV"]
    dst_uv = mesh.uv_layers["VeteranUV"]
    vg = {g.name: g.index for g in body.vertex_groups}
    head_i = vg.get("Head")
    torso_i = vg.get("Torso")
    abdomen_i = vg.get("Abdomen")
    body_i = vg.get("Body")

    filled = 0
    painted = 0
    for poly in mesh.polygons:
        loops = list(poly.loop_indices)
        if len(loops) < 3:
            continue
        suv = src_uv.data[loops[0]].uv
        col = island_color((suv.x, suv.y))
        if col is None:
            sampled = sample_src(src_px, sw, sh, suv.x, suv.y)
            col = (sampled[0] * 0.70, sampled[1] * 0.60, sampled[2] * 0.52)
        verts = [mesh.vertices[mesh.loops[li].vertex_index] for li in loops]
        cx = sum(v.co.x for v in verts) / len(verts)
        cy = sum(v.co.y for v in verts) / len(verts)
        cz = sum(v.co.z for v in verts) / len(verts)
        hw = max(vg_weight(v, head_i) for v in verts)
        tw = max(vg_weight(v, torso_i) for v in verts)
        aw = max(vg_weight(v, abdomen_i) for v in verts)
        bw = max(vg_weight(v, body_i) for v in verts)
        overlay = None
        hairish = uv_close((suv.x, suv.y), HAIR_UV) or uv_close((suv.x, suv.y), EYE_UV)
        if (not hairish) and cy < 0.10:
            if hw >= 0.35 and 2.06 < cz < 2.60:
                overlay = stripe_color_face(cz, cx)
            elif (tw >= 0.20 or aw >= 0.20 or bw >= 0.20) and 1.35 < cz < 1.98:
                overlay = stripe_color_chest(cz, cx)
        use = overlay if overlay is not None else col
        if overlay is not None:
            painted += 1
        for i in range(1, len(loops) - 1):
            a = dst_uv.data[loops[0]].uv
            b = dst_uv.data[loops[i]].uv
            c = dst_uv.data[loops[i + 1]].uv
            rasterize_tri(dst_px, w, h, (a.x, a.y), (b.x, b.y), (c.x, c.y), use)
            filled += 1
    log(f"rasterized {filled} tris, painted {painted} stripe tris")
    dilate_rgba(dst_px, w, h, times=3)
    dst_img.pixels = dst_px
    dst_img.update()
    atlas_debug = SCRATCH_DIR / "veteran_albedo.png"
    dst_img.filepath_raw = str(atlas_debug)
    dst_img.file_format = "PNG"
    dst_img.save()
    log(f"wrote albedo debug {atlas_debug}")

    mat = bpy.data.materials.new("TribalVeteran")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "VeteranUV"
    tex.image = dst_img
    tex.interpolation = "Closest"
    bsdf.inputs["Roughness"].default_value = 0.92
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 1.0
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    force_opaque(mat)
    body.data.materials.clear()
    body.data.materials.append(mat)
    log("body material -> TribalVeteran OPAQUE unique albedo")


def bind_mesh(obj, arm, bone_fn):
    obj.parent = arm
    obj.parent_type = "OBJECT"
    needed = set()
    weights = []
    for v in obj.data.vertices:
        wmap = bone_fn(v)
        weights.append((v.index, wmap))
        needed.update(wmap)
    for name in needed:
        if name not in obj.vertex_groups:
            obj.vertex_groups.new(name=name)
    for vi, wmap in weights:
        for bname, w in wmap.items():
            obj.vertex_groups[bname].add([vi], float(w), "REPLACE")
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True


def mesh_from_bmesh(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def append_transformed(dst_bm, src_bm):
    vert_map = {}
    for v in src_bm.verts:
        vert_map[v] = dst_bm.verts.new(v.co)
    dst_bm.verts.ensure_lookup_table()
    for f in src_bm.faces:
        try:
            dst_bm.faces.new([vert_map[v] for v in f.verts])
        except ValueError:
            pass


def add_gear(arm) -> list:
    created = []
    bone_mat = make_opaque_mat("VeteranBone", BONE, 0.65)
    cord_mat = make_opaque_mat("VeteranCord", CORD, 0.9)
    fur_mat = make_opaque_mat("VeteranFur", FUR, 1.0)
    fur_tip_mat = make_opaque_mat("VeteranFurTip", FUR_TIP, 1.0)

    # Necklace cord: torus around the neck, sitting in front of the throat.
    bpy.ops.mesh.primitive_torus_add(
        align="WORLD",
        location=(0.0, -0.16, 1.90),
        rotation=(math.radians(72.0), 0.0, 0.0),
        major_radius=0.30,
        minor_radius=0.028,
        major_segments=20,
        minor_segments=8,
    )
    cord = bpy.context.active_object
    cord.name = "VeteranCord"
    cord.data.materials.clear()
    cord.data.materials.append(cord_mat)
    bind_mesh(cord, arm, lambda v: {"Neck": 1.0})
    created.append(cord)

    # Bone trophy charms hanging on the CHEST (front = -Y).
    bm = bmesh.new()
    specs = [
        (-0.12, -0.34, 1.72, 0.055, 0.20, 18),
        (0.00, -0.38, 1.62, 0.070, 0.26, 0),
        (0.12, -0.34, 1.72, 0.055, 0.20, -18),
        (-0.07, -0.32, 1.50, 0.048, 0.16, 10),
        (0.07, -0.32, 1.50, 0.048, 0.16, -10),
    ]
    for x, y, z, r, length, yaw in specs:
        tmp = bmesh.new()
        bmesh.ops.create_cone(
            tmp,
            cap_ends=True,
            cap_tris=True,
            segments=8,
            radius1=r,
            radius2=r * 0.38,
            depth=length,
        )
        # extra knobs at the top so they read as bones, not cones
        kn = bmesh.new()
        bmesh.ops.create_uvsphere(kn, u_segments=8, v_segments=6, radius=r * 1.15)
        for v in kn.verts:
            v.co.z += length * 0.42
        append_transformed(tmp, kn)
        kn.free()
        for v in tmp.verts:
            # hang downward
            a = math.radians(90.0)
            cy = v.co.y * math.cos(a) - v.co.z * math.sin(a)
            cz = v.co.y * math.sin(a) + v.co.z * math.cos(a)
            v.co.y = cy
            v.co.z = cz
            ca = math.cos(math.radians(yaw))
            sa = math.sin(math.radians(yaw))
            rx = v.co.x * ca - v.co.y * sa
            ry = v.co.x * sa + v.co.y * ca
            v.co.x = rx + x
            v.co.y = ry + y
            v.co.z += z
        append_transformed(bm, tmp)
        tmp.free()
    charms = mesh_from_bmesh("VeteranBones", bm, bone_mat)
    def charm_w(v):
        t = max(0.0, min(1.0, (v.co.z - 1.45) / 0.40))
        return {"Neck": 0.25 + 0.45 * t, "Torso": 0.75 - 0.45 * t}
    bind_mesh(charms, arm, charm_w)
    created.append(charms)

    # Fur shoulder pelt on LEFT shoulder, offset outward so it is not buried.
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.55)
    for v in bm.verts:
        v.co.x = v.co.x * 0.62 + 0.55
        v.co.y = v.co.y * 0.42 + 0.02
        v.co.z = v.co.z * 0.26 + 1.74
        if v.co.x < 0.22:
            v.co.x = 0.22 + (v.co.x - 0.22) * 0.2
        if v.co.z < 1.50:
            v.co.z = 1.50 + (v.co.z - 1.50) * 0.25
    pelt = mesh_from_bmesh("VeteranPelt", bm, fur_mat)
    def pelt_w(v):
        sl = max(0.0, min(1.0, (v.co.x - 0.20) / 0.55))
        return {"Shoulder.L": 0.40 + 0.60 * sl, "Torso": 0.60 - 0.40 * sl}
    bind_mesh(pelt, arm, pelt_w)
    created.append(pelt)

    bm = bmesh.new()
    tufts = [
        (0.72, -0.02, 1.92, 0.09, 0.20, -25),
        (0.58, -0.18, 1.86, 0.08, 0.17, -8),
        (0.62, 0.18, 1.84, 0.08, 0.18, 18),
        (0.40, -0.06, 1.62, 0.07, 0.15, 6),
        (0.50, 0.08, 1.70, 0.07, 0.14, 10),
    ]
    for x, y, z, r, length, pitch in tufts:
        tmp = bmesh.new()
        bmesh.ops.create_cone(
            tmp,
            cap_ends=True,
            cap_tris=True,
            segments=6,
            radius1=r,
            radius2=0.012,
            depth=length,
        )
        for v in tmp.verts:
            v.co.z += length * 0.5
            a = math.radians(pitch)
            cy = v.co.y * math.cos(a) - v.co.z * math.sin(a)
            cz = v.co.y * math.sin(a) + v.co.z * math.cos(a)
            v.co.y = cy
            v.co.z = cz
            v.co.x += x
            v.co.y += y
            v.co.z += z
        append_transformed(bm, tmp)
        tmp.free()
    tufts_obj = mesh_from_bmesh("VeteranTufts", bm, fur_tip_mat)
    bind_mesh(tufts_obj, arm, pelt_w)
    created.append(tufts_obj)

    log(f"gear objects: {[o.name for o in created]}")
    return created


def export_glb(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    bpy.ops.object.select_all(action="SELECT")
    kwargs = dict(
        filepath=str(path),
        export_format="GLB",
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_nla_strips=True,
        export_force_sampling=True,
        export_optimize_animation_size=False,
        export_apply=False,
        export_skins=True,
        export_rest_position_armature=True,
        export_def_bones=False,
        export_anim_single_armature=True,
        export_current_frame=False,
        export_draco_mesh_compression_enable=False,
        export_extras=False,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
    )
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(
            filepath=str(path),
            export_format="GLB",
            export_animations=True,
            export_skins=True,
            export_yup=True,
            export_draco_mesh_compression_enable=False,
        )
    if not path.is_file():
        alt = Path(str(path) + ".glb")
        if alt.is_file():
            alt.replace(path)
        else:
            raise RuntimeError(f"export produced no file: {path}")
    log(f"exported {path} ({path.stat().st_size} bytes)")


def patch_dest(path: Path) -> dict:
    doc, blob, unknown, _raw = glb_chunks(path)
    if unknown:
        log(f"rewriting unknown/bad chunks {unknown!r} -> JSON + BIN\\0")
    for mat in doc.get("materials", []):
        mat["alphaMode"] = "OPAQUE"
        mat.pop("alphaCutoff", None)
        if "pbrMetallicRoughness" in mat:
            pbr = mat["pbrMetallicRoughness"]
            if "baseColorFactor" in pbr and len(pbr["baseColorFactor"]) == 4:
                pbr["baseColorFactor"][3] = 1.0
    write_glb(path, doc, blob)
    verify_fourcc(path)
    anims = [a.get("name") for a in doc.get("animations", [])]
    missing = [c for c in REQUIRED_CLIPS if c not in anims]
    if missing:
        raise RuntimeError(f"DEST missing required clips {missing}; have {anims}")
    blends = [(m.get("name"), m.get("alphaMode", "OPAQUE")) for m in doc.get("materials", [])]
    return {
        "anims": anims,
        "materials": blends,
        "meshes": [m.get("name") for m in doc.get("meshes", [])],
        "size": path.stat().st_size,
    }


def apply_action(arm, name: str, frame: int):
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing in scene")
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()


def setup_preview_scene(_arm):
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    ground_mat = make_opaque_mat("PreviewGround", (0.18, 0.175, 0.165), 1.0)
    bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "PreviewGround"
    ground.data.materials.append(ground_mat)

    world = bpy.data.worlds.new("PreviewWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.14, 0.145, 0.155, 1.0)
        bg.inputs[1].default_value = 1.0

    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    target = Vector((0.10, 0.00, 1.62))
    cam.location = Vector((3.35, -4.45, 2.10))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    def add_light(name, ltype, loc, energy, size=0.6, rot=None):
        data = bpy.data.lights.new(name, ltype)
        data.energy = energy
        if ltype == "AREA":
            data.size = size
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        if rot:
            obj.rotation_euler = rot
        bpy.context.scene.collection.objects.link(obj)

    add_light("Key", "SUN", (3.0, -2.5, 6.0), 3.4, rot=(math.radians(50), math.radians(15), math.radians(35)))
    add_light("Fill", "AREA", (-3.2, -2.0, 2.4), 200.0, size=2.4)
    add_light("Rim", "AREA", (0.4, 3.4, 3.2), 140.0, size=1.6)

    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    log(f"preview engine={scene.render.engine}")
    return ground


def render_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise RuntimeError(f"preview not written: {path}")
    log(f"preview {path} ({path.stat().st_size} bytes)")


def copy_preview(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    log(f"copied preview -> {dest}")
    return dest


def action_frame(name: str, kind: str) -> int:
    act = bpy.data.actions.get(name)
    if act is None:
        raise RuntimeError(f"action {name!r} missing")
    frames = [kp.co.x for fc in act.fcurves for kp in fc.keyframe_points]
    if not frames:
        return 1
    lo, hi = int(min(frames)), int(max(frames))
    if kind == "idle":
        return lo + max(1, (hi - lo) // 4)
    if kind == "punch":
        return lo + max(1, int((hi - lo) * 0.55))
    return lo


def bake() -> dict:
    if not SRC.is_file():
        raise FileNotFoundError(SRC)
    if DEST.resolve() == SRC.resolve():
        raise RuntimeError("refusing to overwrite Tribal.glb")
    if DEST.name == "Tribal.glb":
        raise RuntimeError("dest name must not be Tribal.glb")

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, SCRATCH_SRC)
    log(f"scratch copy {SCRATCH_SRC} ({SCRATCH_SRC.stat().st_size})")

    src_info = inspect_source_bytes(SRC)

    reset_scene()
    import_gltf(SRC)
    arm = find_armature()
    body = find_body()
    log(f"arm={arm.name!r} body={body.name!r} actions={sorted(a.name for a in bpy.data.actions)}")
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj != body:
            log(f"remove leftover {obj.name!r}")
            bpy.data.objects.remove(obj, do_unlink=True)

    rest_pose(arm)
    body.name = "Tribal_Veteran"
    rebuild_albedo(body)
    add_gear(arm)
    for mat in bpy.data.materials:
        force_opaque(mat)

    have = set(a.name for a in bpy.data.actions)
    miss = [c for c in REQUIRED_CLIPS if c not in have]
    if miss:
        raise RuntimeError(f"Punch/required clips missing after import: {miss} have={sorted(have)}")

    export_glb(DEST)
    dest_info = patch_dest(DEST)
    log(f"dest clips={dest_info['anims']}")
    log(f"dest materials={dest_info['materials']}")

    setup_preview_scene(arm)
    apply_action(arm, "Idle", action_frame("Idle", "idle"))
    render_png(PREVIEW)
    copy_preview(PREVIEW, PREVIEW_COPY_DIR)
    apply_action(arm, "Punch", action_frame("Punch", "punch"))
    render_png(PREVIEW_PUNCH)
    copy_preview(PREVIEW_PUNCH, PREVIEW_COPY_DIR)

    return {
        "source_clips": src_info["anims"],
        "dest": str(DEST),
        "size": dest_info["size"],
        "clips": dest_info["anims"],
        "materials": dest_info["materials"],
        "preview": str(PREVIEW),
        "preview_punch": str(PREVIEW_PUNCH),
    }


def main() -> int:
    log(f"blender {bpy.app.version_string}")
    guard = snapshot(GUARD_PATHS)
    try:
        res = bake()
        assert_untouched(guard, "protected Tribal.glb")
        fourcc = [c.decode("latin1") for c in verify_fourcc(DEST)]
        report = {
            "dest": res["dest"],
            "size": res["size"],
            "clips": res["clips"],
            "materials": res["materials"],
            "bin_fourcc": fourcc,
            "preview": res["preview"],
            "preview_punch": res["preview_punch"],
            "visual": {
                "paint": "ochre/white/soot graphic stripes on tiki-mask face + chest (unique albedo)",
                "gear": "bone trophy necklace on chest (Neck/Torso) + fur left-shoulder pelt/tufts (Shoulder.L/Torso)",
                "palette": "weathered darker leather, faded cloth, slightly darker skin vs stock Tribal",
            },
        }
        log(f"DONE dest={DEST} size={DEST.stat().st_size}")
        print(json.dumps(report, indent=2), flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        try:
            assert_untouched(guard, "protected Tribal.glb")
        except Exception:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
