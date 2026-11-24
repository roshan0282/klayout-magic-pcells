"""sky130_power end to end: cache, stamps, round trips, host database units,
audit, the command line, the form and registration.

Every scenario runs in new Python processes with its own cache directory,
so "reopened" means reopened by another session, as in klayout-magic-pcells'
backend tests. Drawing needs only KLayout; the verify command (one case)
also magic, netgen and sky130A.

    KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
"""

import json
import os
import shutil
import tempfile
import unittest

from tests.power._util import cli, db, env, lines, needs_klayout, run_py

BASE = {"device": "nfet_01v8", "nx": 3, "ny": 2, "P": 4.0, "L": 0.0, "N": 0.0, "gate_strap": "met1_mesh",
        "runners": "met3,met4", "runner_style": "diag45", "bus": "L_buses", "bus_w": 0.0, "guard_ring": True,
        "source_taps": True, "tap_w": 0.0, "deep_nwell": True, "bottom_net": "S"}
NFET = dict(BASE)
PFET = dict(BASE, device="pfet_01v8", nx=2, ny=2, P=3.5, gate_strap="frame_only", bus="none", source_taps=False)

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
        if not (ra ^ rb).is_empty():
            return "layer %d/%d differs" % k
        if [(s, round(x, 4), round(y, 4)) for s, x, y in ta] != [(s, round(x, 4), round(y, 4)) for s, x, y in tb]:
            return "texts on %d/%d differ" % k
    return None


@needs_klayout
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
            from klayout_power_pcells.waffle import WaffleParams
            st = backend.start()
            r = st.generator.get(WaffleParams(nx=2, ny=2))
            print("GOT " + json.dumps([r.source, r.gds_path, st.cache.enabled, r.info["n_gates"]]))
        """
        rc, out = run_py(body, self.env())
        self.assertEqual(rc, 0, out)
        src, gds, enabled, n = lines(out, "GOT ")[0]
        self.assertEqual((src, enabled, n), ("drawn", True, 4))
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
            from klayout_power_pcells.waffle import WaffleParams
            st = backend.start()
            r = st.generator.get(WaffleParams(nx=2, ny=2))
            print("GOT " + json.dumps([r.source, st.cache.enabled, r.gds_path]))
        """
        rc, out = run_py(body, self.env(KMP_CACHE="0"))
        self.assertEqual(rc, 0, out)
        src, enabled, gds = lines(out, "GOT ")[0]
        self.assertEqual((src, enabled), ("drawn", False))
        self.assertFalse(os.path.exists(gds), "KMP_CACHE=0 left %s behind" % gds)
        self.assertFalse(os.path.isdir(os.path.join(self.cache, "power", "v1")))
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
            ly.create_cell("HW_FET", "sky130_power", {"nx": 2, "ny": 2, "hw_created": old})
        """
        rc, out = run_py(body, self.env())
        self.assertEqual(rc, 0, out)
        st, created, current = lines(out, "STAMP ")[0]
        self.assertEqual(created, current)
        self.assertEqual(st["pdk"], "sky130A")
        self.assertEqual(len(st["key"]), 16)
        self.assertEqual(st["grid"], "5")
        self.assertTrue(current.startswith("hw2;version="))
        self.assertIn("instance created with", out)

    # -- round trips -------------------------------------------------------------

    def test_round_trips(self):
        gds = os.path.join(self.tmp, "a.gds")
        oas = os.path.join(self.tmp, "a.oas")
        stored, _ = self.place([NFET, PFET], gds)
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
                            c.pcell_parameters_by_name() if c.is_pcell_variant() else None, st is not None])
            print("CELLS " + json.dumps(out))
            if sys.argv[2] == "lib" and len(sys.argv) > 4:
                lib.refresh()
                print("REFRESHED " + json.dumps([ly.cell(i.cell_index).pcell_parameters_by_name()
                                                for i in top.each_inst()]))
            ly.write(sys.argv[3])
        """
        for src in (gds, oas):
            with self.subTest(file=os.path.basename(src)):
                again = src + ".lib.gds"
                rc, out = run_py(reopen, self.env(KMP_CACHE="0"), [src, "lib", again, "refresh"])
                self.assertEqual(rc, 0, out)
                cells = sorted(lines(out, "CELLS ")[0], key=lambda c: c[3]["device"])
                self.assertEqual(len(cells), 2)
                for (title, live, _proxy, params, has_stamp), want in zip(
                        cells, sorted(stored, key=lambda p: p["device"])):
                    self.assertTrue(live, title)
                    self.assertTrue(has_stamp)
                    for k in ("device", "nx", "ny", "gate_strap", "runners", "bus", "guard_ring"):
                        self.assertEqual(params[k], want[k], k)
                    self.assertAlmostEqual(params["P"], want["P"], places=12)
                refreshed = lines(out, "REFRESHED ")[0]
                self.assertEqual(sorted(p["device"] for p in refreshed), sorted(s["device"] for s in stored))
                self.assertIsNone(same_geometry(gds, again))
                cold = src + ".cold.gds"
                rc, out = run_py(reopen, self.env(), [src, "nolib", cold])
                self.assertEqual(rc, 0, out)
                for title, live, proxy, _p, has_stamp in lines(out, "CELLS ")[0]:
                    self.assertTrue(title.startswith("<defunct>sky130_power.HW_FET"), title)
                    self.assertFalse(live)
                    self.assertTrue(proxy)
                    self.assertTrue(has_stamp)
                self.assertIsNone(same_geometry(gds, cold))
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
        bad = os.path.join(self.tmp, "bad.gds")
        rc, out = cli(self.env(), "generate", "P=0.5", "-o", bad)
        self.assertEqual(rc, 1, out)
        rc, out = cli(self.env(), "audit", bad)
        self.assertEqual(rc, 1, out)
        self.assertIn("error marker", out)
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
        coarse = os.path.join(self.tmp, "coarse.gds")
        self.place([NFET], coarse, dbu=0.002)
        rc, out = cli(self.env(), "audit", coarse)
        self.assertEqual(rc, 1, out)
        self.assertIn("doesn't divide the 5 nm grid", out)

    # -- command line --------------------------------------------------------------

    def test_cli(self):
        rc, out = cli(self.env(), "doctor")
        self.assertEqual(rc, 0, out)
        self.assertIn("drew a 3x3 HW_FET", out)
        self.assertNotIn("PROBLEM", out)
        rc, out = cli(self.env(), "devices")
        self.assertEqual(rc, 0, out)
        self.assertIn("pfet_g5v0d10v5", out)
        rc, out = cli(self.env(), "check", "P=2")
        self.assertEqual(rc, 1, out)
        self.assertIn("parameter tap_w", out)
        rc, out = cli(self.env(), "check", "P=2", "source_taps=0")
        self.assertEqual(rc, 0, out)
        rc, out = cli(self.env(), "check", "nx=3", "ny=3")
        self.assertEqual(rc, 0, out)
        self.assertIn("12 gates, W_total 43.00 um", out)
        rc, out = cli(self.env(), "check", "P=0.5")
        self.assertEqual(rc, 1, out)
        self.assertIn("parameter P", out)
        rc, out = cli(self.env(), "check", "runners=met3,met4,met5")
        self.assertEqual(rc, 1, out)
        self.assertIn("met5", out)
        rc, out = cli(self.env(), "check", "P=abc")
        self.assertEqual(rc, 2, out)
        rc, out = cli(self.env(), "check", "device=nfet_20v0")
        self.assertEqual(rc, 2, out)
        g = os.path.join(self.tmp, "g.gds")
        rc, out = cli(self.env(), "generate", "device=pfet_01v8", "nx=2", "ny=2", "-o", g)
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(g))
        rc, out = cli(self.env(), "hw", "nx=2", "ny=2", "-o", os.path.join(self.tmp, "h.gds"))
        self.assertEqual(rc, 0, out)
        rc, out = cli(self.env(), "hw", "L=0.1", "-o", os.path.join(self.tmp, "h2.gds"))
        self.assertEqual(rc, 1, out)
        if all(shutil.which(t) for t in ("magic", "netgen")):
            rc, out = cli(self.env(), "verify", "nx=2", "ny=2", "device=pfet_01v8")
            self.assertEqual(rc, 0, out)
            self.assertIn("LVS against one device", out)
            self.assertIn(": match", out)

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
        cases = [{"nx": 3, "ny": 3}, {"nx": 3, "ny": 3, "P": 0.5}, {"nx": 3, "ny": 3, "N": 0.3},
                 {"nx": 3, "ny": 3, "L": 0.1}, {"nx": 10, "ny": 10, "source_taps": False},
                 {"nx": 3, "ny": 3, "runners": "met3,met4,met5"}, {"nx": 10, "ny": 10}]
        rc, out = run_py(body, self.env(), [json.dumps(cases)])
        self.assertEqual(rc, 0, out)
        ok, small_p, small_n, small_l, big, met5, big_taps = lines(out, "CB ")
        self.assertEqual(big_taps, {})                    # source taps: no latch-up warning
        self.assertEqual(ok, {})
        self.assertEqual(list(small_p), ["P"])
        self.assertEqual(small_p["P"][0], "ERR")
        self.assertEqual(list(small_n), ["N"])
        self.assertIn("below the minimum 0.550", small_n["N"][1])
        self.assertEqual(list(small_l), ["L"])
        self.assertEqual(sorted(big), ["nx", "ny"])
        self.assertEqual(big["nx"][0], "WARN")
        self.assertIn("15 um", big["nx"][1])
        self.assertEqual(list(met5), ["P"])
        self.assertIn("met5", met5["P"][1])

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

    def test_register_needs_no_magic(self):
        body = """
            ly = db.Layout()
            lib = kpp.register()
            c = ly.create_cell("HW_FET", "sky130_power", {"nx": 2, "ny": 2})
            print("REG " + json.dumps([lib is not None, ly.find_layer(255, 0) is None, c.dbbox().width() > 0]))
        """
        rc, out = run_py(body, self.env(KMP_MAGIC="/nonexistent/magic", PATH="/usr/bin:/bin"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(lines(out, "REG ")[0], [True, True, True])


if __name__ == "__main__":
    unittest.main()
