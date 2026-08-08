"""Refresh the human GLBs Character Studio loads.

Default: run the Asset Lab MPFB export (`tools/character_studio/blender_export_humans.py`)
through the Blender 4.2 vendored in the City checkout. That build carries the 28
face morphs *and* the fitted MakeHuman eyes.

Fallback: `--copy-from-city` copies City's already-exported GLBs. Those are
eyeless, so only use it when the vendored Blender/MPFB toolchain is unavailable.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITY = Path(os.environ.get("CITY_ROOT", str(ROOT.parent / "City")))
DEST = ROOT / "character_studio" / "assets" / "humans"

EXPORT_SCRIPT = ROOT / "tools" / "character_studio" / "blender_export_humans.py"
BLENDER = CITY / "tools" / "vendor" / "blender" / "blender-4.2.9-windows-x64" / "blender.exe"
MPFB_SRC = CITY / "tools" / "vendor" / "mpfb2_plugin" / "mpfb"

FILES = [
    ("assets/humans/male_base.glb", "male_base.glb"),
    ("assets/humans/female_base.glb", "female_base.glb"),
    ("assets/humans/outfits/male_casual_01.glb", "outfits/male_casual_01.glb"),
    ("assets/humans/outfits/female_casual_01.glb", "outfits/female_casual_01.glb"),
]


def export_from_mpfb(only: str | None) -> int:
    for required in (BLENDER, MPFB_SRC):
        if not required.exists():
            print(f"ERROR: missing {required}", file=sys.stderr)
            print(
                "Set CITY_ROOT to a City checkout with the vendored Blender/MPFB, "
                "or re-run with --copy-from-city for the eyeless GLBs.",
                file=sys.stderr,
            )
            return 2
    env = dict(os.environ)
    env["CITY_ROOT"] = str(CITY)
    if only:
        env["STUDIO_ONLY"] = only
    cmd = [str(BLENDER), "--background", "--python", str(EXPORT_SCRIPT)]
    print(f"exporting via {BLENDER}")
    result = subprocess.run(cmd, env=env, check=False)
    if result.returncode != 0:
        print(f"ERROR: Blender export failed (exit {result.returncode})", file=sys.stderr)
        return 1
    print(f"OK exported → {DEST}")
    return 0


def copy_from_city() -> int:
    if not CITY.is_dir():
        print(f"ERROR: City project not found at {CITY}", file=sys.stderr)
        return 2
    for src_rel, dst_rel in FILES:
        src = CITY / src_rel
        dst = DEST / dst_rel
        if not src.is_file():
            print(f"ERROR: missing {src}", file=sys.stderr)
            return 2
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"copied {dst_rel} ({dst.stat().st_size} bytes)")
    print(f"OK {len(FILES)} files → {DEST} (no eyes: City's export does not equip them)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--copy-from-city",
        action="store_true",
        help="copy City's exported GLBs instead of running the MPFB export (no eyes)",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated subset of export ids, e.g. male_base,female_base",
    )
    args = parser.parse_args()
    if args.copy_from_city:
        if args.only:
            print("ERROR: --only applies to the MPFB export, not --copy-from-city", file=sys.stderr)
            return 2
        return copy_from_city()
    return export_from_mpfb(args.only)


if __name__ == "__main__":
    raise SystemExit(main())
