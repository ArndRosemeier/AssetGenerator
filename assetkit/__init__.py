"""The asset kit: the stable layer asset generators are written against.

A kit generator turns a spec into an `Asset` (meshes, materials, finishing steps)
using only this package and the standard library. It never imports `bpy`,
`bmesh` or `mathutils`, so it runs and can be tested without Blender, and a new
Blender version changes the backend (blender/backend/), not the generators.

`assetkit.sdf` (distance-function shapes and their meshing), `assetkit.simplify`,
`assetkit.sculpt` (shape trees as JSON), `assetkit.skinning`, `assetkit.rigspec`
(rigs as JSON) and `assetkit.texbake` (patterns baked to textures) also need numpy;
import them by name. `assetkit.rig` (skeletons, poses, clips) and `assetkit.motion`
(clips as JSON) are standard library only; `assetkit.material` parses material
patterns with the standard library and evaluates them with numpy.

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
