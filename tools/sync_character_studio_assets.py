"""Build the modular human assets Character Studio loads.

Runs the Asset Lab MPFB export (`tools/character_studio/blender_export_humans.py`)
through the Blender 4.2 vendored in the City checkout. One pass produces the nude
and dressed bases per sex, one GLB per wardrobe garment, and `wardrobe.json`.

There is no copy-from-City fallback: City only ships monolithic eyeless outfits,
which cannot drive the modular editor.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITY = Path(os.environ.get("CITY_ROOT", str(ROOT.parent / "City")))
DEST = ROOT / "character_studio" / "assets" / "humans"

EXPORT_SCRIPT = ROOT / "tools" / "character_studio" / "blender_export_humans.py"
BLENDER = CITY / "tools" / "vendor" / "blender" / "blender-4.2.9-windows-x64" / "blender.exe"
MPFB_SRC = CITY / "tools" / "vendor" / "mpfb2_plugin" / "mpfb"


def export_from_mpfb(only: str | None) -> int:
    for required in (BLENDER, MPFB_SRC):
        if not required.exists():
            print(f"ERROR: missing {required}", file=sys.stderr)
            print(
                "Set CITY_ROOT to a City checkout with the vendored Blender/MPFB.",
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
    print(f"OK exported to {DEST}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated subset of export ids, e.g. male_base,male_shoes01",
    )
    args = parser.parse_args()
    return export_from_mpfb(args.only)


if __name__ == "__main__":
    raise SystemExit(main())
