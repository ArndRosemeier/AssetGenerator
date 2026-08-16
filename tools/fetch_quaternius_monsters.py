#!/usr/bin/env python3
"""Vendor the Quaternius Ultimate Monsters pack (CC0) as .glb with one shared atlas.

The pack ships from a Google Drive folder as self-contained .gltf: every mesh, every
animation and a base64 copy of the 9 KB Atlas_Monsters.png inlined into the JSON text.
Each file is rewritten as binary .glb whose image points at one external atlas next
to the family folders.

If a sibling City checkout already has the converted pack, those files are copied
instead of hitting Drive.

    python tools/fetch_quaternius_monsters.py
    python tools/fetch_quaternius_monsters.py --from-city
    python tools/fetch_quaternius_monsters.py --from-drive
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "monsters" / "quaternius"
ATLAS_NAME = "Atlas_Monsters.png"
CITY_DEFAULT = Path(os.environ.get("CITY_ROOT", str(ROOT.parent / "City")))
CITY_PACK = CITY_DEFAULT / "assets" / "monsters" / "quaternius_monsters"

DRIVE_FOLDER = "18m4KpzpEzhC9wl7jzr6dUc0N8Jozr79C"
LICENSE_ID = "16GqsDGESyEOfRbc4dS7EqAwkIUSIW4_y"
ATLAS_ID = "1CtLGgAKj-6a6GGNVNQT7GRPM7uyo9Fj8"

# family -> model name -> Drive file id of the .gltf
MODELS: dict[str, dict[str, str]] = {
    "big": {
        "Alien": "1rWF4Jo_G7-odDa5LfkQ0e2d9_p9pxb3W",
        "Birb": "1x_TV2p9dZg6UKhEM-5484Wt_4Mw1zMGL",
        "BlueDemon": "1mcxtHj9Aw1uu1FWYhl1rfPenuq3My-Z4",
        "Bunny": "1wy1OR4I3CHbWqgD_JMrMkQiUABRGKQfO",
        "Cactoro": "19Po2Ae16TbImr6dCu7PRZdpPQhEA13OQ",
        "Demon": "1XhBLnR6tjqIrFy0AUfRlqKf-hYmVwIR4",
        "Dino": "1xBAObQmJQP1kCslielMmS_KMfPZUsdNm",
        "Fish": "1mQqf-c9O4u3bk2ycpt-DFraGfRjcVfZV",
        "Frog": "19QwNJOpMLNtw5jS2D6tOQQ48nPPk9VSI",
        "Monkroose": "1EhDGjdMRdNZA52otQt73a0x3VpiunwOP",
        "MushroomKing": "1sCGed1ce1CrdCdFz5bxVQMqphu5e3a1m",
        "Ninja": "1T45Ab6f3oX6m-r-kRqEOsmv0Yp9ySmDb",
        "Orc": "17675H4Owu5FeHUk_7Goyc9TKI5YK3cEM",
        "Orc_Skull": "13wbbztVj_2eYyF5lavumLvK9JyCfQEhI",
        "Tribal": "1hWEwACHKMfDzYbqG2Cum3KP6semUY_Ap",
        "Yeti": "1_skNq11VXoaGPu9D-hHb4-0OQXEWNTzY",
    },
    "blob": {
        "Alien": "1DY3eAtSljj-Iiww1Q2kWnj7t25L1Wx8F",
        "Birb": "1S3pQ-fJ3FLZjFNU2QvRI_o37dzu4LqS3",
        "Cactoro": "1zkRgEGD59pniSqIWt4ycEU4CR0wPop7u",
        "Cat": "1DaLGZYClS3GTBHVP3F6tF3mVjQ4-rTc-",
        "Chicken": "1IB0MLe3-z1oKSR2AxXBWWx5t9wzreRIe",
        "Dog": "1zLzeCmfxleaolUOPvAEDSWzWXSlKAnQe",
        "Fish": "1Fqsl3XXpkXb1w0Wxn5EikENpy-0O6bAr",
        "GreenBlob": "1Qj3EPCAzN7P3KNrfjV_sFMw98nsBUyob",
        "GreenSpikyBlob": "125zPNBLl1VAgzhfVom9Kj29hSClaZhjF",
        "Mushnub": "1bNqyLU2o3FbQueRyaHFuhxN_XEGosnwo",
        "Mushnub_Evolved": "1x86_FT5A-d7oVcCRuqczS7GB1t2GydyN",
        "Ninja": "1GXgJxRhROHmHAAcoDzIKkQgDmnLqglPf",
        "Orc": "154RnrgtkqQ_KgMhRS-Jiz7WeiSdcq4EQ",
        "Pigeon": "19-BdZiXRrGvgZFDusAxoksTWH1yqb9SP",
        "PinkBlob": "1KcjhxeBkIhsdm_lMKY-OcTmsKDQt3uoK",
        "Wizard": "1lkfBVrpoKi3JwrkJ3M_vwi7tQXG53RjV",
        "Yeti": "1VpqldMiSmrmoDtTqA5PqOZ0FrPIKKjiP",
    },
    "flying": {
        "Alpaking": "1GDlXgTJ8-eQyIsCPlhsQGHQ4yvtl_xtl",
        "Alpaking_Evolved": "11ns6AbnnC6WtC7zzrSPEWJkwQG_h0rQN",
        "Armabee": "1k7LbRse-00nyMQhTdJMvebPp8B-05hcG",
        "Armabee_Evolved": "196ay2r-nuDXcRiwYu84CoE7Qy_gBj8sB",
        "Demon": "1CLzKKcKfwGRyK4SM7w8Z0vxeH04HW4RQ",
        "Dragon": "1-mQSm6_oGt7-EEQfNj1dFWYgPQy4AdPC",
        "Dragon_Evolved": "1Mcfuavq7F4itG9xhqc-20_IL257ZY2_3",
        "Ghost": "1rUs1QRA9v1Y2wRYEXsfteBisTsz4JlLi",
        "Ghost_Skull": "1JIw8lx6H5IIhf_3Z5FprEu_yCoMcoRN7",
        "Glub": "1X-6f4qyrbloGVq3wf-IdxUgmuA0u1JGu",
        "Glub_Evolved": "1WyNv3hlbY4gIxzbm3sFyn8MzBORQHCIr",
        "Goleling": "1bVAbwxtJhLOBpuJNtl3XBbJhl4cDPdcL",
        "Goleling_Evolved": "1DXqke-QxMth9mq5eYiawcmJDACm4-jvL",
        "Hywirl": "1LJG8sJYUwdoF7zrzPbEO-Vt9Xt7MQCu-",
        "Pigeon": "1m5PJFA3ytir_ES3nPq0HC8UmCynHIzZY",
        "Squidle": "1VbcCYeqrlwYF6b64EY2S_e9hV0HXMr3O",
        "Tribal": "10vwCwj_WXcOG0PTC6l3yhaAN63DLyX9p",
    },
}

_UA = "AssetLabMonsterFetch/1.0 (+local asset lab; CC0 assets)"


def expected_glb_relpaths() -> list[str]:
    paths: list[str] = []
    for family, models in MODELS.items():
        for name in models:
            paths.append(f"{family}/{name}.glb")
    return paths


def city_pack_complete(src: Path) -> bool:
    if not (src / ATLAS_NAME).is_file():
        return False
    if not (src / "License.txt").is_file():
        return False
    for rel in expected_glb_relpaths():
        if not (src / rel).is_file():
            return False
    return True


def copy_from_city(src: Path) -> int:
    if not city_pack_complete(src):
        print(f"ERROR: City pack at {src} is missing files", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    atlas = src / ATLAS_NAME
    shutil.copy2(atlas, OUT / ATLAS_NAME)
    shutil.copy2(src / "License.txt", OUT / "License.txt")
    copied = 0
    for family, models in MODELS.items():
        dest_dir = OUT / family
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in models:
            rel = f"{family}/{name}.glb"
            shutil.copy2(src / rel, OUT / rel)
            copied += 1
            print(f"  copied {rel}")
    print(f"\n{copied} models copied from {src}")
    return 0


def drive_get(file_id: str) -> bytes:
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data: bytes = resp.read()
    if data[:15].lstrip().lower().startswith(b"<!doctype html") or data[:5] == b"<html":
        raise RuntimeError(f"Drive returned an HTML page for {file_id}, not the file")
    return data


def _align4(n: int) -> int:
    return (n + 3) & ~3


def gltf_to_glb(text: bytes, atlas_uri: str) -> tuple[bytes, int]:
    """Rewrite a self-contained .gltf as .glb whose sole image is `atlas_uri`."""
    doc = json.loads(text)

    blobs: list[bytes] = []
    for buf in doc.get("buffers", []):
        uri = buf.get("uri")
        if uri is None:
            raise RuntimeError("buffer without uri — file is already binary")
        if not uri.startswith("data:"):
            raise RuntimeError(f"buffer points at an external file: {uri}")
        blob = base64.b64decode(uri.split(",", 1)[1])
        if len(blob) != int(buf["byteLength"]):
            raise RuntimeError("buffer byteLength disagrees with its data URI")
        blobs.append(blob)

    images: list[dict] = doc.get("images", [])
    dropped: set[int] = set()
    for image in images:
        if "bufferView" not in image:
            raise RuntimeError("image is not a bufferView — atlas layout changed")
        dropped.add(int(image["bufferView"]))
        image.pop("bufferView", None)
        image.pop("mimeType", None)
        image["uri"] = atlas_uri

    views: list[dict] = doc.get("bufferViews", [])
    remap: dict[int, int] = {}
    kept: list[dict] = []
    binary = bytearray()
    for index, view in enumerate(views):
        if index in dropped:
            continue
        blob = blobs[int(view.get("buffer", 0))]
        start = int(view.get("byteOffset", 0))
        length = int(view["byteLength"])
        binary.extend(b"\x00" * (_align4(len(binary)) - len(binary)))
        view["byteOffset"] = len(binary)
        view["buffer"] = 0
        binary.extend(blob[start : start + length])
        remap[index] = len(kept)
        kept.append(view)
    binary.extend(b"\x00" * (_align4(len(binary)) - len(binary)))

    for accessor in doc.get("accessors", []):
        if "bufferView" in accessor:
            accessor["bufferView"] = remap[int(accessor["bufferView"])]
        sparse = accessor.get("sparse")
        if sparse is not None:
            raise RuntimeError("sparse accessor — bufferView remap would be incomplete")
    doc["bufferViews"] = kept
    doc["buffers"] = [{"byteLength": len(binary)}]

    json_chunk = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (_align4(len(json_chunk)) - len(json_chunk))

    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    out = bytearray()
    out.extend(struct.pack("<III", 0x46546C67, 2, total))
    out.extend(struct.pack("<II", len(json_chunk), 0x4E4F534A))
    out.extend(json_chunk)
    out.extend(struct.pack("<II", len(binary), 0x004E4942))
    out.extend(binary)
    return bytes(out), len(dropped)


def fetch_from_drive() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    atlas_path = OUT / ATLAS_NAME
    print(f"GET {ATLAS_NAME}")
    atlas = drive_get(ATLAS_ID)
    atlas_path.write_bytes(atlas)
    print(f"  -> {atlas_path.relative_to(ROOT)} ({len(atlas)} bytes)")

    print("GET License.txt")
    (OUT / "License.txt").write_bytes(drive_get(LICENSE_ID))

    raw_total = 0
    glb_total = 0
    failures: list[str] = []
    for family, models in MODELS.items():
        family_dir = OUT / family
        family_dir.mkdir(parents=True, exist_ok=True)
        for name, file_id in sorted(models.items()):
            dest = family_dir / f"{name}.glb"
            try:
                raw = drive_get(file_id)
                glb, images = gltf_to_glb(raw, f"../{ATLAS_NAME}")
            except (urllib.error.URLError, RuntimeError, ValueError) as exc:
                failures.append(f"{family}/{name}: {exc}")
                print(f"FAILED {family}/{name}: {exc}", file=sys.stderr)
                continue
            dest.write_bytes(glb)
            raw_total += len(raw)
            glb_total += len(glb)
            print(
                f"  {family}/{name}.glb  {len(raw) / 1024:.0f} KiB gltf"
                f" -> {len(glb) / 1024:.0f} KiB glb  ({images} atlas copy dropped)"
            )

    expected = len(MODELS["big"]) + len(MODELS["blob"]) + len(MODELS["flying"])
    print(
        f"\n{expected - len(failures)} models: {raw_total / 1048576:.1f} MiB of .gltf ->"
        f" {glb_total / 1048576:.1f} MiB of .glb + {len(atlas) / 1024:.0f} KiB atlas"
    )
    if failures:
        print(f"{len(failures)} download(s) failed", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--from-city",
        action="store_true",
        help="copy the converted pack from CITY_ROOT (required; no Drive fallback)",
    )
    source.add_argument(
        "--from-drive",
        action="store_true",
        help="download from the author's Drive folder even if City is present",
    )
    args = parser.parse_args()

    if args.from_city:
        if not city_pack_complete(CITY_PACK):
            print(
                f"ERROR: --from-city requested but pack is incomplete at {CITY_PACK}",
                file=sys.stderr,
            )
            print("Set CITY_ROOT to a City checkout that already fetched the pack.", file=sys.stderr)
            return 2
        print(f"copying from {CITY_PACK}")
        return copy_from_city(CITY_PACK)

    if args.from_drive:
        return fetch_from_drive()

    if city_pack_complete(CITY_PACK):
        print(f"City pack present at {CITY_PACK}; copying (pass --from-drive to re-download)")
        return copy_from_city(CITY_PACK)
    return fetch_from_drive()


if __name__ == "__main__":
    raise SystemExit(main())
