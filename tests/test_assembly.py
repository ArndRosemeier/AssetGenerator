"""Hard-surface props as JSON pieces, the new sculpt operations, exact clip lengths and limps,
clips read back from a .glb, and the new pattern layers.

    python -m unittest discover tests

The assembly tests need only the standard library; the rest need numpy (skipped without it).
"""

from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assetkit.assembly import AssemblyError, bevelled_triangles, build_pieces  # noqa: E402

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None


def _closed_outward(test: unittest.TestCase, shell: tuple) -> float:
    """Every edge shared by exactly two faces, in opposite directions; returns the volume."""
    verts, faces = shell
    directed: Counter = Counter()
    for face in faces:
        for k in range(len(face)):
            directed[(face[k], face[(k + 1) % len(face)])] += 1
    for (a, b), n in directed.items():
        test.assertEqual(n, 1, f"edge {a}-{b} used {n} times the same way")
        test.assertEqual(directed.get((b, a), 0), 1, f"edge {a}-{b} has no opposite")
    volume = 0.0
    for face in faces:
        a = verts[face[0]]
        for k in range(1, len(face) - 1):
            b, c = verts[face[k]], verts[face[k + 1]]
            volume += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6
    return volume


class AssemblyTests(unittest.TestCase):
    def test_every_shape_is_closed_and_outward_with_the_right_volume(self) -> None:
        cases = [
            ({"box": {"size": [0.2, 0.1, 0.4]}}, 0.2 * 0.1 * 0.4, 1e-9),
            (
                {"cylinder": {"a": [0, 0, 0], "b": [0.3, 0.1, 0.2], "radius": 0.05}},
                math.pi * 0.05**2 * math.sqrt(0.14),
                0.03,
            ),
            (
                {"cylinder": {"a": [0, 0, 0], "b": [0, 0, 0.3], "radius": 0.1, "radius_b": 0.0}},
                math.pi * 0.01 * 0.1,
                0.03,
            ),
            ({"sphere": {"centre": [1, 2, 3], "radius": 0.1}}, 4 / 3 * math.pi * 0.001, 0.05),
            (
                {"torus": {"centre": [0, 0, 0], "radius": 0.1, "thickness": 0.02, "axis": "y"}},
                2 * math.pi**2 * 0.1 * 0.01**2,
                0.05,
            ),
            ({"lathe": {"profile": [[0.1, 0], [0.1, 0.2]]}}, math.pi * 0.01 * 0.2, 0.03),
            ({"tube": {"path": [[0, 0, 0], [0.1, 0, 0.1], [0.2, 0, 0]], "radius": 0.01}}, None, 0),
            (
                {
                    "extrude": {
                        "outline": [[0, 0], [0.1, 0], [0.1, 0.1], [0.05, 0.05], [0, 0.1]],
                        "height": 0.02,
                    }
                },
                0.0075 * 0.02,
                1e-9,
            ),
            (
                {
                    "extrude": {
                        "outline": [[0, 0.1], [0.05, 0.05], [0.1, 0.1], [0.1, 0], [0, 0]],
                        "height": 0.02,
                    }
                },
                0.0075 * 0.02,
                1e-9,
            ),
        ]
        for node, volume, tolerance in cases:
            with self.subTest(shape=next(iter(node))):
                ((shell, slot, _, _),) = build_pieces([{**node, "slot": "iron"}], {}, "p")
                self.assertEqual(slot, "iron")
                got = _closed_outward(self, shell)
                self.assertGreater(got, 0)
                if volume is not None:
                    self.assertAlmostEqual(got / volume, 1.0, delta=tolerance + 1e-6)

    def test_placing_repeating_and_mirroring(self) -> None:
        post = {"box": {"size": [0.02, 0.02, 0.3]}, "at": [0.1, 0, 0.15], "slot": "iron"}
        around = build_pieces([{**post, "repeat": {"around": 4, "start": 45}}], {}, "p")
        self.assertEqual(len(around), 4)
        centres = sorted(
            (round(sum(v[0] for v in s[0]) / 8, 4), round(sum(v[1] for v in s[0]) / 8, 4))
            for s, _, _, _ in around
        )
        r = 0.1 / math.sqrt(2)
        self.assertEqual(
            centres, sorted([(round(x * r, 4), round(y * r, 4)) for x in (-1, 1) for y in (-1, 1)])
        )
        row = build_pieces([{**post, "repeat": {"count": 3, "step": [0, 0.1, 0]}, "mirror": "x"}], {}, "p")
        self.assertEqual(len(row), 6)
        for shell, _, _, _ in row:
            self.assertGreater(_closed_outward(self, shell), 0)  # mirrored copies stay outward
        flipped = build_pieces([{**post, "scale": [-1, 1, 1]}], {}, "p")
        self.assertGreater(_closed_outward(self, flipped[0][0]), 0)

    def test_groups_refs_and_slots(self) -> None:
        parts = {"rivet": {"sphere": {"centre": [0, 0, 0], "radius": 0.005}, "slot": "iron"}}
        pieces = build_pieces(
            [
                {
                    "group": [{"ref": "rivet", "at": [0.1, 0, 0]}, {"box": {"size": [0.1, 0.1, 0.01]}}],
                    "slot": "wood",
                    "at": [0, 0, 1],
                }
            ],
            parts,
            "p",
        )
        self.assertEqual([slot for _, slot, _, _ in pieces], ["iron", "wood"])
        self.assertAlmostEqual(min(v[2] for v in pieces[0][0][0]), 0.995, places=6)

    def test_only_pieces_thick_enough_are_bevelled(self) -> None:
        pieces = build_pieces(
            [
                {"box": {"size": [0.1, 0.1, 0.1]}, "slot": "a"},
                {"sphere": {"centre": [0, 0, 0], "radius": 0.004}, "slot": "a"},
                {"sphere": {"centre": [0, 0, 0], "radius": 0.004}, "slot": "a", "bevel": True},
            ],
            {},
            "p",
            bevel=0.002,
        )
        self.assertEqual([b for _, _, b, _ in pieces], [True, False, True])

    def test_the_bevel_estimate_counts_strips_and_corners(self) -> None:
        from assetkit import MeshBuilder

        builder = MeshBuilder(["a"])
        builder.add_box_bounds((0, 0, 0), (1, 1, 1), "a")
        mesh = builder.build()
        self.assertEqual(bevelled_triangles(mesh), 12 * 2 + 8 * 2)
        self.assertEqual(bevelled_triangles(mesh, [0.0] * 8), 0)

    def test_mistakes_name_their_place(self) -> None:
        cases = [
            ([{"box": {"size": [1, 1, 1]}}], "p[0]: missing 'slot'"),
            ([{"box": {"size": [1, 1, 1]}, "cylinder": {}, "slot": "a"}], "exactly one shape"),
            (
                [{"cylinder": {"a": [0, 0, 0], "b": [0, 0, 0], "radius": 1}, "slot": "a"}],
                "`a` and `b` must differ",
            ),
            ([{"ref": "nope", "slot": "a"}], "no part named 'nope'"),
            (
                [{"box": {"size": [1, 1, 1]}, "slot": "a", "repeat": {"count": 0, "step": [0, 0, 1]}}],
                "p[0].repeat.count",
            ),
            ([{"torus": {"centre": [0, 0, 0], "radius": 0.01, "thickness": 0.05}, "slot": "a"}], "thickness"),
            ([{"box": {"size": [1, 1, 1]}, "slot": "a", "spin": 3}], "unknown key(s) ['spin']"),
        ]
        for pieces, message in cases:
            with self.subTest(message=message), self.assertRaises(AssemblyError) as caught:
                build_pieces(pieces, {}, "p")
            self.assertIn(message, str(caught.exception))

    def test_the_lantern_spec_builds_within_its_budget(self) -> None:
        from blender.generators import prop_assembly
        from blender.lib.spec import load_spec

        spec = load_spec(REPO_ROOT / "assets" / "specs" / "prop_crypt_lantern.json")
        asset = prop_assembly.build(spec)
        mesh = asset.parts[0].mesh
        self.assertEqual(set(mesh.slots), {"iron", "glass", "wax"})
        lower, upper = mesh.bounds()
        self.assertTrue(0.45 <= upper[2] - lower[2] <= 0.55)
        expected = mesh.triangle_count() + bevelled_triangles(mesh, mesh.point_attributes["bevel"])
        self.assertLessEqual(expected, spec.qa.max_triangles)
        self.assertLess(spec.materials["glass"].alpha, 1.0)


@unittest.skipIf(np is None, "numpy is not installed")
class SculptTests(unittest.TestCase):
    def test_a_cone_has_the_volume_of_a_frustum(self) -> None:
        from assetkit import sdf

        verts, faces = sdf.mesh(sdf.cone((0, 0, 0), (0, 0, 0.3), 0.1, 0.04), 2000)
        v, f = np.asarray(verts), np.asarray(faces)
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        volume = float((a * np.cross(b, c)).sum() / 6)
        self.assertAlmostEqual(volume / (math.pi * 0.3 / 3 * (0.01 + 0.004 + 0.0016)), 1.0, delta=0.02)

    def test_repeat_rotate_about_and_scatter(self) -> None:
        from assetkit.sculpt import build_shape

        ring = build_shape(
            {"repeat": {"around": 6, "shape": {"sphere": {"centre": [0.5, 0, 0], "radius": 0.05}}}}, {}, "s"
        )
        angles = np.radians(np.arange(6) * 60.0)
        on = np.stack([0.5 * np.cos(angles), 0.5 * np.sin(angles), np.zeros(6)], axis=1)
        self.assertTrue(np.allclose(ring(on), -0.05, atol=1e-9))
        tilted = build_shape(
            {
                "rotate": {
                    "degrees": [0, 0, 90],
                    "about": [1, 0, 0],
                    "shape": {"sphere": {"centre": [2, 0, 0], "radius": 0.1}},
                }
            },
            {},
            "s",
        )
        self.assertAlmostEqual(float(tilted(np.array([[1.0, 1.0, 0.0]]))[0]), -0.1, places=9)
        rock = {"box": {"centre": [0, 0, 0.2], "size": [1, 1, 0.4]}}
        spikes = build_shape(
            {
                "scatter": {
                    "on": rock,
                    "shape": {"cone": {"a": [0, 0, 0], "b": [0, 0, 0.1], "radius": 0.02, "radius_b": 0}},
                    "count": 5,
                    "seed": 1,
                    "spacing": 0.2,
                    "angle": 10,
                    "at": [[0, 0]],
                }
            },
            {},
            "s",
        )
        # Six spikes standing on the top face (z = 0.4): a slice just above it cuts six discs.
        grid = np.array(
            [[x, y, 0.405] for x in np.arange(-0.5, 0.5, 0.004) for y in np.arange(-0.5, 0.5, 0.004)]
        )
        inside = grid[spikes(grid) < 0][:, :2]
        clusters: list[np.ndarray] = []
        for point in inside:
            if not any(np.hypot(*(point - c)) < 0.05 for c in clusters):
                clusters.append(point)
        self.assertEqual(len(clusters), 6)
        self.assertTrue(any(np.hypot(*c) < 0.03 for c in clusters))  # the one set `at` the centre

    def test_batched_simplification_keeps_a_closed_outward_mesh(self) -> None:
        from assetkit import sdf
        from assetkit.simplify import simplify

        ball = sdf.sphere((0, 0, 0), 0.3)
        lower, upper = np.array(ball.lower), np.array(ball.upper)
        verts, faces = sdf._march(ball, lower, upper, 0.01)  # some 25 000 triangles: batches run
        self.assertGreater(len(faces), 20000)
        v, f = simplify(verts, faces, 800)
        self.assertLessEqual(len(f), 800)
        volume = _closed_outward(self, (v.tolist(), f.tolist()))
        self.assertAlmostEqual(volume / (4 / 3 * math.pi * 0.3**3), 1.0, delta=0.05)
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        self.assertGreater(float(np.linalg.norm(np.cross(b - a, c - a), axis=1).min()), 1e-9)

    def test_thin_limbs_keep_their_roundness(self) -> None:
        """A 1.2 cm rod on a 16 cm ball: with meshing weighed by thickness and refined, the
        rod has enough sides that its section is near round."""
        from assetkit import sdf

        shape = sdf.union(sdf.sphere((0, 0, 0.08), 0.08), sdf.capsule((0, 0, 0.1), (0, 0, 0.4), 0.012))
        verts, faces = sdf.mesh(shape, 600)
        v = np.asarray(verts)
        rod = v[(v[:, 2] > 0.18) & (v[:, 2] < 0.37)]
        sides = len({round(float(np.degrees(np.arctan2(y, x))) / 15) for x, y, _ in rod})
        self.assertGreaterEqual(sides, 7)  # vertices at seven or more of 24 bearings round it
        radius = np.sqrt(rod[:, 0] ** 2 + rod[:, 1] ** 2)
        self.assertLess(float(np.abs(radius - 0.012).max()), 0.002)


class ClipTests(unittest.TestCase):
    def test_clips_last_exactly_their_seconds(self) -> None:
        from assetkit.motion import pick_fps
        from assetkit.rig import Bone, Skeleton

        self.assertEqual(pick_fps([3.0, 1.2, 0.9]), 30)
        self.assertEqual(pick_fps([1.0, 0.5]), 24)
        self.assertIsNone(pick_fps([0.123]))
        skeleton = Skeleton((Bone("root", (0, 0, 0), (0, 0, 1)),))
        from assetkit.motion import MotionError, build_clip

        loop = build_clip(
            "Spin",
            {"seconds": 1.2, "motions": [{"turn": {"bone": "root", "yaw": 10}}]},
            skeleton,
            {},
            30,
            "c",
        )
        once = build_clip(
            "Nod",
            {"seconds": 0.9, "loop": False, "motions": [{"turn": {"bone": "root", "yaw": 10}}]},
            skeleton,
            {},
            30,
            "c",
        )
        self.assertAlmostEqual(loop.seconds, 1.2)
        self.assertAlmostEqual(once.seconds, 0.9)
        with self.assertRaises(MotionError) as caught:
            build_clip(
                "Nod",
                {"seconds": 0.9, "motions": [{"turn": {"bone": "root", "yaw": 10}}]},
                skeleton,
                {},
                24,
                "c",
            )
        self.assertIn("give the rig an `fps` that fits (30", str(caught.exception))

    def test_a_limp_keeps_every_planted_foot_at_the_bodys_pace(self) -> None:
        from assetkit.motion import build_clip
        from assetkit.rig import Bone, Leg, Skeleton

        skeleton = Skeleton.with_twins(
            (
                Bone("hips", (0, 0, 0.9), (0, 0, 1.0)),
                Bone("thigh.L", (0.1, 0, 0.9), (0.1, -0.03, 0.5), "hips"),
                Bone("shin.L", (0.1, -0.03, 0.5), (0.1, 0, 0.1), "thigh.L"),
            )
        )
        legs = {"leg.L": Leg("thigh.L", "shin.L"), "leg.R": Leg("thigh.R", "shin.R")}
        clip = build_clip(
            "Limp",
            {
                "seconds": 1.0,
                "motions": [
                    {
                        "gait": {
                            "legs": {"leg.L": 0, "leg.R": 0.55},
                            "stride": 0.3,
                            "duty": 0.66,
                            "per_leg": {"leg.R": {"lift": 0.01, "duty": 0.5}},
                        }
                    }
                ],
            },
            skeleton,
            legs,
            30,
            "c",
        )
        speeds = {}
        for side in ("L", "R"):
            tips = [frame[f"shin.{side}"].apply(skeleton[f"shin.{side}"].tail) for frame in clip.frames]
            planted = [
                tips[k + 1][1] - tips[k][1]
                for k in range(len(tips) - 1)
                if abs(tips[k][2] - 0.1) < 1e-6 and abs(tips[k + 1][2] - 0.1) < 1e-6
            ]
            speeds[side] = sorted(round(d, 6) for d in planted)
        self.assertTrue(speeds["L"] and speeds["R"])
        self.assertAlmostEqual(
            speeds["L"][len(speeds["L"]) // 2], speeds["R"][len(speeds["R"]) // 2], places=5
        )

    def test_clips_read_back_from_a_glb(self) -> None:
        from blender.lib.glb import Glb

        times = [0.0, 0.5, 1.2]
        closed = [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.7071, 0.7071), (0.0, 0.0, 0.0, -1.0)]  # q and -q
        opened = [(0.0, 0.0, 0.0), (0.0, 0.1, 0.0), (0.0, 0.2, 0.0)]
        path = Path(tempfile.mkdtemp()) / "clips.glb"
        _write_glb(path, times, closed, opened)
        clips = {c["name"]: c for c in Glb(path).clips()}
        self.assertAlmostEqual(clips["Turn"]["seconds"], 1.2, places=6)
        self.assertTrue(clips["Turn"]["closed"] and clips["Turn"]["moves"])
        self.assertFalse(clips["Slide"]["closed"])


@unittest.skipIf(np is None, "numpy is not installed")
class LayerTests(unittest.TestCase):
    def test_facing_and_cells(self) -> None:
        from assetkit import sdf
        from assetkit.material import Surface, coverage, parse_pattern

        v, f = sdf.mesh(sdf.sphere((0, 0, 0), 0.3), 3000)
        surface = Surface(v, f)
        rng = np.random.default_rng(1)
        a = np.asarray(v)[np.asarray(f)]
        area = 0.5 * np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1)
        tri = rng.integers(0, len(f), 20000)
        bary = rng.dirichlet((1, 1, 1), 20000)
        pattern = parse_pattern(
            {
                "layers": [
                    {"facing": {"color": [0, 1, 0], "angle": 45, "soft": 0.001}},
                    {"facing": {"color": [0, 1, 0], "direction": [0, 0, -1], "angle": 90, "soft": 0.001}},
                    {"cells": {"color": [0, 0, 0], "size": 0.1, "fill": 1.0}},
                    {"gradient": {"color": [0, 0, 0], "from": -0.3, "to": 0.3, "breakup": 0.5}},
                ]
            },
            "p",
        )
        cap, half, cells, gradient = coverage(pattern, surface, tri, bary, weights=area[tri])
        self.assertAlmostEqual(cap, (1 - math.cos(math.radians(45))) / 2, delta=0.01)
        self.assertAlmostEqual(half, 0.5, delta=0.01)
        self.assertAlmostEqual(cells, 0.5, delta=0.1)  # a random share per cell: half on average
        self.assertAlmostEqual(gradient, 0.5, delta=0.08)

    def test_where_a_clip_tears(self) -> None:
        from assetkit.skinning import clip_flags

        report = {
            "moves_m": 0.1,
            "sinks_m": 0.0,
            "stretch_max": 2.5,
            "stretch_min": 1.0,
            "strained_edges": 1,
            "edges": 100,
            "where": ["chest", "upper_arm.L"],
        }
        self.assertIn("skin tears: stretches to 2.5x at chest/upper_arm.L", clip_flags(report))


def _write_glb(path: Path, times: list, rotations: list, translations: list) -> None:
    """A minimal .glb with two animations of one node: a rotation that returns to its start
    (as its negative) and a translation that does not."""
    blob = b"".join(struct.pack("<f", t) for t in times)
    rot = b"".join(struct.pack("<4f", *q) for q in rotations)
    tra = b"".join(struct.pack("<3f", *p) for p in translations)
    binary = blob + rot + tra
    views = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(blob)},
        {"buffer": 0, "byteOffset": len(blob), "byteLength": len(rot)},
        {"buffer": 0, "byteOffset": len(blob) + len(rot), "byteLength": len(tra)},
    ]
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": 3, "type": "SCALAR"},
        {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC4"},
        {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC3"},
    ]
    doc = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": "bone"}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": accessors,
        "animations": [
            {
                "name": "Turn",
                "samplers": [{"input": 0, "output": 1}],
                "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}],
            },
            {
                "name": "Slide",
                "samplers": [{"input": 0, "output": 2}],
                "channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}],
            },
        ],
    }
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(text) + 8 + len(binary)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(text), b"JSON")
        + text
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )


if __name__ == "__main__":
    unittest.main()
