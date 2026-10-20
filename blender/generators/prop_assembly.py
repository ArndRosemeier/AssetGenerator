"""prop.assembly: a hard-surface prop written in the spec as exact pieces (assetkit/assembly.py).

Lanterns, cages, chests, tools, furniture, fittings: anything made of turned, cut and bent parts
with crisp edges. A new prop is a new spec, not new code.

    "params": {
      "parts":  {"post": {"box": {"size": [0.016, 0.016, 0.3]}, "slot": "iron"}},
      "pieces": [
        {"lathe": {"profile": [[0.1, 0], [0.1, 0.02], [0.08, 0.03]]}, "slot": "iron"},
        {"ref": "post", "at": [0.08, 0, 0.18], "repeat": {"around": 4, "start": 45}},
        {"cylinder": {"a": [0, 0, 0.03], "b": [0, 0, 0.33], "radius": 0.07}, "slot": "glass"}
      ],
      "bevel": 0.002
    }

`bevel` (metres, default 0) rounds edges sharper than 30 degrees on pieces at least 8 bevels
thick (or marked `"bevel": true`), so edges catch light and wear patterns find them;
`sharp_angle` (default 35) keeps edges that turn more hard in the shading and rounds the rest;
`detail` (default 1) scales how many sides round shapes get; `settle` (default true) centres
the footprint on the origin and stands the prop on z = 0.
Material slots are the spec's materials, each used by some piece. Patterns on them are written
in the pieces' coordinates.
"""

from __future__ import annotations

from assetkit import Asset, Bevel, MeshBuilder, Part, ShadeSmooth, Unwrap
from assetkit.assembly import AssemblyError, bevelled_triangles, build_pieces
from blender.lib.spec import AssetSpec, SpecError, as_bool, as_float, as_mapping, reject_unknown, require_key

MATERIAL_SLOTS: tuple[str, ...] = ()  # from the spec: every slot a piece uses

_KEYS = ("pieces", "parts", "bevel", "sharp_angle", "detail", "settle")


def build(spec: AssetSpec) -> Asset:
    raw = spec.params
    reject_unknown(raw, _KEYS, "params")
    parts = dict(as_mapping(raw.get("parts", {}), "params.parts"))
    detail = as_float(raw.get("detail", 1.0), "params.detail")
    if not 0.25 <= detail <= 4.0:
        raise SpecError("params.detail: expected 0.25..4")
    bevel = as_float(raw.get("bevel", 0.0), "params.bevel")
    if bevel < 0:
        raise SpecError("params.bevel: must not be negative")
    try:
        pieces = build_pieces(require_key(raw, "pieces", "params"), parts, "params.pieces", detail, bevel)
    except AssemblyError as exc:
        raise SpecError(str(exc)) from exc

    used = list(dict.fromkeys(slot for _, slot, _ in pieces))
    unknown = [s for s in used if s not in spec.materials]
    if unknown:
        raise SpecError(
            f"params.pieces: slot(s) {unknown} have no material; materials are {sorted(spec.materials)}"
        )
    unused = sorted(set(spec.materials) - set(used))
    if unused:
        raise SpecError(f"materials: {unused} are used by no piece")

    builder = MeshBuilder(used)
    marks: list[float] = []
    for shell, slot, bevelled in pieces:
        builder.add(shell, slot)
        marks += [1.0 if bevelled else 0.0] * len(shell[0])
    builder.set_point_attribute("bevel", marks)
    mesh = builder.build()
    expected = mesh.triangle_count() + (bevelled_triangles(mesh, marks) if bevel > 0 else 0)
    if expected > spec.qa.max_triangles:
        raise SpecError(
            f"params.pieces: about {expected} triangles after the bevel ({mesh.triangle_count()} before), "
            f"over qa.max_triangles {spec.qa.max_triangles}: a lower `detail`, fewer `segments` on "
            "small round pieces, fewer pieces, or no bevel"
        )
    unsettled = mesh
    if as_bool(raw.get("settle", True), "params.settle"):
        mesh = mesh.settled()
    offset = tuple(a - b for a, b in zip(mesh.vertices[0], unsettled.vertices[0], strict=True))

    finish = (
        *((Bevel(width=bevel, segments=1, angle_deg=30.0, only="bevel"),) if bevel > 0 else ()),
        ShadeSmooth(sharp_angle_deg=as_float(raw.get("sharp_angle", 35.0), "params.sharp_angle")),
        Unwrap(),
    )
    return Asset((Part(spec.asset_id, mesh, spec.materials, finish, pattern_origin=offset),))
