"""The skeleton, and skin weights from the sculpt itself.

Each shape of the sculpt names the bone that carries it, so a vertex belongs to
the bones whose shapes it lies on: the weight falls off with the distance to
each bone's nearest shape. The jaw and the ears fall off sharply, so the mouth
opens cleanly along its slit and the ears move on their own.
"""

from __future__ import annotations

import bpy
import numpy as np

from blender.generators.crawler_generator.rig import bind_mesh, build_armature
from blender.generators.quadruped_generator.anatomy import Body

#: How softly each bone's weight falls off (metres); the default is for the joints of body and legs.
SOFTNESS = {"jaw": 0.0025, "head": 0.006, "ear.L": 0.004, "ear.R": 0.004}
DEFAULT_SOFTNESS = 0.014
MAX_INFLUENCES = 4


def armature_for(name: str, body: Body) -> bpy.types.Object:
    return build_armature(name, body)


def skin_weights(body: Body, points: np.ndarray) -> tuple[list[str], np.ndarray]:
    """Bone names and an (points x bones) weight table, at most four influences per point."""
    names = [b.name for b in body.bones]
    dist = np.full((len(points), len(names)), np.inf)
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    col = {n: i for i, n in enumerate(names)}
    for shape in body.shapes:
        if shape.carve:
            continue
        d = shape.field(x, y, z)
        j = col[shape.bone]
        dist[:, j] = np.minimum(dist[:, j], d)
    soft = np.array([SOFTNESS.get(n, DEFAULT_SOFTNESS) for n in names])
    near = dist.min(axis=1, keepdims=True)
    w = np.exp(-(dist - near) / soft[None, :])
    w[~np.isfinite(w)] = 0.0
    # Keep the strongest four.
    cut = np.sort(w, axis=1)[:, -MAX_INFLUENCES][:, None]
    w = np.where(w >= cut, w, 0.0)
    w[w < 0.01] = 0.0
    w /= w.sum(axis=1, keepdims=True)
    return names, w


def bind(
    mesh: bpy.types.Object,
    armature: bpy.types.Object,
    names: list[str],
    weights: np.ndarray,
    fixed: dict[int, str] | None = None,
) -> None:
    """Write the weights as vertex groups (`fixed` vertices go wholly to one bone) and skin `mesh` to `armature`."""
    groups = {n: mesh.vertex_groups.new(name=n) for n in names}
    fixed = fixed or {}
    for i in range(len(weights)):
        if i in fixed:
            groups[fixed[i]].add([i], 1.0, "REPLACE")
            continue
        for j in np.nonzero(weights[i])[0]:
            groups[names[j]].add([i], float(weights[i, j]), "REPLACE")
    bind_mesh(mesh, armature)
