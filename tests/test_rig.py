"""Skeletons, poses, inverse kinematics, clips, skin weights and the rig JSON, without Blender.

    python -m unittest discover tests

The pose maths is standard library only; the skinning tests need numpy (skipped without it).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assetkit.motion import MotionError, build_clip  # noqa: E402
from assetkit.rig import (  # noqa: E402
    Bone,
    Leg,
    Motion,
    Pose,
    Skeleton,
    length,
    q_rotate,
    solve,
    sub,
    turn,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - CI installs numpy
    np = None


def _close(test: unittest.TestCase, a: tuple, b: tuple, places: int = 9) -> None:
    for x, y in zip(a, b, strict=True):
        test.assertAlmostEqual(x, y, places=places)


def _creature() -> tuple[Skeleton, dict[str, Leg]]:
    """A body with one bent left leg (twinned) and a head."""
    skeleton = Skeleton.with_twins(
        [
            Bone("body", (0.0, 0.2, 0.3), (0.0, -0.2, 0.3)),
            Bone("head", (0.0, -0.2, 0.32), (0.0, -0.35, 0.33), "body"),
            Bone("thigh.L", (0.1, 0.1, 0.3), (0.15, 0.0, 0.15), "body"),
            Bone("shin.L", (0.15, 0.0, 0.15), (0.15, 0.1, 0.02), "thigh.L"),
            Bone("foot.L", (0.15, 0.1, 0.02), (0.15, 0.0, 0.0), "shin.L"),
        ]
    )
    legs = {
        "hind.L": Leg("thigh.L", "shin.L", "foot.L"),
        "hind.R": Leg("thigh.R", "shin.R", "foot.R"),
    }
    return skeleton, legs


class ConventionTests(unittest.TestCase):
    """The words agents use: pitch lifts a nose (or a limb's far end), yaw turns to the
    creature's left (+X), roll lowers its right side (-X). Front is -Y, up is +Z."""

    def test_pitch_lifts_the_nose(self) -> None:
        _close(self, q_rotate(turn(pitch=90), (0.0, -1.0, 0.0)), (0.0, 0.0, 1.0))

    def test_yaw_turns_to_the_left(self) -> None:
        _close(self, q_rotate(turn(yaw=90), (0.0, -1.0, 0.0)), (1.0, 0.0, 0.0))

    def test_roll_lowers_the_right_side(self) -> None:
        _close(self, q_rotate(turn(roll=90), (-1.0, 0.0, 0.0)), (0.0, 0.0, -1.0))


class SkeletonTests(unittest.TestCase):
    def test_twins_mirror_left_bones(self) -> None:
        skeleton, _ = _creature()
        twin = skeleton["shin.R"]
        self.assertEqual(twin.parent, "thigh.R")
        _close(self, twin.head, (-0.15, 0.0, 0.15))
        self.assertEqual(len(skeleton.bones), 8)

    def test_bad_skeletons_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            Skeleton([Bone("a", (0, 0, 0), (0, 0, 1), "missing")])
        with self.assertRaises(ValueError):
            Skeleton([Bone("a", (0, 0, 0), (0, 0, 0.0001))])
        with self.assertRaises(ValueError):
            Skeleton([Bone("a", (0, 0, 0), (0, 0, 1), "b"), Bone("b", (0, 0, 1), (0, 0, 2), "a")])


class PoseTests(unittest.TestCase):
    def test_rest_pose_moves_nothing(self) -> None:
        skeleton, legs = _creature()
        ankles = {leg.upper: skeleton[leg.lower].tail for leg in legs.values()}
        motions = solve(skeleton, Pose(reach=ankles), {leg.upper: leg for leg in legs.values()})
        for name, motion in motions.items():
            _close(self, motion.rotation, (1.0, 0.0, 0.0, 0.0), places=9)
            _close(self, motion.translation, (0.0, 0.0, 0.0), places=9)
            self.assertIn(name, skeleton)

    def test_a_child_follows_its_parent(self) -> None:
        skeleton, _ = _creature()
        pose = Pose()
        pose.add_turn("body", turn(yaw=30))
        motions = solve(skeleton, pose)
        head = skeleton["head"]
        # The head did not turn itself, yet its tail swings with the body about the body's head.
        moved = motions["head"].apply(head.tail)
        expected = Motion.about(skeleton["body"].head, turn(yaw=30)).apply(head.tail)
        _close(self, moved, expected)

    def test_ik_puts_the_ankle_on_target_and_keeps_bone_lengths(self) -> None:
        skeleton, legs = _creature()
        target = (0.16, 0.04, 0.05)
        motions = solve(skeleton, Pose(reach={"thigh.L": target}), {"thigh.L": legs["hind.L"]})
        thigh, shin = skeleton["thigh.L"], skeleton["shin.L"]
        hip = motions["thigh.L"].apply(thigh.head)
        knee = motions["thigh.L"].apply(thigh.tail)
        ankle = motions["shin.L"].apply(shin.tail)
        _close(self, ankle, target)
        _close(self, motions["shin.L"].apply(shin.head), knee)
        self.assertAlmostEqual(length(sub(knee, hip)), thigh.length)
        # The foot stays level: it only moves along with the ankle.
        _close(self, motions["foot.L"].rotation, (1.0, 0.0, 0.0, 0.0))

    def test_ik_keeps_the_knee_bending_the_modelled_way(self) -> None:
        skeleton, legs = _creature()
        rest_knee = skeleton["thigh.L"].tail
        motions = solve(skeleton, Pose(reach={"thigh.L": (0.15, 0.1, 0.08)}), {"thigh.L": legs["hind.L"]})
        knee = motions["thigh.L"].apply(skeleton["thigh.L"].tail)
        # Modelled forward of the hip-ankle line (towards -Y): still forward when the leg folds.
        self.assertLess(knee[1], 0.1)
        self.assertLess(rest_knee[1], 0.1)


class ClipTests(unittest.TestCase):
    def test_a_loop_ends_where_it_begins(self) -> None:
        skeleton, legs = _creature()
        clip = build_clip(
            "Walk",
            {
                "seconds": 1.0,
                "motions": [
                    {"gait": {"legs": {"hind.L": 0.0}, "stride": 0.1, "lift": 0.03}},
                    {"turn": {"bone": "head", "yaw": 10}},
                ],
            },
            skeleton,
            legs,
            24,
            "clips.Walk",
        )
        self.assertEqual(len(clip.frames), 24)
        self.assertTrue(clip.loop)
        # No seam: stepping from the last frame back to the first is an ordinary step.
        ankle = skeleton["shin.L"].tail
        nose = skeleton["head"].tail
        path = [(f["shin.L"].apply(ankle), f["head"].apply(nose)) for f in clip.frames]
        steps = [
            max(length(sub(path[i][0], path[i - 1][0])), length(sub(path[i][1], path[i - 1][1])))
            for i in range(1, len(path))
        ]
        wrap = max(length(sub(path[0][0], path[-1][0])), length(sub(path[0][1], path[-1][1])))
        self.assertLessEqual(wrap, max(steps) * 1.01)

    def test_planted_feet_stay_on_the_ground(self) -> None:
        skeleton, legs = _creature()
        clip = build_clip(
            "Walk",
            {
                "seconds": 1.0,
                "motions": [{"gait": {"legs": {"hind.L": 0.0}, "stride": 0.1, "lift": 0.03, "duty": 0.6}}],
            },
            skeleton,
            legs,
            24,
            "clips.Walk",
        )
        rest_ankle = skeleton["shin.L"].tail
        heights = [frame["shin.L"].apply(rest_ankle)[2] for frame in clip.frames]
        planted = heights[: int(0.6 * 24)]
        for h in planted:
            self.assertAlmostEqual(h, rest_ankle[2], places=9)
        self.assertGreater(max(heights), rest_ankle[2] + 0.02)  # it lifts while it swings

    def test_errors_name_the_path(self) -> None:
        skeleton, legs = _creature()
        cases = [
            ({"seconds": 1, "motions": [{"turn": {"bone": "tail", "yaw": 5}}]}, "no bone 'tail'"),
            (
                {"seconds": 1, "motions": [{"turn": {"bone": "head", "yaw": 5, "cycles": 1.5}}]},
                "whole cycles",
            ),
            ({"seconds": 1, "motions": [{"spin": {}}]}, "unknown motion 'spin'"),
            (
                {"seconds": 1, "motions": [{"gait": {"legs": {"fore.L": 0}, "stride": 0.1}}]},
                "no leg 'fore.L'",
            ),
            ({"seconds": 1, "motions": [{"keys": {"at": [{"t": 0.5}, {"t": 0.2}]}}]}, "run forward in time"),
        ]
        for spec, message in cases:
            with self.subTest(message=message), self.assertRaises(MotionError) as caught:
                build_clip("C", spec, skeleton, legs, 24, "clips.C")
            self.assertIn(message, str(caught.exception))
            self.assertIn("clips.C", str(caught.exception))

    def test_wildcard_turns_mirror_the_right_side(self) -> None:
        skeleton = Skeleton.with_twins(
            [
                Bone("head", (0, 0, 0.3), (0, -0.1, 0.3)),
                Bone("ear.L", (0.05, 0, 0.35), (0.15, 0, 0.4), "head"),
            ]
        )
        clip = build_clip(
            "Twitch",
            {
                "seconds": 1,
                "loop": False,
                "motions": [{"turn": {"bone": "ear.*", "yaw": 20, "wave": "constant"}}],
            },
            skeleton,
            {},
            24,
            "clips.Twitch",
        )
        left = clip.frames[0]["ear.L"].apply(skeleton["ear.L"].tail)
        right = clip.frames[0]["ear.R"].apply(skeleton["ear.R"].tail)
        _close(self, right, (-left[0], left[1], left[2]))


@unittest.skipIf(np is None, "skinning needs numpy")
class SkinningTests(unittest.TestCase):
    def _bound(self) -> tuple:
        from assetkit import sdf
        from assetkit.skinning import bind

        upper = sdf.capsule((0, 0, 0.0), (0, 0, 0.5), 0.08)
        lower = sdf.capsule((0, 0, 0.5), (0, 0, 1.0), 0.07)
        shape = sdf.smooth_union(upper, lower, 0.03)
        verts, faces = sdf.mesh(shape, max_triangles=1500)
        points, tris = np.asarray(verts), np.asarray(faces)
        skeleton = Skeleton(
            [Bone("upper", (0, 0, 0.0), (0, 0, 0.5)), Bone("lower", (0, 0, 0.5), (0, 0, 1.0), "upper")]
        )
        skin = bind(
            points,
            {"upper": [upper], "lower": [lower]},
            {},
            0.02,
            parents={"upper": None, "lower": "upper"},
            faces=tris,
        )
        return skeleton, skin, points, tris

    def test_weights_are_whole_and_follow_the_parts(self) -> None:
        _, skin, points, _ = self._bound()
        for w in skin.weights:
            self.assertAlmostEqual(sum(w), 1.0, places=12)
        low = skin.bones.index("lower")
        top = np.argmax(points[:, 2])
        bottom = np.argmin(points[:, 2])
        self.assertEqual(skin.indices[top][int(np.argmax(skin.weights[top]))], low)
        self.assertNotEqual(skin.indices[bottom][int(np.argmax(skin.weights[bottom]))], low)

    def test_rest_motions_move_nothing_and_a_bend_moves_the_tip(self) -> None:
        from assetkit.skinning import deform

        skeleton, skin, points, _ = self._bound()
        rest = {b.name: Motion() for b in skeleton.bones}
        np.testing.assert_allclose(deform(points, skin, rest), points, atol=1e-12)
        pose = Pose()
        pose.add_turn("lower", turn(pitch=60))
        bent = deform(points, skin, solve(skeleton, pose))
        top = np.argmax(points[:, 2])
        self.assertLess(bent[top, 2], points[top, 2] - 0.1)  # the tip swung down
        bottom = np.argmin(points[:, 2])
        np.testing.assert_allclose(bent[bottom], points[bottom], atol=1e-9)  # the base stayed

    def test_unrelated_bones_do_not_share_skin(self) -> None:
        from assetkit import sdf
        from assetkit.skinning import bind, shared_skin

        body = sdf.ellipsoid((0, 0, 0.5), (0.2, 0.2, 0.3))
        head = sdf.sphere((0, 0, 0.9), 0.15)
        arm = sdf.capsule((0.15, 0, 0.75), (0.4, 0, 0.75), 0.06)
        shape = sdf.smooth_union(sdf.smooth_union(body, head, 0.05), arm, 0.05)
        verts, faces = sdf.mesh(shape, max_triangles=2000)
        parents = {"body": None, "head": "body", "arm": "body"}
        skin = bind(
            np.asarray(verts),
            {"body": [body], "head": [head], "arm": [arm]},
            {},
            0.03,
            parents=parents,
            faces=np.asarray(faces),
        )
        self.assertEqual(shared_skin(skin, parents), [])

    def test_clip_report_flags_a_clip_that_does_not_move(self) -> None:
        from assetkit.rig import Clip
        from assetkit.skinning import clip_flags, clip_report

        skeleton, skin, points, tris = self._bound()
        still = Clip("Still", 24, True, tuple({b.name: Motion() for b in skeleton.bones} for _ in range(4)))
        report = clip_report(points, tris, skin, still, float(points[:, 2].min()))
        self.assertIn("nothing moves", clip_flags(report))


@unittest.skipIf(np is None, "rigs need numpy")
class RigSpecTests(unittest.TestCase):
    def test_rigged_sculpts_build_with_skin_skeleton_and_clips(self) -> None:
        from blender.generators import organic_sculpt
        from blender.lib.spec import load_spec

        for name in ("sculpt_cave_toad", "sculpt_cave_imp"):
            with self.subTest(spec=name):
                asset = organic_sculpt.build(load_spec(REPO_ROOT / "assets" / "specs" / f"{name}.json"))
                self.assertIsNotNone(asset.skeleton)
                self.assertTrue(asset.clips)
                part = asset.parts[0]
                self.assertEqual(len(part.skin.indices), len(part.mesh.vertices))
                # Bones taken `from` a part sit where the part is, moved by the same settling.
                self.assertTrue(any(b.name.endswith(".R") for b in asset.skeleton.bones))

    def test_rig_errors_name_the_path(self) -> None:
        from assetkit import sdf
        from assetkit.rigspec import RigError, build_rig

        parts = {"thigh": {"capsule": {"a": [0.1, 0, 0.3], "b": [0.1, 0, 0.1], "radius": 0.05}}}
        shape_of = lambda name: sdf.sphere((0, 0, 0), 0.1)  # noqa: E731
        cases = [
            ({"bones": {"leg.R": {"head": [0, 0, 0], "tail": [0, 0, 1]}}}, "model the left side"),
            ({"bones": {"thigh.L": {"from": "shin"}}}, "no part 'shin'"),
            (
                {"bones": {"b": {"head": [0, 0, 0], "tail": [0, 0, 1]}}, "carry": {"b": ["nope"]}},
                "no part 'nope'",
            ),
            ({"bones": {"b": {"head": [0, 0, 0], "tail": [0, 0, 1]}}}, "nothing would move"),
        ]
        for spec, message in cases:
            with self.subTest(message=message), self.assertRaises(RigError) as caught:
                build_rig(spec, parts, shape_of, 1.0, (0.0, 0.0, 0.0), "params.rig")
            self.assertIn(message, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
