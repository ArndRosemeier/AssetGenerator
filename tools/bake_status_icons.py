"""Bake Orrun status icon family (2D PNG via Pillow, no Blender).

    python tools/bake_status_icons.py

Reads assets/specs/status_icons.json. Writes only under assets/icons/status/
plus requested copies. Does not touch loot PNGs in assets/icons/.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO / "assets" / "specs" / "status_icons.json"
STATUS_DIR = REPO / "assets" / "icons" / "status"

ORRUN_STATUS = Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\icons\status")
PREVIEWS = Path(r"C:\Users\windo\agent-previews")

SCALE = 4
SIZE = 256

# Loot-language outline (club.png / families.md oak)
OUTLINE = (42, 24, 14, 255)

# Ashen gray-green (shaken only)
FILL = (108, 122, 98, 255)
SHADE = (72, 86, 68, 255)
LIGHT = (166, 178, 150, 255)
PALE = (200, 206, 186, 255)
DEEP = (58, 66, 54, 255)
CRACK = (42, 24, 14, 255)

PARCHMENT = (243, 230, 204, 255)
CREAM = (252, 244, 226, 255)
OAK = (74, 42, 20, 255)
STRAW = (201, 163, 106, 255)


def hex_rgba(value: str) -> tuple[int, int, int, int]:
    text = value.strip().lstrip("#")
    r = int(text[0:2], 16)
    g = int(text[2:4], 16)
    b = int(text[4:6], 16)
    return (r, g, b, 255)


def load_spec() -> dict:
    data = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
    if data.get("kind") != "status_icons":
        raise SystemExit("status_icons.json must have kind=status_icons")
    ids = [row["id"] for row in data.get("families", [])]
    if ids != ["shaken"]:
        raise SystemExit(f"this baker ships only shaken, got {ids}")
    return data


def heater_points(cx: float, cy: float, rw: float, rh: float) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for deg in range(0, 181, 6):
        ang = math.radians(180 - deg)
        x = cx + math.cos(ang) * rw
        y = cy - rh * 0.52 + math.sin(ang) * rh * 0.24
        pts.append((x, y))
    pts.append((cx + rw * 0.94, cy + rh * 0.10))
    pts.append((cx + rw * 0.58, cy + rh * 0.52))
    pts.append((cx, cy + rh * 0.98))
    pts.append((cx - rw * 0.58, cy + rh * 0.52))
    pts.append((cx - rw * 0.94, cy + rh * 0.10))
    return pts


def inset_points(pts: list[tuple[float, float]], cx: float, cy: float, factor: float) -> list[tuple[float, float]]:
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in pts]


def draw_polyline(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill, width: int) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")
    r = max(1, width // 2)
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def stamp(dst: Image.Image, color: tuple[int, int, int, int], poly: list[tuple[float, float]], mask: Image.Image) -> None:
    layer = Image.new("RGBA", dst.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(poly, fill=color)
    combined = ImageChops.multiply(layer.getchannel("A"), mask)
    dst.paste(layer, mask=combined)


def paint_shaken() -> Image.Image:
    big = SIZE * SCALE
    cx, cy = big / 2.0, big / 2.0 + 4 * SCALE
    rw, rh = 80 * SCALE, 96 * SCALE
    shield = heater_points(cx, cy, rw, rh)
    inner = inset_points(shield, cx, cy, 0.82)

    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).polygon(shield, fill=255)

    interior = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(interior).polygon(shield, fill=FILL)

    stamp(
        interior,
        SHADE,
        [
            (cx + rw * 0.02, cy - rh * 0.20),
            (cx + rw * 1.15, cy - rh * 0.55),
            (cx + rw * 1.15, cy + rh * 1.15),
            (cx - rw * 0.20, cy + rh * 1.15),
        ],
        mask,
    )
    stamp(
        interior,
        LIGHT,
        [
            (cx - rw * 1.15, cy - rh * 0.95),
            (cx + rw * 0.08, cy - rh * 0.95),
            (cx - rw * 0.18, cy + rh * 0.05),
            (cx - rw * 1.15, cy + rh * 0.18),
        ],
        mask,
    )

    d = ImageDraw.Draw(interior)
    d.line(inner + [inner[0]], fill=DEEP, width=4 * SCALE, joint="curve")
    d.line(inner[:14], fill=PALE, width=3 * SCALE, joint="curve")

    ur = 20 * SCALE
    d.ellipse((cx - ur, cy - ur * 0.90, cx + ur, cy + ur * 0.90), fill=LIGHT, outline=DEEP, width=4 * SCALE)
    d.ellipse((cx - ur * 0.48, cy - ur * 0.52, cx + ur * 0.18, cy + ur * 0.08), fill=PALE)

    main = [
        (cx + 0 * SCALE, cy - rh * 0.68),
        (cx + 8 * SCALE, cy - rh * 0.42),
        (cx - 4 * SCALE, cy - rh * 0.08),
        (cx + 3 * SCALE, cy + rh * 0.08),
    ]
    left = [
        (cx + 3 * SCALE, cy + rh * 0.08),
        (cx - 16 * SCALE, cy + rh * 0.34),
        (cx - 38 * SCALE, cy + rh * 0.60),
    ]
    right = [
        (cx + 3 * SCALE, cy + rh * 0.08),
        (cx + 24 * SCALE, cy + rh * 0.32),
        (cx + 40 * SCALE, cy + rh * 0.62),
    ]
    cw = 10 * SCALE
    for path in (main, left, right):
        draw_polyline(d, path, CRACK, cw)
    split = [
        (cx - 4 * SCALE, cy - rh * 0.62),
        (cx + 4 * SCALE, cy - rh * 0.40),
        (cx - 8 * SCALE, cy - rh * 0.06),
        (cx - 1 * SCALE, cy + rh * 0.06),
        (cx - 20 * SCALE, cy + rh * 0.32),
        (cx - 36 * SCALE, cy + rh * 0.56),
    ]
    draw_polyline(d, split, PALE, 3 * SCALE)

    clipped = Image.new("RGBA", interior.size, (0, 0, 0, 0))
    clipped.paste(interior, mask=mask)
    interior = clipped

    k = 10 * SCALE * 2 + 1
    outline_m = mask.filter(ImageFilter.MaxFilter(k))
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    canvas.paste(OUTLINE, mask=outline_m)
    canvas.alpha_composite(interior)
    return canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        r"C:\Windows\Fonts\georgia.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def paste_icon(sheet: Image.Image, icon: Image.Image, xy: tuple[int, int], box: int) -> None:
    scaled = icon.resize((box, box), Image.Resampling.LANCZOS) if box != icon.size[0] else icon
    sheet.alpha_composite(scaled, dest=xy)


def paint_atlas(icon: Image.Image) -> Image.Image:
    w, h = 880, 430
    sheet = Image.new("RGBA", (w, h), PARCHMENT)
    d = ImageDraw.Draw(sheet)
    d.rectangle((0, 0, w, 56), fill=OAK)
    d.text((24, 10), "STATUS ICONS", font=font(28), fill=CREAM)
    d.text((280, 20), "one family  ·  shaken", font=font(16), fill=STRAW)
    d.text((w - 24, 18), "Pillow  ·  no Blender", font=font(14), fill=STRAW, anchor="rt")

    # Left card: 256
    d.rounded_rectangle((22, 74, 350, 408), radius=10, fill=CREAM, outline=OAK, width=4)
    paste_icon(sheet, icon, (46, 90), 256)
    d.text((186, 360), "shaken", font=font(22), fill=OAK, anchor="mt")
    d.text((186, 388), "256 px", font=font(13), fill=STRAW, anchor="mt")

    # Right: scales
    d.rounded_rectangle((370, 74, 856, 408), radius=10, fill=CREAM, outline=OAK, width=4)
    d.text((392, 90), "HUD scales", font=font(20), fill=OAK)
    d.text((392, 118), "ashen gray-green cracked shield", font=font(14), fill=SHADE[:3] + (255,))

    rows = [(48, 160, "48 px  ·  HUD"), (40, 240, "40 px  ·  readability"), (32, 312, "32 px")]
    for box, y, label in rows:
        # parchment
        paste_icon(sheet, icon, (400, y), box)
        # dark HUD chip
        chip_x = 400 + box + 28
        d.rounded_rectangle((chip_x - 8, y - 8, chip_x + box + 8, y + box + 8), radius=6, fill=OAK)
        paste_icon(sheet, icon, (chip_x, y), box)
        d.text((chip_x + box + 20, y + box / 2), label, font=font(16), fill=OAK, anchor="lm")

    return sheet


def write_families_md(spec: dict, path: Path) -> None:
    rows = spec["families"]
    lines = [
        "# Orrun status icon families",
        "",
        "Each family is one 256×256 PNG (`{id}.png`) under `icons/status/`.",
        "Baked from `assets/specs/status_icons.json` via `tools/bake_status_icons.py` (Pillow, no Blender).",
        "Do not add other status names here until a later bake.",
        "",
        "| family | reads as | silhouette |",
        "|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| `{row['id']}` | {row['reads_as']} | {row['silhouette']} |")
    pal = rows[0]["palette"]
    lines.extend(
        [
            "",
            "Palette: "
            + ", ".join(f"{key} `{value}`" for key, value in pal.items())
            + ".",
            "",
            "Language: same as loot icons — flat cartoon, thick dark outline, limited palette, transparent ground.",
            "Readable at ~40 px. Contact sheet: `atlas_contact.png`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def copy_outputs(icon_path: Path, atlas_path: Path) -> None:
    ORRUN_STATUS.mkdir(parents=True, exist_ok=True)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(icon_path, ORRUN_STATUS / "shaken.png")
    shutil.copy2(atlas_path, ORRUN_STATUS / "atlas_contact.png")
    shutil.copy2(icon_path, PREVIEWS / "shaken.png")
    shutil.copy2(atlas_path, PREVIEWS / "status_atlas_contact.png")


def report(paths: list[Path]) -> None:
    for path in paths:
        extra = ""
        if path.suffix.lower() == ".png":
            im = Image.open(path)
            extra = f"  {im.size[0]}x{im.size[1]}  {im.mode}"
        print(f"{path}{extra}  {path.stat().st_size} bytes")


def main() -> int:
    spec = load_spec()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    icon = paint_shaken()
    if icon.size != (256, 256) or icon.mode != "RGBA":
        raise SystemExit(f"bad icon {icon.size} {icon.mode}")
    icon_path = STATUS_DIR / "shaken.png"
    atlas_path = STATUS_DIR / "atlas_contact.png"
    md_path = STATUS_DIR / "families.md"
    icon.save(icon_path, "PNG")
    paint_atlas(icon).save(atlas_path, "PNG")
    write_families_md(spec, md_path)
    copy_outputs(icon_path, atlas_path)
    report(
        [
            icon_path,
            atlas_path,
            md_path,
            SPEC_PATH,
            ORRUN_STATUS / "shaken.png",
            ORRUN_STATUS / "atlas_contact.png",
            PREVIEWS / "shaken.png",
            PREVIEWS / "status_atlas_contact.png",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
