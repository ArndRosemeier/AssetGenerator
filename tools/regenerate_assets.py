"""Clone-and-go: verify host tools, ensure Blender, then rebuild every asset.

    python tools/regenerate_assets.py

This is the one command a fresh checkout needs. It:

1. Verifies Python and other host prerequisites (with install hints)
2. Locates or downloads the pinned headless Blender (same as bootstrap.py)
3. Runs the smoke test
4. Regenerates every JSON spec under assets/specs/ into assets/out/

Options mirror `python tools/ag.py regenerate`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.ag import DEFAULT_RESOLUTION, DEFAULT_SAMPLES, cmd_regenerate
from tools.blenderctl import BlenderError
from tools.bootstrap import ensure_blender
from tools.prereqs import PrereqError, require_prereqs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="regenerate_assets",
        description="Verify prerequisites, bootstrap Blender if needed, regenerate all assets.",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON reports")
    parser.add_argument("--no-preview", action="store_true", help="skip preview renders")
    parser.add_argument("--no-smoke", action="store_true", help="skip the bootstrap smoke test")
    parser.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="do not install/locate Blender; fail if it is missing",
    )
    parser.add_argument(
        "--skip-prereqs",
        action="store_true",
        help="skip host prerequisite checks (not recommended)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print("=== regenerate assets ===")

    if not args.skip_prereqs:
        try:
            require_prereqs(for_bootstrap=not args.skip_bootstrap)
        except PrereqError as exc:
            print(f"\nerror: {exc}", file=sys.stderr)
            return 2
        print()
    else:
        print("Skipping prerequisite checks (--skip-prereqs).")

    if not args.skip_bootstrap:
        try:
            ensure_blender(smoke=not args.no_smoke)
        except BlenderError as exc:
            print(f"\nerror: {exc}", file=sys.stderr)
            print(
                "Hint: fix network/disk issues from the prerequisite report, "
                "or install Blender and set BLENDER_BIN.",
                file=sys.stderr,
            )
            return 2
    else:
        print("Skipping bootstrap (--skip-bootstrap).")

    return int(cmd_regenerate(args))


if __name__ == "__main__":
    raise SystemExit(main())
