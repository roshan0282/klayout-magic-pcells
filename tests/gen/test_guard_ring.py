"""GUARD_RING (sky130_gen): geometry, sky130A KLayout and Magic DRC, and
that a device inside a ring takes the ring as its body.

    KMP_PDKS=sky130A KMP_PDK=sky130A python3 -m unittest discover -s tests/gen -t .
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


def shapes():
    import klayout.db as db
    L = db.DPolygon([db.DPoint(0, 0), db.DPoint(12, 0), db.DPoint(12, 4), db.DPoint(5, 4), db.DPoint(5, 9),
                     db.DPoint(0, 9)])
    U = db.DPolygon([db.DPoint(0, 0), db.DPoint(10, 0), db.DPoint(10, 8), db.DPoint(7, 8), db.DPoint(7, 3),
                     db.DPoint(3, 3), db.DPoint(3, 8), db.DPoint(0, 8)])
    return {
        "gr_box_p": {"shape": db.DBox(0, 0, 10, 5)},
        "gr_box_n": {"shape": db.DBox(0, 0, 10, 5), "kind": "ntap"},
        "gr_L_p": {"shape": L},
        "gr_U_n": {"shape": U, "kind": "ntap", "width": 0.6},
        "gr_U_nomet": {"shape": U, "met1": False},
        "gr_path": {"shape": db.DPath([db.DPoint(0, 0), db.DPoint(20, 0), db.DPoint(20, 10)], 2.0)},
        "gr_dnw": {"shape": db.DBox(0, 0, 8, 6), "kind": "ntap", "deep_nwell": True},
    }


@needs_klayout
class TestGeometry(unittest.TestCase):
    def test_ring_encloses_with_clearance(self):
        import klayout.db as db
        from klayout_gen.guard_ring import ring
        box = db.DBox(0, 0, 10, 5)
        r = ring(box, 0.001, clearance=0.5)
        tap = r["tap"]
        inner_edge = db.Region(box.to_itype(0.001)).sized(500)
        self.assertTrue((tap & inner_edge).is_empty())          # clearance kept
        polys = list(tap.merged().each())
        self.assertEqual((len(polys), polys[0].holes()), (1, 1))          # one closed ring
        self.assertGreaterEqual(r["licon"].count(), 4)
        self.assertTrue((r["licon"] - tap).is_empty())
        self.assertTrue((r["mcon"] - r["met1"]).is_empty())

    def test_refusals(self):
        import klayout.db as db
        from klayout_gen.guard_ring import RingError, ring
        with self.assertRaises(RingError):
            ring(db.DBox(0, 0, 5, 5), 0.001, width=0.2)
        with self.assertRaises(RingError):
            ring(db.DPolygon([db.DPoint(0, 0), db.DPoint(5, 0), db.DPoint(0, 5)]), 0.001)
        with self.assertRaises(RingError):
            ring(db.DBox(0, 0, 5, 5), 0.001, kind="ptap", deep_nwell=True)

    def test_pcell_error_marker(self):
        import klayout.db as db
        import klayout_gen
        klayout_gen.register()
        ly = db.Layout()
        c = ly.create_cell("GUARD_RING", "sky130_gen", {"width": 0.2})
        texts = [s.text_string for li in ly.layer_indexes() for s in c.shapes(li).each() if s.is_text()]
        self.assertTrue(any(t.startswith("GEN_ERROR") for t in texts), texts)


@needs_magic
class TestDRC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import klayout_gen
        klayout_gen.register()
        cls.work = tempfile.mkdtemp(prefix="gr_test_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def _gds(self, name, params, extra=None):
        import klayout.db as db
        ly = db.Layout()
        ly.dbu = 0.001
        top = ly.create_cell(name)
        c = ly.create_cell("GUARD_RING", "sky130_gen", params)
        top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
        if extra:
            extra(ly, top)
        gds = os.path.join(self.work, name + ".gds")
        ly.write(gds)
        w = os.path.join(self.work, name)
        os.makedirs(w, exist_ok=True)
        return gds, w

    def test_drc_clean(self):
        from klayout_power_pcells import verify
        for name, params in shapes().items():
            with self.subTest(name):
                gds, w = self._gds(name, params)
                self.assertEqual(verify.klayout_drc(gds, name, w), {})
                self.assertEqual(verify.magic_drc(gds, name, w), {})

    def test_ring_is_the_body(self):
        """A tapless Magic nfet inside a p-tap ring: Magic DRC clean (the
        ring satisfies the latch-up rules) and the device's body is B."""
        import klayout.db as db
        import klayout_magic_pcells as kmp
        from klayout_power_pcells import verify
        kmp.register()

        def nfet(ly, top):
            c = ly.create_cell("sky130_fd_pr__nfet_01v8", "sky130_magic", {"w": 1.0, "l": 0.5, "nf": 2, "guard": 0})
            top.insert(db.DCellInstArray(c.cell_index(), db.DTrans(db.DVector(4, 2.5))))

        name = "gr_body"
        gds, w = self._gds(name, {"shape": db.DBox(2.5, 1, 5.5, 4)}, nfet)
        self.assertEqual(verify.klayout_drc(gds, name, w), {})
        self.assertEqual(verify.magic_drc(gds, name, w), {})
        ly = db.Layout()
        ly.read(gds)
        ly.top_cell().flatten(-1, True)
        flat = gds.replace(".gds", "_flat.gds")
        ly.write(flat)
        _, devs = verify.extract(flat, name, w)
        self.assertEqual(len(devs), 2)
        self.assertEqual({d["b"] for d in devs}, {"B"})


if __name__ == "__main__":
    unittest.main()
