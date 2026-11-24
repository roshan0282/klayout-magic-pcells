"""Hybrid-waffle nfet (milestone 1): Magic DRC and Magic extraction through
the parity harness's runners (tests/parity/drc.py).

Needs Magic, sky130A and the klayout Python module; run from the repository
root:

    KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .

Each case must be DRC clean in Magic's drc(full) and must extract as
blocks x nf devices of sky130_fd_pr__nfet_01v8, each with Magic's checked W
and L, summing to the generator's total W, with every gate on G and every
source/drain on S and D.
"""

import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "python"))
os.environ.setdefault("KMP_PDKS", "sky130A")

try:
    import klayout.db as db
except ImportError:  # pragma: no cover
    db = None

from tests.parity import drc  # noqa: E402

HAVE_MAGIC = shutil.which("magic") is not None and os.path.isdir(
    os.path.join(drc.PDK_ROOT, "sky130A", "libs.tech", "magic"))

CASES = [
    # name, params
    ("default_3x3_nf3", dict(l=0.5, w=2.0, nf=3, nx=3, ny=3, strap_w=3.0)),
    ("min_l_2x2_nf1", dict(l=0.15, w=1.0, nf=1, nx=2, ny=2, strap_w=2.4)),
    ("even_nf_3x2", dict(l=0.15, w=1.5, nf=2, nx=3, ny=2, strap_w=2.5)),
    ("wide_4x3_nf4", dict(l=0.25, w=3.0, nf=4, nx=4, ny=3, strap_w=4.0)),
    ("set_pitch_2x3", dict(l=0.5, w=1.2, nf=5, nx=2, ny=3, strap_w=3.0, pitch=9.0)),
    ("one_row_4x1_staggered", dict(l=0.18, w=3.5, nf=1, nx=4, ny=1, strap_w=2.75)),
]

DEVICE = "sky130_fd_pr__nfet_01v8"


def spice_terminals(path):
    """(d, g, s, b) of every device line of an ext2spice netlist."""
    out = []
    with open(path, errors="replace") as f:
        text = f.read().replace("\n+", " ")
    for line in text.splitlines():
        toks = line.split()
        if toks and toks[0][0] in "Xx" and DEVICE in toks:
            plain = [t for t in toks if "=" not in t]
            out.append(tuple(plain[1:5]))
    return out


@unittest.skipUnless(db is not None and HAVE_MAGIC, "needs klayout, Magic and sky130A")
class HybridWaffleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from klayout_power_pcells import HWParams, write_gds
        cls.tmp = tempfile.mkdtemp(prefix="hw_test_")
        cls.made = {}
        for name, kw in CASES:
            gds = os.path.join(cls.tmp, name + ".gds")
            res = write_gds(HWParams(**kw), gds, name="HW_" + name.upper())
            cls.made[name] = (gds, res)

    @classmethod
    def tearDownClass(cls):
        if os.environ.get("HW_KEEP"):
            print("kept test files in %s" % cls.tmp)
        else:
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def _cell(self, name):
        gds, res = self.made[name]
        ly = db.Layout()
        ly.read(gds)
        self.assertEqual([c.name for c in ly.top_cells()], [res.cell_name])
        self.assertFalse(ly.cell(res.cell_name).bbox().empty())
        return gds, res

    def test_magic_drc_clean(self):
        for name, _kw in CASES:
            with self.subTest(case=name):
                gds, res = self._cell(name)
                base = os.path.join(self.tmp, name)
                errs = drc.run_magic_drc(gds, res.cell_name, base + ".drc.tsv", base + ".drc.log")
                self.assertEqual(errs, [], "%s: Magic DRC errors %s" % (res.summary(), errs[:10]))

    def test_magic_extraction(self):
        for name, kw in CASES:
            with self.subTest(case=name):
                gds, res = self._cell(name)
                out = os.path.join(self.tmp, name + "_ext")
                got = drc.run_magic_extract(gds, [res.cell_name], out,
                                            os.path.join(self.tmp, name + ".ext.log"))
                devs = got[res.cell_name]
                self.assertTrue(devs, "%s: no netlist" % name)
                # Magic's checked values of the unit cell are the ones asked for
                self.assertAlmostEqual(res.w, kw["w"], places=6)
                self.assertAlmostEqual(res.l, kw["l"], places=6)
                self.assertEqual(res.nf, kw["nf"])
                blocks = (kw["nx"] - 1) * kw["ny"] + kw["nx"] * (kw["ny"] - 1)
                self.assertEqual(res.blocks, blocks)
                self.assertEqual({d[0] for d in devs}, {DEVICE})
                for model, w, l in devs:
                    self.assertAlmostEqual(w, res.w, delta=0.0051)
                    self.assertAlmostEqual(l, res.l, delta=0.0051)
                self.assertEqual(len(devs), blocks * kw["nf"])
                self.assertAlmostEqual(sum(d[1] for d in devs), res.total_w, delta=0.001)
                self.assertAlmostEqual(res.total_w, blocks * kw["nf"] * kw["w"], delta=1e-6)
                terms = spice_terminals(os.path.join(out, res.cell_name + ".spice"))
                self.assertEqual(len(terms), len(devs))
                for d, g, s, b in terms:
                    self.assertEqual(g, "G")
                    self.assertEqual({d, s}, {"S", "D"})
                    self.assertEqual(b, "B")

    def test_too_narrow_or_too_large_refused(self):
        from klayout_power_pcells import HWParams, write_gds
        path = os.path.join(self.tmp, "refused.gds")
        for kw in (dict(w=0.6), dict(strap_w=1.5), dict(strap_w=2.3), dict(nx=6, ny=6), dict(nx=1, ny=1)):
            with self.subTest(params=kw):
                with self.assertRaises(ValueError):
                    write_gds(HWParams(**kw), path)


if __name__ == "__main__":
    unittest.main()
