"""Pattern core: pure Python, no KLayout.

    python3 -m unittest discover -s tests/centroid -t .
"""

import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "python"))

from klayout_centroid import metrics  # noqa: E402
from klayout_centroid.pattern import (DUMMY, STYLES, Grid, PatternError, _skeleton, _layout_counts,  # noqa: E402
                                      auto_shape, build, centroid_offsets, check_centroid, optimize,
                                      parse_devices, parse_grid)

RATIOS = ["A:2,B:2", "A:4,B:4", "1:2", "1:2:4:8", "A:3,B:5", "A:8,B:8",
          "A:6,B:6,C:6", "1:2:4:8:16", "A:5,B:7,C:9", "A:16,B:16"]


def assert_cc(tc, p):
    off = centroid_offsets(p.grid)
    for name, n in p.devices:
        tc.assertEqual(off[name], (0, 0), "%s: %s off centre in %s" % (name, off[name], p))
        tc.assertEqual(sum(r.count(name) for r in p.grid), n)


class TestParse(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_devices("A:4,B:4"), [("A", 4), ("B", 4)])
        self.assertEqual(parse_devices("A:4 B:2"), [("A", 4), ("B", 2)])
        self.assertEqual(parse_devices("1:2:4:8"), [("A", 1), ("B", 2), ("C", 4), ("D", 8)])
        self.assertEqual(parse_grid("ABBA / BAAB"), ("ABBA", "BAAB"))
        self.assertEqual(parse_grid("A-A\nB_B"), ("A.A", "B.B"))

    def test_bad(self):
        for bad in ("", "AB:4", "A:0", "A:4,A:2", "A:x", ".:2"):
            with self.assertRaises(PatternError, msg=bad):
                parse_devices(bad)
        with self.assertRaises(PatternError):
            parse_grid("AB/A")


class TestCentroid(unittest.TestCase):
    def test_every_style_and_ratio(self):
        for ratio, style in itertools.product(RATIOS, STYLES):
            with self.subTest(ratio=ratio, style=style):
                assert_cc(self, build(ratio, style=style))

    def test_grids_2x2_to_8x8(self):
        n = 0
        for R, C in itertools.product(range(2, 9), repeat=2):
            for ratio in ("A:%d,B:%d" % ((R * C) // 2, (R * C) // 2), "1:2:4:8"):
                devs = parse_devices(ratio)
                if sum(c for _, c in devs) > R * C:
                    continue
                for style in STYLES:
                    try:
                        p = build(devs, R, C, style)
                    except PatternError:
                        continue    # infeasible shapes are refused, never drawn wrong
                    assert_cc(self, p)
                    n += 1
        self.assertGreater(n, 150)

    def test_odd_counts_use_centre_and_triads(self):
        p = build("A:3,B:5")
        self.assertEqual((p.rows, p.cols), (3, 3))
        p = build("A:3,B:5,C:7", rows=5, cols=5)
        assert_cc(self, p)

    def test_infeasible(self):
        with self.assertRaises(PatternError):
            build("A:1,B:1")
        with self.assertRaises(PatternError):
            build("A:3,B:3", rows=2, cols=3)      # no centre cell, odd counts
        with self.assertRaises(PatternError):
            build("A:4,B:4", rows=1, cols=4)      # too few cells

    def test_override(self):
        p = build("A:2,B:2", override="ABBA")
        self.assertEqual(p.grid, ("ABBA",))
        with self.assertRaises(PatternError):
            build("A:2,B:2", override="AABB")     # A left of centre
        with self.assertRaises(PatternError):
            build("A:2,B:2", override="ABBC")     # C is no device
        with self.assertRaises(PatternError):
            check_centroid(("AAB", "BBA"), [("A", 3), ("B", 3)])


class TestGolden(unittest.TestCase):
    def test_abba(self):
        self.assertEqual(build("A:2,B:2", rows=1, cols=4, style="interdigitated").grid, ("ABBA",))

    def test_cross_coupled_quad(self):
        self.assertEqual(build("A:2,B:2", style="checkerboard").grid, ("AB", "BA"))

    def test_tiled_quad(self):
        self.assertEqual(build("A:8,B:8", style="checkerboard").grid, ("ABAB", "BABA", "ABAB", "BABA"))

    def test_binary_caps_centre(self):
        p = build("1:2:4:8")
        self.assertEqual((p.rows, p.cols), (3, 5))
        self.assertEqual(p.grid[1][2], "A")       # the unit cap sits on the centre


class TestOptimized(unittest.TestCase):
    def test_random_swaps_keep_centroid(self):
        """Property test: symmetric-pair swaps never move a centroid."""
        rnd = random.Random(7)
        for ratio in ("A:8,B:8", "1:2:4:8:16", "A:5,B:7,C:9"):
            p = build(ratio)
            g = Grid(p.rows, p.cols)
            lab = {(i, j): p.grid[i][j] for i in range(p.rows) for j in range(p.cols)}
            fixed = set(_skeleton(g, _layout_counts(p.devices, p.rows, p.cols)))
            half = [u for u in g.half_cells(fixed)]
            for _ in range(300):
                a, b = rnd.sample(half, 2)
                la, lb = lab[a], lab[b]
                lab[a] = lab[g.mirror(a)] = lb
                lab[b] = lab[g.mirror(b)] = la
                grid = tuple("".join(lab[(i, j)] for j in range(p.cols)) for i in range(p.rows))
                check_centroid(grid, p.devices)

    def test_not_worse_than_constructive(self):
        for ratio in ("A:8,B:8", "1:2:4:8", "A:6,B:6,C:6", "A:16,B:16"):
            opt = metrics.evaluate(build(ratio, style="optimized"))["score"]
            for s in ("interdigitated", "checkerboard", "symmetric"):
                self.assertLessEqual(opt, metrics.evaluate(build(ratio, style=s))["score"] + 1e-12,
                                     "%s vs %s" % (ratio, s))

    def test_deterministic(self):
        self.assertEqual(build("A:6,B:6,C:6", style="optimized", seed=3).grid,
                         build("A:6,B:6,C:6", style="optimized", seed=3).grid)

    def test_optimize_keeps_counts(self):
        p = build("A:5,B:7,C:9", style="symmetric")
        g = optimize(p.grid, p.devices, seed=2)
        check_centroid(g, p.devices)


class TestMetrics(unittest.TestCase):
    def test_gradients(self):
        """Linear gradients cancel for every pattern; quadratic ones don't,
        and spreading the devices lowers them."""
        for ratio in RATIOS:
            for style in STYLES:
                m = metrics.evaluate(build(ratio, style=style))
                self.assertAlmostEqual(m["gradient"]["linear x+y"], 0.0, places=9)
        clumped = metrics.evaluate(build("A:8,B:8", style="symmetric"))
        quad = metrics.evaluate(build("A:8,B:8", style="checkerboard"))
        q = ("x^2", "y^2", "x*y")
        self.assertLess(sum(quad["gradient"][k] for k in q), sum(clumped["gradient"][k] for k in q))
        self.assertLess(quad["sigma"][("A", "B")], clumped["sigma"][("A", "B")])

    def test_adjacency_and_report(self):
        m = metrics.evaluate(build("A:2,B:2", style="checkerboard"))
        self.assertEqual(m["adjacency"], {"AB": (2, 2)})
        self.assertEqual(m["longest_run"], 1)
        text = metrics.report_text(build("1:2:4:8"))
        self.assertIn("common centroid: yes", text)

    def test_auto_shape(self):
        self.assertEqual(auto_shape(parse_devices("A:4,B:4")), (2, 4))
        self.assertEqual(auto_shape(parse_devices("1:2:4:8:16")), (5, 7))
        self.assertEqual(auto_shape(parse_devices("A:4,B:4"), rows=1), (1, 8))
        # a unit twice as wide as tall: fewer columns
        r, c = auto_shape(parse_devices("A:8,B:8"), aspect=2.0)
        self.assertLessEqual(c, r)


if __name__ == "__main__":
    unittest.main()
