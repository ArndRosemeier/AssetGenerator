"""Material patterns: parsing, what each layer paints, baking to textures, and reading them back.

    python -m unittest discover tests

Needs numpy for everything but parsing (skipped without it); no Blender.
"""

from __future__ import annotations

import io
import struct
import sys
import unittest
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assetkit.material import PatternError, parse_pattern  # noqa: E402
from blender.lib.spec import MaterialSpec, SpecError  # noqa: E402

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None

BARK = {
    "layers": [
        {"mottle": {"color": [0.07, 0.05, 0.03], "scale": 7, "stretch": [1, 1, 6], "coverage": 0.45}},
        {"spots": {"color": [0.3, 0.4, 0.1], "size": 0.05, "spacing": 0.1, "seed": 2}},
        {"grain": {"color": [0.3, 0.2, 0.1], "axis": "radial", "spacing": 0.02}},
        {"gradient": {"color": [0.1, 0.1, 0.1], "axis": "z", "from": 0.0, "to": 0.2, "roughness": 1.0}},
        {"cavities": {"color": [0.02, 0.02, 0.02], "radius": 0.04, "breakup": 0.5}},
        {"edges": {"color": [0.5, 0.4, 0.3], "radius": 0.03, "amount": 0.5}},
    ]
}


class ParsingTests(unittest.TestCase):
    def test_a_full_pattern_parses_with_defaults_filled_in(self) -> None:
        pattern = parse_pattern(BARK, "p")
        self.assertEqual(
            [layer.kind for layer in pattern.layers],
            ["mottle", "spots", "grain", "gradient", "cavities", "edges"],
        )
        self.assertEqual(pattern.layers[0].params["octaves"], 3)
        self.assertEqual(pattern.layers[3].roughness, 1.0)
        self.assertEqual(pattern.layers[5].amount, 0.5)

    def test_mistakes_name_their_place(self) -> None:
        cases = [
            ({"layers": []}, "p.layers"),
            ({"layers": [{"stripes": {"color": [0, 0, 0]}}]}, "unknown layer 'stripes'"),
            ({"layers": [{"grain": {"color": [0, 0, 0]}}]}, "p.layers[0].grain: missing 'spacing'"),
            ({"layers": [{"mottle": {"color": [0, 2, 0]}}]}, "p.layers[0].mottle.color"),
            ({"layers": [{"mottle": {"color": [0, 0, 0], "sharp": 1}}]}, "unknown key(s) ['sharp']"),
            ({"layers": [{"grain": {"color": [0, 0, 0], "spacing": 0.1, "axis": "w"}}]}, ".axis"),
            ({"layers": [{"spots": {"color": [0, 0, 0], "size": 0.1, "spacing": 0.05}}]}, ".spacing"),
            ({"layers": [{"gradient": {"color": [0, 0, 0], "from": 1, "to": 1}}]}, "must differ"),
            ({"layers": [{"edges": {"color": [0, 0, 0], "radius": -1}}]}, ".radius: must be positive"),
        ]
        for raw, message in cases:
            with self.subTest(message=message), self.assertRaises(PatternError) as caught:
                parse_pattern(raw, "p")
            self.assertIn(message, str(caught.exception))

    def test_a_spec_material_carries_its_pattern(self) -> None:
        raw = {"base_color": [0.2, 0.1, 0.05, 1], "roughness": 0.9, "metallic": 0.0, "pattern": BARK}
        self.assertEqual(len(MaterialSpec.parse(raw, "materials.bark").pattern.layers), 6)
        plain = {k: v for k, v in raw.items() if k != "pattern"}
        self.assertIsNone(MaterialSpec.parse(plain, "materials.bark").pattern)
        raw["pattern"] = {"layers": [{"mottle": {}}]}
        with self.assertRaises(SpecError) as caught:
            MaterialSpec.parse(raw, "materials.bark")
        self.assertIn("materials.bark.pattern.layers[0].mottle.color", str(caught.exception))


@unittest.skipIf(np is None, "numpy is not installed")
class SurfaceTests(unittest.TestCase):
    def test_a_sphere_bends_by_one_over_its_radius(self) -> None:
        from assetkit import sdf
        from assetkit.material import Surface

        vertices, faces = sdf.mesh(sdf.sphere((0, 0, 0), 0.2), 3000)
        surface = Surface(vertices, faces)
        self.assertAlmostEqual(float(np.median(surface.bend)), 5.0, delta=0.25)
        self.assertEqual(len(surface.crease_a), 0)

    def test_a_box_has_twelve_outward_creases_and_an_l_an_inward_one(self) -> None:
        from assetkit.material import Surface

        box = _triangulated(_box((0, 0, 0), (0.5, 0.3, 0.2)))
        surface = Surface(*box)
        self.assertEqual(len(surface.crease_a), 12)
        self.assertTrue(surface.crease_convex.all())
        near_edge, mid_face = [0.01, 0.15, 0.2], [0.25, 0.15, 0.2]
        mask = surface.near_creases(np.array([near_edge, mid_face]), 0.03, outward=True)
        self.assertGreater(mask[0], 0.5)
        self.assertEqual(mask[1], 0.0)

        # An L: a tall box on a flat one, fused, so the inner corner is an inward crease.
        vertices = np.array(
            [[0, 0, 0], [2, 0, 0], [2, 0, 1], [1, 0, 1], [1, 0, 2], [0, 0, 2]], dtype=np.float64
        )
        profile = _extrude(vertices, 1.0)
        surface = Surface(*profile)
        inner = surface.near_creases(np.array([[1.05, 0.5, 1.0]]), 0.2, outward=False)
        self.assertGreater(inner[0], 0.5)


@unittest.skipIf(np is None, "numpy is not installed")
class BakeTests(unittest.TestCase):
    def test_masks_paint_where_they_say(self) -> None:
        from assetkit.material import Surface, coverage

        vertices, triangles = _triangulated(_box((-0.25, -0.25, 0.0), (0.25, 0.25, 0.5)))
        surface = Surface(vertices, triangles)
        rng = np.random.default_rng(7)
        tri = rng.integers(0, len(triangles), 20000)  # all twelve triangles have the same area
        bary = rng.dirichlet((1.0, 1.0, 1.0), 20000)
        pattern = parse_pattern(
            {
                "layers": [
                    {"gradient": {"color": [0, 0, 0], "axis": "z", "from": 0.0, "to": 0.5}},
                    {"edges": {"color": [1, 1, 1], "radius": 0.02}},
                    {"cavities": {"color": [1, 1, 1], "radius": 0.02}},
                    {
                        "spots": {
                            "color": [1, 1, 1],
                            "size": 0.04,
                            "spacing": 0.08,
                            "density": 1.0,
                            "softness": 0.0,
                        }
                    },
                ]
            },
            "p",
        )
        gradient, edges, cavities, spots = coverage(pattern, surface, tri, bary)
        # The sides fade from full at the bottom to none at the top (a third of the box is its
        # bottom, all full, and its top, all empty): half overall.
        self.assertAlmostEqual(gradient, 0.5, delta=0.03)
        # Fading out over 2 cm from each edge (1 cm on average) along a face's four half-metre
        # edges: 4 x 0.5 m x 1 cm over 0.25 square metres.
        self.assertAlmostEqual(edges, 0.08, delta=0.01)
        self.assertEqual(cavities, 0.0)  # a box bends only outward
        # Spots of 4 cm every 8 cm on the surface, all present: pi/16 of it, less where they overlap.
        self.assertAlmostEqual(spots, np.pi / 16, delta=0.04)

    def test_a_baked_texture_shows_what_the_pattern_says(self) -> None:
        """Bake on a UV layout, sample the texture as a glTF viewer would, compare to the pattern."""
        from assetkit import sdf
        from assetkit.texbake import SlotLook, bake, to_srgb
        from assetview.paint import PatternPaint, TexturePaint, decode_png
        from assetview.sheet import write_png

        vertices, faces = sdf.mesh(sdf.sphere((0, 0, 0.2), 0.2), 600)
        uvs = _atlas(len(faces))
        look = SlotLook(parse_pattern(BARK, "p"), (0.2, 0.12, 0.07), 0.9)
        maps = bake(vertices, faces, uvs, np.zeros(len(faces), dtype=np.int64), [look], size=256)
        self.assertGreater(maps.covered, 0.3)
        # Through an 8-bit PNG, rows top first and v flipped as a glTF file holds it.
        path = Path(self._tmp()) / "color.png"
        write_png(path, to_srgb(maps.color[::-1]))
        texture = decode_png(path.read_bytes())
        from assetkit.texbake import from_srgb

        gltf_uvs = uvs.copy()
        gltf_uvs[..., 1] = 1.0 - gltf_uvs[..., 1]
        slots = np.zeros(len(faces), dtype=np.int64)
        shipped = TexturePaint(gltf_uvs, slots, [from_srgb(texture)], np.ones((1, 3)))
        kit = PatternPaint(np.asarray(vertices), np.asarray(faces), slots, [look], [(0.0, 0.0, 0.0)])
        rng = np.random.default_rng(3)
        tri = rng.integers(0, len(faces), 4000)
        bary = rng.dirichlet((4.0, 4.0, 4.0), 4000)  # away from triangle edges
        error = np.abs(shipped.colors(tri, bary) - kit.colors(tri, bary)).max(axis=1)
        self.assertLess(float(np.median(error)), 0.02)

    def test_baking_is_reproducible(self) -> None:
        from assetkit import sdf
        from assetkit.texbake import SlotLook, bake

        vertices, faces = sdf.mesh(sdf.sphere((0, 0, 0.2), 0.2), 400)
        look = SlotLook(parse_pattern(BARK, "p"), (0.2, 0.12, 0.07), 0.9)
        slots = np.zeros(len(faces), dtype=np.int64)
        maps = bake(vertices, faces, _atlas(len(faces)), slots, [look], size=64)
        twice = bake(vertices, faces, _atlas(len(faces)), slots, [look], size=64)
        self.assertTrue(np.array_equal(maps.color, twice.color))
        self.assertTrue(np.array_equal(maps.roughness, twice.roughness))

    def test_islands_grow_into_the_gaps(self) -> None:
        from assetkit.texbake import SlotLook, bake

        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
        uvs = np.array([[[0.25, 0.25], [0.5, 0.25], [0.25, 0.5]]])
        maps = bake(
            vertices,
            np.array([[0, 1, 2]]),
            uvs,
            np.array([0]),
            [SlotLook(None, (1.0, 0.5, 0.0), 0.3)],
            size=64,
        )
        self.assertTrue(
            np.allclose(maps.color[14:34, 14:34][maps.color[14:34, 14:34, 0] > 0], (1.0, 0.5, 0.0))
        )
        self.assertTrue(np.allclose(maps.color, (1.0, 0.5, 0.0)))  # grown, then the rest filled
        self.assertTrue(np.allclose(maps.roughness, 0.3))

    def test_texture_size_follows_the_surface(self) -> None:
        from assetkit.texbake import texture_size

        quad = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
        triangles = np.array([[0, 1, 2], [0, 2, 3]])
        full = np.array([[[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 1], [0, 1]]], dtype=np.float64)
        self.assertEqual(texture_size(quad, triangles, full), 512)  # 1 m square at 512 per metre
        self.assertEqual(texture_size(quad * 0.1, triangles, full), 256)  # the smallest
        self.assertEqual(texture_size(quad * 2.2, triangles, full), 1024)  # nearest by ratio

    def _tmp(self) -> str:
        import tempfile

        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        return directory


@unittest.skipIf(np is None, "numpy is not installed")
class PngTests(unittest.TestCase):
    def test_every_filter_decodes(self) -> None:
        from assetview.paint import decode_png

        rng = np.random.default_rng(5)
        image = rng.integers(0, 256, (13, 17, 3)).astype(np.uint8)
        for kind in range(5):
            with self.subTest(filter=kind):
                decoded = decode_png(_png(image, kind))
                self.assertTrue(np.array_equal((decoded * 255 + 0.5).astype(np.uint8), image))
        grey = rng.integers(0, 256, (5, 4, 4)).astype(np.uint8)  # RGBA
        self.assertTrue(
            np.array_equal((decode_png(_png(grey, 4)) * 255 + 0.5).astype(np.uint8), grey[..., :3])
        )


@unittest.skipIf(np is None, "numpy is not installed")
class AssetTests(unittest.TestCase):
    def test_a_pattern_needs_an_unwrap(self) -> None:
        from assetkit import MeshBuilder, Part, ShadeFlat, Unwrap

        builder = MeshBuilder(["wood"])
        builder.add_box_bounds((0, 0, 0), (1, 1, 1), "wood")
        material = MaterialSpec((0.4, 0.3, 0.2, 1.0), 0.8, 0.0, parse_pattern(BARK, "p"))
        with self.assertRaises(ValueError) as caught:
            Part("crate", builder.build(), {"wood": material}, (ShadeFlat(),))
        self.assertIn("Unwrap", str(caught.exception))
        Part("crate", builder.build(), {"wood": material}, (ShadeFlat(), Unwrap()))

    def test_the_example_specs_report_their_layers(self) -> None:
        import importlib

        from assetview import from_asset
        from blender.lib.registry import resolve_generator_module
        from blender.lib.spec import load_spec

        spec = load_spec(REPO_ROOT / "assets" / "specs" / "crate_small.json")
        asset = importlib.import_module(resolve_generator_module(spec.generator)).build(spec)
        model = from_asset(asset)
        report = model.paint.report(model.slots)  # type: ignore[union-attr]
        self.assertEqual([r["slot"] for r in report], ["frame", "planks"])
        for slot in report:
            self.assertTrue(all(0.0 <= layer["covers"] <= 1.0 for layer in slot["layers"]))


def _box(lower: tuple, upper: tuple) -> tuple:
    (x0, y0, z0), (x1, y1, z1) = lower, upper
    v = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, quads


def _triangulated(mesh: tuple) -> tuple:
    vertices, quads = mesh
    return np.asarray(vertices, dtype=np.float64), np.array(
        [t for q in quads for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]
    )


def _extrude(profile: np.ndarray, depth: float) -> tuple:
    """A closed prism from a convex-or-not polygon in the XZ plane (counter-clockwise seen from -Y),
    pushed `depth` along +Y."""
    n = len(profile)
    back = profile + np.array([0.0, depth, 0.0])
    vertices = np.concatenate([profile, back])
    triangles = []
    for i in range(n):
        j = (i + 1) % n
        triangles += [(i, j, n + j), (i, n + j, n + i)]
    # Caps by ear fan from a vertex that sees all others (vertex 0 of the L does).
    for i in range(1, n - 1):
        triangles.append((0, i + 1, i))
        triangles.append((n, n + i, n + i + 1))
    triangles = np.array(triangles)
    # Orient outward: flip all if the volume is negative.
    a, b, c = (vertices[triangles[:, k]] for k in range(3))
    if (a * np.cross(b, c)).sum() < 0:
        triangles = triangles[:, ::-1]
    return vertices, triangles


def _atlas(count: int) -> np.ndarray:
    """A UV layout with every triangle in its own cell of a grid (the corner half of the cell)."""
    side = int(np.ceil(np.sqrt(count)))
    cell = 1.0 / side
    uvs = np.zeros((count, 3, 2))
    for k in range(count):
        x, y = (k % side) * cell, (k // side) * cell
        m = 0.1 * cell
        uvs[k] = [[x + m, y + m], [x + cell - m, y + m], [x + m, y + cell - m]]
    return uvs


def _png(image: np.ndarray, kind: int) -> bytes:
    """Encode with one PNG filter on every row (the test's own encoder, the filters by the spec)."""
    h, w, c = image.shape
    data = image.astype(np.int64)
    rows = []
    for y in range(h):
        line = data[y].reshape(-1)
        up = data[y - 1].reshape(-1) if y else np.zeros_like(line)
        left = np.concatenate([np.zeros(c, dtype=np.int64), line[:-c]])
        ul = np.concatenate([np.zeros(c, dtype=np.int64), up[:-c]])
        if kind == 0:
            pred = np.zeros_like(line)
        elif kind == 1:
            pred = left
        elif kind == 2:
            pred = up
        elif kind == 3:
            pred = (left + up) >> 1
        else:
            p = left + up - ul
            pa, pb, pc = np.abs(p - left), np.abs(p - up), np.abs(p - ul)
            pred = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, up, ul))
        rows.append(bytes([kind]) + ((line - pred) & 255).astype(np.uint8).tobytes())
    color_type = {3: 2, 4: 6, 1: 0}[c]

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    out = io.BytesIO()
    out.write(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )
    return out.getvalue()


if __name__ == "__main__":
    unittest.main()
