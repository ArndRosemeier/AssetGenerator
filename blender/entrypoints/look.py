"""Draw an asset's inspection sheet in Blender's Python, for a CLI Python without numpy.

Same result as `ag.py look` run directly: assetview needs numpy, not Blender.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections.abc import Mapping

from assetview.cli import look_target
from blender.lib.report import Report
from blender.lib.runner import execute


def handle(payload: Mapping[str, object]) -> Report:
    report = look_target(str(payload["target"]), Path(str(payload["out_dir"])), bool(payload["glb"]))
    return {
        "ok": True,
        "command": "look",
        "asset_id": report["asset_id"],
        "look": report,
        "checks": [],
        "errors": [],
    }


execute("look", handle)
