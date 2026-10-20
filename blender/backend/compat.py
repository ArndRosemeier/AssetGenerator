"""Every Blender-version difference the pipeline knows about, in one place.

Code outside this module calls these functions instead of checking
`bpy.app.version` or probing with `hasattr`. A new Blender release that breaks
something is fixed here, once, for every generator; one that does something
better (a better unwrap, a better bevel) is taken up here too, and every kit
generator gets it without changing.

Supported range: SUPPORTED_MIN up to (not including) SUPPORTED_BELOW. The cross
check (`python tools/backend_matrix.py`) builds the same specs on versions in the
range: the spec's contract must hold on each, and what differs is listed.
"""

from __future__ import annotations

import math
from typing import Final

import bpy

SUPPORTED_MIN: Final[tuple[int, int]] = (4, 5)
SUPPORTED_BELOW: Final[tuple[int, int]] = (6, 0)


def version() -> tuple[int, int, int]:
    major, minor, patch = bpy.app.version
    return (major, minor, patch)


def require_supported() -> None:
    if not SUPPORTED_MIN <= version()[:2] < SUPPORTED_BELOW:
        raise RuntimeError(
            f"Blender {bpy.app.version_string} is outside the supported range "
            f"{SUPPORTED_MIN[0]}.{SUPPORTED_MIN[1]} to below {SUPPORTED_BELOW[0]}.{SUPPORTED_BELOW[1]}: "
            "add what it needs to blender/backend/compat.py and widen the range."
        )


def set_sharp_from_angle(mesh: bpy.types.Mesh, angle_deg: float) -> None:
    """Mark edges whose faces turn by more than `angle_deg` sharp, so smooth shading keeps them hard.

    4.1 replaced auto smooth (a mesh setting) with this; every supported version has it.
    """
    mesh.set_sharp_from_angle(angle=math.radians(angle_deg))


def action_fcurves(action: bpy.types.Action) -> list[bpy.types.FCurve]:
    """Every F-curve of an action.

    4.4 made actions layered (layers, strips, channel bags per slot) and kept
    `Action.fcurves` as a view of the first slot; 5.0 removed that view. The
    layered path works on every supported version.
    """
    return [
        fcurve
        for layer in action.layers
        for strip in layer.strips
        for bag in strip.channelbags
        for fcurve in bag.fcurves
    ]


def set_blended(material: bpy.types.Material) -> None:
    """Draw the material see-through by its alpha (glTF alphaMode BLEND).

    4.2 replaced `blend_method` with `surface_render_method`; every supported version has it,
    and the glTF exporter writes BLEND for an alpha below 1 either way.
    """
    material.surface_render_method = "BLENDED"


def set_edge_bevel_weights(mesh: bpy.types.Mesh, weights: list[float]) -> str:
    """One bevel weight per edge, for a bevel limited by weight; returns the attribute's name.

    4.0 moved bevel weights from `MeshEdge.bevel_weight` to this float edge attribute.
    """
    name = "bevel_weight_edge"
    attribute = mesh.attributes.get(name) or mesh.attributes.new(name, "FLOAT", "EDGE")
    attribute.data.foreach_set("value", weights)
    return name


def corner_frames(mesh: bpy.types.Mesh) -> tuple[list[float], list[float], list[float]]:
    """Per face corner (loop), flattened: the shading normal, the MikkTSpace tangent of the
    active UV map and the bitangent sign, as glTF viewers rebuild them.

    `calc_tangents` fills `MeshLoop.tangent`, `.bitangent_sign` and `.normal` on every
    supported version (4.1 moved custom normals to `corner_normals`; the loop's normal stays).
    """
    mesh.calc_tangents(uvmap=mesh.uv_layers.active.name)
    count = len(mesh.loops)
    normals, tangents, signs = [0.0] * (3 * count), [0.0] * (3 * count), [0.0] * count
    mesh.loops.foreach_get("normal", normals)
    mesh.loops.foreach_get("tangent", tangents)
    mesh.loops.foreach_get("bitangent_sign", signs)
    mesh.free_tangents()
    return normals, tangents, signs
