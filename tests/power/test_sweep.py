"""Design-space sweep (sweep.py): ngspice channel values and one point.

    KMP_PDKS=sky130A python3 -m unittest tests.power.test_sweep
"""

import shutil
import sys
import unittest

from tests.power._util import HAVE_KLAYOUT, PY  # noqa: F401

if PY not in sys.path:
    sys.path.insert(0, PY)

needs = unittest.skipUnless(HAVE_KLAYOUT and shutil.which("ngspice"), "needs klayout and ngspice")


@needs
class TestSweep(unittest.TestCase):
    def test_channel(self):
        from klayout_power_pcells.sweep import channel
        r, q = channel("nfet_01v8", 0.15)
        self.assertTrue(300 < r < 2000, r)                  # ohm um, linear region at 1.8 V
        # gate charge close to C_ox W L Vgs with C_ox ~ 8.4 fF/um2
        self.assertAlmostEqual(q, 8.4 * 0.15 * 1.8, delta=0.25 * 8.4 * 0.15 * 1.8)
        r_long, _ = channel("nfet_01v8", 0.5)
        self.assertGreater(r_long, r)

    def test_point(self):
        from klayout_power_pcells.sweep import point
        from klayout_power_pcells.waffle import WaffleParams
        p = point(WaffleParams(nx=2, ny=2, P=4.0))
        self.assertAlmostEqual(p["Ron"], p["R_ch"] + p["R_metal"] + p["R_contacts"], places=9)
        self.assertGreater(p["core_W_per_area"], p["W_per_area"])     # periphery costs area
        self.assertGreater(p["Ron_area_mohm_mm2"], 0)


if __name__ == "__main__":
    unittest.main()
