"""Read a .glb file's JSON and binary chunks, and its accessors, without Blender.

Stdlib-only: the CLI tools read shipped files with it, and so does code inside Blender.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

_COMPONENTS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Glb:
    def __init__(self, path: Path) -> None:
        data = path.read_bytes()
        magic, _, _ = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF":
            raise ValueError(f"{path} is not a .glb file")
        json_size = struct.unpack_from("<I", data, 12)[0]
        self.doc: dict = json.loads(data[20 : 20 + json_size])
        self.binary = data[28 + json_size :]

    def values(self, accessor_index: int) -> list[tuple[float, ...]]:
        """An accessor's elements as tuples (a scalar is a 1-tuple)."""
        acc = self.doc["accessors"][accessor_index]
        view = self.doc["bufferViews"][acc["bufferView"]]
        fmt = _COMPONENTS[acc["componentType"]]
        n = _WIDTHS[acc["type"]]
        size = struct.calcsize(f"<{fmt}")
        stride = view.get("byteStride", size * n)
        at = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        return [struct.unpack_from(f"<{n}{fmt}", self.binary, at + stride * k) for k in range(acc["count"])]
