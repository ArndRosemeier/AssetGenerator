"""Build an asset from a spec, gate it on QA, export it and verify the export."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import importlib
from collections.abc import Mapping

from assetview import from_glb, look
from assetview.cli import look_rig
from blender.backend import build, rig_deviation
from blender.lib.export import clip_checks, export_glb, import_glb, roundtrip_checks
from blender.lib.qa import collect_stats, run_checks
from blender.lib.registry import resolve_generator_module
from blender.lib.report import Report, check, failed_checks
from blender.lib.runner import execute
from blender.lib.scene import reset_scene
from blender.lib.spec import load_spec


def handle(payload: Mapping[str, object]) -> Report:
    spec_path = Path(str(payload["spec_path"]))
    out_dir = Path(str(payload["out_dir"]))

    spec = load_spec(spec_path)
    module = importlib.import_module(resolve_generator_module(spec.generator))

    reset_scene()
    objects, kit_asset = build(module, spec)

    stats = collect_stats(objects)
    checks = run_checks(objects, spec.qa, stats, topology=True)
    if kit_asset is not None and kit_asset.clips:
        # The rig sheet and the clip checks come from the kit's skinning: hold Blender to it.
        deviation = rig_deviation(kit_asset, objects)
        checks.append(
            check("rig_matches_kit", deviation < 1e-4, f"Blender vs kit skinning: {deviation:.1e} m")
        )

    rigged = any(obj.type == "ARMATURE" for obj in objects)
    glb_path = export_glb(objects, out_dir / spec.glb_name, getattr(module, "IMAGE_FORMAT", "AUTO"))

    reimported = import_glb(glb_path)
    roundtrip_stats = collect_stats(reimported)
    checks.extend(roundtrip_checks(stats, roundtrip_stats))
    if rigged:
        expected = [(c.name, c.seconds, c.loop) for c in kit_asset.clips] if kit_asset is not None else []
        checks.extend(clip_checks(glb_path, expected))
    # The inspection sheet of the shipped file: the first thing to look at after a build.
    inspection = look(from_glb(glb_path), spec.asset_id, out_dir / "look" / f"{spec.asset_id}.png")
    if kit_asset is not None and kit_asset.skeleton is not None:
        # The rig sheet from the kit asset: its frames are the skinning sum Blender runs.
        rig = look_rig(kit_asset, spec.asset_id, out_dir)
        inspection.update(rig)
        inspection["summary"] = [*inspection["summary"], *rig["rig_summary"]]

    return {
        "ok": not failed_checks(checks),
        "command": "generate",
        "asset_id": spec.asset_id,
        "generator": spec.generator,
        "outputs": {
            "glb": str(glb_path),
            "look": inspection["sheet"],
            **({"rig": inspection["rig_sheet"]} if "rig_sheet" in inspection else {}),
        },
        "look": inspection,
        "stats": stats,
        "roundtrip": roundtrip_stats,
        "checks": checks,
        "errors": [],
    }


execute("generate", handle)
