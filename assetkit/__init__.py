"""The asset kit: the stable layer asset generators are written against.

A kit generator turns a spec into an `Asset` (meshes, materials, finishing steps)
using only this package and the standard library. It never imports `bpy`,
`bmesh` or `mathutils`, so it runs and can be tested without Blender, and a new
Blender version changes the backend (blender/backend/), not the generators.

`assetkit.sdf` (distance-function shapes and their meshing), `assetkit.simplify`
and `assetkit.sculpt` (shape trees as JSON) also need numpy; import them by name.

API_VERSION counts breaking changes to what is exported here. Adding is not
breaking; renaming or changing a meaning is, and needs every kit generator moved
along in the same change.
"""

from __future__ import annotations

from typing import Final

from assetkit import noise, shells
from assetkit.asset import Asset, Bevel, Material, Part, ShadeFlat, ShadeSmooth, Step, Unwrap
from assetkit.mesh import Mesh, MeshBuilder

API_VERSION: Final[int] = 1

__all__ = [
    "API_VERSION",
    "Asset",
    "Bevel",
    "Material",
    "Mesh",
    "MeshBuilder",
    "Part",
    "ShadeFlat",
    "ShadeSmooth",
    "Step",
    "Unwrap",
    "noise",
    "shells",
]
