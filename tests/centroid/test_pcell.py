"""CC_ARRAY in KLayout: placement, sky130A KLayout DRC, Magic DRC and
extraction. Needs the klayout module; the DRC/extraction tests also need
Magic and sky130A.

    KMP_PDKS=sky130A KMP_PDK=sky130A python3 -m unittest discover -s tests/centroid -t .
"""

import collections
import os
import shutil
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, HAVE_MAGIC, PY  # noqa: F401  (sets KMP_PDKS and a temp cache)

if PY not in sys.path:
    sys.path.insert(0, PY)

needs_klayout = unittest.skipUnless(HAVE_KLAYOUT, "the klayout Python module is not installed")
needs_magic = unittest.skipUnless(HAVE_MAGIC, "needs klayout, Magic and sky130A")


def _setup():
    import klayout_magic_pcells as kmp
    import klayout_centroid as kc
    kmp.register()
    kc.register()


def make(name, params, flat=False):
    import klayout.db as db
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell(name)
    c = ly.create_cell("CC_ARRAY", "centroid", params)
    top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
    if flat:
        top.flatten(-1, True)
    return ly, top, c


def props(ly, c):
    out = []
    for inst in c.each_inst():
        out.append(dict(kv.split("=") for kv in inst.property(1).split(";")))
    return out


@needs_klayout
class TestPlacement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()

    def test_instances_follow_pattern(self):
        from klayout_centroid.pattern import build
        ly, top, c = make("T", {"devices": "A:4,B:4", "style": "checkerboard", "dummies": "ring",
                                "rows": 2, "cols": 4})
        p = props(ly, c)
        self.assertEqual(len(p), 4 * 6)
        cnt = collections.Counter(d["device"] for d in p)
        self.assertEqual(cnt, {"A": 4, "B": 4, "dummy": 16})
        grid = build("A:4,B:4", rows=2, cols=4, style="checkerboard").grid
        for d in p:
            i, j = int(d["row"]), int(d["col"])
            if 0 <= i < len(grid) and 0 <= j < len(grid[0]):
                self.assertEqual(d["device"], grid[i][j])

    def test_device_centroids_coincide_in_um(self):
        ly, top, c = make("T", {"devices": "1:2:4:8", "dummies": "none"})
        pos = collections.defaultdict(list)
        for inst in c.each_inst():
            dev = inst.property(1).split(";")[0].split("=")[1]
            pos[dev].append(inst.dbbox().center())
        cents = {k: (sum(p.x for p in v) / len(v), sum(p.y for p in v) / len(v)) for k, v in pos.items()}
        ref = cents["A"]
        for k, v in cents.items():
            self.assertAlmostEqual(v[0], ref[0], places=6, msg=k)
            self.assertAlmostEqual(v[1], ref[1], places=6, msg=k)

    def test_labels(self):
        """One text per unit with its device name, on 81/79 (ignored by
        extraction), at the unit's centre; none with labels off."""
        ly, top, c = make("T", {"devices": "A:4,B:4", "rows": 2, "cols": 4, "dummies": "ring"})
        li = ly.find_layer(81, 79)
        texts = [s for s in c.shapes(li).each() if s.is_text()]
        by_inst = {}
        for inst in c.each_inst():
            by_inst[(round(inst.dbbox().center().x, 3), round(inst.dbbox().center().y, 3))] = \
                inst.property(1).split(";")[0].split("=")[1]
        self.assertEqual(len(texts), len(by_inst))
        for s in texts:
            p = s.dtext.position()
            self.assertEqual(s.text_string, by_inst[(round(p.x, 3), round(p.y, 3))])
        self.assertEqual(collections.Counter(s.text_string for s in texts), {"A": 4, "B": 4, "dummy": 16})
        ly, top, c = make("T", {"devices": "A:4,B:4", "labels": False})
        li = ly.find_layer(81, 79)
        self.assertTrue(li is None or c.shapes(li).is_empty())

    def test_dummy_modes(self):
        for mode, n in (("ring", 6 * 4), ("edge", 2 * 6), ("none", 2 * 4)):
            ly, top, c = make("T", {"devices": "A:4,B:4", "dummies": mode, "rows": 2, "cols": 4})
            self.assertEqual(len(props(ly, c)), n, mode)

    def test_error_marker(self):
        ly, top, c = make("T", {"devices": "A:1,B:1"})
        texts = [s.text_string for li in ly.layer_indexes() for s in c.shapes(li).each() if s.is_text()]
        self.assertTrue(any(t.startswith("CC_ERROR") for t in texts), texts)
        ly, top, c = make("T", {"unit": "no_such_cell"})
        texts = [s.text_string for li in ly.layer_indexes() for s in c.shapes(li).each() if s.is_text()]
        self.assertTrue(any("no PCell no_such_cell" in t for t in texts), texts)

    def test_unit_dropdown(self):
        import klayout.db as db
        from klayout_centroid import pcell
        decl = db.Library.library_by_name("centroid").layout().pcell_declaration("CC_ARRAY")
        unit = [p for p in decl.get_parameters() if p.name == "unit"][0]
        values = unit.choice_values()
        labels = unit.choice_descriptions()
        self.assertIn("sky130_magic/sky130_fd_pr__nfet_01v8", values)
        self.assertIn("sky130_magic/sky130_fd_pr__cap_mim_m3_1", values)
        self.assertFalse(any("via" in v.split("/")[1] for v in values))     # no box-paint generators
        self.assertTrue(labels[0].startswith("MOS: "), labels[0])           # MOS devices first
        self.assertEqual(pcell.suggested_params("sky130_magic/sky130_fd_pr__nfet_01v8"), "w=1 l=0.5 nf=2 guard=1")
        self.assertIn("w=", pcell.suggested_params("sky130_magic/sky130_fd_pr__cap_mim_m3_1"))
        # picking another unit in the form (coerce) offers its parameters,
        # but keeps values the user typed if they fit the new unit
        names = [p.name for p in decl.get_parameters()]
        vals = [p.default for p in decl.get_parameters()]
        vals[names.index("unit")] = "sky130_magic/sky130_fd_pr__cap_mim_m3_1"
        out = decl.coerce_parameters(db.Layout(), vals)
        self.assertEqual(out[names.index("unit_params")], pcell.suggested_params(vals[names.index("unit")]))
        self.assertEqual(out[names.index("last_unit")], vals[names.index("unit")])
        vals = [p.default for p in decl.get_parameters()]
        vals[names.index("unit")] = "sky130_magic/sky130_fd_pr__pfet_01v8"
        vals[names.index("unit_params")] = "w=2 l=1 nf=4"
        out = decl.coerce_parameters(db.Layout(), vals)
        self.assertEqual(out[names.index("unit_params")], "w=2 l=1 nf=4")
        # a bare PCell name still works
        ly, top, c = make("T", {"unit": "sky130_fd_pr__nfet_01v8", "devices": "A:2,B:2", "dummies": "none"})
        self.assertEqual(len(props(ly, c)), 4)

    def test_form_coerce(self):
        import klayout.db as db
        decl = db.Library.library_by_name("centroid").layout().pcell_declaration("CC_ARRAY")
        names = [p.name for p in decl.get_parameters()]
        vals = [p.default for p in decl.get_parameters()]
        vals[names.index("devices")] = "A:2,B:2"
        vals[names.index("style")] = "checkerboard"
        out = decl.coerce_parameters(db.Layout(), vals)
        self.assertEqual(out[names.index("grid")], "AB / BA")
        self.assertIn("centroid OK", out[names.index("info")])


@needs_magic
class TestVerify(unittest.TestCase):
    CASES = {
        "cc_nf_ring": {"devices": "A:4,B:4", "unit_params": "w=1 l=0.5 nf=2 guard=0"},
        "cc_nf_none": {"devices": "A:4,B:4", "dummies": "none", "unit_params": "w=1 l=0.5 nf=2 guard=0"},
        "cc_pf_ring": {"unit": "sky130_magic/sky130_fd_pr__pfet_01v8", "devices": "A:4,B:4",
                       "unit_params": "w=1 l=0.5 nf=2 guard=0"},
        "cc_nf_guard": {"devices": "A:3,B:5", "dummies": "edge"},
        # (w=0.6 l=0.15 is not used: Magic's unit alone breaks m1.6, met1 area)
        "cc_ratio_guard": {"devices": "1:2:4:8", "dummies": "ring", "unit_params": "w=1 l=0.5 nf=1 guard=1"},
    }

    @classmethod
    def setUpClass(cls):
        _setup()
        cls.work = tempfile.mkdtemp(prefix="cc_test_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def _gds(self, name, flat=False):
        ly, top, c = make(name, self.CASES[name], flat)
        gds = os.path.join(self.work, name + (".flat" if flat else "") + ".gds")
        ly.write(gds)
        w = os.path.join(self.work, name + ("_flat" if flat else ""))
        os.makedirs(w, exist_ok=True)
        return gds, w

    def test_klayout_drc_clean(self):
        from klayout_power_pcells import verify
        for name in self.CASES:
            with self.subTest(name):
                gds, w = self._gds(name)
                self.assertEqual(verify.klayout_drc(gds, name, w), {})

    def test_magic_drc_clean_with_guard_rings(self):
        """Units with guard rings are Magic-clean; tapless units only break
        Magic's latch-up rules (no tap within 15 um), never a spacing rule."""
        from klayout_power_pcells import verify
        for name in self.CASES:
            with self.subTest(name):
                gds, w = self._gds(name)
                errs = verify.magic_drc(gds, name, w)
                if "guard" in name:
                    self.assertEqual(errs, {})
                else:
                    self.assertTrue(set(errs) <= {"LU.2", "LU.3", "nwell.4"}, errs)

    def test_extraction_units_isolated(self):
        """Every unit extracts as its own device(s): nf devices per unit, and
        no S/D net shared between units."""
        from klayout_power_pcells import verify
        name = "cc_nf_ring"
        gds, w = self._gds(name, flat=True)
        spice, devs = verify.extract(gds, name, w)
        units = 6 * 4
        self.assertEqual(len(devs), units * 2)
        nets = collections.Counter(d[t] for d in devs for t in "ds")
        self.assertEqual(len(nets), units * 3)       # D0, S1, D2 per two-finger unit
        self.assertTrue(all(d["w"] == 1.0 and d["l"] == 0.5 for d in devs))


if __name__ == "__main__":
    unittest.main()
