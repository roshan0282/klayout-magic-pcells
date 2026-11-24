"""sky130_power against a real Magic and sky130A: cache, stamps, round trips,
host database units, audit, the command line, the form and registration.

Every scenario runs in new Python processes with its own cache directory,
so "reopened" means reopened by another session, as in klayout-magic-pcells'
backend tests.

    KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
"""

import json
import os
import shutil
import tempfile
import unittest

from tests.power._util import cli, db, env, lines, needs_magic, run_py

NFET = {"device": "sky130_fd_pr__nfet_01v8", "bulk": "ring", "l": 0.5, "w": 2.0, "nf": 2, "nx": 3,
        "ny": 2, "strap_w": 3.0, "pitch": 0.0}
PFET = {"device": "sky130_fd_pr__pfet_01v8", "bulk": "source", "l": 0.1, "w": 1.5, "nf": 2, "nx": 2,
        "ny": 2, "strap_w": 2.5, "pitch": 0.0}

PLACE = """
lib = kpp.register()
assert lib is not None
ly = db.Layout()
ly.dbu = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
top = ly.create_cell("TOP")
x = 0
for pv in json.loads(sys.argv[1]):
    v = kpp.form_values(pv)
    c = ly.create_cell("HW_FET", "sky130_power", v)
    top.insert(db.CellInstArray(c.cell_index(), db.Trans(db.Vector(int(round(x / ly.dbu)), 0))))
    x += c.dbbox().width() + 20
    print("PARAMS " + json.dumps({k: v for k, v in c.pcell_parameters_by_name().items()}))
ly.write(sys.argv[2])
"""


def flat(path):
    """{layer: merged region} and texts of the single top cell, flattened."""
    ly = db.Layout()
    ly.read(path)
    top = ly.top_cells()
    assert len(top) == 1
    out = {}
    for li in ly.layer_indices():
        info = ly.get_info(li)
        r = db.Region(top[0].begin_shapes_rec(li))
        r.merge()
        t = sorted((t.string, t.x * ly.dbu, t.y * ly.dbu) for t in db.Texts(top[0].begin_shapes_rec(li)).each())
        if not r.is_empty() or t:
            out[(info.layer, info.datatype)] = (r, t, ly.dbu)
    return out


def same_geometry(a, b):
    fa, fb = flat(a), flat(b)
    if sorted(fa) != sorted(fb):
        return "layers %s vs %s" % (sorted(fa), sorted(fb))
    for k in fa:
        ra, ta, da = fa[k]
        rb, tb, dbb = fb[k]
        if da != dbb:
            ra = ra.transformed(db.ICplxTrans(da / dbb))
            ta = [(s, x, y) for s, x, y in ta]
        if not (ra ^ rb).is_empty():
            return "layer %d/%d differs" % k
        if [(s, round(x, 4), round(y, 4)) for s, x, y in ta] != [(s, round(x, 4), round(y, 4)) for s, x, y in tb]:
            return "texts on %d/%d differ" % k
    return None


@needs_magic
class Backend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hw_backend_")
        self.cache = os.path.join(self.tmp, "cache")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, **kw):
        return env(self.cache, **kw)

    def place(self, variants, path, dbu=0.001, **kw):
        rc, out = run_py(PLACE, self.env(**kw), [json.dumps(variants), path, repr(dbu)])
        self.assertEqual(rc, 0, out)
        return lines(out, "PARAMS "), out

    # -- cache ---------------------------------------------------------------

    def test_cache(self):
        body = """
            from klayout_power_pcells import backend
            from klayout_power_pcells.hybrid_waffle import HWParams
            st = backend.start()
            r = st.generator.get(HWParams(nx=2, ny=2, nf=1))
            print("GOT " + json.dumps([r.source, r.gds_path, st.cache.enabled]))
        """
        rc, out = run_py(body, self.env())
        self.assertEqual(rc, 0, out)
        src, gds, enabled = lines(out, "GOT ")[0]
        self.assertEqual((src, enabled), ("drawn", True))
        self.assertTrue(gds.startswith(os.path.join(self.cache, "power", "v1")), gds)
        rc, out = run_py(body, self.env())                 # another session: from disk
        self.assertEqual(lines(out, "GOT ")[0][0], "disk", out)
        with open(gds, "ab") as f:                          # damaged entry: drawn again
            f.write(b"junk")
        rc, out = run_py(body, self.env())
        self.assertEqual(lines(out, "GOT ")[0][0], "drawn", out)
        rc, out = run_py(body, self.env())
        self.assertEqual(lines(out, "GOT ")[0][0], "disk", out)
        rc, out = cli(self.env(), "cache", "stats")
        self.assertEqual(rc, 0, out)
        self.assertIn("1 entries", out)
        rc, out = cli(self.env(), "cache", "clear")
        self.assertEqual(rc, 0, out)
        rc, out = run_py(body, self.env())
        self.assertEqual(lines(out, "GOT ")[0][0], "drawn", out)

    def test_cache_off_and_unwritable(self):
        body = """
            from klayout_power_pcells import backend
            from klayout_power_pcells.hybrid_waffle import HWParams
            st = backend.start()
            r = st.generator.get(HWParams(nx=2, ny=2, nf=1))
            print("GOT " + json.dumps([r.source, st.cache.enabled, r.gds_path]))
        """
        rc, out = run_py(body, self.env(KMP_CACHE="0"))
        self.assertEqual(rc, 0, out)
        src, enabled, gds = lines(out, "GOT ")[0]
        self.assertEqual((src, enabled), ("drawn", False))
        self.assertFalse(os.path.exists(gds), "KMP_CACHE=0 left %s behind" % gds)
        self.assertFalse(os.path.isdir(os.path.join(self.cache, "power", "v1")))
        # a cache directory that is a file: warning, then drawn without a disk cache
        blocker = os.path.join(self.tmp, "afile")
        open(blocker, "w").close()
        rc, out = run_py(body, env(blocker))
        self.assertEqual(rc, 0, out)
        self.assertEqual(lines(out, "GOT ")[0][:2], ["drawn", False], out)
        self.assertIn("can't be used", out)

    # -- stamps ----------------------------------------------------------------

    def test_stamps(self):
        body = """
            from klayout_power_pcells import backend
            lib = kpp.register()
            ly = db.Layout()
            c = ly.create_cell("HW_FET", "sky130_power", {"nx": 2, "ny": 2})
            st = backend.read_stamp(c)
            print("STAMP " + json.dumps([st, c.pcell_parameters_by_name()["hw_created"],
                                         backend.state.created_stamp]))
            old = backend.state.created_stamp.replace("code=", "code=0")
            c2 = ly.create_cell("HW_FET", "sky130_power", {"nx": 2, "ny": 2, "hw_created": old})
            print("DONE")
        """
        rc, out = run_py(body, self.env())
        self.assertEqual(rc, 0, out)
        st, created, current = lines(out, "STAMP ")[0]
        self.assertEqual(created, current)
        self.assertEqual(st["pdk"], "sky130A")
        self.assertEqual(len(st["key"]), 16)
        self.assertEqual(st["grid"], "5")
        self.assertTrue(current.startswith("hw1;version="))
        self.assertIn("instance created with", out)

    # -- round trips -------------------------------------------------------------

    def test_round_trips(self):
        gds = os.path.join(self.tmp, "a.gds")
        oas = os.path.join(self.tmp, "a.oas")
        stored, _ = self.place([NFET, PFET], gds)
        self.assertEqual(stored[1]["l"], 0.15)          # Magic's dialog value, as the GUI stores it
        ly = db.Layout()
        ly.read(gds)
        ly.write(oas)
        reopen = """
            from klayout_power_pcells import backend
            path = sys.argv[1]
            if sys.argv[2] == "lib":
                lib = kpp.register()
                assert lib is not None
            ly = db.Layout()
            ly.read(path)
            top = ly.cell("TOP")
            out = []
            for inst in top.each_inst():
                c = ly.cell(inst.cell_index)
                st = backend.read_stamp(c)
                out.append([c.display_title(), c.is_pcell_variant(), c.is_proxy(),
                            c.pcell_parameters_by_name() if c.is_pcell_variant() else None,
                            st is not None])
            print("CELLS " + json.dumps(out))
            if sys.argv[2] == "lib" and len(sys.argv) > 4:
                lib.refresh()
                print("REFRESHED " + json.dumps([ly.cell(i.cell_index).pcell_parameters_by_name()
                                                for i in top.each_inst()]))
            ly.write(sys.argv[3])
        """
        for src in (gds, oas):
            with self.subTest(file=os.path.basename(src)):
                # with the library, the disk cache off: every variant drawn again
                again = src + ".lib.gds"
                rc, out = run_py(reopen, self.env(KMP_CACHE="0"), [src, "lib", again, "refresh"])
                self.assertEqual(rc, 0, out)
                cells = sorted(lines(out, "CELLS ")[0], key=lambda c: c[3]["device"])
                self.assertEqual(len(cells), 2)
                for (title, live, _proxy, params, has_stamp), want in zip(
                        cells, sorted(stored, key=lambda p: p["device"])):
                    self.assertTrue(live, title)
                    self.assertTrue(has_stamp)
                    for k in ("device", "bulk", "l", "w", "nf", "nx", "ny", "strap_w", "pitch"):
                        self.assertEqual(params[k], want[k], k)
                refreshed = lines(out, "REFRESHED ")[0]
                self.assertEqual(sorted(p["l"] for p in refreshed), sorted(s["l"] for s in stored))
                self.assertIsNone(same_geometry(gds, again))
                # without the library: <defunct> cells keep the stored geometry and stamps
                cold = src + ".cold.gds"
                rc, out = run_py(reopen, self.env(KMP_MAGIC="/nonexistent/magic"), [src, "nolib", cold])
                self.assertEqual(rc, 0, out)
                for title, live, proxy, _p, has_stamp in lines(out, "CELLS ")[0]:
                    self.assertTrue(title.startswith("<defunct>sky130_power.HW_FET"), title)
                    self.assertFalse(live)
                    self.assertTrue(proxy)
                    self.assertTrue(has_stamp)
                self.assertIsNone(same_geometry(gds, cold))
                # saved without the library, reopened with it: live again
                rc, out = run_py(reopen, self.env(), [cold, "lib", cold + ".2.gds"])
                self.assertEqual(rc, 0, out)
                self.assertTrue(all(c[1] for c in lines(out, "CELLS ")[0]), out)
                self.assertIsNone(same_geometry(gds, cold + ".2.gds"))

    def test_host_dbu(self):
        ref = os.path.join(self.tmp, "ref.gds")
        self.place([NFET], ref)
        for dbu in (0.0005, 0.005):
            with self.subTest(dbu=dbu):
                p = os.path.join(self.tmp, "host_%g.gds" % dbu)
                self.place([NFET], p, dbu=dbu)
                self.assertIsNone(same_geometry(ref, p))

    # -- audit -------------------------------------------------------------------

    def test_audit(self):
        good = os.path.join(self.tmp, "good.gds")
        self.place([NFET], good)
        rc, out = cli(self.env(), "audit", good)
        self.assertEqual(rc, 0, out)
        self.assertIn("1 sky130_power cells, 0 with problems", out)
        rc, out = cli(self.env(), "audit", good, "--regen")
        self.assertEqual(rc, 0, out)
        self.assertIn("regenerated: same as stored", out)
        # the error marker
        bad = os.path.join(self.tmp, "bad.gds")
        rc, out = cli(self.env(), "generate", "strap_w=1.0", "-o", bad)
        self.assertEqual(rc, 1, out)
        rc, out = cli(self.env(), "audit", bad)
        self.assertEqual(rc, 1, out)
        self.assertIn("error marker", out)
        # a stamp from another generator
        stale = os.path.join(self.tmp, "stale.gds")
        ly = db.Layout()
        ly.read(good)
        for c in ly.each_cell():
            for li in ly.layer_indices():
                for sh in c.shapes(li).each():
                    if sh.prop_id and sh.property(100):
                        sh.set_property(100, sh.property(100).replace("code=", "code=f"))
        ly.write(stale)
        rc, out = cli(self.env(), "audit", stale)
        self.assertEqual(rc, 1, out)
        self.assertIn("generated with", out)
        # a file whose dbu can't hold the 5 nm grid
        coarse = os.path.join(self.tmp, "coarse.gds")
        self.place([NFET], coarse, dbu=0.002)
        rc, out = cli(self.env(), "audit", coarse)
        self.assertEqual(rc, 1, out)
        self.assertIn("doesn't divide 5 nm", out)

    # -- command line --------------------------------------------------------------

    def test_cli(self):
        rc, out = cli(self.env(), "doctor")
        self.assertEqual(rc, 0, out)
        self.assertIn("drew a 2x2 HW_FET", out)
        self.assertNotIn("PROBLEM", out)
        rc, out = cli(self.env(), "devices", "-v")
        self.assertEqual(rc, 0, out)
        self.assertIn("l >= 0.15 um", out)
        rc, out = cli(self.env(), "check", "l=0.1", "nx=2", "ny=2")
        self.assertEqual(rc, 0, out)
        self.assertIn("Magic's dialog shows l=0.15 (entered 0.1)", out)
        rc, out = cli(self.env(), "check", "nx=6", "ny=6")
        self.assertEqual(rc, 1, out)
        self.assertIn("parameter nx", out)
        rc, out = cli(self.env(), "check", "nx=6", "ny=6", "bulk=source")
        self.assertEqual(rc, 0, out)
        rc, out = cli(self.env(), "check", "l=abc")
        self.assertEqual(rc, 2, out)
        rc, out = cli(self.env(), "check", "device=nfet_g5v0d16v0")
        self.assertEqual(rc, 2, out)
        g = os.path.join(self.tmp, "g.gds")
        rc, out = cli(self.env(), "generate", "device=pfet_01v8", "nx=2", "ny=2", "-o", g)
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(g))
        rc, out = cli(self.env(), "hw", "--nx", "2", "--ny", "2", "-o", os.path.join(self.tmp, "h.gds"))
        self.assertEqual(rc, 0, out)
        rc, out = cli(self.env(), "hw", "--strap", "1", "-o", os.path.join(self.tmp, "h2.gds"))
        self.assertEqual(rc, 1, out)

    # -- the form -------------------------------------------------------------------

    def test_form_callback_icons(self):
        body = """
            lib = kpp.register()
            ly = lib.layout()
            decl = ly.pcell_declaration("HW_FET")
            icons = {db.PCellParameterState.WarningIcon: "WARN", db.PCellParameterState.ErrorIcon: "ERR"}
            for vals in json.loads(sys.argv[1]):
                states = db.PCellParameterStates()
                for pd in decl.get_parameters():
                    states.parameter(pd.name).value = vals.get(pd.name, pd.default)
                decl.callback(ly, list(vals)[0] if vals else "device", states)
                print("CB " + json.dumps({pd.name: [icons[states.parameter(pd.name).icon],
                                                    states.parameter(pd.name).tooltip]
                                          for pd in decl.get_parameters()
                                          if states.parameter(pd.name).icon in icons}))
        """
        cases = [{}, {"l": 0.1}, {"strap_w": 1.0}, {"nx": 6, "ny": 6}, {"pitch": 4.0}, {"w": 0.6},
                 {"nx": 6, "ny": 6, "bulk": "source"}]
        rc, out = run_py(body, self.env(), [json.dumps(cases)])
        self.assertEqual(rc, 0, out)
        ok, small_l, strap, big, pitch, narrow, big_source = lines(out, "CB ")
        self.assertEqual(ok, {})
        self.assertEqual(small_l, {"l": ["WARN", "Magic's dialog shows 0.15 (entered 0.1)"]})
        self.assertEqual(list(strap), ["strap_w"])
        self.assertEqual(strap["strap_w"][0], "ERR")
        self.assertEqual(list(big), ["nx"])
        self.assertIn("bulk='source'", big["nx"][1])
        self.assertEqual(list(pitch), ["pitch"])
        self.assertEqual(list(narrow), ["w"])
        self.assertEqual(big_source, {})

    def test_lazy(self):
        body = """
            lib = kpp.register()
            decl = lib.layout().pcell_declaration("HW_FET")
            print("LAZY " + json.dumps(bool(decl.wants_lazy_evaluation())))
        """
        for val, want in (("1", True), ("0", False)):
            rc, out = run_py(body, self.env(KMP_LAZY=val))
            self.assertEqual(rc, 0, out)
            self.assertEqual(lines(out, "LAZY ")[0], want)

    # -- registration ------------------------------------------------------------------

    def test_register_without_magic(self):
        body = """
            from klayout_power_pcells import backend
            print("REG " + json.dumps([kpp.register() is None,
                                       db.Library.library_by_name("sky130_power") is None,
                                       backend.state.last_error]))
        """
        rc, out = run_py(body, self.env(KMP_MAGIC="/nonexistent/magic"))
        self.assertEqual(rc, 0, out)
        none, absent, why = lines(out, "REG ")[0]
        self.assertTrue(none and absent, out)
        self.assertIn("KMP_MAGIC", why)
        self.assertIn("sky130_power not registered", out)


if __name__ == "__main__":
    unittest.main()
