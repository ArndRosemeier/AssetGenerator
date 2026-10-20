"""Resolve what to look at: a spec id (kit generators drawn straight from the generator,
others from their shipped .glb), a path to any .glb, or `kit:<name>` (assets/kits/<name>.json:
several assets placed together, their joints measured)."""

from __future__ import annotations

import importlib
from pathlib import Path

from assetview import from_asset, from_glb, look, write_png
from assetview.rigsheet import render_rig_sheet
from blender.lib.registry import KIT_GENERATORS, resolve_generator_module
from blender.lib.spec import SpecError, load_spec, lod_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = REPO_ROOT / "assets" / "specs"
KIT_DIR = REPO_ROOT / "assets" / "kits"


def look_target(target: str, out_dir: Path, from_shipped: bool) -> dict[str, object]:
    path = Path(target)
    if target.startswith("kit:") or (path.suffix == ".json" and path.parent.name == "kits"):
        return look_kit(target, out_dir, from_shipped)
    if path.suffix == ".glb":
        if not path.is_file():
            raise SpecError(f"No such .glb: {path}")
        report = look(from_glb(path), path.stem, out_dir / "look" / f"{path.stem}.png")
        report["asset_id"] = path.stem
        return report
    spec_path = path if path.is_file() else SPEC_DIR / f"{target.removesuffix('.json')}.json"
    base, _, level = target.removesuffix(".json").rpartition("_lod")
    if not spec_path.is_file() and base and level.isdigit() and (SPEC_DIR / f"{base}.json").is_file():
        spec_path = lod_spec(
            load_spec(SPEC_DIR / f"{base}.json"), int(level), out_dir / "lods" / f"{base}_lod{level}.json"
        ).source_path
    spec = load_spec(spec_path)
    asset = None
    if spec.generator in KIT_GENERATORS and not from_shipped:
        module = importlib.import_module(resolve_generator_module(spec.generator))
        asset = module.build(spec)
        model = from_asset(asset)
    else:
        glb = out_dir / spec.glb_name
        if not glb.is_file():
            raise SpecError(
                f"{glb} does not exist yet: run `python tools/ag.py generate {spec.asset_id}` first"
            )
        model = from_glb(glb)
    report = look(model, spec.asset_id, out_dir / "look" / f"{spec.asset_id}.png")
    report["asset_id"] = spec.asset_id
    if asset is not None and asset.skeleton is not None:
        report.update(look_rig(asset, spec.asset_id, out_dir))
    return report


def look_kit(target: str, out_dir: Path, from_shipped: bool) -> dict[str, object]:
    from assetview.kit import compose, joint_lines, joints, load_kit

    name = target.removeprefix("kit:").removesuffix(".json")
    path = Path(target) if not target.startswith("kit:") else KIT_DIR / f"{name}.json"
    name = path.stem
    if not path.is_file():
        known = sorted(p.stem for p in KIT_DIR.glob("*.json"))
        raise SpecError(f"No kit {path}; kits are {known}")
    placed = load_kit(path, SPEC_DIR, out_dir, from_shipped)
    report = look(compose(placed, name), f"kit {name}", out_dir / "look" / f"kit_{name}.png")
    found = joints(placed)
    report["asset_id"] = f"kit:{name}"
    report["joints"] = found
    report["summary"] = [*report["summary"], *joint_lines(found)]  # type: ignore[misc]
    return report


def look_rig(asset: object, asset_id: str, out_dir: Path) -> dict[str, object]:
    """The rig sheet of a rigged kit asset, and the lines it adds to the report."""
    image, clips, warnings = render_rig_sheet(asset, asset_id)  # type: ignore[arg-type]
    path = out_dir / "look" / f"{asset_id}_rig.png"
    write_png(path, image)
    lines = [f"rig: {len(asset.skeleton.bones)} bones, sheet {path.name}"]  # type: ignore[attr-defined]
    lines += [f"rig: {w}" for w in warnings]
    for c in clips:
        lines.append(
            f"clip {c['clip']}: {c['seconds']} s, " + ("; ".join(c["flags"]) if c["flags"] else "ok")
        )  # type: ignore[arg-type]
    return {"rig_sheet": str(path), "clips": clips, "rig_warnings": warnings, "rig_summary": lines}
