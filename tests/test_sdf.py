"""Distance-function shapes, their meshing and simplification, and the JSON shape trees.

    python -m unittest discover tests

Needs numpy (skipped without it); no Blender.
"""

from __future__ import annotations

import math
import sys
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None


def _check_closed(test: unittest.TestCase, verts: list, faces: list) -> float:
    """Every edge shared by exactly two faces; returns the signed volume."""
    edges: Counter = Counter()
    for face in faces:
        for i in range(3):
            a, b = face[i], face[(i + 1) % 3]
            edges[(min(a, b), max(a, b))] += 1
    test.assertTrue(all(n == 2 for n in edges.values()), "every edge has exactly two faces")
    v = np.asarray(verts)
    f = np.asarray(faces)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    test.assertGreater(area.min(), 1e-10, "no zero-area face (QA's no_degenerate_faces)")
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


@unittest.skipIf(np is None, "sdf needs numpy")
class PrimitiveTests(unittest.TestCase):
    def test_distances(self) -> None:
        from assetkit import sdf

        p = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 3.0]])
        np.testing.assert_allclose(sdf.sphere((0, 0, 0), 1.0)(p), [-1.0, 1.0, 2.0])
        np.testing.assert_allclose(sdf.box((0, 0, 0), (2, 2, 2))(p), [-1.0, 1.0, 2.0])
        np.testing.assert_allclose(sdf.capsule((0, 0, 0), (0, 0, 1), 0.5)(p), [-0.5, 1.5, 1.5])
        # A round cone: 1.0 wide at the bottom, 0.5 at the top, 2 m long.
        cone = sdf.capsule((0, 0, 0), (0, 0, 2), 1.0, 0.5)
        np.testing.assert_allclose(cone(np.array([[0, 0, -2.0], [0, 0, 3.0]])), [1.0, 0.5])

    def test_combinations(self) -> None:
        from assetkit import sdf

        a, b = sdf.sphere((0, 0, 0), 1.0), sdf.sphere((1.5, 0, 0), 1.0)
        p = np.array([[0.75, 0.0, 0.0]])
        self.assertAlmostEqual(float(sdf.union(a, b)(p)[0]), -0.25)
        self.assertLess(float(sdf.smooth_union(a, b, 0.4)(p)[0]), -0.25)  # the seam fills in
        self.assertAlmostEqual(float(sdf.subtract(a, b)(np.array([[-0.5, 0, 0]]))[0]), -0.5)
        mirrored = sdf.mirror_x(sdf.sphere((1.0, 0, 0), 0.2))
        self.assertAlmostEqual(float(mirrored(np.array([[-1.0, 0, 0]]))[0]), -0.2)
        turned = sdf.rotate(sdf.box((1.0, 0, 0), (0.2, 0.2, 0.2)), (0.0, 0.0, math.pi / 2))
        self.assertLess(float(turned(np.array([[0.0, 1.0, 0.0]]))[0]), 0.0)


@unittest.skipIf(np is None, "sdf needs numpy")
class MeshTests(unittest.TestCase):
    def test_sphere_is_closed_outward_and_on_the_surface(self) -> None:
        from assetkit import sdf

        shape = sdf.sphere((0, 0, 0.5), 0.5)
        verts, faces = sdf.mesh(shape, max_triangles=1200)
        self.assertLessEqual(len(faces), 1200)
        volume = _check_closed(self, verts, faces)
        self.assertAlmostEqual(volume, 4 / 3 * math.pi * 0.125, delta=0.01)
        self.assertLess(np.abs(shape(np.asarray(verts))).max(), 1e-3)

    def test_rounded_box_keeps_its_volume_at_a_small_budget(self) -> None:
        from assetkit import sdf

        verts, faces = sdf.mesh(sdf.box((0, 0, 0), (1.0, 0.5, 0.3), 0.05), max_triangles=400)
        self.assertLessEqual(len(faces), 400)
        self.assertAlmostEqual(_check_closed(self, verts, faces), 0.1455, delta=0.004)

    def test_torus_has_a_hole(self) -> None:
        from assetkit import sdf

        verts, faces = sdf.mesh(sdf.torus((0, 0, 0), 0.5, 0.12), max_triangles=1500)
        _check_closed(self, verts, faces)
        euler = (
            len(verts)
            - len({tuple(sorted((f[i], f[(i + 1) % 3]))) for f in faces for i in range(3)})
            + len(faces)
        )
        self.assertEqual(euler, 0, "a torus has Euler characteristic 0")

    def test_empty_and_unbounded_shapes_are_refused(self) -> None:
        from assetkit import sdf

        with self.assertRaises(ValueError):
            sdf.mesh(sdf.half_space(0.0))
        with self.assertRaises(ValueError):
            sdf.mesh(sdf.subtract(sdf.sphere((0, 0, 0), 0.5), sdf.sphere((0, 0, 0), 1.0)))


@unittest.skipIf(np is None, "sdf needs numpy")
class DeterminismTests(unittest.TestCase):
    def test_the_same_shape_gives_the_same_mesh_bit_for_bit(self) -> None:
        """Same spec, same asset, on every machine: numpy 1.26 (Blender 4.5) and 2.x (Blender 5,
        CI) give this exact mesh. A change here changes every sculpted asset: do it on purpose."""
        import hashlib

        from assetkit import sdf

        shape = sdf.smooth_union(
            sdf.rotate(sdf.box((0, 0, 0.2), (0.4, 0.3, 0.3), 0.05), (0.2, 0.1, 0.4)),
            sdf.capsule((0.1, 0, 0.3), (0.4, 0.2, 0.5), 0.08, 0.03),
            0.05,
        ).displace(0.01, 9.0, seed=3, octaves=2)
        verts, faces = sdf.mesh(shape, max_triangles=600)
        digest = hashlib.sha256(repr((verts, faces)).encode()).hexdigest()
        self.assertEqual(digest, "a730281ac62c3ad13be1c717c509aa3cc687764043a5b2af9647c3cd37503986")


@unittest.skipIf(np is None, "simplify needs numpy")
class SimplifyTests(unittest.TestCase):
    def test_a_subdivided_cube_returns_to_its_corners(self) -> None:
        from assetkit.shells import grid_cube
        from assetkit.simplify import simplify

        verts, quads = grid_cube(4)
        tris = [t for q in quads for t in ([q[0], q[1], q[2]], [q[0], q[2], q[3]])]
        v, f = simplify(np.asarray(verts), np.asarray(tris), 12)
        self.assertEqual(len(f), 12)
        corners = {tuple(np.round(p, 6)) for p in v}
        self.assertEqual(corners, {(x, y, z) for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)})


@unittest.skipIf(np is None, "sculpt needs numpy")
class SculptTests(unittest.TestCase):
    def test_a_tree_builds(self) -> None:
        from assetkit.sculpt import build_shape

        tree = {
            "subtract": {
                "from": {
                    "smooth_union": {
                        "k": 0.05,
                        "shapes": [{"ref": "a"}, {"sphere": {"centre": [0.3, 0, 0], "radius": 0.2}}],
                    }
                },
                "cut": {"box": {"centre": [0, 0, -0.5], "size": [2, 2, 1]}},
            }
        }
        shape = build_shape(tree, {"a": {"sphere": {"centre": [0, 0, 0], "radius": 0.25}}}, "params.shape")
        self.assertLess(float(shape(np.array([[0.0, 0.0, 0.1]]))[0]), 0.0)
        self.assertGreater(float(shape(np.array([[0.0, 0.0, -0.1]]))[0]), 0.0)  # cut away

    def test_errors_name_the_path(self) -> None:
        from assetkit.sculpt import SculptError, build_shape

        cases = [
            ({"sphere": {"centre": [0, 0, 0], "radius": 1, "colour": 2}}, "params.shape.sphere: unknown key"),
            ({"union": [{"sphere": {"centre": [0, 0], "radius": 1}}]}, "params.shape.union[0].sphere.centre"),
            ({"blob": {}}, "unknown shape kind 'blob'"),
            ({"ref": "nope"}, "no part named 'nope'"),
            ({"sphere": {"centre": [0, 0, 0], "radius": -1}}, "radius must be positive"),
        ]
        for tree, message in cases:
            with self.subTest(message=message), self.assertRaises(SculptError) as caught:
                build_shape(tree, {}, "params.shape")
            self.assertIn(message, str(caught.exception))

    def test_a_part_cannot_contain_itself(self) -> None:
        from assetkit.sculpt import SculptError, build_shape

        with self.assertRaises(SculptError):
            build_shape({"ref": "a"}, {"a": {"union": [{"ref": "a"}]}}, "params.shape")

    def test_paint_marks_regions(self) -> None:
        from assetkit import sdf

        body = sdf.sphere((0, 0, 0), 0.5)
        shell = sdf.mesh(body, max_triangles=800)
        shell, slots = sdf.paint(
            shell, {"cap": sdf.half_space(0.3, above=True)}, "skin", reach=0.0, shape=body
        )
        verts, faces = np.asarray(shell[0]), np.asarray(shell[1])
        _check_closed(self, shell[0], shell[1])
        # The border lies on the region's edge: every vertex of a painted face is at z >= 0.3 - a hair.
        painted_verts = verts[faces[np.array([s == "cap" for s in slots])].ravel()]
        self.assertGreater(painted_verts[:, 2].min(), 0.3 - 1e-3)
        self.assertLess(np.abs(body(verts)).max(), 1e-3, "border vertices stay on the surface")
        centres = verts[faces].mean(axis=1)
        painted = np.array([s == "cap" for s in slots])
        self.assertTrue(np.all(centres[painted, 2] >= 0.3))
        self.assertTrue(np.all(centres[~painted, 2] < 0.3))
        self.assertGreater(painted.sum(), 10)


if __name__ == "__main__":
    unittest.main()
