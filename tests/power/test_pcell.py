"""The sky130_power library's HW_FET PCell.

Needs Magic, sky130A and the klayout Python module (the macro test also the
klayout binary); run from the repository root:

    KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "python"))
os.environ.setdefault("KMP_PDKS", "sky130A")

try:
    import klayout.db as db
except ImportError:  # pragma: no cover
    db = None

from tests.parity import compare, drc  # noqa: E402

HAVE_MAGIC = shutil.which("magic") is not None and os.path.isdir(
    os.path.join(drc.PDK_ROOT, "sky130A", "libs.tech", "magic"))

CASES = [
    dict(device="sky130_fd_pr__pfet_01v8", bulk="source", l=0.5, w=2.0, nf=3, nx=4, ny=4,
         strap_w=3.0, pitch=0.0),
    dict(device="sky130_fd_pr__nfet_01v8", bulk="ring", l=0.15, w=1.5, nf=2, nx=3, ny=2,
         strap_w=2.5, pitch=9.0),
]


def _gen_params(pc):
    from klayout_power_pcells import HWParams
    kw = dict(pc)
    kw["pitch"] = kw["pitch"] or None
    return HWParams(**kw)


@unittest.skipUnless(db is not None and HAVE_MAGIC, "needs klayout, Magic and sky130A")
class PCellTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import klayout_power_pcells as kpp
        cls.kpp = kpp
        cls.lib = kpp.register()
        cls.tmp = tempfile.mkdtemp(prefix="hw_pcell_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _place(self, params, path):
        ly = db.Layout()
        ly.dbu = 0.001
        top = ly.create_cell("TOP")
        var = ly.create_cell("HW_FET", "sky130_power", params)
        self.assertIsNotNone(var)
        self.assertTrue(var.is_pcell_variant())
        top.insert(db.CellInstArray(var.cell_index(), db.Trans()))
        ly.write(path)
        return ly, top, var

    def test_register_idempotent(self):
        self.assertIs(self.kpp.register(), self.lib)
        self.assertIn("HW_FET", self.lib.layout().pcell_names())

    def test_same_geometry_as_generator(self):
        for k, pc in enumerate(CASES):
            with self.subTest(case=pc):
                pfile = os.path.join(self.tmp, "pc%d.gds" % k)
                gfile = os.path.join(self.tmp, "gen%d.gds" % k)
                self._place(pc, pfile)
                self.kpp.write_gds(_gen_params(pc), gfile, name="GEN")
                r = compare.compare_cells(gfile, "GEN", pfile, "TOP")
                self.assertTrue(r["identical"], r)

    def test_drc_and_extraction(self):
        pc = CASES[0]
        path = os.path.join(self.tmp, "pc_drc.gds")
        ly, top, var = self._place(pc, path)
        errs = drc.run_magic_drc(path, "TOP", path + ".tsv", path + ".log")
        self.assertEqual(errs, [])
        flat = os.path.join(self.tmp, "pc_flat.gds")
        top.flatten(-1, True)
        ly.write(flat)
        devs = drc.run_magic_extract(flat, ["TOP"], flat + "_ext", flat + ".log")["TOP"]
        res = _gen_params(pc)
        blocks = (res.nx - 1) * res.ny + res.nx * (res.ny - 1)
        self.assertEqual(len(devs), blocks * res.nf)
        self.assertEqual({d[0] for d in devs}, {pc["device"]})
        self.assertAlmostEqual(sum(d[1] for d in devs), blocks * res.nf * res.w, delta=0.001)

    def test_round_trip(self):
        pc = CASES[1]
        path = os.path.join(self.tmp, "rt.gds")
        self._place(pc, path)
        ly = db.Layout()
        ly.read(path)
        top = ly.cell("TOP")
        inst = next(top.each_inst())
        child = ly.cell(inst.cell_index)
        self.assertTrue(child.is_pcell_variant())
        got = child.pcell_parameters_by_name()
        for k, v in pc.items():
            self.assertEqual(got[k], v, k)
        resaved = os.path.join(self.tmp, "rt2.gds")
        ly.write(resaved)
        r = compare.compare_cells(path, "TOP", resaved, "TOP")
        self.assertTrue(r["identical"], r)

    def test_refused_parameters_draw_error_marker(self):
        ly = db.Layout()
        var = ly.create_cell("HW_FET", "sky130_power", {"strap_w": 1.0})
        li = ly.find_layer(255, 0)
        self.assertIsNotNone(li)
        texts = [s.text_string for s in var.shapes(li).each() if s.is_text()]
        self.assertTrue(texts and texts[0].startswith("HW_ERROR: strap width"), texts)
        self.assertEqual(sum(1 for i in ly.layer_indexes() if i != li and not var.shapes(i).is_empty()), 0)

    @unittest.skipUnless(shutil.which("klayout"), "no klayout binary")
    def test_autorun_macros_in_batch(self):
        out = os.path.join(self.tmp, "batch.gds")
        script = os.path.join(self.tmp, "batch.py")
        with open(script, "w") as f:
            f.write(textwrap.dedent("""
                import pya
                ly = pya.Layout()
                top = ly.create_cell("TOP")
                c = ly.create_cell("HW_FET", "sky130_power", {"nx": 2, "ny": 2, "nf": 1})
                assert c is not None and c.is_pcell_variant(), c
                assert ly.find_layer(255, 0) is None or c.shapes(ly.find_layer(255, 0)).is_empty()
                top.insert(pya.CellInstArray(c.cell_index(), pya.Trans()))
                ly.write(%r)
                print("BATCH_OK", c.display_title())
            """ % out))
        cmd = ["klayout", "-b",
               "-rm", os.path.join(REPO, "pymacros", "klayout_magic_pcells.lym"),
               "-rm", os.path.join(REPO, "pymacros", "klayout_power_pcells.lym"),
               "-r", script]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, KMP_PDKS="sky130A"))
        self.assertIn("BATCH_OK", p.stdout, p.stdout + p.stderr)
        self.assertTrue(os.path.isfile(out))


if __name__ == "__main__":
    unittest.main()
