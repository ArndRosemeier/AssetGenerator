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

from blender.lib.report import format_report
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
from tools.prereqs import PrereqError, require_prereqs

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


def ensure_blender(*, smoke: bool = True) -> BlenderInstall:
    """Locate or install Blender, record its path, optionally run the smoke test."""
    install = acquire_blender()
    record_blender_path(install)
    print(f"Using Blender {install.version_str}: {install.executable}")

    if not smoke:
        return install

    print("\nRunning pipeline smoke test (build -> export glb -> reimport)")
    result = run_entrypoint(install, "smoke", {"out_dir": str(SMOKE_DIR)})
    report: Report = result.report  # type: ignore[assignment]
    print(format_report(report))
    if not report.get("ok"):
        raise BlenderError("Bootstrap smoke test failed. See report above.")
    return install


def main() -> int:
    print("=== Blender Asset Lab bootstrap ===")
    try:
        require_prereqs(for_bootstrap=True)
        print()
        ensure_blender(smoke=True)
    except PrereqError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 2
    except BlenderError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    print("\nBootstrap complete. Next:")
    print("  python tools/regenerate_assets.py")
    print("  # or: python tools/ag.py generate crate_small")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
