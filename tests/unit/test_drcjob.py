"""drcjob.py and the drc additions to markers.py, without Magic: rule IDs and
categories, µm conversion, the area filter, the copy drop, the TSV,
the item texts and descriptions, and the Rerun generator."""

import io
import os
import shutil
import tempfile
import types
import unittest

from tests.unit._util import REPO, needs_klayout, db  # noqa: F401

from klayout_magic_pcells import drcjob
from klayout_magic_pcells.drcjob import Error, Xf

SCALE = 0.004999999888241291   # Magic's [cif scale out] on all four PDKs, as printed


class Ids(unittest.TestCase):
    def test_rule_id_is_the_last_parentheses(self):
        self.assertEqual(drcjob.rule_id("N-well width < 0.84um (nwell.1)"), "nwell.1")
        self.assertEqual(drcjob.rule_id("Diffusion to tap (diff/tap.8)"), "diff/tap.8")
        self.assertEqual(drcjob.rule_id("licon spacing (well) to psdm < 0.13um (licon.9 + psdm.5a)"),
                         "licon.9 + psdm.5a")
        self.assertEqual(drcjob.rule_id("Only 45 and 90 degree angles permitted on metal1 (Grid Rules)"),
                         "Grid Rules")
        self.assertEqual(drcjob.rule_id("via spacing (via.5a - via.4a)  "), "via.5a - via.4a")

    def test_empty_ids_are_keyed_by_the_why_text(self):
        for why in ("Can't overlap those layers", "P-diffusion and N-ohmic must be over N-well or deep N-well",
                    "Something ()"):
            self.assertEqual(drcjob.rule_id(why), why)
            self.assertEqual(drcjob.category_path(why), (drcjob.CAT_DRC, why))

    def test_one_category_per_why_text_under_its_rule(self):
        a = "Licon spacing to diff < 0.055um (licon.11)"
        b = "Licon spacing to diff < 0.05um (licon.11)"
        self.assertEqual(drcjob.category_path(a), (drcjob.CAT_DRC, "licon.11", a))
        self.assertEqual(drcjob.category_path(b), (drcjob.CAT_DRC, "licon.11", b))
        self.assertNotEqual(drcjob.category_path(a), drcjob.category_path(b))
        c = "x (licon.9 + psdm.5a)"
        self.assertEqual(drcjob.category_path(c), (drcjob.CAT_DRC, "licon.9 + psdm.5a", c))


class Units(unittest.TestCase):
    def test_magic_units_to_nm(self):
        self.assertEqual(drcjob.nm_per_unit(SCALE), 5.0)
        self.assertEqual(drcjob.to_nm(270, SCALE), 1350)
        self.assertEqual(drcjob.to_nm(-3, SCALE), -15)
        self.assertEqual(drcjob.to_nm("234", SCALE), 1170)
        # 100 mm: whole units stay whole, where v * scale * 1000 would be off by 2 nm
        self.assertEqual(drcjob.to_nm(20000000, SCALE), 100000000)
        # units rescaled by 5 for an off-grid file: 1 nm per unit
        self.assertEqual(drcjob.to_nm(7, SCALE / 5), 7)

    def test_um_text(self):
        self.assertEqual(drcjob.fmt_um(1350), "1.35")
        self.assertEqual(drcjob.fmt_um(-500), "-0.5")
        self.assertEqual(drcjob.fmt_um(0), "0")
        self.assertEqual(drcjob.fmt_um(-0), "0")
        self.assertEqual(drcjob.fmt_um(1), "0.001")
        self.assertEqual(drcjob.fmt_um(100000000), "100000")

    def test_area_in_nm(self):
        self.assertEqual(drcjob.area_nm((85, 0, 100, 3)), (85000, 0, 100000, 3000))
        self.assertEqual(drcjob.area_nm("0.1,-0.2,0.3,0.4"), (100, -200, 300, 400))
        with self.assertRaises(ValueError):
            drcjob.area_nm((1, 0, 1, 2))

    def test_parse_cell_tsv(self):
        d = tempfile.mkdtemp(prefix="kmp-drc-unit-")
        try:
            p = os.path.join(d, "drc_0.tsv")
            with open(p, "w") as f:
                f.write("a_poly8\tpoly overhang of transistor < 0.13um (poly.8)\t270\t234\t300\t250\n")
                f.write("a_poly8\tbroken line\n")
                f.write("a_poly8\tflipped\t300\t250\t270\t234\n")
            errs = drcjob.parse_cell_tsv(p, SCALE)
            self.assertEqual(errs, [Error("a_poly8", "poly overhang of transistor < 0.13um (poly.8)",
                                          (1350, 1170, 1500, 1250)),
                                    Error("a_poly8", "flipped", (1350, 1170, 1500, 1250))])
            self.assertEqual(drcjob.parse_cell_tsv(os.path.join(d, "none.tsv"), SCALE), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Tsv(unittest.TestCase):
    def test_rows_in_um_with_the_rule(self):
        rows = [("inv", "N-well width < 0.84um (nwell.1)", (1170, 3320, 1680, 3400)),
                ("a.b", "Can't overlap those layers", (-500, 0, 0, 250))]
        f = io.StringIO()
        drcjob.write_tsv(f, rows)
        self.assertEqual(f.getvalue().splitlines(), [
            "cell\trule\twhy\tl\tb\tr\tt",
            "inv\tnwell.1\tN-well width < 0.84um (nwell.1)\t1.17\t3.32\t1.68\t3.4",
            "a.b\tCan't overlap those layers\tCan't overlap those layers\t-0.5\t0\t0\t0.25"])

    def test_empty_result_is_the_header(self):
        f = io.StringIO()
        drcjob.write_tsv(f, [])
        self.assertEqual(f.getvalue(), drcjob.TSV_HEADER + "\n")


class Area(unittest.TestCase):
    def test_touching_counts(self):
        area = (85000, 0, 100000, 3000)
        self.assertTrue(drcjob.touches((70000, 0, 100000, 3000), area))   # overlaps
        self.assertTrue(drcjob.touches((80000, 3000, 85000, 4000), area))  # shares a corner
        self.assertTrue(drcjob.touches((100000, 1000, 101000, 2000), area))  # shares an edge
        self.assertFalse(drcjob.touches((0, 0, 84999, 3000), area))
        self.assertFalse(drcjob.touches((90000, 3001, 91000, 4000), area))

    def test_child_errors_through_every_placement(self):
        # TOP holds CHILD at x=0 and at x=50 um, rotated by 90°.
        children = {"TOP": [("CHILD", Xf()), ("CHILD", Xf((0, -1, 1, 0), (50000, 0)))]}
        order = ["CHILD", "TOP"]
        e = Error("CHILD", "w (m1.1)", (1000, 0, 2000, 500))
        places = drcjob.placements(children, "TOP", order)
        self.assertEqual(len(places["CHILD"]), 2)
        # only the rotated placement lands in x 49-50 um: (1000..2000, 0..500) -> x -500..0, y 1000..2000
        near = drcjob.in_area({"CHILD": [e], "TOP": []}, places, (49000, 1000, 49600, 1500))
        self.assertEqual(near["CHILD"], [e])
        far = drcjob.in_area({"CHILD": [e], "TOP": []}, places, (20000, 0, 30000, 3000))
        self.assertEqual(far["CHILD"], [])


class Transforms(unittest.TestCase):
    def test_compose_and_boxes(self):
        r90 = Xf((0, -1, 1, 0), (0, 0))
        move = Xf(d=(100, 0))
        self.assertEqual(r90.box((0, 0, 10, 20)), (-20, 0, 0, 10))
        self.assertEqual((move * r90).box((0, 0, 10, 20)), (80, 0, 100, 10))
        self.assertEqual((r90 * move).box((0, 0, 10, 20)), (-20, 100, 0, 110))
        self.assertEqual(Xf() * move, move)

    @needs_klayout
    def test_matches_klayout(self):
        b = (100, 200, 400, 300)
        for rot in range(4):
            for mirror in (False, True):
                t = db.DCplxTrans(1.0, 90.0 * rot, mirror, db.DVector(1.5, -2.25))
                u = db.DCplxTrans(1.0, 90.0 * ((rot + 1) % 4), not mirror, db.DVector(-0.75, 4))
                want = (t * u) * db.DBox(b[0] / 1000.0, b[1] / 1000.0, b[2] / 1000.0, b[3] / 1000.0)
                got = (Xf.from_klayout(t) * Xf.from_klayout(u)).box(b)
                self.assertEqual(got, tuple(int(round(v * 1000)) for v in
                                            (want.left, want.bottom, want.right, want.top)), (rot, mirror))


class Dedup(unittest.TestCase):
    def test_parent_copies_of_child_boxes_are_dropped(self):
        why = "N-well width < 0.84um (nwell.1)"
        child = [Error("C", why, (0, 0, 100, 100)), Error("C", "other (x.1)", (0, 0, 50, 50))]
        top = [Error("T", why, (1000, 0, 1100, 100)),      # the child's box at x=1 um: a copy
               Error("T", why, (0, 0, 100, 100)),          # the same box, but the child is not at 0
               Error("T", "other (x.1)", (1000, 0, 1100, 100)),  # same place, other rule: kept
               Error("T", why, (5000, 0, 5100, 100))]      # the second placement: a copy
        children = {"T": [("C", Xf(d=(1000, 0))), ("C", Xf(d=(5000, 0)))]}
        kept, dropped = drcjob.dedup({"C": child, "T": top}, children, ["C", "T"])
        self.assertEqual(dropped, 2)
        self.assertEqual(kept["C"], child)
        self.assertEqual(kept["T"], [top[1], top[2]])

    def test_grandchild_boxes_reach_the_top(self):
        why = "w (m1.1)"
        g = [Error("G", why, (0, 0, 10, 10))]
        m = [Error("M", why, (100, 0, 110, 10))]            # G's box through M's instance: dropped
        t = [Error("T", why, (1100, 0, 1110, 10)),          # G's box through M and T: dropped
             Error("T", why, (2000, 0, 2010, 10))]
        children = {"M": [("G", Xf(d=(100, 0)))], "T": [("M", Xf(d=(1000, 0)))]}
        kept, dropped = drcjob.dedup({"G": g, "M": m, "T": t}, children, ["G", "M", "T"])
        self.assertEqual((dropped, kept["M"], kept["T"]), (2, [], [t[1]]))

    def test_cells_outside_the_order_are_kept(self):
        e = [Error("X", "w", (0, 0, 1, 1))]
        kept, dropped = drcjob.dedup({"X": e}, {}, [])
        self.assertEqual((kept["X"], dropped), (e, 0))


class Classes(unittest.TestCase):
    """Hierarchical mode: a subcell's box is an error when the top cell's
    check lists it (a) or the flattened layout's check confirms it (b), and
    information only when only the cell's own check lists it (c)."""

    AREA = "Metal1 minimum area < 0.083um^2 (met1.6)"
    WIDTH = "Metal1 width < 0.14um (met1.1)"

    def setUp(self):
        # TOP holds C at x = 10 um and at x = 30 um, mirrored.
        children = {"TOP": [("C", Xf(d=(10000, 0))), ("C", Xf((1, 0, 0, -1), (30000, 0)))]}
        self.order = ["C", "TOP"]
        self.places = drcjob.placements(children, "TOP", self.order)
        self.pad = Error("C", self.AREA, (-145, 330, 145, 360))      # the gate pad: inv_pcell's met1.6
        self.wide = Error("C", self.WIDTH, (0, 1000, 100, 2000))
        self.tiled = Error("C", self.WIDTH, (0, 3000, 100, 4000))
        self.top_own = Error("TOP", self.WIDTH, (50000, 0, 50100, 1000))

    def kept(self):
        return {"C": [self.pad, self.wide, self.tiled], "TOP": [self.top_own]}

    def test_the_three_classes(self):
        top = [self.top_own,
               Error("TOP", self.WIDTH, (10000, 1000, 10100, 2000)),   # C's wide box at x = 10: equal
               Error("TOP", self.WIDTH, (10000, 3500, 10100, 4500))]   # C's tiled box, tiled otherwise
        # Before the flattened check: what is not in the top's listing is undecided.
        got = drcjob.classify(self.kept(), "TOP", top, self.places)
        self.assertEqual(got["TOP"], [(self.top_own, drcjob.TOP)])
        self.assertEqual(got["C"], [(self.pad, None), (self.wide, drcjob.IN_TOP), (self.tiled, drcjob.IN_TOP)])
        # The flattened check lists no area error: the pad is information only.
        got = drcjob.classify(self.kept(), "TOP", top, self.places, flat=[self.top_own])
        self.assertEqual(got["C"][0], (self.pad, drcjob.ALONE))
        self.assertEqual(drcjob.class_counts(got),
                         {drcjob.TOP: 1, drcjob.IN_TOP: 2, drcjob.FLAT_ONLY: 0, drcjob.ALONE: 1})
        # It lists one at the mirrored placement (x = 30 um, y flipped): confirmed.
        flat = [Error("TOP", self.AREA, (29855, -360, 30145, -330))]
        got = drcjob.classify(self.kept(), "TOP", top, self.places, flat=flat)
        self.assertEqual(got["C"][0], (self.pad, drcjob.FLAT_ONLY))
        # Another rule at that place, or the same rule elsewhere, confirms nothing.
        for f in (Error("TOP", self.WIDTH, (29855, -360, 30145, -330)),
                  Error("TOP", self.AREA, (20000, 0, 20100, 100))):
            got = drcjob.classify(self.kept(), "TOP", top, self.places, flat=[f])
            self.assertEqual(got["C"][0], (self.pad, drcjob.ALONE), f)

    def test_a_cell_without_placements_keeps_its_errors(self):
        got = drcjob.classify({"X": [self.wide]}, "TOP", [], self.places, flat=[])
        self.assertEqual(got["X"], [(self.wide, drcjob.IN_TOP)])

    def test_index_finds_what_touches_and_big_boxes(self):
        idx = drcjob.BoxIndex([Error("T", self.WIDTH, (0, 0, 100, 100)),
                               Error("T", self.WIDTH, (-10 ** 9, 0, 10 ** 9, 10))])
        self.assertTrue(idx.hit("met1.1", (100, 100, 200, 200)))        # a corner
        self.assertTrue(idx.hit("met1.1", (5 * 10 ** 8, 5, 5 * 10 ** 8 + 1, 6)))   # inside the long one
        self.assertFalse(idx.hit("met1.1", (101, 50, 200, 60)))
        self.assertFalse(idx.hit("met1.6", (0, 0, 100, 100)))
        self.assertTrue(idx.hit("met1.1", (-5 * 10 ** 8, -10 ** 8, 5 * 10 ** 8, 10 ** 8)))  # a big query

    def test_category_of_a_box_only_the_cell_gives(self):
        self.assertEqual(drcjob.alone_category(self.AREA, "nfet__kmp_e044c2db"),
                         (drcjob.CAT_DRC, "met1.6", "only when nfet__kmp_e044c2db is checked on its own"))
        why = "P-diffusion and N-ohmic must be over N-well or deep N-well"
        self.assertEqual(drcjob.alone_category(why, "dev"),
                         (drcjob.CAT_DRC, why, "only when dev is checked on its own"))


class MagicOutput(unittest.TestCase):
    def test_said_and_version(self):
        out = ["Magic 8.3 revision 681 - Compiled on Tue Aug 25 2026.", "Processing system .magicrc file",
               'Loading "kmp_drc.tcl" from command line.', "Warning: Calma reading is not undoable!  I hope that's OK.",
               "Library name: LIB", 'Reading "a_poly8".', "Unknown layer/datatype in boundary, layer=3 type=0",
               "KMP_JOB_SCALE 0.005", "DRC style is now \"drc(full)\"", "No errors found.", "KMP_JOB_DONE 1"]
        self.assertEqual(drcjob.magic_said(out), ["Unknown layer/datatype in boundary, layer=3 type=0"])
        self.assertEqual(drcjob.magic_version(out), "8.3.681")
        self.assertIsNone(drcjob.magic_version(["nothing"]))
        # A batch an older version cached may still hold the line; it is dropped on reading.
        self.assertTrue(drcjob.is_noise("No errors found."))
        self.assertFalse(drcjob.is_noise("No errors found in the cell, which is odd"))


class FakeData:
    """A stand-in for pdkdata.PdkData with two rule statements."""

    def __init__(self):
        self.pdk = "sky130A"
        self.source = {"magic_tech_version": "1.0.588", "tech_files": []}
        self.drc = {"styles": ["drc(fast)", "drc(full)", "drc(routing)", "empty"]}
        self.cifout = {"nwell": [[64, 20]], "pdiff": [[65, 20], [94, 20]]}
        self.layers = [{"gds": [64, 20], "name": "nwell.drawing"}, {"gds": [65, 20], "name": "diff.drawing"}]
        self.raw = {"aliases": {"allnwell": ["nwell", "pwell_alias"], "pwell_alias": ["nwell"]}}
        self.rules = [
            {"line": 4195, "file": "sky130A.tech", "keyword": "width", "styles": ["drc(fast)", "drc(full)"],
             "types": ["allnwell"], "value_um": 0.84, "unit": "um", "why": "N-well width < %d (nwell.1)",
             "ids": ["nwell.1"]},
            {"line": 4324, "file": "sky130A.tech", "keyword": "cifmaxwidth", "styles": ["drc(full)"],
             "types": ["*pdiff"], "value_um": 0.0, "unit": "um", "why": "LU rule (LU.3)", "ids": ["LU.3"]}]

    def rules_by_why(self, why):
        key = {"N-well width < 0.84um (nwell.1)": "N-well width < %d (nwell.1)"}.get(why, why)
        return [r for r in self.rules if r["why"] == key]


class Texts(unittest.TestCase):
    def test_types_and_layers(self):
        self.assertEqual(drcjob.type_names(["*poly", "(allcont)/a", "xhrpoly,uhrpoly,xpc", "mcon/m1", "~(nwell)"]),
                         ["poly", "allcont", "xhrpoly", "uhrpoly", "xpc", "mcon", "nwell"])
        data = FakeData()
        aliases = drcjob.tech_aliases(data, None)
        self.assertEqual(aliases["allnwell"], ["nwell"])
        info = drcjob.RuleInfo(data, "N-well width < 0.84um (nwell.1)", {}, aliases)
        self.assertEqual(info.item_text(), "N-well width < 0.84um (nwell.1); Magic types: allnwell; "
                                           "GDS layers: 64/20 (nwell.drawing)")
        d = info.description()
        self.assertIn("Tech file sky130A.tech:4195: width allnwell 0.84 um", d)
        self.assertIn("In the styles: drc(fast), drc(full)", d)
        lu = drcjob.RuleInfo(data, "LU rule (LU.3)", {}, aliases)
        self.assertIn("(drc(full) only)", lu.description())
        self.assertIn("GDS layers: 65/20 (diff.drawing), 94/20", lu.item_text())

    def test_type_synonyms_from_the_tech_file(self):
        """met1.6 checks allm1,*obsm1; allm1 is *m1,rm1, m1 is a synonym of
        metal1, which the gdsii style (and cifout) names. Without the types
        section only obsm1's 68/98 was found."""
        d = tempfile.mkdtemp(prefix="kmp-tech-")
        try:
            with open(os.path.join(d, "mini.tech"), "w") as f:
                f.write("tech\n mini\nend\n\ntypes\n# metals\n  metal1 metal1,m1,met1\n  metal1 rmetal1,rm1\n"
                        " -metal1 obsm1\nend\n\naliases\n  allm1   *m1,rm1\nend\n")
            data = FakeData()
            data.raw = {}
            data.source = {"tech_files": ["mini.tech"]}
            data.cifout = {"metal1": [[68, 20]], "rmetal1": [[68, 13], [68, 20]], "obsm1": [[68, 98]]}
            data.layers = [{"gds": [68, 20], "name": "met1.drawing"}, {"gds": [68, 98], "name": "MET1BLOCK"}]
            data.rules = [{"line": 4603, "file": "mini.tech", "keyword": "area", "styles": ["drc(full)"],
                           "types": ["allm1,*obsm1"], "why": "Metal1 minimum area < %a (met1.6)", "ids": ["met1.6"]}]
            cfg = types.SimpleNamespace(magicrc=os.path.join(d, "mini.magicrc"), pdk="sky130A")
            aliases = drcjob.tech_aliases(data, cfg)
            synonyms = drcjob.tech_types(data, cfg)
            self.assertEqual(aliases["allm1"], ["m1", "rm1"])
            self.assertEqual((synonyms["m1"], synonyms["met1"], synonyms["rm1"], synonyms["obsm1"]),
                             ("metal1", "metal1", "rmetal1", "obsm1"))
            why = "Metal1 minimum area < %a (met1.6)"
            old = drcjob.RuleInfo(data, why, {}, aliases)
            self.assertEqual(old.layers, [(68, 98)])
            info = drcjob.RuleInfo(data, why, {}, aliases, synonyms)
            self.assertEqual(info.layers, [(68, 20), (68, 13), (68, 98)])
            self.assertIn("GDS layers: 68/20 (met1.drawing), 68/13, 68/98 (MET1BLOCK)", info.item_text())
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_gap_table_names_and_its_absence(self):
        data = FakeData()
        gaps = {"nwell.1": {"status": "both", "klayout": [{"deck": "sky130A_mr.drc", "name": "nwell.1",
                                                            "value": 0.84}]}}
        d = drcjob.RuleInfo(data, "N-well width < 0.84um (nwell.1)", gaps, {}).description()
        self.assertIn("Gap table: both; KLayout: sky130A_mr.drc: nwell.1 (0.84)", d)
        self.assertNotIn("Gap table", drcjob.RuleInfo(data, "N-well width < 0.84um (nwell.1)", {}, {}).description())
        self.assertEqual(drcjob.load_gaps("no-such-pdk"), {})
        none = drcjob.RuleInfo(None, "Can't overlap those layers")
        self.assertEqual(none.item_text(), "Can't overlap those layers")
        self.assertIn("no rule statement", none.description())

    def test_styles_are_the_drc_ones(self):
        self.assertEqual(drcjob.drc_styles(FakeData()), ["drc(fast)", "drc(full)", "drc(routing)"])
        self.assertEqual(drcjob.drc_styles(None), [])

    def test_command_line(self):
        opts = {"file": "my dir/x.gds", "style": "drc(full)", "mode": "flat", "box": (0, 0, 1.5, 2)}
        self.assertEqual(drcjob.command_line(opts, ["inv$1"]),
                         "python3 -m klayout_magic_pcells drc 'my dir/x.gds' --cell 'inv$1' --style 'drc(full)' "
                         "--mode flat --box 0,0,1.5,2")

    def test_the_description_says_a_tmp_job_dir_goes(self):
        # An uncached run's tmp-* directories go when the command ends, and the
        # description says so; a key's directory, or KMP_JOB_KEEP=1, gets no such note.
        import os
        import types
        unit = types.SimpleNamespace(name="inv", empty=[], magic="8.3", tech_version="1",
                                     dirs=["/c/jobs/sky130A/drc/tmp-abc"], flat_dir="/c/jobs/sky130A/drc/tmp-def",
                                     flat=[], flat_elapsed=0.5, flat_cached=False)
        cfg = types.SimpleNamespace(pdk="sky130A")
        opts = {"file": "x.gds", "style": "drc(full)", "mode": "hierarchical"}
        note = "(removed when the check ends; KMP_JOB_KEEP=1 keeps it)"
        old = os.environ.pop("KMP_JOB_KEEP", None)
        try:
            text = drcjob._description(cfg, None, opts, [unit], [], None)
            self.assertIn("exported file /c/jobs/sky130A/drc/tmp-abc/in.gds %s" % note, text)
            self.assertIn("job directory /c/jobs/sky130A/drc/tmp-def %s" % note, text)
            unit.dirs, unit.flat_dir = ["/c/jobs/sky130A/drc/" + "k" * 64], "/c/jobs/sky130A/drc/" + "f" * 64
            self.assertNotIn("removed when", drcjob._description(cfg, None, opts, [unit], [], None))
            unit.dirs = ["/c/jobs/sky130A/drc/tmp-abc"]
            os.environ["KMP_JOB_KEEP"] = "1"
            self.assertNotIn("removed when", drcjob._description(cfg, None, opts, [unit], [], None))
        finally:
            os.environ.pop("KMP_JOB_KEEP", None)
            if old is not None:
                os.environ["KMP_JOB_KEEP"] = old


@needs_klayout
class Generator(unittest.TestCase):
    def test_generator_text(self):
        from klayout_magic_pcells import markers
        g = markers.recipe_generator({"cmd": "drc", "file": "/a b/x.gds", "cell": "a$b", "style": "drc(full)",
                                      "mode": "hierarchical", "box": None})
        self.assertEqual(g, "klayout_magic_pcells: cell='a$b',cmd='drc',file='/a b/x.gds',"
                            "mode='hierarchical',style='drc(full)'")

    def test_generator_quotes_as_klayout_does(self):
        from klayout_magic_pcells import markers
        try:
            import klayout.tl as tl
            Recipe = tl.Recipe
        except (ImportError, AttributeError):
            self.skipTest("no Recipe class in this klayout module")

        class Fmt(Recipe):
            def __init__(self):
                super().__init__(markers.RECIPE + "_unit_test", "quoting test")
        fmt = Fmt()
        params = {"cmd": "drc", "file": "/a b/c'd\\e.gds", "cell": "café", "tab": "x\ty\nz\r",
                  "Z": "1", "ctl": "a\x01b\x7f", "empty": ""}
        want = fmt.generator(params).split(": ", 1)[1]
        self.assertEqual(markers.recipe_generator(params).split(": ", 1)[1], want)


@needs_klayout
class Database(unittest.TestCase):
    def test_categories_items_and_references(self):
        from klayout_magic_pcells import markers
        ly = db.Layout()
        ly.dbu = 0.001
        top = ly.create_cell("TOP")
        child = ly.create_cell("CHILD")
        top.insert(db.DCellInstArray(child.cell_index(), db.DTrans(db.DVector(20, 0))))
        top.insert(db.DCellInstArray(child.cell_index(), db.DTrans(db.DTrans.R90, db.DVector(40, 2))))
        r = markers.Rdb("Magic DRC drc(full): TOP", "", markers.recipe_generator({"cmd": "drc"}), "TOP")
        why = "N-well width < 0.84um (nwell.1)"
        r.item(drcjob.category_path(why), "CHILD", db.DBox(1, 1, 4, 2), why)
        n = markers.add_parent_references(r, ly)
        self.assertEqual(n, 2)
        rc = r.cell("CHILD")
        refs = [(ref.trans.disp.x, ref.trans.disp.y, ref.trans.angle) for ref in rc.each_reference()]
        self.assertEqual(sorted(refs), [(20.0, 0.0, 0.0), (40.0, 2.0, 90.0)])
        self.assertEqual(r.count(drcjob.CAT_DRC), 1)
        self.assertEqual(r.count((drcjob.CAT_DRC, "nwell.1")), 1)
        # A parent outside the given top's tree is not followed.
        other = ly.create_cell("OTHER")
        other.insert(db.DCellInstArray(child.cell_index(), db.DTrans()))
        r2 = markers.Rdb("x", "", "", "TOP")
        r2.item("a", "CHILD", db.DBox(0, 0, 1, 1))
        self.assertEqual(markers.add_parent_references(r2, ly), 2)

    def test_children_from_a_layout(self):
        ly = db.Layout()
        ly.dbu = 0.001
        top = ly.create_cell("TOP")
        mid = ly.create_cell("MID")
        leaf = ly.create_cell("LEAF")
        mid.insert(db.DCellInstArray(leaf.cell_index(), db.DTrans(db.DVector(1, 0))))
        top.insert(db.DCellInstArray(mid.cell_index(), db.DTrans(db.DTrans.M0, db.DVector(0, 5)),
                                     db.DVector(10, 0), db.DVector(0, 0), 2, 1))
        children, order = drcjob._children(ly, "TOP")
        self.assertEqual(order, ["LEAF", "MID", "TOP"])
        self.assertEqual(sorted(x.d for _, x in children["TOP"]), [(0, 5000), (10000, 5000)])
        places = drcjob.placements(children, "TOP", order)
        self.assertEqual(sorted(p.box((0, 0, 100, 100)) for p in places["LEAF"]),
                         [(1000, 4900, 1100, 5000), (11000, 4900, 11100, 5000)])


class Prepare(unittest.TestCase):
    def test_bad_options_fail_without_magic(self):
        cfg = types.SimpleNamespace(pdk="sky130A", drc_style="drc(full)", drc_mode="hierarchical",
                                    cache_enabled=False)
        if db is None:
            self.skipTest("the klayout Python module is not installed")
        ly = db.Layout()
        ly.create_cell("TOP")
        for opts, text in (({"style": "drc(nope)"}, "has no DRC style drc(nope)"),
                           ({"mode": "per-cell"}, "unknown mode"),
                           ({"box": (1, 1, 0, 2)}, "l < r")):
            out = drcjob.prepare(ly, "TOP", cfg, FakeData(), opts).wait()
            self.assertEqual(out.status, 2, opts)
            self.assertIn(text, out.summary)
            self.assertEqual(out.rdb.count(drcjob.CAT_FAILED), 1)


if __name__ == "__main__":
    unittest.main()
