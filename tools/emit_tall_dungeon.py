"""Append floor/rise/vault dungeon pieces and their Asset Lab specs.

Idempotent: running twice does not duplicate catalog entries or overwrite a
hand-edited spec that already exists.

    python tools/emit_tall_dungeon.py
"""

from __future__ import annotations

import json
from pathlib import Path

_MODULAR = Path(__file__).resolve().parents[2] / "Modular" / "catalogs" / "dungeon.json"
_SPECS = Path(__file__).resolve().parents[1] / "assets" / "specs"

_TOPO = ("open", "wall", "corner", "passage", "end")
_ROLES = ("floor", "rise", "vault")

_HORIZONTAL = {
    "open": (
        ("pos_x", "+x", "+z"),
        ("neg_x", "-x", "+z"),
        ("pos_z", "+z", "+x"),
        ("neg_z", "-z", "+x"),
    ),
    "wall": (
        ("pos_x", "+x", "+z"),
        ("neg_x", "-x", "+z"),
        ("pos_z", "+z", "+x"),
    ),
    "corner": (
        ("pos_x", "+x", "+z"),
        ("pos_z", "+z", "+x"),
    ),
    "passage": (
        ("pos_x", "+x", "+z"),
        ("neg_x", "-x", "+z"),
    ),
    "end": (("pos_x", "+x", "+z"),),
}

_KIND = {
    "open": "dungeon_open",
    "wall": "dungeon_wall",
    "corner": "dungeon_corner",
    "passage": "dungeon_passage",
    "end": "dungeon_end",
}

_SEEDS = {
    ("cave", "open", "floor"): 141,
    ("cave", "open", "rise"): 142,
    ("cave", "open", "vault"): 143,
    ("cave", "wall", "floor"): 147,
    ("cave", "wall", "rise"): 148,
    ("cave", "wall", "vault"): 149,
    ("cave", "corner", "floor"): 159,
    ("cave", "corner", "rise"): 160,
    ("cave", "corner", "vault"): 161,
    ("cave", "passage", "floor"): 161,
    ("cave", "passage", "rise"): 162,
    ("cave", "passage", "vault"): 163,
    ("cave", "end", "floor"): 167,
    ("cave", "end", "rise"): 168,
    ("cave", "end", "vault"): 169,
    ("room", "open", "floor"): 113,
    ("room", "open", "rise"): 114,
    ("room", "open", "vault"): 115,
    ("room", "wall", "floor"): 117,
    ("room", "wall", "rise"): 118,
    ("room", "wall", "vault"): 119,
    ("room", "corner", "floor"): 121,
    ("room", "corner", "rise"): 122,
    ("room", "corner", "vault"): 123,
    ("room", "passage", "floor"): 125,
    ("room", "passage", "rise"): 126,
    ("room", "passage", "vault"): 127,
    ("room", "end", "floor"): 129,
    ("room", "end", "rise"): 130,
    ("room", "end", "vault"): 131,
}


def _docks(topo: str, role: str) -> list[dict[str, object]]:
    docks = [
        {
            "id": name,
            "profile": "join",
            "cell": [0, 0, 0],
            "outward": outward,
            "along": along,
        }
        for name, outward, along in _HORIZONTAL[topo]
    ]
    up = "storey_void" if role in ("floor", "rise") else "storey"
    down = "storey_void" if role in ("vault", "rise") else "storey"
    docks.append(
        {"id": "up", "profile": up, "cell": [0, 0, 0], "outward": "+y", "along": "+x"}
    )
    docks.append(
        {"id": "down", "profile": down, "cell": [0, 0, 0], "outward": "-y", "along": "+x"}
    )
    return docks


def _piece(style: str, topo: str, role: str) -> dict[str, object]:
    ident = f"{style}_{topo}_{role}"
    return {
        "id": ident,
        "family": ident,
        "occupancy": [[0, 0, 0]],
        "docks": _docks(topo, role),
    }


def _spec(style: str, topo: str, role: str) -> dict[str, object]:
    cave = style == "cave"
    return {
        "spec_version": 1,
        "id": f"dungeon_{style}_{topo}_{role}",
        "generator": "hard_surface.kit_cell",
        "params": {
            "kind": _KIND[topo],
            "cell_xz": 5.0,
            "cell_y": 3.5,
            "wall_thickness": 0.5 if cave else 0.38,
            # Cave rise/vault slices sit over another rock slice, not a plinth.
            # A millimetre keeps the storey planes distinct without opening a
            # visible horizontal slot. Floor slices and dressed walls retain
            # the normal shiplap overlap.
            "overlap": 0.001 if cave and role in ("rise", "vault") else 0.02,
            "door_width": 1.2,
            "door_height": 2.15,
            "window_width": 0.7,
            "window_height": 0.9,
            "window_sill": 1.0,
            "roof_height": 0.85,
            "overhang": 0.18,
            "jetty": 0.0,
            "timber": False,
            "bevel_width": 0.0,
            "jagged": cave,
            "storey_role": role,
            "texture_resolution": 2048 if cave else 1024,
            "bake_samples": 12 if cave else 8,
            "seed": _SEEDS[(style, topo, role)],
        },
        "materials": {
            "structure": {
                "base_color": [0.18, 0.16, 0.135, 1.0]
                if cave
                else [0.105, 0.115, 0.105, 1.0],
                "roughness": 0.93 if cave else 0.94,
                "metallic": 0.0,
            },
            "trim": {
                "base_color": [0.225, 0.205, 0.175, 1.0]
                if cave
                else [0.035, 0.028, 0.02, 1.0],
                "roughness": 0.72 if cave else 0.9,
                "metallic": 0.0,
            },
        },
        "qa": {
            "max_triangles": 20000 if cave else 6000,
            "require_uvs": True,
            "require_manifold": True,
            "require_origin_at_base": False,
            "max_dimension_m": 6.0,
        },
    }


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _compact_piece(piece: dict[str, object]) -> str:
    return json.dumps(piece, indent=2).replace("\n", "\n    ")


def main() -> None:
    raw = _MODULAR.read_text(encoding="utf-8")
    catalog = json.loads(raw)
    if "storey_void" not in raw:
        raw = raw.replace(
            '      "id": "storey",\n      "width": 5.0,\n      "height": 5.0,\n'
            '      "thickness": 0.5,\n      "floor_y": 0.0\n    }\n  ],',
            '      "id": "storey",\n      "width": 5.0,\n      "height": 5.0,\n'
            '      "thickness": 0.5,\n      "floor_y": 0.0\n    },\n    {\n'
            '      "id": "storey_void",\n      "width": 5.0,\n      "height": 5.0,\n'
            '      "thickness": 0.5,\n      "floor_y": 0.0\n    }\n  ],',
            1,
        )
    have = {piece["id"] for piece in catalog["pieces"]}
    added: list[str] = []
    for style in ("room", "cave"):
        for topo in _TOPO:
            for role in _ROLES:
                piece = _piece(style, topo, role)
                if piece["id"] not in have:
                    added.append(_compact_piece(piece))
                    have.add(piece["id"])
                spec_path = _SPECS / f"dungeon_{style}_{topo}_{role}.json"
                if not spec_path.exists():
                    _write_json(spec_path, _spec(style, topo, role))
    if added:
        insertion = ",\n    ".join(added)
        marker = "        { \"id\": \"up\", \"profile\": \"storey\", \"cell\": [0, 1, 1], \"outward\": \"+y\", \"along\": \"+x\" }\n      ]\n    }\n  ]\n}\n"
        if marker not in raw:
            raise SystemExit("catalog tail marker moved; update emit_tall_dungeon.py")
        raw = raw.replace(
            marker,
            "        { \"id\": \"up\", \"profile\": \"storey\", \"cell\": [0, 1, 1], \"outward\": \"+y\", \"along\": \"+x\" }\n"
            f"      ]\n    }},\n    {insertion}\n  ]\n}}\n",
            1,
        )
        _MODULAR.write_text(raw, encoding="utf-8")
    json.loads(_MODULAR.read_text(encoding="utf-8"))
    print(f"catalog pieces added: {len(added)}; specs under {_SPECS}")


if __name__ == "__main__":
    main()
