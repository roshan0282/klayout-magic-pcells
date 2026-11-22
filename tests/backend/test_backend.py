"""Backend tests: need Magic and the PDKs (run them in the pinned image).

The PDK under test is the one KMP_PDK names (sky130A by default); the
harness runs this file once per PDK. Tests that name sky130A devices run only
for sky130A; the rest run for every PDK. Skipped when Magic or the rcfile
can't be found.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "python"))

from klayout_magic_pcells.backend import BackendError, MagicServer  # noqa: E402
from klayout_magic_pcells.config import Config  # noqa: E402
from klayout_magic_pcells.manifest import Manifest  # noqa: E402

try:
    import klayout.db as db
except ImportError:
    db = None


def _cfg(**env):
    e = dict(os.environ)
    e.setdefault("KMP_CACHE_DIR", tempfile.mkdtemp(prefix="kmp-test-cache-"))
    e.update(env)
    return Config.load(env=e)


try:
    CFG = _cfg()
    HAVE_MAGIC = not CFG.problems()
except Exception:
    HAVE_MAGIC = False

needs_magic = unittest.skipUnless(HAVE_MAGIC and db is not None,
                                  "Magic, the PDK or the klayout module is missing")
PDK = CFG.pdk if HAVE_MAGIC else "sky130A"
sky130_only = unittest.skipUnless(PDK == "sky130A", "names sky130A devices")


def alive(pid):
    try:
        with open("/proc/%d/status" % pid) as f:
            return "State:\tZ" not in f.read()
    except OSError:
        return False


def flat_signature(path):
    ly = db.Layout()
    ly.read(path)
    top = ly.top_cells()
    assert len(top) == 1, [c.name for c in top]
    out = {}
    for li in ly.layer_indices():
        info = ly.get_info(li)
        r = db.Region(top[0].begin_shapes_rec(li))
        r.merge()
        t = sorted((x.string, x.x, x.y) for x in db.Texts(top[0].begin_shapes_rec(li)).each())
        if not r.is_empty() or t:
            out["%d/%d" % (info.layer, info.datatype)] = (r.area(), r.count(), str(r.bbox()), t)
    return out


@needs_magic
class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kmp-backend-")
        cls.cfg = _cfg(KMP_CACHE_DIR=os.path.join(cls.tmp, "cache"))
        cls.man = Manifest.load(cls.cfg.manifest)
        cls.s = MagicServer(cls.cfg)
        cls.versions = cls.s.start()

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.tmp, name)

    def test_versions(self):
        v = self.versions
        self.assertRegex(v.magic, r"^\d+\.\d+\.\d+$")
        self.assertTrue(v.tech)
        self.assertEqual(len(v.code), 64)
        self.assertEqual(len(v.defaults), sum(1 for d in self.man.devices if d.kind == "device"))
        self.assertEqual(sorted(v.boxpaint), sorted(d.name for d in self.man.devices if d.kind == "box"))
        self.assertEqual(v.namespace, self.man.namespace)
        self.assertEqual(len(v.techdir), 64)
        self.assertTrue(v.pdk_commit)
        self.assertEqual(v.defaults_digest, self.man.defaults_digest,
                         "the running Magic's defaults differ from the shipped manifest")

    def test_every_device_twice_in_one_session(self):
        # M3: the same parameters twice must work (the server deletes the cell).
        for spec in self.man.devices:
            sigs = []
            for k in range(2):
                p = self.out("%s_%d.gds" % (spec.short_name, k))
                req = spec.build_request(spec.defaults_values()) if spec.kind == "box" else {}
                r = self.s.generate(spec.name, req, spec.form, p)
                self.assertTrue(r.cell or spec.kind == "box", spec.name)
                self.assertFalse(r.restart, (spec.name, r.kv))
                self.assertGreater(os.path.getsize(p), 100, spec.name)
                sigs.append(flat_signature(p))
                os.remove(p)
            self.assertEqual(sigs[0], sigs[1], spec.name)
            if not spec.batch.get("empty"):
                self.assertTrue(sigs[0], spec.name + " wrote no shapes")

    @sky130_only
    def test_brace_in_a_value(self):
        r = self.s.generate("sky130_fd_pr__nfet_01v8", {"w": "1{.5"}, "cell", self.out("b.gds"))
        self.assertIn("not numeric", r.log)
        self.assertEqual(r.checked["w"], "0.42")
        r2 = self.s.generate("sky130_fd_pr__nfet_01v8", {"w": "1.5"}, "cell", self.out("b2.gds"))
        self.assertEqual(r2.checked["w"], "1.5")

    @sky130_only
    def test_a_value_that_tcl_would_substitute_is_refused(self):
        # Defence in depth behind ParamSpec.check: the server itself refuses
        # [, ], $ and backslash in any value, whoever sends it.
        marker = self.out("server_marker")
        for op in ("generate", "check"):
            with self.assertRaises(BackendError) as cm:
                if op == "generate":
                    self.s.generate("sky130_fd_pr__nfet_01v8", {"guard": "1", "viagb": "[exec touch %s]" % marker},
                                    "cell", self.out("inj.gds"))
                else:
                    self.s.check("sky130_fd_pr__nfet_01v8", {"viagb": "$::env(HOME)"})
            self.assertIn("refused", str(cm.exception))
        self.assertFalse(os.path.exists(marker))
        self.assertTrue(self.s.ping())

    @sky130_only
    def test_endless_check_loop_is_stopped(self):
        # sky130::mos_check never returns when w and l are both above 28 um,
        # whatever nf and m are. The server stops it without a restart.
        pid = self.s.pid
        for dev in ("sky130_fd_pr__nfet_01v8", "sky130_fd_pr__cap_var_lvt"):
            for params in ({"w": "35", "l": "35", "nf": "1"}, {"w": "29", "l": "29", "nf": "4"}):
                t = time.time()
                with self.assertRaises(BackendError) as cm:
                    self.s.generate(dev, params, "cell", self.out("loop.gds"))
                self.assertIn("endless loop", str(cm.exception))
                with self.assertRaises(BackendError) as cm:
                    self.s.check(dev, params)
                self.assertIn("endless loop", str(cm.exception))
                self.assertLess(time.time() - t, 10, (dev, params))
        self.assertEqual(self.s.pid, pid)
        # Just below the condition Magic terminates and draws.
        r = self.s.generate("sky130_fd_pr__nfet_01v8", {"w": "28", "l": "35"}, "cell", self.out("w28.gds"))
        self.assertTrue(r.cell)
        self.assertNotIn("endless", r.log)

    @sky130_only
    def test_unknown_device_is_an_error(self):
        with self.assertRaises(BackendError) as cm:
            self.s.generate("sky130_fd_pr__nope", {}, "cell", self.out("n.gds"))
        self.assertIn("unknown device", str(cm.exception))
        self.assertTrue(self.s.ping())

    @sky130_only
    def test_check_messages_arrive_in_the_log(self):
        r = self.s.check("sky130_fd_pr__nfet_01v8", {"l": "0.1", "w": "0.1"})
        self.assertEqual((r.checked["l"], r.checked["w"]), ("0.15", "0.42"))
        self.assertIn("Mos length must be >= 0.15 um", r.log)
        r = self.s.generate("sky130_fd_pr__nfet_01v8", {"l": "0.1"}, "cell", self.out("c.gds"))
        self.assertIn("Mos length must be >= 0.15 um", r.log)

    @sky130_only
    def test_fixed_device_array(self):
        r = self.s.generate("sky130_fd_pr__npn_05v5_W1p00L1p00", {"nx": "2", "ny": "3"},
                            "wrapper", self.out("a.gds"))
        self.assertEqual((r.checked["nx"], r.checked["ny"]), ("2", "3"))
        ly = db.Layout()
        ly.read(self.out("a.gds"))
        insts = list(ly.top_cell().each_inst())
        self.assertEqual(len(insts), 1)
        self.assertEqual((insts[0].na, insts[0].nb), (3, 2))


# Requests that leave Magic's session changed, per PDK, and the requests that
# must still draw what a fresh Magic draws after them.
DISTURB = {
    "sky130A": [("nwell", "box", {"w": "3.0", "h": "2.0"}),         # runs tech revert
                ("deep_nwell", "box", {"w": "5.0", "h": "4.0"})],   # leaves ::boxstack
    "gf180mcuD": [("subcon_3p3", "box", {"w": "1.0", "h": "1.0"})],
    "ihp-sg13g2": [("dantenna", "cell", {"w": "0"}),               # leaves layers locked
                   ("subconn", "box", {"w": "1.0", "h": "1.0"})],   # sets units microns
    "ihp-sg13cmos5l": [("dantenna", "cell", {"w": "0"}),
                       ("subconn", "box", {"w": "1.0", "h": "1.0"})],
}
AFTER = {
    "sky130A": [("via1", "box", {"w": "1.0", "h": "1.0"}), ("sky130_fd_pr__nfet_01v8", "cell", {})],
    "gf180mcuD": [("via1", "box", {"w": "1.0", "h": "1.0"}), ("nfet_03v3", "cell", {})],
    "ihp-sg13g2": [("via", "cell", {}), ("inductor2", "cell", {}), ("inductor3", "cell", {}),
                   ("via1", "box", {"w": "1.0", "h": "1.0"})],
    "ihp-sg13cmos5l": [("via", "cell", {}), ("inductor2", "cell", {}),
                       ("via1", "box", {"w": "1.0", "h": "1.0"})],
}


@needs_magic
class AnyPdk(unittest.TestCase):
    """Run for the PDK that KMP_PDK names."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kmp-pdk-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sigs(self, s, reqs, tag):
        out = []
        for i, (dev, form, params) in enumerate(reqs):
            p = os.path.join(self.tmp, "%s_%d.gds" % (tag, i))
            try:
                r = s.generate(dev, params, form, p)
                out.append((dev, flat_signature(p), r.kv.get("restored", "")))
            except BackendError as e:
                out.append((dev, "error: %s" % e, ""))
        return out

    def test_session_state_is_put_back_after_each_request(self):
        cfg = _cfg(KMP_CACHE_DIR=self.tmp)
        a, b = MagicServer(cfg), MagicServer(cfg)
        try:
            a.start()
            b.start()
            fresh = self.sigs(a, AFTER[PDK], "fresh")
            dist = self.sigs(b, DISTURB[PDK], "dist")
            after = self.sigs(b, AFTER[PDK], "after")
        finally:
            a.close()
            b.close()
        if PDK != "gf180mcuD":
            self.assertTrue(any(d[2] for d in dist), "no request changed the session: %s" % dist)
        for f, g in zip(fresh, after):
            self.assertEqual(f[1], g[1], f[0])

    def test_box_paint_check_reports_the_box_magic_uses(self):
        cfg = _cfg(KMP_CACHE_DIR=self.tmp)
        man = Manifest.load(cfg.manifest)
        spec = man["via1"]
        s = MagicServer(cfg)
        try:
            s.start()
            r = s.check("via1", {"w": "1.003", "h": "1.0"}, "box")
            self.assertEqual((r.checked["w"], r.checked["h"]), ("1.005", "1.0"))
            self.assertEqual(r.log.strip(), "")
            m = float(spec.raw["min_box_um"])
            r = s.check("via1", {"w": "%.3f" % (m - 0.005), "h": "1.0"}, "box")
            self.assertIn("must be at least", r.log)
            with self.assertRaises(BackendError):
                s.check("via1", {"w": "1 [exec x]", "h": "1"}, "box")
            with self.assertRaises(BackendError):
                s.generate("nope_draw", {"w": "1", "h": "1"}, "box", os.path.join(self.tmp, "x.gds"))
        finally:
            s.close()

    @unittest.skipUnless(PDK in ("ihp-sg13g2", "gf180mcuD"), "needs a device without _check or "
                         "with a _check that raises")
    def test_check_without_a_check_proc_or_with_one_that_raises(self):
        s = MagicServer(_cfg(KMP_CACHE_DIR=self.tmp))
        try:
            s.start()
            if PDK == "ihp-sg13g2":
                r = s.check("rm6", {"w": "1.0"})
                self.assertEqual(r.kv.get("check"), "none")
            else:
                r = s.check("npolyf_s", {"w": "0"})
                self.assertEqual(r.kv.get("check"), "failed")
                self.assertIn("integer value too large", r.kv.get("check_error", ""))
            self.assertTrue(r.checked)
        finally:
            s.close()


@needs_magic
@sky130_only
class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kmp-recover-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_killed_magic_is_restarted_and_the_request_retried(self):
        s = MagicServer(_cfg(KMP_CACHE_DIR=self.tmp))
        try:
            s.start()
            pid = s.pid
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.2)
            r = s.generate("sky130_fd_pr__nfet_01v8", {}, "cell", os.path.join(self.tmp, "k.gds"))
            self.assertTrue(r.cell)
            self.assertNotEqual(s.pid, pid)
            self.assertGreaterEqual(s.stats["spawns"], 2)
        finally:
            s.close()

    def test_timeout_restarts_magic(self):
        s = MagicServer(_cfg(KMP_CACHE_DIR=self.tmp, KMP_TIMEOUT="3"))
        try:
            s.start()
            pid = s.pid
            # An incomplete Tcl command makes Magic wait for more input (M2);
            # the next request then gets no reply until the timeout.
            s._proc.stdin.write(b"puts {unbalanced\n")
            s._proc.stdin.flush()
            t = time.time()
            r = s.generate("sky130_fd_pr__nfet_01v8", {}, "cell", os.path.join(self.tmp, "t.gds"))
            self.assertTrue(r.cell)
            self.assertGreater(time.time() - t, 2.5)
            self.assertNotEqual(s.pid, pid)
            self.assertFalse(alive(pid))
        finally:
            s.close()

    def test_magic_missing(self):
        s = MagicServer(_cfg(KMP_CACHE_DIR=self.tmp, KMP_MAGIC="/no/such/magic"))
        with self.assertRaises(BackendError):
            s.start()

    def test_start_errors_say_why(self):
        # Exit status and Magic's own stderr in the message, the real wait in
        # a timeout, and no traceback from the pipe reader threads.
        boom = os.path.join(self.tmp, "boom.sh")
        with open(boom, "w") as f:
            f.write("#!/bin/sh\necho 'boom: no tech file' >&2\nexit 3\n")
        hang = os.path.join(self.tmp, "hang.sh")
        with open(hang, "w") as f:
            f.write("#!/bin/sh\nexec cat\n")
        os.chmod(boom, 0o755)
        os.chmod(hang, 0o755)
        script = textwrap.dedent("""
            import os, sys, time
            sys.path.insert(0, %r)
            from klayout_magic_pcells.backend import MagicServer
            from klayout_magic_pcells.config import Config
            env = dict(os.environ)
            for kv in sys.argv[1:]:
                k, v = kv.split("=", 1)
                env[k] = v
            s = MagicServer(Config.load(env=env))
            t = time.time()
            try:
                s.start()
                print("STARTED")
            except Exception as e:
                print("ERR %%.0f %%s" %% (time.time() - t, e))
            finally:
                s.close()
        """ % os.path.join(REPO, "python"))
        rc = os.path.join(os.path.dirname(CFG.magicrc))
        cases = [
            (["KMP_MAGIC=/bin/false"], "Magic exited (status 1)"),
            (["KMP_MAGIC=" + boom], "Magic exited (status 3); Magic said: boom: no tech file"),
            (["KMP_MAGIC=" + hang, "KMP_TIMEOUT=1"], "timed out after 10 s waiting for Magic to load kmp_server.tcl"),
            (["PDK_ROOT=/nonexistent", "KMP_MAGICRC=" + CFG.magicrc],
             "Could not find file '/nonexistent/sky130A/libs.tech/magic/sky130A.tech'"),
        ]
        self.assertTrue(os.path.isdir(rc))
        for args, expect in cases:
            p = subprocess.run([sys.executable, "-c", script, "KMP_CACHE_DIR=" + self.tmp] + args,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            text = p.stdout.decode()
            self.assertIn(expect, text, args)
            self.assertNotIn("Traceback", text, args)
            self.assertNotIn("Exception in thread", text, args)
            if "KMP_TIMEOUT=1" in args:
                self.assertIn("is %s Magic?" % hang, text)
                self.assertRegex(text, r"ERR (9|10|11) ")
        # Every server deleted its private run directory.
        self.assertEqual(os.listdir(os.path.join(self.tmp, "run")), [])

    def test_no_magic_left_after_the_client_exits(self):
        script = textwrap.dedent("""
            import os, sys
            sys.path.insert(0, %r)
            from klayout_magic_pcells.backend import make_server
            from klayout_magic_pcells.config import Config
            s = make_server(Config.load())
            s.start()
            print(s.pid, flush=True)
            if sys.argv[1] == "kill":
                os.kill(os.getpid(), 9)
            # normal exit: the atexit handler closes Magic
        """ % os.path.join(REPO, "python"))
        for how in ("exit", "kill"):
            env = dict(os.environ, KMP_CACHE_DIR=self.tmp)
            p = subprocess.run([sys.executable, "-c", script, how], stdout=subprocess.PIPE,
                               env=env, timeout=60)
            pid = int(p.stdout.split()[0])
            for _ in range(50):
                if not alive(pid):
                    break
                time.sleep(0.1)
            self.assertFalse(alive(pid), "Magic %d still running after the client's %s" % (pid, how))


@needs_magic
@sky130_only
class GeneratorAndLibrary(unittest.TestCase):
    def test_memo_disk_magic(self):
        from klayout_magic_pcells.backend import Generator
        from klayout_magic_pcells.cache import GdsCache, versions_fields
        tmp = tempfile.mkdtemp(prefix="kmp-gen-")
        cfg = _cfg(KMP_CACHE_DIR=tmp)
        man = Manifest.load(cfg.manifest)
        spec = man["sky130_fd_pr__res_high_po_0p69"]
        s = MagicServer(cfg)
        try:
            v = s.start()
            cache = GdsCache(tmp, versions_fields(v, cfg.pdk))
            g = Generator(s, cache, v)
            req = spec.build_request(dict(spec.defaults_values(), l=5.0, nx=2))
            a = g.get(spec, req)
            b = g.get(spec, req)
            self.assertEqual((a.source, b.source), ("magic", "memo"))
            g2 = Generator(s, GdsCache(tmp, versions_fields(v, cfg.pdk)), v)
            c = g2.get(spec, req)
            self.assertEqual(c.source, "disk")
            self.assertEqual(c.checked, a.checked)
            self.assertEqual(c.magic_cell, "sky130_fd_pr__res_high_po_0p69_G99TND")
            self.assertEqual(s.stats["generate"], 1)
        finally:
            s.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_damaged_cache_entries_are_regenerated(self):
        # A cache GDS that is garbage, truncated, or another device's file is
        # regenerated by Magic in the next session, in produce as well.
        tmp = tempfile.mkdtemp(prefix="kmp-damage-")
        script = textwrap.dedent("""
            import glob, os, shutil, sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            def place(dev):
                ly = db.Layout()
                c = ly.create_cell(dev, "sky130_magic", {})
                ph = ly.find_layer(255, 0)
                return "%%s %%s %%s" %% (dev[14:], c.dbbox(), ph is not None and not c.shapes(ph).is_empty())
            print("PLACE", place("sky130_fd_pr__res_high_po_0p69"), kmp.state.generator.stats)
            print("PLACE", place("sky130_fd_pr__cap_mim_m3_1"), kmp.state.generator.stats)
            res = glob.glob(os.path.join(os.environ["KMP_CACHE_DIR"], "v1/*/sky130_fd_pr__res_high_po_0p69/*.gds"))[0]
            if sys.argv[1] == "live":
                # damage the file under the memo of this session
                open(res, "wb").write(b"not a GDS file")
                print("PLACE", place("sky130_fd_pr__res_high_po_0p69"), kmp.state.generator.stats)
            elif sys.argv[1] != "none":
                mim = glob.glob(os.path.join(os.environ["KMP_CACHE_DIR"], "v1/*/sky130_fd_pr__cap_mim_m3_1/*.gds"))[0]
                if sys.argv[1] == "swap":
                    shutil.copy(mim, res)
                elif sys.argv[1] == "truncate":
                    data = open(res, "rb").read()
                    open(res, "wb").write(data[:len(data) // 2])
                else:
                    open(res, "wb").write(b"garbage" * 40)
        """ % os.path.join(REPO, "python"))
        good = "res_high_po_0p69 (-1.12,-3.355;1.12,3.355) False"
        try:
            for damage in ("garbage", "truncate", "swap", "live"):
                env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, damage))
                outs = []
                for step in (damage, "none"):
                    p = subprocess.run([sys.executable, "-c", script, step], stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env, timeout=120)
                    outs.append(p.stdout.decode())
                    self.assertEqual(p.returncode, 0, outs[-1])
                first, second = outs
                if damage == "live":
                    self.assertIn("can't be read", first)
                    self.assertIn("PLACE " + good + " {'memo': 1, 'disk': 0, 'magic': 3, 'evicted': 1}", first)
                # The next session sees the damage, deletes the entry and asks Magic.
                self.assertIn("PLACE " + good + " {'memo': 0, 'disk': 0, 'magic': 1, 'evicted': 0}"
                              if damage != "live" else
                              "PLACE " + good + " {'memo': 0, 'disk': 1, 'magic': 0, 'evicted': 0}", second, damage)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_register_in_plain_python(self):
        tmp = tempfile.mkdtemp(prefix="kmp-lib-")
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            lib = kmp.register("sky130A")
            assert lib is not None, kmp.state.last_error
            assert kmp.register("sky130A") is lib
            pid = kmp.state.server.pid
            assert kmp.state.server.stats["spawns"] == 1
            ly = db.Layout()
            top = ly.create_cell("TOP")
            c = ly.create_cell("sky130_fd_pr__nfet_01v8", "sky130_magic", {"w": 1.5, "l": 0.5, "nf": 3})
            top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
            b = c.dbbox()
            print("BBOX", b.left, b.bottom, b.right, b.top, c.display_title())
        """ % os.path.join(REPO, "python"))
        p = subprocess.run([sys.executable, "-c", script], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, env=dict(os.environ, KMP_CACHE_DIR=tmp), timeout=120)
        text = p.stdout.decode()
        shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(p.returncode, 0, text)
        self.assertIn("BBOX -1.965 -1.745 1.965 1.745 sky130_magic.nfet_01v8(w=1.5 l=0.5 nf=3)", text)

    def test_opening_a_file_never_runs_a_command_in_a_parameter(self):
        # A saved instance whose coverage string holds a Tcl command: placing
        # it and reopening the file (empty cache, so produce asks Magic) must
        # not run the command, and the cell must carry the error marker.
        tmp = tempfile.mkdtemp(prefix="kmp-inject-")
        marker = os.path.join(tmp, "INJECTED")
        gds = os.path.join(tmp, "inj.gds")
        script = textwrap.dedent("""
            import os, sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            marker, gds = sys.argv[1], sys.argv[2]
            if sys.argv[3] == "make":
                ly = db.Layout()
                top = ly.create_cell("TOP")
                for dev, name in (("sky130_fd_pr__nfet_01v8", "viagb"),
                                  ("sky130_fd_pr__res_high_po_0p35", "viagb"),
                                  ("sky130_fd_pr__cap_mim_m3_1", "ccov"),
                                  ("sky130_fd_pr__diode_pw2nd_05v5", "viagt")):
                    c = ly.create_cell(dev, "sky130_magic", {"guard": True, name: "[exec touch %%s]" %% marker})
                    top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
                ly.write(gds)
            else:
                ly = db.Layout()
                ly.read(gds)
            ph = ly.layer(255, 0)
            for c in ly.each_cell():
                if c.name == "TOP":
                    continue
                texts = [t.text_string for t in c.shapes(ph).each() if t.is_text()]
                print("CELL", c.name, c.is_pcell_variant(), "|".join(texts))
            print("MARKER", os.path.exists(marker))
        """ % os.path.join(REPO, "python"))
        try:
            for step in ("make", "open"):
                env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, "cache-" + step))
                p = subprocess.run([sys.executable, "-c", script, marker, gds, step], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=env, timeout=120)
                text = p.stdout.decode()
                self.assertEqual(p.returncode, 0, text)
                self.assertIn("MARKER False", text, step)
                cells = [ln for ln in text.splitlines() if ln.startswith("CELL ")]
                self.assertEqual(len(cells), 4, text)
                for ln in cells:
                    self.assertIn(" True KMP_ERROR ", ln, step)
                    self.assertIn("not sent to Magic", ln, step)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_register_fails_cleanly_on_a_bad_manifest(self):
        tmp = tempfile.mkdtemp(prefix="kmp-badman-")
        import json
        with open(CFG.manifest) as f:
            man = json.load(f)
        # A parameter called "layout" would overwrite PCellDeclarationHelper.layout.
        man["devices"][0]["params"].append({"name": "layout", "type": "float", "default": "1",
                                            "editable": True})
        bad = os.path.join(tmp, "bad.json")
        with open(bad, "w") as f:
            json.dump(man, f)
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout_magic_pcells as kmp
            import klayout.db as db
            assert kmp.register("sky130A") is None
            assert db.Library.library_by_name("sky130_magic") is None
            assert kmp.state.server is None
            print("ERR", kmp.state.last_error)
        """ % os.path.join(REPO, "python"))
        p = subprocess.run([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=dict(os.environ, KMP_MANIFEST=bad, KMP_CACHE_DIR=tmp), timeout=60)
        text = p.stdout.decode()
        shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(p.returncode, 0, text)
        self.assertIn("collide", text)

    def _py(self, script, env, args=()):
        p = subprocess.run([sys.executable, "-c", script] + list(args), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, env=env, timeout=120)
        return p.returncode, p.stdout.decode()

    def test_register_refuses_a_magic_without_the_devices(self):
        # An rcfile that loads no PDK (here: an empty one; a sky130A.tcl that
        # fails to load behaves the same): every PCell would draw the marker
        # and saving a file would replace its geometry, so nothing registers.
        tmp = tempfile.mkdtemp(prefix="kmp-nodev-")
        empty = os.path.join(tmp, "empty.magicrc")
        open(empty, "w").close()
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is None
            assert db.Library.library_by_name("sky130_magic") is None
            assert kmp.state.server is None
            print("ERR", kmp.state.last_error)
        """ % os.path.join(REPO, "python"))
        rc, text = self._py(script, dict(os.environ, KMP_MAGICRC=empty, KMP_CACHE_DIR=os.path.join(tmp, "c")))
        shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(rc, 0, text)
        self.assertIn("the running Magic defines 0 of the manifest's 73 generators", text)
        self.assertIn("KMP_MANIFEST", text)

    def test_an_unwritable_cache_dir_only_turns_the_cache_off(self):
        tmp = tempfile.mkdtemp(prefix="kmp-rocache-")
        ro = os.path.join(tmp, "ro")
        os.makedirs(ro)
        os.chmod(ro, 0o555)
        tmpdir = os.path.join(tmp, "tmpdir")
        os.makedirs(tmpdir)
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            ly = db.Layout()
            c = ly.create_cell("sky130_fd_pr__nfet_01v8", "sky130_magic", {"w": 1.0})
            print("CELL", c.dbbox(), kmp.state.cfg.cache_enabled, kmp.state.generator.stats["magic"])
        """ % os.path.join(REPO, "python"))
        try:
            for cache in ("1", "0"):
                env = dict(os.environ, KMP_CACHE_DIR=os.path.join(ro, "c"), KMP_CACHE=cache, TMPDIR=tmpdir)
                rc, text = self._py(script, env)
                self.assertEqual(rc, 0, text)
                self.assertIn("CELL (-1,-1.495;1,1.495) False 1", text)
                if cache == "1":
                    self.assertIn("can't be used", text)
                    self.assertIn("KMP_CACHE_DIR", text)
                else:
                    self.assertNotIn("can't be used", text)
                # the session's run and no-cache directories are gone
                self.assertEqual(os.listdir(tmpdir), [], cache)
        finally:
            os.chmod(ro, 0o755)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_leaves_nothing_behind_and_generate_reports_failure(self):
        tmp = tempfile.mkdtemp(prefix="kmp-cli-")
        tmpdir = os.path.join(tmp, "tmpdir")
        os.makedirs(tmpdir)
        env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, "cache"), TMPDIR=tmpdir,
                   PYTHONPATH=os.path.join(REPO, "python"))

        def cli(*args):
            p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells"] + list(args), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=env, timeout=120, cwd=tmp)
            return p.returncode, p.stdout.decode()
        try:
            out = os.path.join(tmp, "x.gds")
            rc, text = cli("generate", "sky130_fd_pr__nfet_01v8", "w=1", "-o", out)
            self.assertEqual(rc, 0, text)
            rc, text = cli("generate", "sky130_fd_pr__res_generic_po", "l=0", "-o", out)
            self.assertEqual(rc, 1, text)
            self.assertIn("Magic drew nothing", text)
            rc, text = cli("generate", "sky130_fd_pr__nfet_01v8", "viagb=abc", "-o", out)
            self.assertEqual(rc, 1, text)
            self.assertIn("KMP_ERROR", text)
            rc, text = cli("check", "sky130_fd_pr__nfet_01v8", "viagb=[exec ls]")
            self.assertEqual(rc, 2, text)
            self.assertIn("not sent to Magic", text)
            for args in (("check", "sky130_fd_pr__nfet_01v8", "w=0.1"), ("doctor",), ("cache", "stats"),
                         ("audit", out)):
                rc, text = cli(*args)
                self.assertNotIn("Traceback", text, args)
            self.assertEqual(os.listdir(tmpdir), [])
            self.assertEqual(os.listdir(os.path.join(tmp, "cache", "run")), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _farm(self, root, edit_tcl=lambda text: text, no_vendor_gds=False, edit_vendor_gds=None):
        """A PDK_ROOT whose sky130A is the installed one through symlinks,
        with sky130A.tcl passed through ``edit_tcl``, and optionally without
        libs.ref/sky130_fd_pr/gds (the vendor cells of the fixed devices),
        or with sky130_fd_pr.gds passed through ``edit_vendor_gds`` (bytes)."""
        src = os.path.join(CFG.pdk_root, "sky130A")
        dst = os.path.join(root, "sky130A")
        os.makedirs(os.path.join(dst, "libs.tech", "magic"))
        for name in os.listdir(src):
            if name == "libs.ref" and edit_vendor_gds is not None:
                for lib in os.listdir(os.path.join(src, name)):
                    d = os.path.join(dst, name, lib)
                    if lib != "sky130_fd_pr":
                        os.makedirs(os.path.dirname(d), exist_ok=True)
                        os.symlink(os.path.join(src, name, lib), d)
                        continue
                    os.makedirs(os.path.join(d, "gds"))
                    for sub in os.listdir(os.path.join(src, name, lib)):
                        if sub != "gds":
                            os.symlink(os.path.join(src, name, lib, sub), os.path.join(d, sub))
                    g = os.path.join(src, name, lib, "gds")
                    for fn in os.listdir(g):
                        if fn == "sky130_fd_pr.gds":
                            with open(os.path.join(g, fn), "rb") as f:
                                data = edit_vendor_gds(f.read())
                            with open(os.path.join(d, "gds", fn), "wb") as f:
                                f.write(data)
                        else:
                            os.symlink(os.path.join(g, fn), os.path.join(d, "gds", fn))
            elif name == "libs.ref" and no_vendor_gds:
                for lib in os.listdir(os.path.join(src, name)):
                    d = os.path.join(dst, name, lib)
                    if lib != "sky130_fd_pr":
                        os.makedirs(os.path.dirname(d), exist_ok=True)
                        os.symlink(os.path.join(src, name, lib), d)
                        continue
                    os.makedirs(d)
                    for sub in os.listdir(os.path.join(src, name, lib)):
                        if sub != "gds":
                            os.symlink(os.path.join(src, name, lib, sub), os.path.join(d, sub))
            elif name != "libs.tech":
                os.symlink(os.path.join(src, name), os.path.join(dst, name))
        for name in os.listdir(os.path.join(src, "libs.tech")):
            if name != "magic":
                os.symlink(os.path.join(src, "libs.tech", name), os.path.join(dst, "libs.tech", name))
        for name in os.listdir(os.path.join(src, "libs.tech", "magic")):
            p = os.path.join(src, "libs.tech", "magic", name)
            if name == "sky130A.tcl":
                with open(p) as f:
                    text = f.read()
                with open(os.path.join(dst, "libs.tech", "magic", name), "w") as f:
                    f.write(edit_tcl(text))
            else:
                os.symlink(p, os.path.join(dst, "libs.tech", "magic", name))
        return root

    def test_audit_after_a_local_sky130A_tcl_edit(self):
        # The photodiode's guard ring spacing edited in sky130A.tcl: the
        # stamp's digest shows it, audit --regen counts the difference as a
        # problem and exits 1, and reopening the file warns.
        tmp = tempfile.mkdtemp(prefix="kmp-edit-")
        old = "guard_sub_surround  0.18\t"
        def edit(text):
            self.assertEqual(text.count(old), 1)
            return text.replace(old, "guard_sub_surround  0.19\t")
        farm = self._farm(os.path.join(tmp, "farm"), edit)
        gds = os.path.join(tmp, "pd.gds")
        make = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            ly = db.Layout()
            if sys.argv[1] == "make":
                top = ly.create_cell("TOP")
                for dev in ("sky130_fd_pr__photodiode", "sky130_fd_pr__nfet_01v8"):
                    c = ly.create_cell(dev, "sky130_magic", {})
                    top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
                ly.write(sys.argv[2])
            else:
                ly.read(sys.argv[2])
            print("OK")
        """ % os.path.join(REPO, "python"))
        env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, "cache"), PYTHONPATH=os.path.join(REPO, "python"))
        edited = dict(env, PDK_ROOT=farm)
        try:
            rc, text = self._py(make, env, ["make", gds])
            self.assertEqual(rc, 0, text)
            p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells", "audit", gds, "--regen"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
            self.assertEqual(p.returncode, 0, p.stdout.decode())
            p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells", "audit", gds, "--regen"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=edited, timeout=120)
            text = p.stdout.decode()
            self.assertEqual(p.returncode, 1, text)
            pd = [ln for ln in text.splitlines() if "photodiode__kmp_" in ln][0]
            nf = [ln for ln in text.splitlines() if "nfet_01v8__kmp_" in ln][0]
            self.assertIn("regenerated geometry differs on 64/20", pd)
            self.assertIn("digest=", pd)
            self.assertIn("generated with", nf)          # same tech version, other code digest
            self.assertNotIn("regenerated geometry differs", nf)
            self.assertIn("2 sky130_magic cells, 2 with problems", text)
            rc, text = self._py(make, edited, ["open", gds])
            self.assertEqual(rc, 0, text)
            self.assertIn("photodiode: instance created with", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_after_a_vendor_gds_edit(self):
        # The review's case: one boundary of rf_test_coil1 in sky130_fd_pr.gds
        # moved 1 um, under the same open_pdks commit. The cache key and the
        # stamp cover the vendor GDS, so the edited PDK neither reads the old
        # cache entry nor passes the stamp check.
        import struct
        tmp = tempfile.mkdtemp(prefix="kmp-vendor-")

        def move_first_boundary(data):
            data = bytearray(data)
            i, in_bnd = 10318056, False         # rf_test_coil1's GDS_START
            while i < 10324764:
                n, rt, _ = struct.unpack(">HBB", data[i:i + 4])
                if rt == 0x08:
                    in_bnd = True
                if rt == 0x10 and in_bnd:
                    k = (n - 4) // 4
                    v = list(struct.unpack(">%di" % k, data[i + 4:i + n]))
                    for j in range(0, k, 2):
                        v[j] += 1000
                    data[i + 4:i + n] = struct.pack(">%di" % k, *v)
                    return bytes(data)
                i += n
            raise AssertionError("no boundary found")
        farm = self._farm(os.path.join(tmp, "farm"), edit_vendor_gds=move_first_boundary)
        gds = os.path.join(tmp, "coil.gds")
        make = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            ly = db.Layout()
            top = ly.create_cell("TOP")
            c = ly.create_cell("sky130_fd_pr__rf_test_coil1", "sky130_magic", {})
            top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
            ly.write(sys.argv[1])
            print("OK", kmp.state.generator.stats)
        """ % os.path.join(REPO, "python"))
        env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, "cache"), KMP_PDKS="sky130A",
                   PYTHONPATH=os.path.join(REPO, "python"))
        try:
            rc, text = self._py(make, env, [gds])
            self.assertEqual(rc, 0, text)
            p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells", "audit", gds, "--regen"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env=dict(env, PDK_ROOT=farm), timeout=180)
            text = p.stdout.decode()
            self.assertEqual(p.returncode, 1, text)
            self.assertIn("regenerated geometry differs on", text)
            self.assertIn("generated with", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_regen_replaces_a_stale_cache_entry(self):
        # A cache entry whose GDS (with a matching sidecar digest) isn't what
        # Magic generates now: audit --regen asks Magic anyway, reports the
        # entry and replaces it, so the next session reads the new one.
        import glob
        import hashlib
        import json
        tmp = tempfile.mkdtemp(prefix="kmp-stale-")
        make = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            ly = db.Layout()
            top = ly.create_cell("TOP")
            for dev, p in (("sky130_fd_pr__res_generic_po", {}), ("sky130_fd_pr__res_generic_po", {"l": 5.0})):
                c = ly.create_cell(dev, "sky130_magic", p)
                top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
            ly.write(sys.argv[1])
            print("OK", kmp.state.generator.stats)
        """ % os.path.join(REPO, "python"))
        gds = os.path.join(tmp, "res.gds")
        env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, "cache"), KMP_PDKS="sky130A",
                   PYTHONPATH=os.path.join(REPO, "python"))
        try:
            rc, text = self._py(make, env, [gds])
            self.assertEqual(rc, 0, text)
            entries = sorted(glob.glob(os.path.join(tmp, "cache", "v1", "*", "sky130_fd_pr__res_generic_po", "*.gds")))
            self.assertEqual(len(entries), 2)
            # Put one entry's GDS under the other's key, with a matching digest.
            a, b = entries
            shutil.copyfile(b, a)
            side = a[:-4] + ".json"
            with open(side) as f:
                sc = json.load(f)
            with open(a, "rb") as f:
                sc["gds_sha256"] = hashlib.sha256(f.read()).hexdigest()
            with open(side, "w") as f:
                json.dump(sc, f)
            p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells", "audit", gds, "--regen"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=180)
            text = p.stdout.decode()
            self.assertEqual(p.returncode, 1, text)
            self.assertIn("disk cache held a stale sky130_fd_pr__res_generic_po", text)
            self.assertEqual(text.count("regenerated: same as stored"), 2, text)
            # Replaced: a second audit finds nothing.
            p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells", "audit", gds, "--regen"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=180)
            self.assertEqual(p.returncode, 0, p.stdout.decode())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_missing_vendor_gds_is_named_in_the_marker(self):
        tmp = tempfile.mkdtemp(prefix="kmp-novendor-")
        farm = self._farm(os.path.join(tmp, "farm"), no_vendor_gds=True)
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            ly = db.Layout()
            c = ly.create_cell("sky130_fd_pr__npn_05v5_W1p00L1p00", "sky130_magic", {})
            print("MARKER", [sh.text_string for sh in c.shapes(ly.layer(255, 0)).each() if sh.is_text()])
        """ % os.path.join(REPO, "python"))
        try:
            rc, text = self._py(script, dict(os.environ, PDK_ROOT=farm, KMP_CACHE_DIR=os.path.join(tmp, "c")))
            self.assertEqual(rc, 0, text)
            marker = [ln for ln in text.splitlines() if ln.startswith("MARKER")][0]
            self.assertIn("KMP_ERROR sky130_fd_pr__npn_05v5_W1p00L1p00", marker)
            self.assertIn("sky130_fd_pr.gds", marker)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_flags_vendor_coordinates_rounded_by_the_file_dbu(self):
        tmp = tempfile.mkdtemp(prefix="kmp-grid-")
        make = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout.db as db
            import klayout_magic_pcells as kmp
            assert kmp.register("sky130A") is not None, kmp.state.last_error
            ly = db.Layout()
            ly.dbu = float(sys.argv[2])
            top = ly.create_cell("TOP")
            for dev in ("sky130_fd_pr__pnp_05v5_W0p68L0p68", "sky130_fd_pr__nfet_01v8"):
                c = ly.create_cell(dev, "sky130_magic", {})
                top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
            ly.write(sys.argv[1])
        """ % os.path.join(REPO, "python"))
        env = dict(os.environ, KMP_CACHE_DIR=os.path.join(tmp, "cache"), PYTHONPATH=os.path.join(REPO, "python"))
        try:
            for dbu, want in (("0.005", 1), ("0.001", 0)):
                gds = os.path.join(tmp, "g%s.gds" % dbu)
                rc, text = self._py(make, env, [gds, dbu])
                self.assertEqual(rc, 0, text)
                p = subprocess.run([sys.executable, "-m", "klayout_magic_pcells", "audit", gds],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
                text = p.stdout.decode()
                self.assertEqual(p.returncode, want, text)
                pnp = [ln for ln in text.splitlines() if "pnp_05v5_W0p68L0p68__kmp_" in ln][0]
                nf = [ln for ln in text.splitlines() if "nfet_01v8__kmp_" in ln][0]
                self.assertEqual("1 nm grid" in pnp, want == 1, text)
                self.assertTrue(nf.rstrip().endswith(" ok"), text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_register_fails_cleanly_without_magic(self):
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            import klayout_magic_pcells as kmp
            import klayout.db as db
            assert kmp.register("sky130A") is None
            assert db.Library.library_by_name("sky130_magic") is None
            print("ERR", kmp.state.last_error)
        """ % os.path.join(REPO, "python"))
        p = subprocess.run([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=dict(os.environ, KMP_MAGIC="/no/magic"), timeout=60)
        text = p.stdout.decode()
        self.assertEqual(p.returncode, 0, text)
        self.assertIn("KMP_MAGIC", text)


if __name__ == "__main__":
    unittest.main()
