"""Build an asset from a spec, gate it on QA, export it and verify the export."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import importlib
from collections.abc import Mapping

from assetview import from_glb, look
from blender.backend import build_objects
from blender.lib.export import clip_checks, export_glb, import_glb, roundtrip_checks
from blender.lib.qa import collect_stats, run_checks
from blender.lib.registry import resolve_generator_module
from blender.lib.report import Report, failed_checks
from blender.lib.runner import execute
from blender.lib.scene import reset_scene
from blender.lib.spec import load_spec


def handle(payload: Mapping[str, object]) -> Report:
    spec_path = Path(str(payload["spec_path"]))
    out_dir = Path(str(payload["out_dir"]))

    spec = load_spec(spec_path)
    module = importlib.import_module(resolve_generator_module(spec.generator))

    reset_scene()
    objects = build_objects(module, spec)

    stats = collect_stats(objects)
    checks = run_checks(objects, spec.qa, stats, topology=True)

    rigged = any(obj.type == "ARMATURE" for obj in objects)
    glb_path = export_glb(objects, out_dir / spec.glb_name, getattr(module, "IMAGE_FORMAT", "AUTO"))

    reimported = import_glb(glb_path)
    roundtrip_stats = collect_stats(reimported)
    checks.extend(roundtrip_checks(stats, roundtrip_stats))
    if rigged:
        checks.extend(clip_checks(glb_path))
    # The inspection sheet of the shipped file: the first thing to look at after a build.
    inspection = look(from_glb(glb_path), spec.asset_id, out_dir / "look" / f"{spec.asset_id}.png")

    return {
        "ok": not failed_checks(checks),
        "command": "generate",
        "asset_id": spec.asset_id,
        "generator": spec.generator,
        "outputs": {"glb": str(glb_path), "look": inspection["sheet"]},
        "look": inspection,
        "stats": stats,
        "roundtrip": roundtrip_stats,
        "checks": checks,
        "errors": [],
    }


execute("generate", handle)
