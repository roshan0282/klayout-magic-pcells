"""Metal resistance extractor (ron.py): analytic strips, mesh convergence,
and HW_FET trends.

    python3 -m unittest tests.power.test_ron
"""

import os
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, PY  # noqa: F401

if PY not in sys.path:
    sys.path.insert(0, PY)

try:
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:  # pragma: no cover
    HAVE_SCIPY = False

needs = unittest.skipUnless(HAVE_KLAYOUT and HAVE_SCIPY, "needs klayout and scipy")


@needs
class TestAnalytic(unittest.TestCase):
    def setUp(self):
        import klayout.db as db
        self.db = db
        self.strip = db.Region(db.Box(0, 0, 10000, 1000))           # 10 x 1 um met1
        self.gnd = [("met1", db.Region(db.Box(0, 0, 100, 1000)))]

    def test_end_injection(self):
        from klayout_power_pcells.ron import solve
        end = [("met1", self.db.Region(self.db.Box(9900, 0, 10000, 1000)))]
        r = solve({"met1": self.strip}, {"N": end}, {"N": self.gnd}, pixel=0.05)["R"]["N"]
        self.assertAlmostEqual(r, 0.125 * 9.9, delta=0.02 * 0.125 * 9.9)    # Rs L / W

    def test_uniform_injection(self):
        from klayout_power_pcells.ron import solve
        sites = [("met1", self.db.Region(self.db.Box(x, 0, x + 100, 1000))) for x in range(100, 10000, 100)]
        r = solve({"met1": self.strip}, {"N": sites}, {"N": self.gnd}, pixel=0.05)["R"]["N"]
        self.assertAlmostEqual(r, 0.125 * 9.9 / 3, delta=0.02 * 0.125 * 9.9 / 3)   # Rs L / (3 W)

    def test_via_between_layers(self):
        """met1 and met2 squares joined by 4 vias: R = 4.5 / 4 ohm plus the spreading."""
        from klayout_power_pcells.ron import solve
        db = self.db
        m = db.Region(db.Box(0, 0, 1000, 1000))
        vias = db.Region([db.Box(x, y, x + 150, y + 150) for x in (200, 650) for y in (200, 650)])
        r = solve({"met1": m, "met2": m, "via": vias}, {"N": [("met1", m)]}, {"N": [("met2", m)]},
                  pixel=0.05)["R"]["N"]
        self.assertAlmostEqual(r, 4.5 / 4, delta=0.1)

    def test_shorts_and_open_sites_are_refused(self):
        from klayout_power_pcells.ron import RonError, solve
        db = self.db
        with self.assertRaises(RonError):
            solve({"met1": self.strip}, {"A": self.gnd}, {"A": self.gnd, "B": [("met1", self.strip)]}, pixel=0.1)
        far = [("met1", db.Region(db.Box(20000, 0, 20100, 1000)))]
        with self.assertRaises(RonError):
            solve({"met1": self.strip + db.Region(db.Box(20000, 0, 21000, 1000))}, {"N": far}, {"N": self.gnd},
                  pixel=0.1)


@needs
class TestHWFet(unittest.TestCase):
    def test_converges_and_scales(self):
        from klayout_power_pcells.ron import ron_metal
        from klayout_power_pcells.waffle import WaffleParams
        p = WaffleParams(nx=2, ny=2, P=4.0)
        a = ron_metal(p, pixel=0.1)
        b = ron_metal(p, pixel=0.05)
        self.assertAlmostEqual(a["R_metal"], b["R_metal"], delta=0.05 * b["R_metal"])   # mesh converged
        big = ron_metal(WaffleParams(nx=4, ny=4, P=4.0), pixel=0.1)
        self.assertEqual(big["squares"], (8, 8))
        self.assertLess(big["R_metal"], a["R_metal"])          # more squares in parallel
        self.assertGreater(a["R_S"], 0)
        self.assertGreater(a["R_D"], 0)

    def test_heatmap(self):
        from klayout_power_pcells.ron import ron_metal
        from klayout_power_pcells.waffle import WaffleParams
        out = os.path.join(tempfile.mkdtemp(prefix="ron_"), "map.png")
        ron_metal(WaffleParams(nx=2, ny=2, P=4.0), pixel=0.1, heatmap=out)
        self.assertGreater(os.path.getsize(out), 10000)


if __name__ == "__main__":
    unittest.main()
