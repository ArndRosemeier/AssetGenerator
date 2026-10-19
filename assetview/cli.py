"""Resolve what to look at: a spec id (kit generators drawn straight from the generator,
others from their shipped .glb) or a path to any .glb."""

from __future__ import annotations

import importlib
from pathlib import Path

from assetview import from_asset, from_glb, look
from blender.lib.registry import KIT_GENERATORS, resolve_generator_module
from blender.lib.spec import SpecError, load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = REPO_ROOT / "assets" / "specs"


def look_target(target: str, out_dir: Path, from_shipped: bool) -> dict[str, object]:
    path = Path(target)
    if path.suffix == ".glb":
        if not path.is_file():
            raise SpecError(f"No such .glb: {path}")
        report = look(from_glb(path), path.stem, out_dir / "look" / f"{path.stem}.png")
        report["asset_id"] = path.stem
        return report
    spec_path = path if path.is_file() else SPEC_DIR / f"{target.removesuffix('.json')}.json"
    spec = load_spec(spec_path)
    if spec.generator in KIT_GENERATORS and not from_shipped:
        module = importlib.import_module(resolve_generator_module(spec.generator))
        model = from_asset(module.build(spec))
    else:
        glb = out_dir / spec.glb_name
        if not glb.is_file():
            raise SpecError(
                f"{glb} does not exist yet: run `python tools/ag.py generate {spec.asset_id}` first"
            )
        model = from_glb(glb)
    report = look(model, spec.asset_id, out_dir / "look" / f"{spec.asset_id}.png")
    report["asset_id"] = spec.asset_id
    return report
