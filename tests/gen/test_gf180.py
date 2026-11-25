"""gf180mcu_gen: guard rings and via stacks through gf180mcu.drc and
Magic's gf180mcuD DRC, plus a negative control that the deck runs.

    python3 -m unittest tests.gen.test_gf180
"""

import os
import shutil
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, PY  # noqa: F401

if PY not in sys.path:
    sys.path.insert(0, PY)

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")
HAVE_GF = HAVE_KLAYOUT and shutil.which("magic") is not None and os.path.isfile(
    os.path.join(PDK_ROOT, "gf180mcuD", "libs.tech", "klayout", "tech", "drc", "gf180mcu.drc"))


def _drc(ly, name, work):
    from klayout_power_pcells import verify
    from tests.parity import drc as pdrc
    gds = os.path.join(work, name + ".gds")
    ly.write(gds)
    w = os.path.join(work, name)
    os.makedirs(w, exist_ok=True)
    kl = pdrc.run_klayout_drc(gds, name, os.path.join(w, "kl.lyrdb"), os.path.join(w, "kl.log"), pdk="gf180mcuD")
    return sorted(set(r[0] for r in kl)), verify.magic_drc(gds, name, w, pdk="gf180mcuD")


@unittest.skipUnless(HAVE_GF, "needs klayout, Magic and gf180mcuD")
class TestGf180(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import klayout_gen
        klayout_gen.register()
        cls.work = tempfile.mkdtemp(prefix="gf_gen_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_deck_catches_a_violation(self):
        import klayout.db as db
        ly = db.Layout()
        ly.dbu = 0.001
        top = ly.create_cell("BAD")
        top.shapes(ly.layer(34, 0)).insert(db.DBox(0, 0, 5, 0.1))
        kl, mg = _drc(ly, "BAD", self.work)
        self.assertIn("M1.1", kl)
        self.assertIn("M1.1", mg)

    def test_clean(self):
        import klayout.db as db
        L = db.DPolygon([db.DPoint(0, 0), db.DPoint(12, 0), db.DPoint(12, 4), db.DPoint(5, 4), db.DPoint(5, 9),
                         db.DPoint(0, 9)])
        cases = {"gf_gr_p": ("GUARD_RING", {"shape": db.DBox(0, 0, 10, 5)}),
                 "gf_gr_n": ("GUARD_RING", {"shape": db.DBox(0, 0, 10, 5), "kind": "ntap"}),
                 "gf_gr_L": ("GUARD_RING", {"shape": L}),
                 "gf_vs_12": ("VIA_STACK", {}),
                 "gf_vs_14": ("VIA_STACK", {"top": "met4"}),
                 "gf_vs_box": ("VIA_STACK", {"top": "met3", "width": 3.0, "height": 1.2})}
        for name, (pc, params) in cases.items():
            with self.subTest(name):
                ly = db.Layout()
                ly.dbu = 0.001
                top = ly.create_cell(name)
                c = ly.create_cell(pc, "gf180mcu_gen", params)
                top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
                kl, mg = _drc(ly, name, self.work)
                self.assertEqual(kl, [])
                self.assertEqual(mg, {})

    def test_no_deep_nwell_yet(self):
        import klayout.db as db
        from klayout_gen.guard_ring import RingError, ring
        with self.assertRaises(RingError):
            ring(db.DBox(0, 0, 5, 5), 0.001, kind="ntap", deep_nwell=True, pdk="gf180mcuD")


if __name__ == "__main__":
    unittest.main()
