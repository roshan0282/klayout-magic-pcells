"""CC_ARRAY with gf180mcu_magic unit cells: gf180mcu.drc and Magic.

    python3 -m unittest tests.centroid.test_gf180
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
HAVE_GF = HAVE_KLAYOUT and shutil.which("magic") is not None and os.path.isdir(
    os.path.join(PDK_ROOT, "gf180mcuD", "libs.tech", "magic"))


@unittest.skipUnless(HAVE_GF, "needs klayout, Magic and gf180mcuD")
class TestGf180Arrays(unittest.TestCase):
    def test_drc(self):
        import klayout.db as db
        import klayout_magic_pcells as kmp
        import klayout_centroid as kc
        from klayout_power_pcells import verify
        from tests.parity import drc as pdrc
        self.assertIsNotNone(kmp.register("gf180mcuD"))
        kc.register()
        work = tempfile.mkdtemp(prefix="gf_cc_")
        # (w=2 is not used: Magic's gf180 nfet alone breaks M1.3 there)
        cases = {
            "gfcc_ring": ({"unit": "gf180mcu_magic/nfet_03v3", "unit_params": "w=5 l=1 nf=2 guard=1",
                           "devices": "A:4,B:4"}, set()),
            # tapless pfets: only the tap-distance rule DF.13_LV
            "gfcc_none": ({"unit": "gf180mcu_magic/pfet_03v3", "unit_params": "w=5 l=1 nf=2 guard=0",
                           "devices": "A:2,B:2", "dummies": "none"}, {"DF.13_LV"}),
        }
        try:
            for name, (params, allowed) in cases.items():
                with self.subTest(name):
                    ly = db.Layout()
                    ly.dbu = 0.001
                    top = ly.create_cell(name)
                    c = ly.create_cell("CC_ARRAY", "centroid", params)
                    top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
                    self.assertEqual(len(list(c.each_inst())), 24 if name == "gfcc_ring" else 4)
                    gds = os.path.join(work, name + ".gds")
                    ly.write(gds)
                    w = os.path.join(work, name)
                    os.makedirs(w, exist_ok=True)
                    kl = pdrc.run_klayout_drc(gds, name, os.path.join(w, "kl.lyrdb"), os.path.join(w, "kl.log"),
                                              pdk="gf180mcuD")
                    self.assertTrue(set(r[0] for r in kl) <= allowed, kl)
                    self.assertEqual(verify.magic_drc(gds, name, w, pdk="gf180mcuD"), {})
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
