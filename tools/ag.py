"""Asset Lab CLI - the single interface between Cursor and headless Blender.

    python tools/ag.py doctor
    python tools/ag.py generate crate_small
    python tools/ag.py preview crate_small
    python tools/ag.py validate crate_small

Stdlib-only, so it runs with any Python 3.11+ and needs no virtualenv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blender.lib.registry import GENERATORS, UnknownGeneratorError, resolve_generator_module
from blender.lib.report import Report, format_report
from blender.lib.spec import AssetSpec, SpecError, load_spec
from tools.blenderctl import (
    BLENDER_VERSION,
    BlenderError,
    BlenderInstall,
    RunResult,
    find_blender,
    require_blender,
    run_entrypoint,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SPEC_DIR: Final[Path] = REPO_ROOT / "assets" / "specs"
OUT_DIR: Final[Path] = REPO_ROOT / "assets" / "out"

DEFAULT_RESOLUTION: Final[int] = 640
DEFAULT_SAMPLES: Final[int] = 48


def resolve_spec_path(reference: str) -> Path:
    """Accept a spec id, a bare filename or a path."""
    candidate = Path(reference)
    if candidate.is_file():
        return candidate.resolve()
    for guess in (SPEC_DIR / reference, SPEC_DIR / f"{reference}.json"):
        if guess.is_file():
            return guess.resolve()
    available = sorted(path.stem for path in SPEC_DIR.glob("*.json"))
    raise SpecError(f"No spec matches '{reference}'. Available specs: {available}")


def load_and_check_spec(reference: str) -> AssetSpec:
    spec = load_spec(resolve_spec_path(reference))
    resolve_generator_module(spec.generator)
    return spec


def _emit(result: RunResult, as_json: bool) -> int:
    report: Report = result.report  # type: ignore[assignment]
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0 if report.get("ok") else 1


def _run_preview(
    install: BlenderInstall,
    asset_id: str,
    glb_path: Path,
    resolution: int,
    samples: int,
) -> RunResult:
    return run_entrypoint(
        install,
        "preview",
        {
            "glb_path": str(glb_path),
            "out_dir": str(OUT_DIR / "previews"),
            "asset_id": asset_id,
            "resolution": resolution,
            "samples": samples,
        },
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"repo root      : {REPO_ROOT}")
    print(f"pinned Blender : {BLENDER_VERSION}")
    install = find_blender()
    if install is None:
        print("blender        : NOT FOUND")
        print("\nRun `python tools/bootstrap.py` to install it.")
        return 1
    print(f"blender        : {install.executable}")
    print(f"version        : {install.version_str}  (found via {install.source})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    probe = OUT_DIR / ".write-probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    print(f"output dir     : {OUT_DIR} (writable)")

    specs = sorted(path.stem for path in SPEC_DIR.glob("*.json"))
    print(f"generators     : {sorted(GENERATORS)}")
    print(f"specs          : {specs}")
    return 0


def cmd_generators(args: argparse.Namespace) -> int:
    for name, module in sorted(GENERATORS.items()):
        print(f"{name}  ->  {module}")
    return 0


def cmd_specs(args: argparse.Namespace) -> int:
    for path in sorted(SPEC_DIR.glob("*.json")):
        spec = load_spec(path)
        print(f"{spec.asset_id:24s} {spec.generator:22s} {path}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    spec = load_and_check_spec(args.spec)
    install = require_blender()

    result = run_entrypoint(
        install,
        "generate",
        {"spec_path": str(spec.source_path), "out_dir": str(OUT_DIR)},
    )
    status = _emit(result, args.json)
    if status != 0 or args.no_preview:
        return status

    glb_path = OUT_DIR / spec.glb_name
    preview_result = _run_preview(install, spec.asset_id, glb_path, args.resolution, args.samples)
    return _emit(preview_result, args.json)


def cmd_preview(args: argparse.Namespace) -> int:
    install = require_blender()
    reference = Path(args.target)
    if reference.suffix.lower() == ".glb":
        glb_path = reference.resolve()
        asset_id = glb_path.stem
    else:
        spec = load_and_check_spec(args.target)
        glb_path = OUT_DIR / spec.glb_name
        asset_id = spec.asset_id
    if not glb_path.is_file():
        raise BlenderError(f"{glb_path} does not exist. Run `generate` first.")
    return _emit(_run_preview(install, asset_id, glb_path, args.resolution, args.samples), args.json)


def cmd_validate(args: argparse.Namespace) -> int:
    spec = load_and_check_spec(args.spec)
    install = require_blender()
    glb_path = OUT_DIR / spec.glb_name
    if not glb_path.is_file():
        raise BlenderError(f"{glb_path} does not exist. Run `generate` first.")
    result = run_entrypoint(
        install,
        "validate",
        {"glb_path": str(glb_path), "spec_path": str(spec.source_path)},
    )
    return _emit(result, args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ag", description="Blender Asset Lab")
    parser.add_argument("--json", action="store_true", help="print the raw JSON report")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="check the toolchain").set_defaults(func=cmd_doctor)
    subparsers.add_parser("generators", help="list registered generators").set_defaults(func=cmd_generators)
    subparsers.add_parser("specs", help="list available specs").set_defaults(func=cmd_specs)

    generate = subparsers.add_parser("generate", help="build, QA and export an asset")
    generate.add_argument("spec", help="spec id or path")
    generate.add_argument("--no-preview", action="store_true", help="skip preview renders")
    generate.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION)
    generate.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    generate.set_defaults(func=cmd_generate)

    preview = subparsers.add_parser("preview", help="render preview images of an exported glb")
    preview.add_argument("target", help="spec id or path to a .glb")
    preview.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION)
    preview.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    preview.set_defaults(func=cmd_preview)

    validate = subparsers.add_parser("validate", help="re-check an exported glb against its spec")
    validate.add_argument("spec", help="spec id or path")
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (SpecError, BlenderError, UnknownGeneratorError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
