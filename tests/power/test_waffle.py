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
    ("big_tap_3x3", dict(nx=3, ny=3, tap_w=1.0)),
    ("no_source_taps_3x3", dict(nx=3, ny=3, source_taps=False)),      # body on its own pin, B
    # 45 degree stripes stay under 3 um wide at a large pitch (Magic's wide-metal halo)
    ("diag45_P8_3x3", dict(nx=3, ny=3, P=8.0)),
    # narrower stripes than the widest that fits
    ("runner_w_0.6_3x3", dict(nx=3, ny=3, runner_w=0.6)),
    ("staircase_runner_w_1.2_3x3", dict(nx=3, ny=3, runner_style="staircase", runner_w=1.2)),
    # 0/90 degree runners
    ("staircase_3x3", dict(nx=3, ny=3, runner_style="staircase")),
    ("staircase_met5_3x3_P6", dict(nx=3, ny=3, P=6.0, runners=("met3", "met4", "met5"), runner_style="staircase")),
    ("staircase_bus_none_3x2", dict(nx=3, ny=2, runner_style="staircase", bus="none")),
    ("planes_3x3", dict(nx=3, ny=3, runner_style="planes")),
    ("planes_met5_3x3_P6", dict(nx=3, ny=3, P=6.0, runners=("met3", "met4", "met5"), runner_style="planes")),
    ("planes_D_bottom_3x3", dict(nx=3, ny=3, runner_style="planes", bottom_net="D")),
    ("planes_D_bottom_met5_ld_3x3", dict(nx=3, ny=3, device="nfet_g5v0d16v0", P=7.0, runner_style="planes",
                                         runners=("met3", "met4", "met5"), bottom_net="D")),
    ("planes_bus_none_pfet_3x3", dict(nx=3, ny=3, device="pfet_01v8", runner_style="planes", bus="none")),
    # extended-drain (LDMOS) devices; LVS through verify.extract_ld
    ("nfet16v_3x3_P7", dict(nx=3, ny=3, device="nfet_g5v0d16v0", P=7.0)),
    ("nfet16v_planes_2x3_P7", dict(nx=2, ny=3, device="nfet_g5v0d16v0", P=7.0, runner_style="planes")),
    ("pfet16v_3x3_P6.6", dict(nx=3, ny=3, device="pfet_g5v0d16v0", P=6.6)),
    ("pfet16v_no_dnwell_3x2_P6.6", dict(nx=3, ny=2, device="pfet_g5v0d16v0", P=6.6, deep_nwell=False,
                                        runner_style="staircase")),
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
                          (dict(N=0.4), "N"), (dict(P=0.5), "P"), (dict(device="nfet_20v0"), "device"),
                          (dict(device="nfet_g5v0d16v0"), "P"), (dict(device="nfet_g5v0d16v0", P=7.0, N=2.0), "N"),
                          (dict(device="pfet_g5v0d16v0", P=6.6, guard_ring=False), "deep_nwell"),
                          (dict(runner_style="planes", runners=("met3",)), "runners"),
                          (dict(gate_strap="x"), "gate_strap"), (dict(runners=("met4",)), "runners"),
                          (dict(runner_style="bogus"), "runner_style"), (dict(bottom_net="G"), "bottom_net"), (dict(bus="ring"), "bus"),
                          (dict(P=5.0, runners=("met3", "met4", "met5")), "P"), (dict(P=2.0), "tap_w"),
                          (dict(tap_w=0.3), "tap_w"), (dict(runner_w=3.0), "runner_w"),
                          (dict(runner_w=0.1), "runner_w"), (dict(runner_w=0.4), "runner_w"),
                          (dict(runner_style="planes", runner_w=1.0), "runner_w")):
            with self.subTest(params=kw):
                with self.assertRaises(WaffleError) as cm:
                    build(WaffleParams(nx=kw.pop("nx", 3), ny=kw.pop("ny", 3), **kw))
                self.assertEqual(cm.exception.param, param)

    def test_ld(self):
        """Extended drain: every gate W >= 5 um, gates L - 0.13 wide on
        diffusion, a drain tap in every D square, EDID over them, HVNTM
        for the n device, and N pinned to L + 4 x 0.185 for it."""
        from klayout_power_pcells.waffle import WaffleParams, build
        for dev, P in (("nfet_g5v0d16v0", 7.0), ("pfet_g5v0d16v0", 6.6)):
            with self.subTest(device=dev):
                w = build(WaffleParams(nx=3, ny=3, device=dev, P=P))
                r = w.report
                self.assertTrue(r["ld"])
                self.assertEqual(r["n_gates"], 12)
                self.assertGreaterEqual(min(r["W_seg_um"]), 5.0)
                self.assertEqual(w.regions["tap"].count() >= 4, True)
                self.assertFalse(w.regions["edid"].is_empty())
                if dev.startswith("n"):
                    self.assertAlmostEqual(r["N_um"], r["L_um"] + 0.74)
                    self.assertFalse(w.regions["hvntm"].is_empty())
                else:
                    self.assertTrue(r.get("deep_nwell"))
                    self.assertFalse(w.regions["dnwell"].is_empty())
        # the 5 V nfet gets its tip implant too
        self.assertIn("hvntm", build(WaffleParams(nx=2, ny=2, device="nfet_g5v0d10v5")).regions)

    def test_runner_styles(self):
        """staircase and planes draw 0/90 degree metal only."""
        from klayout_power_pcells.waffle import WaffleParams, build
        for st in ("staircase", "planes"):
            with self.subTest(style=st):
                w = build(WaffleParams(nx=3, ny=3, runner_style=st))
                for lay in ("met3", "met4"):
                    for poly in w.regions[lay].each():
                        for e in poly.each_edge():
                            self.assertTrue(e.dx() == 0 or e.dy() == 0, "%s %s" % (lay, e))

    def test_runner_w(self):
        """runner_w sets the stripe width (to the 4-grid diagonal), 0 = the widest."""
        from klayout_power_pcells.waffle import WaffleParams, build
        auto = build(WaffleParams(nx=3, ny=3)).report["stripe_width_um"]
        for st in ("diag45", "staircase"):
            r = build(WaffleParams(nx=3, ny=3, runner_style=st, runner_w=1.2)).report
            self.assertAlmostEqual(r["stripe_width_um"], 1.2, delta=0.006)
        self.assertGreater(auto, 2.0)

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
                    if not w.report["sd_joined"]:
                        self.assertIsNone(res["lvs"])
                    else:
                        self.assertTrue(res["lvs"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_default_size(self):
        """The 10 x 10 default: with the source-square taps every check is
        clean, Magic's latch-up rules included (the farthest diffusion is
        about 3 um from a tap), and the body is S. Without them, Magic flags
        LU.2 (20.8 um from the guard ring) and nothing else."""
        from klayout_power_pcells.verify import verify
        from klayout_power_pcells.waffle import WaffleParams, write_gds
        tmp = tempfile.mkdtemp(prefix="hw_verify_test_")
        try:
            for taps in (True, False):
                with self.subTest(source_taps=taps):
                    work = os.path.join(tmp, str(taps))
                    os.makedirs(work)
                    gds = os.path.join(work, "HW_FET.gds")
                    w = write_gds(WaffleParams(source_taps=taps), gds)
                    self.assertEqual(w.report["lu_ok"], taps)
                    res = verify(gds, w.report, work=work)
                    self.assertEqual(res["klayout"], {})
                    self.assertEqual(res["magic"], {} if taps else {"LU.2": res["magic"].get("LU.2")})
                    self.assertTrue(res["lvs"])
                    self.assertEqual(res["devices"], 180)
                    self.assertEqual(w.report["body"], "S" if taps else "B")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
