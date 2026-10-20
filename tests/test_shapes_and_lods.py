"""Swept and lofted shapes, squash and layer, the `inside` pattern layer, LODs and texture
density, and the rig checks for fused limbs and walks that barely move.

    python -m unittest discover tests
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from blender.lib.spec import SpecError, TextureSpec, load_spec, lod_raw  # noqa: E402

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None


@unittest.skipIf(np is None, "needs numpy")
class ShapeTests(unittest.TestCase):
    def test_a_sweep_runs_through_its_points_at_their_radii(self) -> None:
        from assetkit import sdf

        points = [(0.0, 0.0, 0.0), (0.3, 0.1, 0.4), (0.5, 0.0, 1.0)]
        radii = [0.12, 0.08, 0.04]
        tube = sdf.sweep(points, radii)
        for (x, y, z), r in zip(points, radii, strict=True):
            # The surface lies one radius out (sideways, across the curve), within 5%.
            self.assertAlmostEqual(float(tube(np.array([[x, y + r, z]]))[0]), 0.0, delta=0.05 * r)
        # Between the points the radius flows: no step anywhere along the way.
        line = np.array([[0.3 * t, 0.0, 0.4 * t] for t in np.linspace(0.05, 0.95, 40)])
        inside = tube(line)
        self.assertLess(float(np.abs(np.diff(inside)).max()), 0.01)

    def test_a_loft_has_its_sections_and_flat_ends(self) -> None:
        from assetkit import sdf

        shape = sdf.loft([[0.0, 0.2, 0.1], [1.0, 0.3, 0.15], [2.0, 0.2, 0.1]], rounding=0.0)
        on = np.array([[0.3, 0.0, 1.0], [0.0, 0.15, 1.0], [0.0, 0.0, 2.0], [0.0, 0.0, 0.0]])
        np.testing.assert_allclose(shape(on), 0.0, atol=1e-9)
        self.assertGreater(float(shape(np.array([[0.0, 0.0, 2.05]]))[0]), 0.0)
        with self.assertRaisesRegex(ValueError, "rise"):
            sdf.loft([[1.0, 0.2, 0.1], [0.5, 0.2, 0.1]])

    def test_squash_and_layer(self) -> None:
        from assetkit import sdf

        ball = sdf.sphere((0, 0, 0), 1.0)
        flat = sdf.squash(ball, (0, 0, 1), 0.5, (0, 0, 0))
        np.testing.assert_allclose(flat(np.array([[0, 0, 0.5], [1.0, 0, 0]])), 0.0, atol=1e-9)
        coat = sdf.intersect(sdf.round_(ball, 0.05), sdf.box((0, 0, 1), (2, 2, 1)))
        self.assertAlmostEqual(float(coat(np.array([[0, 0, 1.05]]))[0]), 0.0, places=9)  # 5 cm on top
        self.assertGreater(float(coat(np.array([[0, 0, -1.02]]))[0]), 0.0)  # none underneath

    def test_blend_equals_folded_smooth_unions(self) -> None:
        from assetkit import sdf

        shapes = [
            sdf.sphere((0, 0, 0), 0.5),
            sdf.capsule((0.4, 0, 0), (1, 0, 0.3), 0.2),
            sdf.sphere((3, 0, 0), 0.3),
        ]
        folded = sdf.smooth_union(sdf.smooth_union(shapes[0], shapes[1], 0.1), shapes[2], 0.05)
        p = np.random.default_rng(0).uniform(-1, 4, (5000, 3))
        np.testing.assert_allclose(sdf.blend(shapes, [0.0, 0.1, 0.05])(p), folded(p), atol=1e-12)

    def test_the_new_nodes_parse_in_a_spec(self) -> None:
        from assetkit.sculpt import SculptError, build_shape

        parts = {"log": {"sweep": {"points": [[0, 0, 0], [1, 0, 0]], "radius": [0.1, 0.05]}}}
        node = {"union": [
            {"ref": "log"},
            {"layer": {"on": {"ref": "log"}, "thickness": 0.01, "within": {"sphere": {"centre": [0, 0, 0.1], "radius": 0.2}}}},
            {"squash": {"axis": [0, 1, 0], "by": 0.5, "about": [0, 0, 0], "shape": {"loft": {"sections": [[0, 0.1, 0.1], [0.5, 0.2, 0.1]]}}}},
        ]}  # fmt: skip
        self.assertTrue(callable(build_shape(node, parts, "params.shape")))
        with self.assertRaisesRegex(SculptError, r"params.shape.sweep.radius"):
            build_shape({"sweep": {"points": [[0, 0, 0], [1, 0, 0]], "radius": [0.1]}}, {}, "params.shape")
        with self.assertRaisesRegex(SculptError, r"params.shape.loft.sections"):
            build_shape({"loft": {"sections": [[0, 0.1]]}}, {}, "params.shape")


@unittest.skipIf(np is None, "needs numpy")
class InsideLayerTests(unittest.TestCase):
    def test_inside_paints_the_shape_with_a_soft_border(self) -> None:
        from assetkit.material import _mask, parse_pattern

        layer = parse_pattern(
            {"layers": [{"inside": {"shape": {"sphere": {"centre": [0, 0, 0], "radius": 0.1}}, "color": [1, 0, 0], "soft": 0.01}}]},
            "p",
        ).layers[0]  # fmt: skip
        p = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.2, 0.0, 0.0]])
        m = _mask(layer, p, np.zeros(3), np.tile([0.0, 0.0, 1.0], (3, 1)), lambda r, o: np.zeros(3))
        np.testing.assert_allclose(m, [1.0, 0.5, 0.0], atol=1e-9)

    def test_a_shape_is_required(self) -> None:
        from assetkit.material import PatternError, parse_pattern

        with self.assertRaisesRegex(PatternError, r"inside.shape"):
            parse_pattern({"layers": [{"inside": {"color": [1, 0, 0]}}]}, "p")


class LodTests(unittest.TestCase):
    def _spec(self, extra: dict) -> object:
        raw = json.loads((REPO_ROOT / "assets" / "specs" / "sculpt_clay_urn.json").read_text())
        raw.update(extra)
        tmp = Path(tempfile.mkdtemp()) / "urn.json"
        tmp.write_text(json.dumps(raw))
        return load_spec(tmp)

    def test_each_level_has_its_budget_and_half_the_texture_density(self) -> None:
        spec = self._spec(
            {"lods": [{"max_triangles": 2400}, {"max_triangles": 900, "params": {"detail": 3}}]}
        )
        one, two = lod_raw(spec, 1), lod_raw(spec, 2)
        self.assertEqual(one["id"], "sculpt_clay_urn_lod1")
        self.assertEqual((one["params"]["max_triangles"], one["qa"]["max_triangles"]), (2400, 2400))
        self.assertEqual((two["params"]["max_triangles"], two["params"]["detail"]), (900, 3))
        self.assertEqual(one["textures"], {"texels_per_metre": 256.0, "max_size": 512})
        self.assertEqual(two["textures"], {"texels_per_metre": 128.0, "max_size": 256})
        self.assertNotIn("lods", one)

    def test_levels_must_get_lighter(self) -> None:
        with self.assertRaisesRegex(SpecError, r"lods\[1\].max_triangles"):
            self._spec({"lods": [{"max_triangles": 2400}, {"max_triangles": 3000}]})

    def test_texture_density_parses_and_bounds_the_maps(self) -> None:
        self.assertEqual(self._spec({"textures": {"texels_per_metre": 1024, "max_size": 4096}}).textures,
                         TextureSpec(1024.0, 4096))  # fmt: skip
        with self.assertRaisesRegex(SpecError, "max_size"):
            self._spec({"textures": {"max_size": 3000}})
        if np is None:
            return
        from assetkit.texbake import texture_size

        v = np.array([[0, 0, 0], [4, 0, 0], [0, 4, 0]], dtype=float)
        uv = np.array([[[0, 0], [1, 0], [0, 1]]], dtype=float)
        self.assertEqual(texture_size(v, np.array([[0, 1, 2]]), uv, 512, 1024), 1024)
        self.assertEqual(texture_size(v, np.array([[0, 1, 2]]), uv, 512, 4096), 2048)


@unittest.skipIf(np is None, "needs numpy")
class RigCheckTests(unittest.TestCase):
    def test_an_arm_fused_down_the_side_is_found(self) -> None:
        from assetkit import sdf
        from assetkit.rig import Bone
        from assetkit.skinning import bind, glued_limbs

        body = sdf.capsule((0, 0, 0.2), (0, 0, 1.0), 0.15)
        found = {}
        for gap in (0.0, 0.12):
            arm = sdf.capsule((0.15 + gap, 0, 0.95), (0.2 + gap, 0, 0.45), 0.04)
            v, f = sdf.mesh(sdf.smooth_union(body, arm, 0.06), 3000)
            v, f = np.asarray(v), np.asarray(f)
            bones = [
                Bone("body", (0, 0, 0.2), (0, 0, 1.0), None),
                Bone("arm", arm_ends(gap)[0], arm_ends(gap)[1], "body"),
            ]
            skin = bind(
                v, {"body": [body], "arm": [arm]}, {}, 0.02, parents={"body": None, "arm": "body"}, faces=f
            )
            found[gap] = glued_limbs(v, f, skin, bones)
        self.assertEqual([(a, b) for a, b, _ in found[0.0]], [("arm", "body")])
        self.assertGreater(found[0.0][0][2], 0.6)
        self.assertEqual(found[0.12], [])

    def test_a_walk_that_barely_moves_is_flagged(self) -> None:
        from assetkit.skinning import clip_flags

        report = {"clip": "Walk", "moves_m": 0.02, "sinks_m": 0.0, "stretch_max": 1.1, "stretch_min": 0.9,
                  "strained_edges": 0, "edges": 100, "where": [], "quarter_step": 0.03}  # fmt: skip
        self.assertTrue(any("barely moves" in f for f in clip_flags(report)))
        self.assertFalse(any("barely moves" in f for f in clip_flags({**report, "quarter_step": 0.14})))
        self.assertFalse(any("barely moves" in f for f in clip_flags({**report, "clip": "Idle"})))


def arm_ends(gap: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (0.15 + gap, 0.0, 0.95), (0.2 + gap, 0.0, 0.45)


if __name__ == "__main__":
    unittest.main()
