"""Mechanisms and cloth in assemblies (bones, spin, wave, the sheet piece), tileable patterns
and bricks, z-fighting, kits of tiles, and the faster crease search.

    python -m unittest discover tests

The parsing and rig tests need only the standard library; the rest need numpy.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assetkit.assembly import build_pieces  # noqa: E402
from assetkit.motion import MotionError, build_clip  # noqa: E402
from assetkit.rig import Bone, Skeleton, length, sub  # noqa: E402
from blender.lib.spec import load_spec  # noqa: E402

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None

SPECS = REPO_ROOT / "assets" / "specs"


def _build(asset_id: str) -> object:
    from blender.generators import prop_assembly

    return prop_assembly.build(load_spec(SPECS / f"{asset_id}.json"))


class SheetTests(unittest.TestCase):
    def test_a_sheet_is_a_closed_thin_panel(self) -> None:
        from tests.test_assembly import _closed_outward

        pieces = build_pieces(
            [{"sheet": {"size": [0.8, 1.2], "thickness": 0.01, "divisions": [4, 6]}, "slot": "cloth"}],
            {},
            "p",
        )
        self.assertEqual(len(pieces), 1)
        shell = pieces[0][0]
        self.assertAlmostEqual(_closed_outward(self, shell), 0.8 * 1.2 * 0.01, places=9)
        xs = [v[0] for v in shell[0]]
        zs = [v[2] for v in shell[0]]
        self.assertAlmostEqual(min(xs), -0.4)
        self.assertAlmostEqual(max(zs), 0.6)


class MechanismTests(unittest.TestCase):
    def _wheel(self) -> Skeleton:
        return Skeleton([Bone("frame", (0, 0, 0), (0, 0, 0.3)), Bone("axle", (0, 0, 1), (1, 0, 1), "frame")])

    def test_spin_turns_steadily_about_the_bone(self) -> None:
        skeleton = self._wheel()
        clip = build_clip(
            "Turn", {"seconds": 1, "motions": [{"spin": {"bone": "axle", "turns": 1}}]}, skeleton, {}, 24, "c"
        )
        rim = (0.5, 0.0, 1.5)  # half a metre above the axle
        quarter = clip.frames[6]["axle"].apply(rim)  # a quarter turn about the axle (+x)
        self.assertAlmostEqual(quarter[0], 0.5, places=9)
        self.assertAlmostEqual(abs(quarter[1]), 0.5, places=9)
        self.assertAlmostEqual(quarter[2], 1.0, places=9)
        # Every step is the same size, and the loop's last step back to the start too.
        points = [f["axle"].apply(rim) for f in clip.frames]
        steps = [length(sub(points[i], points[i - 1])) for i in range(len(points))]
        self.assertLess(max(steps) - min(steps), 1e-9)

    def test_a_looping_spin_needs_whole_turns(self) -> None:
        with self.assertRaisesRegex(MotionError, "whole turns"):
            build_clip(
                "Turn",
                {"seconds": 1, "motions": [{"spin": {"bone": "axle", "turns": 0.5}}]},
                self._wheel(),
                {},
                24,
                "c",
            )

    def test_a_wave_runs_down_the_chain(self) -> None:
        skeleton = Skeleton(
            [
                Bone("pole", (0, 0, 0), (0, 0, 2)),
                Bone("c1", (0.5, 0, 2), (0.5, 0, 1.5), "pole"),
                Bone("c2", (0.5, 0, 1.5), (0.5, 0, 1.0), "c1"),
            ]
        )
        clip = build_clip(
            "Sway",
            {"seconds": 1, "motions": [{"wave": {"bones": ["c1", "c2"], "pitch": 10, "lag": 0.25}}]},
            skeleton,
            {},
            24,
            "c",
        )
        tip = (0.5, 0.0, 1.0)
        swing = [f["c2"].apply(tip)[1] for f in clip.frames]
        self.assertGreater(max(swing) - min(swing), 0.05)  # the free end swings

        # Each bone's own bend (its swing against the bone above) peaks a quarter cycle (6 frames)
        # after the one before it.
        def angle(f: dict, name: str) -> float:
            head, tail = f[name].apply(skeleton[name].head), f[name].apply(skeleton[name].tail)
            return math.atan2(tail[1] - head[1], head[2] - tail[2])

        bend = {
            "c1": [angle(f, "c1") for f in clip.frames],
            "c2": [angle(f, "c2") - angle(f, "c1") for f in clip.frames],
        }
        peak = {name: max(range(24), key=lambda i, b=b: b[i]) for name, b in bend.items()}
        self.assertEqual((peak["c2"] - peak["c1"]) % 24, 6)


class AssemblyRigTests(unittest.TestCase):
    def test_a_wheel_is_bound_rigidly_and_its_frame_stays(self) -> None:
        asset = _build("prop_mill_waterwheel")
        part = asset.parts[0]  # type: ignore[attr-defined]
        skin = part.skin
        wheel = skin.bones.index("wheel")
        on_wheel = [w for idx, w in zip(skin.indices, skin.weights, strict=True) if idx == (wheel,)]
        self.assertGreater(len(on_wheel), len(skin.indices) // 2)
        self.assertTrue(all(len(idx) == 1 for idx in skin.indices))  # rigid: one bone per vertex
        self.assertEqual({c.name for c in asset.clips}, {"Turn", "Flood"})  # type: ignore[attr-defined]

    def test_cloth_is_bound_smoothly_down_its_chain(self) -> None:
        asset = _build("prop_hanging_banner")
        part = asset.parts[0]  # type: ignore[attr-defined]
        skin, verts = part.skin, part.mesh.vertices
        names = skin.bones
        cloth = [i for i, idx in enumerate(skin.indices) if any(names[b].startswith("cloth") for b in idx)]
        self.assertTrue(cloth)
        top = max(cloth, key=lambda i: verts[i][2])
        bottom = min(cloth, key=lambda i: verts[i][2])

        def main(i: int) -> str:
            k = max(range(len(skin.weights[i])), key=lambda j: skin.weights[i][j])
            return names[skin.indices[i][k]]

        self.assertEqual(main(top), "cloth1")
        self.assertEqual(main(bottom), "cloth6")
        self.assertTrue(any(len(skin.indices[i]) > 1 for i in cloth))  # blended between bones


@unittest.skipIf(np is None, "needs numpy")
class TilingTests(unittest.TestCase):
    LAYERS = [
        {"mottle": {"color": [1, 0, 0], "scale": 3.3, "stretch": [1, 1, 3]}},
        {"grain": {"color": [1, 0, 0], "spacing": 0.07, "axis": "x"}},
        {"spots": {"color": [1, 0, 0], "size": 0.05}},
        {"gradient": {"color": [1, 0, 0], "from": 0, "to": 1, "breakup": 0.5}},
        {"facing": {"color": [1, 0, 0], "breakup": 0.5}},
        {"cells": {"color": [1, 0, 0], "size": 0.13, "fill": 0.5}},
        {"bricks": {"color": [1, 0, 0], "size": [0.23, 0.075], "fill": 0.6}},
    ]

    def _points(self) -> tuple:
        rng = np.random.default_rng(2)
        p = rng.uniform(-3, 3, (20000, 3))
        n = rng.normal(size=(20000, 3))
        n /= np.linalg.norm(n, axis=1)[:, None]
        return p, n, rng.normal(size=20000), lambda radius, outward: np.zeros(len(p))

    def test_every_layer_repeats_after_its_period(self) -> None:
        from assetkit.material import _mask, parse_pattern

        p, n, bend, creases = self._points()
        pattern = parse_pattern({"period": [2, 1.5, 0], "layers": self.LAYERS}, "p")
        for layer in pattern.layers:
            here = _mask(layer, p, bend, n, creases)
            np.testing.assert_allclose(
                _mask(layer, p + [2, 0, 0], bend, n, creases), here, atol=1e-9, err_msg=layer.kind
            )
            np.testing.assert_allclose(
                _mask(layer, p + [0, -3, 0], bend, n, creases), here, atol=1e-9, err_msg=layer.kind
            )

    def test_without_a_period_nothing_repeats_by_accident(self) -> None:
        from assetkit.material import _mask, parse_pattern

        p, n, bend, creases = self._points()
        layer = parse_pattern({"layers": self.LAYERS[:1]}, "p").layers[0]
        self.assertGreater(
            np.abs(_mask(layer, p + [2, 0, 0], bend, n, creases) - _mask(layer, p, bend, n, creases)).max(),
            0.1,
        )

    def test_periodic_noise_wraps_its_lattice(self) -> None:
        from assetkit.noise import noise, noise_array

        rng = np.random.default_rng(0)
        p = rng.uniform(-50, 50, (2000, 3))
        np.testing.assert_array_equal(noise_array(p[:, 0], p[:, 1], p[:, 2]), [noise(*q) for q in p])
        a = noise_array(p[:, 0], p[:, 1], p[:, 2], (7, 0, 5))
        b = noise_array(p[:, 0] + 7, p[:, 1], p[:, 2] - 15, (7, 0, 5))
        np.testing.assert_allclose(a, b, atol=1e-12)

    def test_bricks_show_a_running_bond_on_every_wall_face(self) -> None:
        from assetkit.material import _mask, parse_pattern

        layer = parse_pattern(
            {"layers": [{"bricks": {"color": [0, 0, 0], "size": [0.24, 0.075], "mortar": 0.01}}]}, "p"
        ).layers[0]
        creases = lambda radius, outward: np.zeros(4000)  # noqa: E731
        rng = np.random.default_rng(3)
        for normal in ((0, -1, 0), (1, 0, 0)):
            p = rng.uniform(-1, 1, (4000, 3))
            axis = int(np.argmax(np.abs(normal)))
            p[:, axis] = 0.12  # a face lying in a joint plane still shows bricks, not solid mortar
            n = np.tile(np.asarray(normal, dtype=float), (4000, 1))
            share = _mask(layer, p, np.zeros(4000), n, creases).mean()
            self.assertAlmostEqual(share, 0.01 / 0.075 + 0.01 / 0.24, delta=0.04)

    def test_bricks_parse_their_size(self) -> None:
        from assetkit.material import PatternError, parse_pattern

        with self.assertRaisesRegex(PatternError, r"layers\[0\].bricks.size"):
            parse_pattern({"layers": [{"bricks": {"color": [0, 0, 0], "size": 0.2}}]}, "p")
        with self.assertRaisesRegex(PatternError, "period"):
            parse_pattern(
                {"period": [1, 2], "layers": [{"bricks": {"color": [0, 0, 0], "size": [0.2, 0.1]}}]}, "p"
            )


@unittest.skipIf(np is None, "needs numpy")
class CreaseTests(unittest.TestCase):
    def test_the_grid_search_matches_brute_force(self) -> None:
        from assetkit.material import Surface, _smoothstep

        rng = np.random.default_rng(5)
        verts, faces = [], []
        for _ in range(40):
            c, s = rng.uniform(-1, 1, 3), rng.uniform(0.02, 0.4, 3)
            base = len(verts)
            verts += [
                [c[0] + x * s[0], c[1] + y * s[1], c[2] + z * s[2]]
                for x in (-1, 1)
                for y in (-1, 1)
                for z in (-1, 1)
            ]
            quads = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
            faces += [[base + q[0], base + q[1], base + q[2]] for q in quads] + [
                [base + q[0], base + q[2], base + q[3]] for q in quads
            ]
        surface = Surface(np.asarray(verts), np.asarray(faces))
        points = rng.uniform(-1.2, 1.2, (3000, 3))
        for radius in (0.004, 0.08, 0.5):
            got = surface.near_creases(points, radius, True)
            pick = surface.crease_convex
            a, b, w = surface.crease_a[pick], surface.crease_b[pick], surface.crease_strength[pick]
            d = b - a
            t = np.clip(((points[:, None] - a) * d).sum(axis=2) / (d * d).sum(axis=1), 0, 1)
            dist = np.linalg.norm(points[:, None] - (a + t[..., None] * d), axis=2)
            want = ((1 - _smoothstep(0.0, radius, dist)) * w).max(axis=1)
            np.testing.assert_allclose(got, want, atol=1e-12)


def _box(lo: tuple, hi: tuple) -> tuple:
    v = [[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    quads = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return v, [[q[0], q[1], q[2]] for q in quads] + [[q[0], q[2], q[3]] for q in quads]


@unittest.skipIf(np is None, "needs numpy")
class LookTests(unittest.TestCase):
    def _model(self, *boxes: tuple) -> object:
        from assetview.model import ViewModel

        verts, tris = [], []
        for lo, hi in boxes:
            v, f = _box(lo, hi)
            tris += [[len(verts) + i for i in t] for t in f]
            verts += v
        t = np.asarray(tris)
        return ViewModel(
            positions=np.asarray(verts, dtype=float),
            triangles=t,
            tri_slot=np.zeros(len(t), dtype=np.int64),
            slots=["a"],
            slot_colors=np.ones((1, 3)),
            real_edges=np.ones((len(t), 3), dtype=bool),
            source="test",
        )

    def test_flush_faces_of_two_parts_are_z_fighting(self) -> None:
        from assetview.measure import measure

        # A plate flush with the front of a block: both fronts at y = 0, facing -y.
        flush = measure(self._model(((0, 0, 0), (1, 1, 1)), ((0.2, 0, 0.2), (0.6, 0.05, 0.6))))
        self.assertAlmostEqual(flush["coplanar_overlap"]["area_m2"], 0.16, places=6)  # type: ignore[index]
        # Proud by 2 mm: fine. Stacked (faces meet back to back): fine.
        proud = measure(self._model(((0, 0, 0), (1, 1, 1)), ((0.2, -0.002, 0.2), (0.6, 0.05, 0.6))))
        stacked = measure(self._model(((0, 0, 0), (1, 1, 1)), ((0.2, 0.2, 1), (0.6, 0.6, 1.5))))
        self.assertIsNone(proud["coplanar_overlap"])
        self.assertIsNone(stacked["coplanar_overlap"])

    def test_a_narrow_worn_edge_registers_on_a_large_flat_face(self) -> None:
        from assetkit.material import parse_pattern
        from assetkit.texbake import SlotLook
        from assetview.paint import PatternPaint

        m = self._model(((0, 0, 0), (2, 2, 2)))
        look = SlotLook(
            parse_pattern({"layers": [{"edges": {"color": [1, 1, 1], "radius": 0.005}}]}, "p"), (0, 0, 0), 0.5
        )
        paint = PatternPaint(m.positions, m.triangles, m.tri_slot, [look], [(0, 0, 0)])
        share = paint.report(["a"])[0]["layers"][0]["covers"]
        self.assertAlmostEqual(
            share, 4 * 0.005 / 2 * 0.5, delta=0.004
        )  # four edges per face, half-strength fade


@unittest.skipIf(np is None, "needs numpy")
class KitTests(unittest.TestCase):
    def _joints(self, place: list, specs: dict | None = None) -> list:
        from assetview.kit import joints, load_kit

        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = Path(tmp)
            for f in SPECS.glob("tile_brick_*.json"):
                (spec_dir / f.name).write_text(f.read_text())
            for name, spec in (specs or {}).items():
                (spec_dir / f"{name}.json").write_text(json.dumps(spec))
            kit = spec_dir / "kit.json"
            kit.write_text(json.dumps({"place": place}))
            return joints(load_kit(kit, spec_dir, spec_dir))

    def test_the_example_wall_run_meets_cleanly(self) -> None:
        from assetview.kit import STEP_FLAG

        found = self._joints(
            json.loads((REPO_ROOT / "assets" / "kits" / "brick_wall_run.json").read_text())["place"]
        )
        self.assertEqual(len(found), 3)
        for j in found:
            self.assertEqual(j["gap_m"], 0.0)
            self.assertLess(j["pattern_step"], STEP_FLAG)

    def test_gaps_overlaps_and_unrepeated_patterns_are_reported(self) -> None:
        spec = json.loads((SPECS / "tile_brick_wall.json").read_text())
        for m in spec["materials"].values():
            m["pattern"].pop("period")
        spec["id"] = "loose_tile"
        found = self._joints(
            [
                {"asset": "loose_tile", "at": [0, 0, 0]},
                {"asset": "loose_tile", "at": [2.003, 0, 0]},
                {"asset": "tile_brick_wall", "at": [0, 3, 0]},
                {"asset": "tile_brick_wall", "at": [1.99, 3, 0]},
            ],
            {"loose_tile": spec},
        )
        by_pair = {tuple(j["between"]): j for j in found}
        loose = by_pair[("loose_tile#1", "loose_tile#2")]
        self.assertAlmostEqual(loose["gap_m"], 0.003, places=4)
        self.assertGreater(loose["pattern_step"], 0.05)
        overlap = by_pair[("tile_brick_wall#3", "tile_brick_wall#4")]
        self.assertAlmostEqual(overlap["gap_m"], -0.01, places=4)


if __name__ == "__main__":
    unittest.main()
