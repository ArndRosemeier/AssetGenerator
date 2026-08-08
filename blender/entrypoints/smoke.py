"""Bootstrap self-test: prove that this Blender can build, export and reimport."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections.abc import Mapping

import bpy

from blender.lib.export import export_glb, import_glb
from blender.lib.qa import collect_stats
from blender.lib.report import Report, check, failed_checks
from blender.lib.runner import execute
from blender.lib.scene import BoxBuilder, reset_scene
from blender.lib.spec import MaterialSpec


def handle(payload: Mapping[str, object]) -> Report:
    out_dir = Path(str(payload["out_dir"]))

    reset_scene()
    builder = BoxBuilder(("smoke",))
    builder.add_box((0.0, 0.0, 0.5), (1.0, 1.0, 1.0), "smoke")
    obj = builder.to_object(
        "smoke_cube",
        {"smoke": MaterialSpec(base_color=(0.8, 0.3, 0.2, 1.0), roughness=0.5, metallic=0.0)},
    )

    glb_path = export_glb([obj], out_dir / "smoke_cube.glb")
    reimported = import_glb(glb_path)
    stats = collect_stats(reimported)

    checks = [
        check("blender_version", bpy.app.version >= (4, 2, 0), f"Blender {bpy.app.version_string}"),
        check("gltf_roundtrip", stats["triangles"] == 12, f"{stats['triangles']} tris after reimport"),
        check("materials_survived", stats["materials"] == 1, f"{stats['materials']} material(s)"),
    ]

    return {
        "ok": not failed_checks(checks),
        "command": "smoke",
        "asset_id": "smoke_cube",
        "outputs": {"glb": str(glb_path)},
        "stats": stats,
        "checks": checks,
        "errors": [],
    }


execute("smoke", handle)
