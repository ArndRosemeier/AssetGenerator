"""The inspection sheet and its measurements, on small assets with known defects.

    python -m unittest discover tests

Needs numpy (skipped without it); no Blender.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None

from assetkit import Asset, MeshBuilder, Part, shells  # noqa: E402
from blender.lib.spec import MaterialSpec  # noqa: E402

WOOD = MaterialSpec(base_color=(0.4, 0.25, 0.1, 1.0), roughness=0.8, metallic=0.0)
IRON = MaterialSpec(base_color=(0.05, 0.05, 0.06, 1.0), roughness=0.5, metallic=1.0)


def _asset(builder: MeshBuilder) -> Asset:
    materials = {slot: (WOOD if slot == "wood" else IRON) for slot in builder.slots}
    return Asset((Part("test", builder.build(), materials),))


def _inside_out(lower: tuple, upper: tuple) -> tuple[list, list]:
    verts, faces = shells.box(lower, upper)
    return verts, [list(reversed(face)) for face in faces]


@unittest.skipIf(np is None, "assetview needs numpy")
class MeasureTests(unittest.TestCase):
    def _measure(self, builder: MeshBuilder) -> dict:
        from assetview import from_asset, measure

        return measure(from_asset(_asset(builder)))

    def test_a_table_stands(self) -> None:
        b = MeshBuilder(("wood",))
        b.add_box_bounds((-0.5, -0.4, 0.7), (0.5, 0.4, 0.75), "wood")
        for x in (-0.45, 0.45):
            for y in (-0.35, 0.35):
                b.add_box_bounds((x - 0.03, y - 0.03, 0.0), (x + 0.03, y + 0.03, 0.71), "wood")
        report = self._measure(b)
        self.assertEqual(report["parts"], 5)
        self.assertEqual(report["floating_parts"], [])
        self.assertEqual(report["open_edges"], 0)
        self.assertEqual(report["inverted_parts"], 0)
        self.assertEqual(report["balance"]["verdict"], "stands")
        self.assertAlmostEqual(report["size_m"][2], 0.75)

    def test_an_overhang_tips_over(self) -> None:
        b = MeshBuilder(("wood",))
        b.add_box_bounds((0.0, -0.05, 0.0), (0.1, 0.05, 1.0), "wood")
        b.add_box_bounds((0.0, -0.05, 0.9), (1.5, 0.05, 1.0), "wood")  # a heavy arm out to one side
        report = self._measure(b)
        self.assertEqual(report["balance"]["verdict"], "tips over")
        self.assertLess(report["balance"]["margin_m"], 0.0)

    def test_a_floating_piece_is_found(self) -> None:
        b = MeshBuilder(("wood", "iron"))
        b.add_box_bounds((-0.5, -0.5, 0.0), (0.5, 0.5, 0.5), "wood")
        b.add_box_bounds((-0.05, -0.05, 0.8), (0.05, 0.05, 0.9), "iron")  # 30 cm above the block
        report = self._measure(b)
        self.assertEqual(len(report["floating_parts"]), 1)
        self.assertAlmostEqual(report["floating_parts"][0]["lower"][2], 0.8)

    def test_a_resting_piece_is_not_floating(self) -> None:
        b = MeshBuilder(("wood", "iron"))
        b.add_box_bounds((-0.5, -0.5, 0.0), (0.5, 0.5, 0.5), "wood")
        b.add_box_bounds((-0.05, -0.05, 0.5), (0.05, 0.05, 0.6), "iron")
        self.assertEqual(self._measure(b)["floating_parts"], [])

    def test_an_inside_out_shell_is_found(self) -> None:
        b = MeshBuilder(("wood",))
        b.add_box_bounds((-0.5, -0.5, 0.0), (0.5, 0.5, 0.5), "wood")
        b.add_shell(*_inside_out((0.6, -0.1, 0.0), (0.8, 0.1, 0.2)), "wood")
        self.assertEqual(self._measure(b)["inverted_parts"], 1)

    def test_a_hole_is_found(self) -> None:
        from assetview import from_asset, measure

        b = MeshBuilder(("wood",))
        b.add_box_bounds((-0.5, -0.5, 0.0), (0.5, 0.5, 0.5), "wood")
        asset = _asset(b)
        mesh = asset.parts[0].mesh
        # Drop the top face: four edges are left with one face each.
        holed = type(mesh)(mesh.vertices, mesh.faces[:1] + mesh.faces[2:], mesh.face_slots[1:], mesh.slots)
        report = measure(from_asset(Asset((Part("test", holed, asset.parts[0].materials),))))
        self.assertEqual(report["open_edges"], 4)


@unittest.skipIf(np is None, "assetview needs numpy")
class SheetTests(unittest.TestCase):
    def test_sheet_shows_the_asset_and_marks_inside_out_faces(self) -> None:
        from assetview import from_asset, render_sheet, write_png
        from assetview.sheet import HEADER, TILE

        b = MeshBuilder(("wood",))
        b.add_shell(*_inside_out((-0.5, -0.5, 0.0), (0.5, 0.5, 1.0)), "wood")
        image, report = render_sheet(from_asset(_asset(b)), "inside out")
        self.assertEqual(image.shape, (HEADER + 3 * TILE, 3 * TILE, 3))
        self.assertEqual(report["inverted_parts"], 1)
        facing = image[HEADER + 2 * TILE + 20 :, TILE : 2 * TILE]
        red = (facing[..., 0] > 0.45) & (facing[..., 1] < 0.2) & (facing[..., 2] < 0.2)
        self.assertGreater(red.mean(), 0.05, "the facing view shows inside-out faces in red")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.png"
            write_png(path, image)
            self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_orthographic_views_share_one_scale(self) -> None:
        from assetview import from_asset
        from assetview.raster import frame
        from assetview.sheet import FRONT, SIDE, TILE

        b = MeshBuilder(("wood",))
        b.add_box_bounds((-1.0, -0.1, 0.0), (1.0, 0.1, 0.2), "wood")  # long in X, thin in Y
        model = from_asset(_asset(b))
        scale = min(frame(c, model.positions, TILE).scale for c in (FRONT, SIDE))
        front = frame(FRONT, model.positions, TILE, scale=scale)
        side = frame(SIDE, model.positions, TILE, scale=scale)
        width_front = np.ptp(front.project(model.positions)[0][:, 0])
        width_side = np.ptp(side.project(model.positions)[0][:, 0])
        self.assertAlmostEqual(width_front / width_side, 10.0, places=6)


if __name__ == "__main__":
    unittest.main()
