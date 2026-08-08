"""One-command setup.

    python tools/bootstrap.py

Finds a usable Blender or downloads the pinned portable build into the repo,
verifies its checksum, records the path and proves the whole pipeline works by
building, exporting and reimporting a cube. Nothing is installed system-wide and
no Blender UI is ever opened.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blender.lib.report import Report, format_report
from tools.blenderctl import (
    BLENDER_SERIES,
    BLENDER_VERSION,
    BlenderError,
    BlenderInstall,
    find_blender,
    install_pinned_blender,
    record_blender_path,
    run_entrypoint,
)

SMOKE_DIR = Path(__file__).resolve().parent.parent / "assets" / "out" / "_smoke"


def acquire_blender() -> BlenderInstall:
    existing = find_blender()
    if existing is None:
        print(f"No Blender found. Installing pinned Blender {BLENDER_VERSION} (~400 MB download).")
        return install_pinned_blender()

    print(f"Found Blender {existing.version_str} at {existing.executable} (via {existing.source})")
    if existing.series != BLENDER_SERIES and existing.source not in {"BLENDER_BIN", "managed install"}:
        print(
            f"That is not the pinned series {BLENDER_SERIES}. Installing the pinned build "
            f"for reproducible results. Set BLENDER_BIN to override."
        )
        return install_pinned_blender()
    return existing


def main() -> int:
    print("=== Blender Asset Lab bootstrap ===")
    try:
        install = acquire_blender()
    except BlenderError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 2

    record_blender_path(install)
    print(f"Using Blender {install.version_str}: {install.executable}")

    print("\nRunning pipeline smoke test (build -> export glb -> reimport)")
    result = run_entrypoint(install, "smoke", {"out_dir": str(SMOKE_DIR)})
    report: Report = result.report  # type: ignore[assignment]
    print(format_report(report))

    if not report.get("ok"):
        print("\nBootstrap FAILED. The report above shows which stage broke.", file=sys.stderr)
        return 1

    print("\nBootstrap complete. Next:")
    print("  python tools/ag.py doctor")
    print("  python tools/ag.py generate crate_small")
    print("  then look at assets/out/previews/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
