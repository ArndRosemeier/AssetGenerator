"""assetkit.boat: a boat's shells are closed, wound outward and symmetric (no Blender)."""

from __future__ import annotations

import unittest
from collections import Counter

from assetkit.boat import Build, Hull, Lines, boat_shells, curve

LINES = Lines(
    length=5.0, beam=1.7, depth=0.65,
    breadth=((0, 0.03), (0.1, 0.5), (0.3, 0.92), (0.55, 1.0), (0.8, 0.95), (1, 0.8)),
    keel=((0, 0.46), (0.08, 0.16), (0.25, 0.09), (0.75, 0.09), (1, 0.12)),
    sheer=((0, 0.95), (0.25, 0.74), (0.6, 0.7), (1, 0.84)),
    fullness=((0, 0.05), (0.15, 0.5), (0.35, 0.88), (0.75, 0.9), (1, 0.6)),
)
BUILD = Build(strakes=7, thwarts=((0.3, 0.3), (0.5, 0.3)))


def _volume(verts, faces) -> float:
    vol = 0.0
    for f in faces:
        a = verts[f[0]]
        for i in range(1, len(f) - 1):
            b, c = verts[f[i]], verts[f[i + 1]]
            vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    return vol


class BoatTest(unittest.TestCase):
    def test_every_shell_is_closed_and_outward(self) -> None:
        shells = boat_shells(LINES, BUILD)
        self.assertGreater(len(shells), 30)
        for (verts, faces), part in shells:
            edges = Counter()
            for f in faces:
                for i in range(len(f)):
                    edges[(f[i], f[(i + 1) % len(f)])] += 1
            for (a, b), n in edges.items():
                self.assertEqual(n, 1, f"{part}: edge {a}-{b} used {n} times one way")
                self.assertEqual(edges.get((b, a)), 1, f"{part}: edge {a}-{b} has no twin: the shell is open")
            self.assertGreater(_volume(verts, faces), 0, f"{part}: inside out")

    def test_symmetric_and_in_its_lines(self) -> None:
        shells = boat_shells(LINES, BUILD)
        xs = [v[0] for (verts, _), _ in shells for v in verts]
        ys = [v[1] for (verts, _), _ in shells for v in verts]
        self.assertAlmostEqual(max(xs), -min(xs), places=6)
        self.assertLess(max(xs), LINES.beam / 2 + 0.1)
        self.assertLess(max(ys) - min(ys), LINES.length + 0.15)

    def test_hull_section_runs_from_keel_to_sheer(self) -> None:
        hull = Hull(LINES)
        bottom, top = hull.point(0.5, 0.0), hull.point(0.5, 1.0)
        self.assertAlmostEqual(bottom[0], 0.0)
        self.assertAlmostEqual(top[0], LINES.beam / 2 * curve(LINES.breadth)(0.5), places=6)
        self.assertAlmostEqual(top[2], curve(LINES.sheer)(0.5), places=6)
        self.assertGreater(hull.normal(0.5, 0.5)[0], 0.5)


if __name__ == "__main__":
    unittest.main()
