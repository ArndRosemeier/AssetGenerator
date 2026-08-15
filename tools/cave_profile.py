"""Print the walk-height profile of a baked cave tile straight from its glb.

Reads the exported mesh (glTF is Y-up) and reports, per plan cell, the lowest
rock above head height and the highest rock below it: the ceiling the player
sees and the floor they stand on. Flat rows here mean a flat cave.

    python tools/cave_profile.py dungeon_cave_open
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

_OUT = Path(__file__).resolve().parents[1] / "assets" / "out"


def positions(path: Path) -> list[tuple[float, float, float]]:
    blob = path.read_bytes()
    json_length = struct.unpack_from("<I", blob, 12)[0]
    gltf = json.loads(blob[20 : 20 + json_length])
    body = 20 + json_length + 8
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    start = body + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [struct.unpack_from("<3f", blob, start + 12 * index) for index in range(accessor["count"])]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    asset = sys.argv[1]
    points = positions(_OUT / f"{asset}.glb")
    steps = [index * 0.5 - 2.0 for index in range(9)]
    print(f"{asset}: {len(points)} verts")
    for label, pick in (("ceiling", min), ("floor", max)):
        print(f"-- {label} (rows are z, columns x, metres)")
        seen: list[float] = []
        for z in steps:
            row = []
            for x in steps:
                near = [
                    y
                    for px, y, pz in points
                    if abs(px - x) < 0.26 and abs(pz - z) < 0.26 and (y > 1.0) == (label == "ceiling")
                ]
                if near:
                    seen.append(pick(near))
                row.append(f"{pick(near):5.2f}" if near else "  -- ")
            print(f"z={z:5.1f} " + " ".join(row))
        spread = max(seen) - min(seen)
        print(f"   range {min(seen):.2f}..{max(seen):.2f} m (spread {spread:.2f})")


if __name__ == "__main__":
    main()
