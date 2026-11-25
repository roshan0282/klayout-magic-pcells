"""CC_ARRAY routing: row planning (pure), and routed arrays through the
sky130A KLayout deck and Magic extraction + netgen LVS.

    KMP_PDKS=sky130A KMP_PDK=sky130A python3 -m unittest tests.centroid.test_router
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, HAVE_MAGIC, PY  # noqa: F401

if PY not in sys.path:
    sys.path.insert(0, PY)

HAVE_NETGEN = shutil.which("netgen") is not None
needs_klayout = unittest.skipUnless(HAVE_KLAYOUT, "the klayout Python module is not installed")
needs_lvs = unittest.skipUnless(HAVE_MAGIC and HAVE_NETGEN, "needs klayout, Magic, netgen and sky130A")


@needs_klayout
class TestPlan(unittest.TestCase):
    def units(self, rows):
        return [{"row": r, "device": d} for r, devs in enumerate(rows) for d in devs]

    def test_common_source_and_mirroring(self):
        from klayout_centroid.router import plan_rows
        p = plan_rows(self.units([["dummy"] * 3, ["A", "B", "dummy"], ["B", "A"]]))
        self.assertEqual(p[0], {"sd": ["S"], "gate_top": None, "gate_bottom": None})
        self.assertEqual(p[1]["sd"], ["A_D", "S", "B_D"][::-1])          # odd row mirrored
        self.assertEqual((p[1]["gate_top"], p[1]["gate_bottom"]), ("B_G", "A_G"))
        self.assertEqual(p[2]["sd"], ["A_D", "S", "B_D"])
        self.assertEqual((p[2]["gate_top"], p[2]["gate_bottom"]), ("A_G", "B_G"))

    def test_separate_sources_and_dum(self):
        from klayout_centroid.router import plan_rows
        p = plan_rows(self.units([["A", "B", "dummy"]]), source="separate", dummy_tie="DUM")
        self.assertEqual(p[0]["sd"], ["A_D", "A_S", "B_S", "DUM", "B_D"])

    def test_refusals(self):
        from klayout_centroid.pattern import PatternError
        from klayout_centroid.router import plan_rows
        with self.assertRaises(PatternError):
            plan_rows(self.units([["A", "B", "C"]]))
        with self.assertRaises(PatternError):
            plan_rows(self.units([["A", "B"]]), source="separate", dummy_tie="S")


@needs_lvs
class TestRoutedArrays(unittest.TestCase):
    CASES = {
        "cc_dp": {"devices": "A:4,B:4", "rows": 2, "cols": 4, "unit_params": "w=1.3 l=0.5 nf=2 guard=0",
                  "route": "tracks"},
        "cc_sep": {"devices": "A:4,B:4", "rows": 2, "cols": 4, "unit_params": "w=2.1 l=0.5 nf=2 guard=0",
                   "route": "tracks", "source": "separate", "dummy_tie": "DUM"},
        "cc_mirror_pf": {"unit": "sky130_magic/sky130_fd_pr__pfet_01v8", "devices": "A:2,B:6",
                         "style": "symmetric", "unit_params": "w=1.3 l=1 nf=2 guard=0", "route": "tracks"},
    }

    @classmethod
    def setUpClass(cls):
        import klayout_magic_pcells as kmp
        import klayout_centroid as kc
        kmp.register()
        kc.register()
        cls.work = tempfile.mkdtemp(prefix="cc_route_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_drc_and_lvs(self):
        import klayout.db as db
        from klayout_centroid import pcell, router
        from klayout_power_pcells import verify
        for name, params in self.CASES.items():
            with self.subTest(name):
                v = {p.name: p.default for p in pcell.CCArrayPCell().get_parameters()}
                v.update(params)
                ly = db.Layout()
                ly.dbu = 0.001
                top = ly.create_cell(name)
                info = pcell.draw(ly, top, v)
                gds = os.path.join(self.work, name + ".gds")
                ly.write(gds)
                w = os.path.join(self.work, name)
                os.makedirs(w, exist_ok=True)
                self.assertEqual(verify.klayout_drc(gds, name, w), {})
                mag = verify.magic_drc(gds, name, w)
                self.assertTrue(set(mag) <= {"LU.2", "LU.3", "nwell.4"}, mag)   # tapless units only
                up = dict(t.split("=") for t in v["unit_params"].split())
                ref = router.reference_spice(name, info["route"], pcell.split_unit(v["unit"])[1],
                                             float(up["w"]), float(up["l"]), int(up["nf"]))
                spice, _ = verify.extract(gds, name, w)
                sch = os.path.join(w, "ref.spice")
                with open(sch, "w") as f:
                    f.write(ref)
                setup = os.path.join(os.environ.get("PDK_ROOT", "/foss/pdks"), "sky130A", "libs.tech", "netgen",
                                     "sky130A_setup.tcl")
                out = os.path.join(w, "lvs.out")
                subprocess.run(["netgen", "-batch", "lvs", "%s %s" % (spice, name), "%s %s" % (sch, name), setup,
                                out], capture_output=True, text=True, cwd=w, timeout=600)
                with open(out) as f:
                    self.assertIn("Circuits match uniquely", f.read())

    def test_too_narrow_is_refused(self):
        import klayout.db as db
        from klayout_centroid import pcell
        from klayout_centroid.pattern import PatternError
        v = {p.name: p.default for p in pcell.CCArrayPCell().get_parameters()}
        v.update(self.CASES["cc_dp"], unit_params="w=1 l=0.5 nf=2 guard=0")
        ly = db.Layout()
        with self.assertRaisesRegex(PatternError, "wider"):
            pcell.draw(ly, ly.create_cell("T"), v)


if __name__ == "__main__":
    unittest.main()
