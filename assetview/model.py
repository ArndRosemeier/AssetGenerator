"""The mesh an inspection looks at: triangles with a material slot, welded into parts.

Loaded from a kit `Asset` (before the backend's finishing steps) or from a shipped
.glb, so every generator can be inspected, kit or not. Z up, metres.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from assetkit import Asset
from assetkit.asset import pattern_of
from assetkit.texbake import SlotLook
from assetview.paint import PatternPaint, TexturePaint, glb_textures
from blender.lib.glb import Glb


class Paint(Protocol):
    def colors(self, tri: np.ndarray, bary: np.ndarray) -> np.ndarray:
        """Linear colour (N, 3) at N surface points: triangle ids and barycentric weights."""
        ...


WELD = 1e-5  # metres: vertices closer than this are one (glTF splits them per normal and UV)


@dataclass
class ViewModel:
    positions: np.ndarray  # (V, 3) float64, welded
    triangles: np.ndarray  # (T, 3) int64 into positions
    tri_slot: np.ndarray  # (T,) int64 into slots
    slots: list[str]
    slot_colors: np.ndarray  # (S, 3) float64, linear 0..1
    real_edges: np.ndarray  # (T, 3) bool: edge k (corner k to k+1) is a polygon edge, not a fan diagonal
    source: str
    #: Colour per surface point (assetview/paint.py) where materials vary over the surface, or None.
    paint: Paint | None = None
    #: Per slot, 1 opaque, below 1 see-through (glass); None: all opaque.
    slot_alpha: np.ndarray | None = None
    #: How the asset is shaded: per triangle, the cosine of the angle beyond which a vertex
    #: normal is not shared (2: flat, -2: all smooth); or normals per triangle corner (T, 3, 3),
    #: as a shipped file stores them. None: smooth with hard creases past 40 degrees.
    crease: np.ndarray | None = None
    corner_normals: np.ndarray | None = None

    def see_through(self) -> np.ndarray:
        """Per triangle, whether its material is see-through."""
        if self.slot_alpha is None:
            return np.zeros(len(self.triangles), dtype=bool)
        return self.slot_alpha[self.tri_slot] < 0.95

    def islands(self) -> np.ndarray:
        """Connected part per triangle (shared welded vertices)."""
        parent = np.arange(len(self.positions))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for a, b, c in self.triangles:
            ra, rb, rc = find(a), find(b), find(c)
            parent[rb] = ra
            parent[find(rc)] = ra
        roots = np.array([find(i) for i in range(len(self.positions))])
        _, labels = np.unique(roots[self.triangles[:, 0]], return_inverse=True)
        return labels


def _weld(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    keys = np.round(points / WELD).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    return points[first], inverse.reshape(-1)


def from_asset(asset: Asset) -> ViewModel:
    points: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int]] = []
    real: list[tuple[bool, bool, bool]] = []
    tri_slot: list[int] = []
    slots: list[str] = []
    colors: list[tuple[float, float, float]] = []
    looks: list[SlotLook] = []
    origins: list[tuple[float, float, float]] = []
    alphas: list[float] = []
    crease: list[float] = []
    for part in asset.parts:
        mesh = part.mesh
        offset = len(points)
        points.extend(mesh.vertices)
        cos = shading_crease(part.finish)
        slot_base = len(slots)
        for slot in mesh.slots:
            slots.append(slot if len(asset.parts) == 1 else f"{part.name}.{slot}")
            material = part.materials[slot]
            colors.append(tuple(material.base_color[:3]))
            looks.append(SlotLook(pattern_of(material), colors[-1], material.roughness))  # type: ignore[arg-type]
            origins.append(part.pattern_origin)
            alphas.append(float(getattr(material, "alpha", 1.0)))
        for face, slot in zip(mesh.faces, mesh.face_slots, strict=True):
            n = len(face)
            for k in range(1, n - 1):
                tris.append((offset + face[0], offset + face[k], offset + face[k + 1]))
                real.append((k == 1, True, k == n - 2))
                tri_slot.append(slot_base + slot)
                crease.append(cos)
    welded, remap = _weld(np.asarray(points, dtype=np.float64))
    triangles = remap[np.asarray(tris, dtype=np.int64)]
    slot_of = np.asarray(tri_slot, dtype=np.int64)
    paint = None
    if any(look.pattern is not None for look in looks):
        paint = PatternPaint(welded, triangles, slot_of, looks, origins)
    return ViewModel(
        positions=welded,
        triangles=triangles,
        tri_slot=slot_of,
        slots=slots,
        slot_colors=np.asarray(colors, dtype=np.float64),
        real_edges=np.asarray(real, dtype=bool),
        source="kit asset (before bevel and unwrap)" + (", patterns evaluated" if paint else ""),
        paint=paint,
        slot_alpha=np.asarray(alphas, dtype=np.float64),
        crease=np.asarray(crease, dtype=np.float64),
    )


def shading_crease(finish: object) -> float:
    """The cosine past which a part's shading keeps an edge hard, from its finishing steps."""
    import math

    from assetkit import ShadeFlat, ShadeSmooth

    cos = 2.0  # unshaded parts ship flat
    for step in finish:  # type: ignore[attr-defined]
        if isinstance(step, ShadeFlat):
            cos = 2.0
        elif isinstance(step, ShadeSmooth):
            angle = step.sharp_angle_deg
            cos = -2.0 if angle is None else math.cos(math.radians(angle))
    return cos


def from_glb(path: Path) -> ViewModel:
    glb = Glb(path)
    doc = glb.doc
    materials = doc.get("materials", [])
    slots = [m.get("name", f"material_{i}") for i, m in enumerate(materials)] or ["default"]
    colors = []
    alphas: list[float] = []
    textured = False
    for m in materials or [{}]:
        pbr = m.get("pbrMetallicRoughness", {})
        textured |= "baseColorTexture" in pbr
        colors.append(tuple(pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])[:3]))
        blended = m.get("alphaMode") == "BLEND"
        alphas.append(float(pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])[3]) if blended else 1.0)
    points: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    tri_slot: list[np.ndarray] = []
    corner_uvs: list[np.ndarray] = []
    corner_normals: list[np.ndarray] = []
    offset = 0
    for node in doc.get("nodes", []):
        if "mesh" not in node:
            continue
        matrix = _node_matrix(node)
        for primitive in doc["meshes"][node["mesh"]]["primitives"]:
            local = np.asarray(glb.values(primitive["attributes"]["POSITION"]), dtype=np.float64)
            world = local @ matrix[:3, :3].T + matrix[:3, 3]
            # glTF is Y up, front +Z; back to Z up, front -Y.
            points.append(np.stack([world[:, 0], -world[:, 2], world[:, 1]], axis=1))
            index = np.asarray([i[0] for i in glb.values(primitive["indices"])], dtype=np.int64).reshape(
                -1, 3
            )
            tris.append(index + offset)
            if "NORMAL" in primitive["attributes"]:
                normal = np.asarray(glb.values(primitive["attributes"]["NORMAL"]), dtype=np.float64)
                normal = normal @ matrix[:3, :3].T
                normal = np.stack([normal[:, 0], -normal[:, 2], normal[:, 1]], axis=1)
                corner_normals.append(normal[index])
            else:
                corner_normals.append(np.full((len(index), 3, 3), np.nan))
            if "TEXCOORD_0" in primitive["attributes"]:
                uv = np.asarray(glb.values(primitive["attributes"]["TEXCOORD_0"]), dtype=np.float64)
                corner_uvs.append(uv[index])
            else:
                corner_uvs.append(np.zeros((len(index), 3, 2)))
            tri_slot.append(np.full(len(index), primitive.get("material", 0), dtype=np.int64))
            offset += len(local)
    if not points:
        raise ValueError(f"{path.name} holds no mesh")
    welded, remap = _weld(np.concatenate(points))
    triangles = remap[np.concatenate(tris)]
    slot_of = np.concatenate(tri_slot)
    paint = None
    if textured:
        textures = glb_textures(glb)
        paint = TexturePaint(
            np.concatenate(corner_uvs), slot_of, textures, np.asarray(colors, dtype=np.float64)
        )
        # Views that colour by material show a textured one by its texture's average over its faces.
        for s, texture in enumerate(textures):
            if texture is not None:
                colors[s] = tuple(np.asarray(colors[s]) * _mean_on(texture, paint.corner_uvs[slot_of == s]))
    return ViewModel(
        positions=welded,
        triangles=triangles,
        tri_slot=slot_of,
        slots=slots,
        slot_colors=np.asarray(colors, dtype=np.float64),
        real_edges=np.ones(triangles.shape, dtype=bool),
        source=f"shipped file {path.name}" + (", textures sampled" if textured else ""),
        paint=paint,
        slot_alpha=np.asarray(alphas, dtype=np.float64) if alphas else None,
        corner_normals=np.concatenate(corner_normals),
    )


def _mean_on(texture: np.ndarray, corner_uvs: np.ndarray) -> np.ndarray:
    """The texture's mean colour at the centres of the given UV triangles."""
    if not len(corner_uvs):
        return texture.reshape(-1, 3).mean(axis=0)
    uv = corner_uvs.mean(axis=1) % 1.0
    h, w = texture.shape[:2]
    return texture[
        (uv[:, 1] * h).astype(np.int64).clip(0, h - 1), (uv[:, 0] * w).astype(np.int64).clip(0, w - 1)
    ].mean(axis=0)


def _node_matrix(node: dict) -> np.ndarray:
    """A node's own transform (the exporter writes meshes at the root; parents are not followed)."""
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    m[:3, :3] = rotation * np.asarray(node.get("scale", [1.0, 1.0, 1.0]))
    m[:3, 3] = node.get("translation", [0.0, 0.0, 0.0])
    return m
