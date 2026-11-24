"""The hybrid-waffle generator (waffle.py): its geometry checks without any
PDK tool, then KLayout DRC, Magic DRC and netgen LVS through verify.py.

    KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
"""

import os
import shutil
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, needs_klayout

try:
    from klayout_power_pcells.verify import tools
    HAVE_TOOLS = HAVE_KLAYOUT and all(tools().values()) and os.path.isdir("/foss/pdks/sky130A")
except Exception:  # pragma: no cover
    HAVE_TOOLS = False

# name, parameters; every case must pass both DRC decks, and LVS where the
# buses join the stripes
CASES = [
    ("nfet_3x3", dict(nx=3, ny=3)),
    ("pfet_3x3", dict(nx=3, ny=3, device="pfet_01v8")),
    ("frame_only_4x2", dict(nx=4, ny=2, gate_strap="frame_only")),
    ("nfet5v_3x3", dict(nx=3, ny=3, device="nfet_g5v0d10v5")),
    ("pfet5v_2x2", dict(nx=2, ny=2, device="pfet_g5v0d10v5")),
    ("pfet_lvt_3x2", dict(nx=3, ny=2, device="pfet_01v8_lvt", L=0.35)),
    ("nfet_lvt_2x3_P3", dict(nx=2, ny=3, device="nfet_01v8_lvt", P=3.0)),
    ("pfet_hvt_2x2_L03", dict(nx=2, ny=2, device="pfet_01v8_hvt", L=0.3)),
    ("one_column_1x3", dict(nx=1, ny=3)),
    ("met5_3x3_P6", dict(nx=3, ny=3, P=6.0, runners=("met3", "met4", "met5"))),
    ("met3_only_3x2", dict(nx=3, ny=2, runners=("met3",))),
    ("bus_none_3x3", dict(nx=3, ny=3, bus="none")),
    ("wide_N_bus_3x2", dict(nx=3, ny=2, N=0.8, bus_w=5.0)),
]


@needs_klayout
class Geometry(unittest.TestCase):
    """Spec sections 5 and 9, without DRC tools."""

    def test_gate_count_and_widths(self):
        from klayout_power_pcells.waffle import WaffleParams, build
        for nx, ny in ((3, 3), (10, 10), (1, 3), (4, 1), (2, 5)):
            with self.subTest(nx=nx, ny=ny):
                w = build(WaffleParams(nx=nx, ny=ny))
                r = w.report
                self.assertEqual(r["n_gates"], (nx - 1) * ny + nx * (ny - 1))
                P, L, N = r["P_um"], r["L_um"], r["N_um"]
                inner, edge = round(P - N, 3), round(P - N / 2 - L / 2, 3)
                segs = r["W_seg_um"]
                if nx > 1 and ny > 1:
                    self.assertEqual(set(segs), {inner, edge} if max(nx, ny) > 2 else {edge})
                self.assertAlmostEqual(r["W_total_um"], sum(k * v for k, v in segs.items()), places=6)

    def test_notch_minimum(self):
        from klayout_power_pcells.waffle import WaffleParams, build
        self.assertEqual(build(WaffleParams(nx=2, ny=2)).report["N_um"], 0.55)       # licon + 2 x licon.14
        self.assertEqual(build(WaffleParams(nx=2, ny=2, gate_strap="frame_only")).report["N_um"], 0.3)
        self.assertEqual(build(WaffleParams(nx=2, ny=2, device="pfet_01v8")).report["N_um"], 0.64)

    def test_refused(self):
        from klayout_power_pcells.waffle import WaffleError, WaffleParams, build
        for kw, param in ((dict(nx=1, ny=1), "nx"), (dict(L=0.1), "L"), (dict(L=0.155), "L"),
                          (dict(N=0.4), "N"), (dict(P=0.5), "P"), (dict(device="nfet_g5v0d16v0"), "device"),
                          (dict(gate_strap="x"), "gate_strap"), (dict(runners=("met4",)), "runners"),
                          (dict(runner_style="staircase"), "runner_style"), (dict(bus="ring"), "bus"),
                          (dict(P=5.0, runners=("met3", "met4", "met5")), "P")):
            with self.subTest(params=kw):
                with self.assertRaises(WaffleError) as cm:
                    build(WaffleParams(nx=kw.pop("nx", 3), ny=kw.pop("ny", 3), **kw))
                self.assertEqual(cm.exception.param, param)

    def test_fill_cuts(self):
        import klayout.db as db
        from klayout_power_pcells.waffle import fill_cuts
        tri = db.Region(db.Polygon([db.Point(0, 0), db.Point(4000, 0), db.Point(0, 4000)]))
        cuts = fill_cuts(tri, 200, 200, 90)
        self.assertGreater(cuts.count(), 5)
        big = cuts.sized(90)
        self.assertTrue((big - tri).is_empty())            # a square of cut + enclosure fits everywhere
        for c in cuts.each():
            b = c.bbox()
            self.assertEqual((b.width(), b.height()), (200, 200))
            self.assertEqual((b.left % 5, b.bottom % 5), (0, 0))
        self.assertTrue(cuts.space_check(200).is_empty())


@unittest.skipUnless(HAVE_TOOLS, "needs klayout, magic, netgen and sky130A")
class Verified(unittest.TestCase):
    """Every case: KLayout's sky130A deck and Magic's drc(full) clean, the
    extracted devices right, and netgen matching one device of W_total."""

    def test_cases(self):
        from klayout_power_pcells.verify import verify
        from klayout_power_pcells.waffle import WaffleParams, summary, write_gds
        tmp = tempfile.mkdtemp(prefix="hw_verify_test_")
        try:
            for name, kw in CASES:
                with self.subTest(case=name):
                    work = os.path.join(tmp, name)
                    os.makedirs(work)
                    gds = os.path.join(work, "HW_FET.gds")
                    w = write_gds(WaffleParams(**kw), gds)
                    res = verify(gds, w.report, work=work)
                    self.assertEqual(res["problems"], [], "%s: %s" % (summary(w), res))
                    self.assertEqual(res["klayout"], {})
                    self.assertEqual(res["magic"], {})
                    self.assertEqual(res["devices"], w.report["n_gates"])
                    if kw.get("bus") == "none":
                        self.assertIsNone(res["lvs"])
                    else:
                        self.assertTrue(res["lvs"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_default_size_latchup(self):
        """The 10 x 10 default is clean in KLayout's deck and extracts right;
        Magic flags LU.2 only (the array centre is 20.9 um from the ring)."""
        from klayout_power_pcells.verify import verify
        from klayout_power_pcells.waffle import WaffleParams, write_gds
        tmp = tempfile.mkdtemp(prefix="hw_verify_test_")
        try:
            gds = os.path.join(tmp, "HW_FET.gds")
            w = write_gds(WaffleParams(), gds)
            self.assertFalse(w.report["lu_ok"])
            res = verify(gds, w.report, work=tmp)
            self.assertEqual(res["klayout"], {})
            self.assertEqual(set(res["magic"]), {"LU.2"})
            self.assertTrue(res["lvs"])
            self.assertEqual(res["devices"], 180)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
