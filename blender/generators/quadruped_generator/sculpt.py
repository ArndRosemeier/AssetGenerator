"""From a Body's shapes to a smooth mesh object: the field, surface nets, relaxing and thinning."""

from __future__ import annotations

import bmesh
import bpy
import numpy as np

from blender.generators.quadruped_generator.anatomy import Body
from blender.generators.quadruped_generator.sdf import Grid


def field_of(body: Body, step: float) -> Grid:
    lo = np.min([s.lo for s in body.shapes], axis=0) - 0.03
    hi = np.max([s.hi for s in body.shapes], axis=0) + 0.03
    grid = Grid(tuple(lo), tuple(hi), step)
    for shape in sorted(body.shapes, key=lambda s: s.carve):
        grid.add(shape)
    return grid


def ribs(grid: Grid, depth: float) -> None:
    """Shallow grooves between the ribs on the flanks, slanting back as they go down."""
    got = grid.local((0.04, -0.12, 0.36), (0.13, 0.2, 0.6))
    if got is None:
        return
    sl, x, y, z = got
    along = y + (0.56 - z) * 0.35
    mask = np.clip((np.abs(x) - 0.05) / 0.04, 0.0, 1.0)
    mask *= np.clip((z - 0.38) / 0.05, 0.0, 1.0) * np.clip((0.58 - z) / 0.06, 0.0, 1.0)
    mask *= np.clip((y + 0.11) / 0.05, 0.0, 1.0) * np.clip((0.19 - y) / 0.05, 0.0, 1.0)
    groove = 0.5 + 0.5 * np.cos(along * (2.0 * np.pi / 0.034))
    grid.values[sl] += (depth * mask * groove).astype(np.float32)
    # The same on the right flank.
    got = grid.local((-0.13, -0.12, 0.36), (-0.04, 0.2, 0.6))
    if got is None:
        return
    sl, x, y, z = got
    along = y + (0.56 - z) * 0.35
    mask = np.clip((np.abs(x) - 0.05) / 0.04, 0.0, 1.0)
    mask *= np.clip((z - 0.38) / 0.05, 0.0, 1.0) * np.clip((0.58 - z) / 0.06, 0.0, 1.0)
    mask *= np.clip((y + 0.11) / 0.05, 0.0, 1.0) * np.clip((0.19 - y) / 0.05, 0.0, 1.0)
    groove = 0.5 + 0.5 * np.cos(along * (2.0 * np.pi / 0.034))
    grid.values[sl] += (depth * mask * groove).astype(np.float32)


def mesh_object(name: str, verts: np.ndarray, faces: np.ndarray) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.data.scenes[0].collection.objects.link(obj)
    return obj


def relax(obj: bpy.types.Object, iterations: int) -> None:
    """Smooth the voxel steps away and triangulate."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    for _ in range(iterations):
        bmesh.ops.smooth_vert(
            bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True
        )
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def points_and_normals(obj: bpy.types.Object) -> tuple[np.ndarray, np.ndarray]:
    me = obj.data
    n = len(me.vertices)
    p = np.empty(n * 3)
    me.vertices.foreach_get("co", p)
    nn = np.empty(n * 3)
    me.vertices.foreach_get("normal", nn)
    return p.reshape(n, 3), nn.reshape(n, 3)


def push_out(obj: bpy.types.Object, offsets: np.ndarray) -> None:
    """Move every vertex out along its normal by its offset."""
    p, n = points_and_normals(obj)
    obj.data.vertices.foreach_set("co", (p + n * offsets[:, None]).ravel())
    obj.data.update()


def thin(obj: bpy.types.Object, target_tris: int) -> None:
    """Collapse to about `target_tris` triangles, shaded smooth."""
    tris = len(obj.data.polygons)
    if tris > target_tris:
        mod = obj.modifiers.new("thin", "DECIMATE")
        mod.ratio = target_tris / tris
        mod.use_collapse_triangulate = True
        _apply(obj, mod)
    for poly in obj.data.polygons:
        poly.use_smooth = True


def _apply(obj: bpy.types.Object, mod: bpy.types.Modifier) -> None:
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    new = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.remove(mod)
    obj.data = new
    bpy.data.meshes.remove(old)
