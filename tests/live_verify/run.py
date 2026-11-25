"""Headless tests: klayout -b -r tests/live_verify/run.py  (or python3 tests/live_verify/run.py
with the klayout module installed). Needs the sky130A deck for tier 1."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "python"))
sys.path.insert(0, HERE)

import klayout.db as db  # noqa: E402

from live_verify import dirty, engine, pdk  # noqa: E402

HAVE_DECK = pdk.deck("sky130A") is not None
M1 = (68, 20)


def layout_with_violations():
    """met1: a 0.10 um gap at x 0..1 (inside the window) and another at
    x 50 (outside); a 2 um-wide wire that the clip cuts through."""
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell("TOP")
    m1 = ly.layer(*M1)
    s = top.shapes(m1)
    s.insert(db.DBox(0, 0, 1, 1))
    s.insert(db.DBox(1.1, 0, 2, 1))           # 0.10 um from the first: m1 space
    s.insert(db.DBox(50, 0, 51, 1))
    s.insert(db.DBox(51.1, 0, 52, 1))
    s.insert(db.DBox(-20, 5, 20, 7))          # long wire crossing the clip box
    return ly, top


class TestTier0(unittest.TestCase):
    def test_window_and_clip_edges(self):
        ly, top = layout_with_violations()
        res = engine.check_area(ly, top, db.DBox(-2, -2, 4, 8), "sky130A", tiers=(0,))
        rules = [r for r, _ in res[0]]
        self.assertEqual(rules, ["met1 space < 0.14"])          # not the far one, no clip artefact
        b = res[0][0][1].bbox()
        self.assertTrue(b.inside(db.DBox(0.9, -0.1, 1.2, 1.1)))

    def test_clean_area(self):
        ly, top = layout_with_violations()
        res = engine.check_area(ly, top, db.DBox(10, -2, 20, 8), "sky130A", tiers=(0,))
        self.assertEqual(res[0], [])


@unittest.skipUnless(HAVE_DECK, "no sky130A KLayout deck")
class TestTier1(unittest.TestCase):
    def test_deck_on_clip(self):
        ly, top = layout_with_violations()
        res = engine.check_area(ly, top, db.DBox(-2, -2, 4, 8), "sky130A")
        rules = sorted(set(r for r, _ in res[1]))
        self.assertIn("m1.2", [r.split()[0].split(":")[0] for r in rules])
        far = [s for _, s in res[1] if s.bbox().left > 40]
        self.assertEqual(far, [])


@unittest.skipUnless(pdk.deck("gf180mcuD") is not None, "no gf180mcuD KLayout deck")
class TestGf180(unittest.TestCase):
    def test_metal1_gap(self):
        ly = db.Layout()
        ly.dbu = 0.001
        top = ly.create_cell("TOP")
        m1 = ly.layer(34, 0)
        top.shapes(m1).insert(db.DBox(0, 0, 1, 1))
        top.shapes(m1).insert(db.DBox(1.1, 0, 2, 1))
        res = engine.check_area(ly, top, db.DBox(-2, -2, 4, 3), "gf180mcuD")
        self.assertEqual([r for r, _ in res[0]], ["Metal1 space < 0.23"])
        self.assertIn("M1.2a", [r.split()[0] for r, _ in res[1]])


class TestDirty(unittest.TestCase):
    def test_changed_area(self):
        ly, top = layout_with_violations()
        view = db.DBox(-30, -10, 60, 10)
        a = dirty.snapshot(ly, top, view)
        self.assertIsNone(dirty.changed(a, dirty.snapshot(ly, top, view), ly.dbu))
        top.shapes(ly.layer(*M1)).insert(db.DBox(30, 0, 31, 2))
        box = dirty.changed(a, dirty.snapshot(ly, top, view), ly.dbu)
        self.assertEqual(box, db.DBox(30, 0, 31, 2))


class TestReport(unittest.TestCase):
    def test_rdb(self):
        import klayout.rdb as rdb
        from live_verify import results
        ly, top = layout_with_violations()
        res = engine.check_area(ly, top, db.DBox(-2, -2, 4, 8), "sky130A", tiers=(0,))
        r = results.to_rdb(rdb.ReportDatabase("live"), "TOP", res)
        self.assertEqual([c.name() for c in r.each_category()], ["T0 met1 space < 0.14"])
        self.assertEqual(r.num_items(), 1)


if __name__ == "__main__" or "pya" in sys.modules:
    prog = unittest.main(argv=["run.py"], exit=False, verbosity=2)
    ok = prog.result.wasSuccessful()
    if "pya" in sys.modules:
        import pya  # noqa: F401
        os._exit(0 if ok else 1)
    sys.exit(0 if ok else 1)
