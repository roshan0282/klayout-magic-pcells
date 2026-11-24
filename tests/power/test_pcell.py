"""The sky130_power library's HW_FET PCell.

Needs the klayout Python module; DRC/LVS of a placed instance also magic,
netgen and sky130A, and the macro test the klayout binary. Run from the
repository root:

    KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
"""

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from tests.power._util import REPO, db, needs_klayout

from tests.parity import compare  # noqa: E402

CASES = [
    dict(device="pfet_01v8", nx=4, ny=3, P=4.0, L=0.0, N=0.0, gate_strap="met1_mesh", runners="met3,met4",
         runner_style="diag45", bus="L_buses", bus_w=0.0, guard_ring=True, source_taps=True, tap_w=0.0),
    dict(device="nfet_01v8", nx=3, ny=2, P=3.5, L=0.2, N=0.6, gate_strap="frame_only", runners="met3",
         runner_style="diag45", bus="none", bus_w=0.0, guard_ring=True, source_taps=False, tap_w=0.0),
]


def _gen_params(pc):
    from klayout_power_pcells.pcell import params_of_values
    return params_of_values(pc)


@needs_klayout
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
        self.assertIsNotNone(self.lib)
        self.assertIs(self.kpp.register(), self.lib)
        self.assertIn("HW_FET", self.lib.layout().pcell_names())

    def test_same_geometry_as_generator(self):
        from klayout_power_pcells.waffle import write_gds
        for k, pc in enumerate(CASES):
            with self.subTest(case=pc):
                pfile = os.path.join(self.tmp, "pc%d.gds" % k)
                gfile = os.path.join(self.tmp, "gen%d.gds" % k)
                self._place(pc, pfile)
                write_gds(_gen_params(pc), gfile, name="GEN")
                r = compare.compare_cells(gfile, "GEN", pfile, "TOP")
                self.assertTrue(r["identical"], r)

    def test_info_line(self):
        v = self.kpp.form_values(CASES[0])
        self.assertIn("gates", v["info"])
        self.assertIn("W ", v["info"])
        v = self.kpp.form_values(dict(CASES[0], P=0.5))
        self.assertTrue(v["info"].startswith("not drawn:"), v["info"])

    @unittest.skipUnless(all(shutil.which(t) for t in ("klayout", "magic", "netgen"))
                         and os.path.isdir("/foss/pdks/sky130A"), "needs klayout, magic, netgen, sky130A")
    def test_placed_instance_verifies(self):
        from klayout_power_pcells.verify import verify
        from klayout_power_pcells.waffle import build
        path = os.path.join(self.tmp, "placed.gds")
        ly, top, var = self._place(CASES[0], path)
        top.flatten(-1, True)
        flat = os.path.join(self.tmp, "placed_flat.gds")
        ly.write(flat)
        work = os.path.join(self.tmp, "verify")
        os.makedirs(work)
        res = verify(flat, build(_gen_params(CASES[0])).report, top="TOP", work=work)
        self.assertEqual(res["problems"], [], res)
        self.assertTrue(res["lvs"])

    def test_round_trip(self):
        pc = CASES[1]
        path = os.path.join(self.tmp, "rt.gds")
        self._place(pc, path)
        ly = db.Layout()
        ly.read(path)
        child = ly.cell(next(ly.cell("TOP").each_inst()).cell_index)
        self.assertTrue(child.is_pcell_variant())
        got = child.pcell_parameters_by_name()
        for k, v in pc.items():
            if isinstance(v, float):        # KLayout reopens a saved double up to one ULP off
                self.assertAlmostEqual(got[k], v, places=12, msg=k)
            else:
                self.assertEqual(got[k], v, k)
        resaved = os.path.join(self.tmp, "rt2.gds")
        ly.write(resaved)
        self.assertTrue(compare.compare_cells(path, "TOP", resaved, "TOP")["identical"])

    def test_refused_parameters_draw_error_marker(self):
        ly = db.Layout()
        var = ly.create_cell("HW_FET", "sky130_power", {"P": 0.5})
        li = ly.find_layer(255, 0)
        self.assertIsNotNone(li)
        texts = [s.text_string for s in var.shapes(li).each() if s.is_text()]
        self.assertTrue(texts and texts[0].startswith("HW_ERROR HW_FET: P 0.500 um"), texts)
        self.assertEqual(sum(1 for i in ly.layer_indexes() if i != li and not var.shapes(i).is_empty()), 0)

    @unittest.skipUnless(shutil.which("klayout"), "no klayout binary")
    def test_autorun_macro_in_batch(self):
        out = os.path.join(self.tmp, "batch.gds")
        script = os.path.join(self.tmp, "batch.py")
        with open(script, "w") as f:
            f.write(textwrap.dedent("""
                import pya
                ly = pya.Layout()
                top = ly.create_cell("TOP")
                c = ly.create_cell("HW_FET", "sky130_power", {"nx": 2, "ny": 2})
                assert c is not None and c.is_pcell_variant(), c
                assert ly.find_layer(255, 0) is None or c.shapes(ly.find_layer(255, 0)).is_empty()
                top.insert(pya.CellInstArray(c.cell_index(), pya.Trans()))
                ly.write(%r)
                print("BATCH_OK", c.display_title())
            """ % out))
        cmd = ["klayout", "-b", "-rm", os.path.join(REPO, "pymacros", "klayout_power_pcells.lym"), "-r", script]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        self.assertIn("BATCH_OK", p.stdout, p.stdout + p.stderr)
        self.assertTrue(os.path.isfile(out))


if __name__ == "__main__":
    unittest.main()
