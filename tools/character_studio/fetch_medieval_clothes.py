"""Download free medieval MakeHuman clothes into Asset Lab's extra asset tree.

Sources:
  - MakeHuman Suits 02 pack (CC0): monk robes + viking tunic/pants/boots
  - Individual community assets (CC0 / one CC-BY dress)

Does not touch the City checkout. Run before sync_character_studio_assets.py.
"""
from __future__ import annotations

import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXTRA_ROOT = SCRIPT_DIR / "makehuman_extra_assets"
CLOTHES_DIR = EXTRA_ROOT / "clothes"
CACHE_DIR = SCRIPT_DIR / ".mh_download_cache"
LICENSE_PATH = EXTRA_ROOT / "LICENSES.json"
UA = {"User-Agent": "AssetLabClothesFetch/1.0"}

SUITS02_URL = "https://files2.makehumancommunity.org/asset_packs/suits02/suits02_cc0.zip"

# Medieval / early-medieval garments from Suits 02 (folder name inside clothes/).
SUITS02_KEEP: dict[str, dict[str, str]] = {
    "donitz_monk_robe": {"label": "Monk Robe", "license": "CC0", "author": "Donitz"},
    "donitz_monk_robe_hood": {"label": "Monk Hood", "license": "CC0", "author": "Donitz"},
    "donitz_monk_robe_hood_down": {
        "label": "Monk Hood Down",
        "license": "CC0",
        "author": "Donitz",
    },
    "donitz_monk_robe_hood_off": {
        "label": "Monk Robe (Hood Off)",
        "license": "CC0",
        "author": "Donitz",
    },
    "rehmanpolanski_viking_tunic": {
        "label": "Viking Tunic",
        "license": "CC0",
        "author": "RehmanPolanski",
    },
    "rehmanpolanski_viking_pants": {
        "label": "Viking Pants",
        "license": "CC0",
        "author": "RehmanPolanski",
    },
    "rehmanpolanski_viking_boots": {
        "label": "Viking Boots",
        "license": "CC0",
        "author": "RehmanPolanski",
    },
}

# Individual community assets: folder_name -> (license record, list of (url, filename)).
COMMUNITY_ASSETS: dict[str, tuple[dict[str, str], list[tuple[str, str]]]] = {
    "monks_robe": (
        {
            "label": "Monk Robe",
            "license": "CC0",
            "author": "Donitz",
            "source": "http://www.makehumancommunity.org/clothes/monks_robe.html",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/7666/1121851965/Monks_Robe.mhclo",
                "Monks_Robe.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/7666/1106623466/Monks_Robe.obj",
                "Monks_Robe.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/7666/1676078551/monks_robe_brown.mhmat",
                "monks_robe_brown.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/7666/1470724182/robe_brown__diffuse.png",
                "robe_brown__diffuse.png",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/7666/1454128992/robe__normal_gl.png",
                "robe__normal_gl.png",
            ),
        ],
    ),
    "bootsviking": (
        {
            "label": "Viking Boots",
            "license": "CC0",
            "author": "RehmanPolanski",
            "source": "http://www.makehumancommunity.org/clothes/boots_viking.html",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/1542234753/bootsviking.mhclo",
                "bootsviking.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/319065469/bootsviking.obj",
                "bootsviking.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/482421134/bootsviking.mhmat",
                "bootsviking.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/1105980119/BootsViking.png",
                "BootsViking.png",
            ),
        ],
    ),
    "germanic_clothes": (
        {
            "label": "Germanic Clothes",
            "license": "CC0",
            "author": "Aethelraed_Unraed",
            "source": "http://www.makehumancommunity.org/clothes/germanicviking_clothes.html",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/2035606544/germanic_clothes.mhclo",
                "germanic_clothes.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/537201401/germanic_clothes.obj",
                "germanic_clothes.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/903001708/germanic_clothes.mhmat",
                "germanic_clothes.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/175086343/green.png",
                "green.png",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/1649098475/germanic_clothes_glossy.png",
                "germanic_clothes_glossy.png",
            ),
        ],
    ),
    "viking_dress": (
        {
            "label": "Viking Dress",
            "license": "CC0",
            "author": "Aethelraed_Unraed",
            "source": "http://www.makehumancommunity.org/clothes/viking_dress.html",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/797713854/Viking_dress.mhclo",
                "Viking_dress.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/1840030281/_dress_fitting.obj",
                "_dress_fitting.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/1032171695/_dress_fitting.mhmat",
                "_dress_fitting.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/937290788/diffuse.png",
                "diffuse.png",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/1064951734/normals.png",
                "normals.png",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/995/43217268/glossy.png",
                "glossy.png",
            ),
        ],
    ),
    "tunicviking": (
        {
            "label": "Viking Tunic (Armored)",
            "license": "CC0",
            "author": "MakeHuman Community",
            "source": "http://www.makehumancommunity.org/clothes/tunic_viking.html",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/473817296/tunicviking.mhclo",
                "tunicviking.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/1307877393/tunicviking.obj",
                "tunicviking.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/1514954693/tunicviking.mhmat",
                "tunicviking.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/2014318799/TUNIC_Viking.png",
                "TUNIC_Viking.png",
            ),
        ],
    ),
    "pantsviking": (
        {
            "label": "Viking Pants (Leather)",
            "license": "CC0",
            "author": "MakeHuman Community",
            "source": "http://www.makehumancommunity.org/clothes/pants_viking.html",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/1863088465/pantsviking.mhclo",
                "pantsviking.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/79332797/pantsviking.obj",
                "pantsviking.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/411945089/pantsviking.mhmat",
                "pantsviking.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/536/568121941/PantsViking.png",
                "PantsViking.png",
            ),
        ],
    ),
    "medievaldress": (
        {
            "label": "Medieval Dress",
            "license": "CC-BY",
            "author": "MakeHuman Community",
            "source": "http://www.makehumancommunity.org/clothes/medieval_dress_nonhistorical.html",
            "attribution": "Medieval Dress (non-historical) — CC-BY, MakeHuman Community",
        },
        [
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/1665/1200585968/medievaldress.mhclo",
                "medievaldress.mhclo",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/1665/1721449458/medievaldress.obj",
                "medievaldress.obj",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/1665/25446783/medievaldress.mhmat",
                "medievaldress.mhmat",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/1665/1006303013/medievaldress.png",
                "medievaldress.png",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/1665/2026433907/medievaldress_norm.png",
                "medievaldress_norm.png",
            ),
            (
                "http://www.makehumancommunity.org/sites/default/files/clothes/1665/1803667310/clothsim.png",
                "clothsim.png",
            ),
        ],
    ),
}


def download(url: str, dest: Path, *, min_bytes: int = 1) -> None:
    """Stream to disk (large packs must not be buffered in RAM)."""
    if dest.exists() and dest.stat().st_size >= min_bytes:
        print(f"  skip {dest.name} ({dest.stat().st_size} bytes)", flush=True)
        return
    print(f"  GET {url}", flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 1024)
    tmp.replace(dest)
    print(f"  wrote {dest} ({dest.stat().st_size} bytes)", flush=True)


def extract_suits02(zip_path: Path) -> list[str]:
    """Extract only the medieval Suits 02 folders into CLOTHES_DIR."""
    installed: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = Path(info.filename.replace("\\", "/")).parts
            if "clothes" not in parts:
                continue
            idx = parts.index("clothes")
            rel = Path(*parts[idx + 1 :])
            if not rel.parts:
                continue
            asset = rel.parts[0]
            if asset not in SUITS02_KEEP:
                continue
            dest = CLOTHES_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))
            if asset not in installed:
                installed.append(asset)
    return installed


def fetch_community(folder: str, files: list[tuple[str, str]]) -> None:
    dest_dir = CLOTHES_DIR / folder
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for url, filename in files:
        download(url, dest_dir / filename)


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CLOTHES_DIR.mkdir(parents=True, exist_ok=True)

    licenses: dict[str, dict[str, str]] = {}

    zip_path = CACHE_DIR / "suits02_cc0.zip"
    print("=== Suits 02 (medieval subset) ===", flush=True)
    download(SUITS02_URL, zip_path, min_bytes=100_000_000)
    installed = extract_suits02(zip_path)
    print(f"  extracted {len(installed)} asset folders: {installed}")
    for asset in installed:
        licenses[asset] = {
            "pack": "suits02",
            "source": "https://static.makehumancommunity.org/assets/assetpacks/suits02.html",
            **SUITS02_KEEP[asset],
        }

    print("=== Community assets ===")
    for folder, (meta, files) in COMMUNITY_ASSETS.items():
        print(f"-- {folder}")
        fetch_community(folder, files)
        licenses[folder] = meta
        mhclos = list((CLOTHES_DIR / folder).glob("*.mhclo"))
        if not mhclos:
            raise FileNotFoundError(f"{folder}: no .mhclo after download")

    LICENSE_PATH.write_text(json.dumps(licenses, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {LICENSE_PATH} ({len(licenses)} assets)")
    print("Medieval clothes ready under", CLOTHES_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
