"""Report how much high-frequency detail a baked albedo actually carries.

A bake can look fine zoomed out and still be mush at arm's length. This decodes
the packed albedo from a glb and prints, over the largest solid patch it finds,
the mean absolute difference between neighbouring texels (fine grain) and the
spread over the whole patch (large-scale variation), both in 0..255 levels.

    python tools/texel_detail.py dungeon_cave_open
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

_OUT = Path(__file__).resolve().parents[1] / "assets" / "out"


def albedo_png(asset: str) -> bytes:
    blob = (_OUT / f"{asset}.glb").read_bytes()
    json_length = struct.unpack_from("<I", blob, 12)[0]
    gltf = json.loads(blob[20 : 20 + json_length])
    body = 20 + json_length + 8
    for image in gltf["images"]:
        if "albedo" not in image["name"]:
            continue
        view = gltf["bufferViews"][image["bufferView"]]
        start = body + view.get("byteOffset", 0)
        return blob[start : start + view["byteLength"]]
    raise SystemExit(f"{asset} has no baked albedo")


def decode(png: bytes) -> tuple[int, int, int, list[bytes]]:
    position = 8
    width = height = channels = 0
    pixels = b""
    while position < len(png):
        length = struct.unpack_from(">I", png, position)[0]
        kind = png[position + 4 : position + 8]
        data = png[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            width, height, _, colour = struct.unpack(">IIBB", data[:10])
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[colour]
        elif kind == b"IDAT":
            pixels += data
        elif kind == b"IEND":
            break
    raw = zlib.decompress(pixels)
    stride = width * channels
    rows: list[bytes] = []
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        line = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            corner = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 255
            elif filter_type == 2:
                line[index] = (line[index] + up) & 255
            elif filter_type == 3:
                line[index] = (line[index] + ((left + up) >> 1)) & 255
            elif filter_type == 4:
                predict_a = abs(up - corner)
                predict_b = abs(left - corner)
                predict_c = abs(left + up - 2 * corner)
                if predict_a <= predict_b and predict_a <= predict_c:
                    guess = up
                elif predict_b <= predict_c:
                    guess = left
                else:
                    guess = corner
                line[index] = (line[index] + guess) & 255
        previous = line
        rows.append(bytes(line))
    return width, height, channels, rows


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    asset = sys.argv[1]
    width, height, channels, rows = decode(albedo_png(asset))
    best: tuple[int, int, int] | None = None
    window = 128
    for y in range(0, height - window, window):
        for x in range(0, width - window, window):
            filled = sum(
                1
                for row in rows[y : y + window : 8]
                for index in range(x, x + window, 8)
                if row[index * channels] > 8
            )
            total = len(range(0, window, 8)) ** 2
            if filled == total and best is None:
                best = (x, y, filled)
    if best is None:
        raise SystemExit("no fully covered window found; atlas is very fragmented")
    x0, y0, _ = best
    values = [[rows[y][x * channels] for x in range(x0, x0 + window)] for y in range(y0, y0 + window)]
    flat = [value for row in values for value in row]
    steps = [
        abs(values[y][x] - values[y][x + 1]) for y in range(window) for x in range(window - 1)
    ]
    print(f"{asset} albedo {width}x{height}, patch at {x0},{y0}")
    print(f"  neighbour delta (grain): {sum(steps) / len(steps):.2f} levels")
    print(f"  patch spread (form):     {max(flat) - min(flat)} levels")


if __name__ == "__main__":
    main()
