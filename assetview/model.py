"""The mesh an inspection looks at: triangles with a material slot, welded into parts.

Loaded from a kit `Asset` (before the backend's finishing steps) or from a shipped
.glb, so every generator can be inspected, kit or not. Z up, metres.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from assetkit import Asset
from blender.lib.glb import Glb

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
    for part in asset.parts:
        mesh = part.mesh
        offset = len(points)
        points.extend(mesh.vertices)
        slot_base = len(slots)
        for slot in mesh.slots:
            slots.append(slot if len(asset.parts) == 1 else f"{part.name}.{slot}")
            colors.append(tuple(part.materials[slot].base_color[:3]))
        for face, slot in zip(mesh.faces, mesh.face_slots, strict=True):
            n = len(face)
            for k in range(1, n - 1):
                tris.append((offset + face[0], offset + face[k], offset + face[k + 1]))
                real.append((k == 1, True, k == n - 2))
                tri_slot.append(slot_base + slot)
    welded, remap = _weld(np.asarray(points, dtype=np.float64))
    return ViewModel(
        positions=welded,
        triangles=remap[np.asarray(tris, dtype=np.int64)],
        tri_slot=np.asarray(tri_slot, dtype=np.int64),
        slots=slots,
        slot_colors=np.asarray(colors, dtype=np.float64),
        real_edges=np.asarray(real, dtype=bool),
        source="kit asset (before bevel and unwrap)",
    )


def from_glb(path: Path) -> ViewModel:
    glb = Glb(path)
    doc = glb.doc
    materials = doc.get("materials", [])
    slots = [m.get("name", f"material_{i}") for i, m in enumerate(materials)] or ["default"]
    colors = []
    textured = False
    for m in materials or [{}]:
        pbr = m.get("pbrMetallicRoughness", {})
        textured |= "baseColorTexture" in pbr
        colors.append(tuple(pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1.0])[:3]))
    points: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    tri_slot: list[np.ndarray] = []
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
            tri_slot.append(np.full(len(index), primitive.get("material", 0), dtype=np.int64))
            offset += len(local)
    if not points:
        raise ValueError(f"{path.name} holds no mesh")
    welded, remap = _weld(np.concatenate(points))
    triangles = remap[np.concatenate(tris)]
    return ViewModel(
        positions=welded,
        triangles=triangles,
        tri_slot=np.concatenate(tri_slot),
        slots=slots,
        slot_colors=np.asarray(colors, dtype=np.float64),
        real_edges=np.ones(triangles.shape, dtype=bool),
        source=f"shipped file {path.name}" + (" (textures not shown)" if textured else ""),
    )


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
