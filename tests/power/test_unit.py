"""sky130_power logic that needs neither Magic nor a PDK."""

import os
import unittest
import xml.etree.ElementTree as ET

from tests.power._util import REPO, needs_klayout


class Versions:
    magic, tech, pdk, open_pdks, code, techfile = "8.3.685", "1.0.588", "sky130A", "x", "c", "t"
    pdk_commit, techdir, vendor = "p", "d", "v"


@needs_klayout
class Stamps(unittest.TestCase):
    def test_make_and_parse(self):
        from klayout_power_pcells import backend
        s = backend.make_stamp(Versions(), key="ab" * 20, grid=5)
        p = backend.parse_stamp(s)
        self.assertTrue(s.startswith("hw1;version="))
        self.assertEqual(p["magic"], "8.3.685")
        self.assertEqual(p["pdk"], "sky130A")
        self.assertEqual(p["key"], ("ab" * 20)[:16])
        self.assertEqual(p["grid"], "5")
        self.assertEqual(p["code"], backend.code_digest())
        self.assertEqual(len(p["digest"]), 12)

    def test_foreign_stamps_are_not_ours(self):
        from klayout_power_pcells import backend
        self.assertIsNone(backend.parse_stamp("kmp1;magic=8.3;tech=1;pdk=sky130A"))
        self.assertIsNone(backend.parse_stamp(None))
        self.assertIsNone(backend.parse_stamp(""))

    def test_same_versions(self):
        from klayout_power_pcells import backend
        a = backend.parse_stamp(backend.make_stamp(Versions()))
        self.assertTrue(backend.same_versions(a, dict(a, version="9.9.9")))   # version alone: same
        for k in ("code", "magic", "tech", "pdk", "digest"):
            self.assertFalse(backend.same_versions(a, dict(a, **{k: "other"})), k)


@needs_klayout
class Requests(unittest.TestCase):
    def test_round_trip_and_rounding(self):
        from klayout_power_pcells import backend
        from klayout_power_pcells.hybrid_waffle import HWParams
        p = HWParams(l=0.35000000000000003, w=4.2576271568149995, nf=2, nx=3, ny=4, strap_w=3.0,
                     pitch=None, device="sky130_fd_pr__pfet_01v8", bulk="source")
        r = backend.request_of(p)
        self.assertEqual(r["l"], "0.35")
        self.assertEqual(r["w"], "4.25762715681")
        self.assertEqual(r["pitch"], "")
        q = backend.params_of(r)
        self.assertEqual(backend.request_of(q), r)
        # one ULP off (a double reopened from a saved file) gives the same request
        self.assertEqual(backend.request_of(HWParams(l=0.35))["l"],
                         backend.request_of(HWParams(l=0.35000000000000003))["l"])

    def test_code_digest_is_stable(self):
        from klayout_power_pcells import backend
        self.assertEqual(backend.code_digest(), backend.code_digest())
        self.assertEqual(len(backend.code_digest(full=True)), 64)


@needs_klayout
class Cli(unittest.TestCase):
    def test_kv(self):
        from klayout_power_pcells.__main__ import _kv
        v = _kv(["device=pfet_01v8", "bulk=source", "nx=4", "l=0.5"])
        self.assertEqual(v, {"device": "sky130_fd_pr__pfet_01v8", "bulk": "source", "nx": 4, "l": 0.5})
        for bad in (["l=abc"], ["nx=2.5"], ["device=nfet_g5v0d16v0"], ["bulk=well"]):
            with self.assertRaises(SystemExit) as cm:
                _kv(bad)
            self.assertEqual(cm.exception.code, 2, bad)
        with self.assertRaises(SystemExit):
            _kv(["nosuch=1"])


@needs_klayout
class Declaration(unittest.TestCase):
    def test_parameters(self):
        from klayout_power_pcells.pcell import HWFetPCell, EDITABLE
        from klayout_power_pcells.hybrid_waffle import DEVICES
        decl = HWFetPCell()
        params = {p.name: p for p in decl.get_parameters()}
        for n in EDITABLE:
            self.assertIn(n, params)
            self.assertFalse(params[n].readonly)
        self.assertTrue(params["info"].readonly)
        self.assertTrue(params["hw_created"].hidden)
        self.assertEqual(sorted(params["device"].choice_values()), sorted(DEVICES))
        self.assertEqual(sorted(params["bulk"].choice_values()), ["ring", "source"])


class Packaging(unittest.TestCase):
    def test_grain(self):
        root = ET.parse(os.path.join(REPO, "grain.xml")).getroot()
        self.assertEqual(root.find("name").text, "klayout-power-pcells")
        from klayout_power_pcells import __version__
        self.assertEqual(root.find("version").text, __version__)

    def test_macros(self):
        for name, call in (("klayout_magic_pcells.lym", "klayout_magic_pcells.register()"),
                           ("klayout_power_pcells.lym", "klayout_power_pcells.register()")):
            root = ET.parse(os.path.join(REPO, "pymacros", name)).getroot()
            self.assertEqual(root.find("autorun").text, "true")
            self.assertIn(call, root.find("text").text)
        prio = {n: int(ET.parse(os.path.join(REPO, "pymacros", n)).getroot().find("priority").text)
                for n in ("klayout_magic_pcells.lym", "klayout_power_pcells.lym")}
        self.assertLess(prio["klayout_magic_pcells.lym"], prio["klayout_power_pcells.lym"])


if __name__ == "__main__":
    unittest.main()
