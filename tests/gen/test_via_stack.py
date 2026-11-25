"""VIA_STACK (sky130_gen): planning, EM sizing and sky130A DRC.

    KMP_PDKS=sky130A KMP_PDK=sky130A python3 -m unittest tests.gen.test_via_stack
"""

import os
import shutil
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, HAVE_MAGIC, PY  # noqa: F401

if PY not in sys.path:
    sys.path.insert(0, PY)

needs_klayout = unittest.skipUnless(HAVE_KLAYOUT, "the klayout Python module is not installed")
needs_magic = unittest.skipUnless(HAVE_MAGIC, "needs klayout, Magic and sky130A")


@needs_klayout
class TestPlan(unittest.TestCase):
    def test_spans(self):
        from klayout_gen.via_stack import plan
        w, h, arr = plan("li", "met5")
        self.assertEqual([a[0] for a in arr], ["mcon", "via", "via2", "via3", "via4"])
        self.assertGreaterEqual(w * h, 4.0 - 1e-9)                  # met5 area
        self.assertTrue(all(a[1] * a[2] >= 1 for a in arr))

    def test_current(self):
        from klayout_gen.via_stack import StackError, plan
        w, h, arr = plan("met1", "met3", current_ma=2.0, ma_per_cut=0.2)
        self.assertTrue(all(a[1] * a[2] >= 10 for a in arr))
        with self.assertRaisesRegex(StackError, "EM limit"):
            plan("met1", "met2", current_ma=1.0)                        # no sky130 EM table
        with self.assertRaisesRegex(StackError, "larger"):
            plan("met1", "met2", 0.5, 0.5, current_ma=5.0, ma_per_cut=0.1)

    def test_refusals(self):
        from klayout_gen.via_stack import StackError, plan
        with self.assertRaises(StackError):
            plan("met2", "met1")
        with self.assertRaises(StackError):
            plan("met1", "met5", 1.0, 1.0)


@needs_magic
class TestDRC(unittest.TestCase):
    CASES = {"vs_li_m1": {"bottom": "li", "top": "met1"}, "vs_m1_m2": {},
             "vs_li_m5": {"bottom": "li", "top": "met5"},
             "vs_m1_m3_box": {"top": "met3", "width": 4.0, "height": 1.5},
             "vs_m2_m4_em": {"bottom": "met2", "top": "met4", "current_ma": 3.0, "ma_per_cut": 0.25}}

    def test_drc_clean(self):
        import klayout.db as db
        import klayout_gen
        from klayout_power_pcells import verify
        klayout_gen.register()
        work = tempfile.mkdtemp(prefix="vs_test_")
        try:
            for name, params in self.CASES.items():
                with self.subTest(name):
                    ly = db.Layout()
                    ly.dbu = 0.001
                    top = ly.create_cell(name)
                    c = ly.create_cell("VIA_STACK", "sky130_gen", params)
                    top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
                    gds = os.path.join(work, name + ".gds")
                    ly.write(gds)
                    w = os.path.join(work, name)
                    os.makedirs(w, exist_ok=True)
                    self.assertEqual(verify.klayout_drc(gds, name, w), {})
                    self.assertEqual(verify.magic_drc(gds, name, w), {})
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
