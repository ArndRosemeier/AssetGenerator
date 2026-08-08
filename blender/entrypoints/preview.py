"""Render preview images of an exported .glb so the agent can look at the result."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections.abc import Mapping

from blender.lib.export import import_glb
from blender.lib.preview import render_previews
from blender.lib.qa import collect_stats
from blender.lib.report import Report
from blender.lib.runner import execute


def handle(payload: Mapping[str, object]) -> Report:
    glb_path = Path(str(payload["glb_path"]))
    out_dir = Path(str(payload["out_dir"]))
    asset_id = str(payload["asset_id"])
    resolution = int(str(payload["resolution"]))
    samples = int(str(payload["samples"]))

    objects = import_glb(glb_path)
    stats = collect_stats(objects)
    outputs = render_previews(objects, out_dir, asset_id, resolution, samples)

    return {
        "ok": True,
        "command": "preview",
        "asset_id": asset_id,
        "outputs": outputs,
        "stats": stats,
        "checks": [],
        "errors": [],
    }


execute("preview", handle)
