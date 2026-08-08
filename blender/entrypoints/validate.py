"""Re-open an exported .glb and run the QA gates against what is actually in the file."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections.abc import Mapping

from blender.lib.export import import_glb
from blender.lib.qa import collect_stats, run_checks
from blender.lib.report import Report, failed_checks
from blender.lib.runner import execute
from blender.lib.spec import load_spec


def handle(payload: Mapping[str, object]) -> Report:
    glb_path = Path(str(payload["glb_path"]))
    spec_path = Path(str(payload["spec_path"]))

    spec = load_spec(spec_path)
    objects = import_glb(glb_path)
    stats = collect_stats(objects)
    checks = run_checks(objects, spec.qa, stats, topology=False)

    return {
        "ok": not failed_checks(checks),
        "command": "validate",
        "asset_id": spec.asset_id,
        "generator": spec.generator,
        "outputs": {"glb": str(glb_path)},
        "stats": stats,
        "checks": checks,
        "errors": [],
    }


execute("validate", handle)
