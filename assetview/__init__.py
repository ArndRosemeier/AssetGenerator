"""Look at an asset without Blender: a nine-view inspection sheet and its measurements.

The agent's eyes. `ag.py look <id>` (and every `generate`) writes
assets/out/look/<id>.png and prints the measurements: size, parts, floating
pieces, holes, inside-out parts, whether it stands. A kit asset is drawn straight
from the generator in about a second; any other asset from its shipped .glb.

Needs numpy (Blender's own Python has it). See docs/ASSETKIT.md.
"""

from __future__ import annotations

from pathlib import Path

from assetview.measure import measure, summary
from assetview.model import ViewModel, from_asset, from_glb
from assetview.sheet import render_sheet, write_png

__all__ = ["ViewModel", "from_asset", "from_glb", "look", "measure", "render_sheet", "summary", "write_png"]


def look(model: ViewModel, title: str, out: Path) -> dict[str, object]:
    """Write the sheet for `model` to `out` and return its measurements (with `sheet` and `summary`)."""
    image, report = render_sheet(model, title)
    write_png(out, image)
    report["sheet"] = str(out)
    report["summary"] = summary(report)
    return report
