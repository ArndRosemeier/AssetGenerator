"""The asset kit and the generators written against it, checked without Blender.

    python -m unittest discover tests

Blender's modules are blocked for the whole run, so a kit generator that slips an
`import bpy` back in fails here, on any machine, in well under a second.
"""

from __future__ import annotations

import importlib
import importlib.abc
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

BLENDER_MODULES = ("bpy", "bmesh", "mathutils")


class _BlockBlender(importlib.abc.MetaPathFinder):
    def find_spec(self, name: str, path: object = None, target: object = None) -> None:
        if name.split(".")[0] in BLENDER_MODULES:
            raise ImportError(f"'{name}' is a Blender module; kit code must not import it")


sys.meta_path.insert(0, _BlockBlender())

import assetkit  # noqa: E402
from assetkit import Asset, Mesh, MeshBuilder, noise, shells  # noqa: E402
from blender.lib.registry import KIT_GENERATORS, resolve_generator_module  # noqa: E402
from blender.lib.spec import load_spec  # noqa: E402


def _open_edges(vertices: list[tuple[float, float, float]], faces: list[list[int]] | tuple) -> int:
    """Edges not shared by exactly two faces (0 for a closed shell)."""
    count: Counter[tuple[int, int]] = Counter()
    for face in faces:
        for i, a in enumerate(face):
            b = face[(i + 1) % len(face)]
            count[(min(a, b), max(a, b))] += 1
    return sum(1 for n in count.values() if n != 2)


def _signed_volume(vertices: tuple | list, faces: tuple | list) -> float:
    total = 0.0
    for face in faces:
        a = vertices[face[0]]
        for i in range(1, len(face) - 1):
            b, c = vertices[face[i]], vertices[face[i + 1]]
            total += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6.0
    return total


class ShellTests(unittest.TestCase):
    def test_box_is_closed_and_outward(self) -> None:
        verts, faces = shells.box((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))
        self.assertEqual(_open_edges(verts, faces), 0)
        self.assertAlmostEqual(_signed_volume(verts, faces), 6.0)

    def test_grid_cube_is_closed_and_outward(self) -> None:
        for cuts in (0, 1, 3, 7):
            verts, faces = shells.grid_cube(cuts)
            n = cuts + 1
            self.assertEqual(len(faces), 6 * n * n)
            self.assertEqual(len(verts), 6 * n * n + 2)
            self.assertEqual(_open_edges(verts, faces), 0)
            self.assertAlmostEqual(_signed_volume(verts, faces), 1.0)


class NoiseTests(unittest.TestCase):
    def test_values_are_fixed(self) -> None:
        # The noise shapes shipped assets (cut stone, boulders, moss). If these values change,
        # those assets change: do it on purpose, and say so.
        points = [(0.3, 1.7, -2.2), (12.5, 0.25, 3.75), (-7.1, 4.4, 9.9), (105.3, -0.6, 48.2)]
        expected = [-0.012488998, -0.384884357, 0.089309885, 0.225754388]
        self.assertEqual([round(noise.noise(*p), 9) for p in points], expected)

    def test_zero_on_the_lattice(self) -> None:
        self.assertEqual(noise.noise(1.0, 2.0, 3.0), 0.0)


class MeshBuilderTests(unittest.TestCase):
    def test_unknown_slot_is_refused(self) -> None:
        builder = MeshBuilder(("wood",))
        with self.assertRaises(KeyError):
            builder.add_box((0, 0, 0), (1, 1, 1), "iron")

    def test_face_past_the_shell_is_refused(self) -> None:
        builder = MeshBuilder(("wood",))
        verts, faces = shells.box((0, 0, 0), (1, 1, 1))
        with self.assertRaises(ValueError):
            builder.add_shell(verts, [*faces[:-1], [0, 1, 99]], "wood")

    def test_attribute_needs_one_value_per_vertex(self) -> None:
        builder = MeshBuilder(("wood",))
        builder.add_box((0, 0, 0), (1, 1, 1), "wood")
        with self.assertRaises(ValueError):
            builder.set_point_attribute("shade", [1.0] * 7)

    def test_rotated_box_keeps_its_volume(self) -> None:
        builder = MeshBuilder(("wood",))
        builder.add_box((1.0, 2.0, 3.0), (1.0, 2.0, 0.5), "wood", rotation=(0.3, -1.1, 2.0))
        mesh = builder.build()
        self.assertAlmostEqual(_signed_volume(mesh.vertices, mesh.faces), 1.0)

    def test_settled_rests_on_the_origin(self) -> None:
        builder = MeshBuilder(("wood",))
        builder.add_box((3.0, -2.0, 5.0), (1.0, 1.0, 1.0), "wood")
        (x0, y0, z0), (x1, y1, _) = builder.build().settled().bounds()
        self.assertAlmostEqual(x0 + x1, 0.0)
        self.assertAlmostEqual(y0 + y1, 0.0)
        self.assertAlmostEqual(z0, 0.0)


class KitGeneratorTests(unittest.TestCase):
    """Every spec of every kit generator builds without Blender into closed, outward shells."""

    def test_every_kit_spec_builds_without_blender(self) -> None:
        specs = [
            load_spec(path)
            for path in sorted((REPO_ROOT / "assets" / "specs").glob("*.json"))
            if _generator(path) in KIT_GENERATORS
        ]
        self.assertTrue(specs, "no spec uses a kit generator")
        for spec in specs:
            with self.subTest(spec=spec.asset_id):
                module = importlib.import_module(resolve_generator_module(spec.generator))
                asset = module.build(spec)
                self.assertIsInstance(asset, Asset)
                triangles = 0
                for part in asset.parts:
                    mesh: Mesh = part.mesh
                    self.assertEqual(_open_edges(list(mesh.vertices), mesh.faces), 0, part.name)
                    self.assertGreater(_signed_volume(mesh.vertices, mesh.faces), 0.0, part.name)
                    triangles += mesh.triangle_count()
                # The bevel adds triangles in Blender; before it the mesh must already fit.
                self.assertLessEqual(triangles, spec.qa.max_triangles)

    def test_kit_generators_are_registered(self) -> None:
        for name in KIT_GENERATORS:
            resolve_generator_module(name)


def _generator(path: Path) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("generator") if isinstance(data, dict) else None


class ApiTests(unittest.TestCase):
    def test_api_version(self) -> None:
        self.assertEqual(assetkit.API_VERSION, 1)


if __name__ == "__main__":
    unittest.main()
