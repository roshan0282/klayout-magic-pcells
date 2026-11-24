"""sky130_power logic that needs no PDK tool (only the klayout module)."""

import os
import unittest
import xml.etree.ElementTree as ET

from tests.power._util import REPO, needs_klayout


@needs_klayout
class Stamps(unittest.TestCase):
    def test_make_and_parse(self):
        from klayout_power_pcells import backend
        s = backend.make_stamp("sky130A", key="ab" * 20, grid=5)
        p = backend.parse_stamp(s)
        self.assertTrue(s.startswith("hw2;version="))
        self.assertEqual(p["pdk"], "sky130A")
        self.assertEqual(p["key"], ("ab" * 20)[:16])
        self.assertEqual(p["grid"], "5")
        self.assertEqual(p["code"], backend.code_digest())
        self.assertEqual(p["rules"], backend.rules_digest())

    def test_foreign_stamps_are_not_ours(self):
        from klayout_power_pcells import backend
        for s in ("kmp1;magic=8.3;tech=1;pdk=sky130A", "hw1;version=0.3.0;code=x", None, ""):
            self.assertIsNone(backend.parse_stamp(s), s)

    def test_same_versions(self):
        from klayout_power_pcells import backend
        a = backend.parse_stamp(backend.make_stamp())
        self.assertTrue(backend.same_versions(a, dict(a, version="9.9.9")))   # version alone: same
        for k in ("code", "pdk", "rules"):
            self.assertFalse(backend.same_versions(a, dict(a, **{k: "other"})), k)

    def test_rules_digest_follows_the_table(self):
        from klayout_power_pcells import backend
        from klayout_power_pcells.rules import PDKS
        d = backend.rules_digest()
        old = PDKS["sky130A"]["rules"]["li_s"]
        try:
            PDKS["sky130A"]["rules"]["li_s"] = old + 5
            self.assertNotEqual(backend.rules_digest(), d)
        finally:
            PDKS["sky130A"]["rules"]["li_s"] = old
        self.assertEqual(backend.rules_digest(), d)


@needs_klayout
class Requests(unittest.TestCase):
    def test_round_trip_and_rounding(self):
        from klayout_power_pcells import backend
        from klayout_power_pcells.waffle import WaffleParams
        p = WaffleParams(device="pfet_01v8", nx=4, ny=3, P=4.0000000000000009, L=0.35000000000000003, N=None,
                         gate_strap="frame_only", runners=("met3",), bus="none", bus_w=None, guard_ring=False,
                         source_taps=False, tap_w=0.5)
        r = backend.request_of(p)
        self.assertEqual(r["P"], "4")
        self.assertEqual(r["L"], "0.35")
        self.assertEqual(r["N"], "")
        self.assertEqual(r["guard_ring"], "0")
        self.assertEqual((r["source_taps"], r["tap_w"]), ("0", "0.5"))
        q = backend.params_of(r)
        self.assertEqual(backend.request_of(q), r)

    def test_code_digest(self):
        from klayout_power_pcells import backend
        self.assertEqual(backend.code_digest(), backend.code_digest())
        self.assertEqual(len(backend.code_digest(full=True)), 64)


@needs_klayout
class Cli(unittest.TestCase):
    def test_kv(self):
        from klayout_power_pcells.__main__ import _kv
        v = _kv(["device=pfet_01v8", "nx=4", "P=3.5", "guard_ring=0", "runners=met3,met4,met5"])
        self.assertEqual(v, {"device": "pfet_01v8", "nx": 4, "P": 3.5, "guard_ring": False,
                             "runners": "met3,met4,met5"})
        for bad in (["P=abc"], ["nx=2.5"], ["device=nfet_g5v0d16v0"], ["bus=ring"], ["guard_ring=maybe"],
                    ["runners=met4"]):
            with self.assertRaises(SystemExit) as cm:
                _kv(bad)
            self.assertEqual(cm.exception.code, 2, bad)
        with self.assertRaises(SystemExit):
            _kv(["nosuch=1"])


@needs_klayout
class Declaration(unittest.TestCase):
    def test_parameters(self):
        from klayout_power_pcells.pcell import EDITABLE, HWFetPCell
        from klayout_power_pcells.rules import PDKS
        params = {p.name: p for p in HWFetPCell().get_parameters()}
        self.assertEqual([n for n in params if n in EDITABLE], list(EDITABLE))
        for n in EDITABLE:
            self.assertFalse(params[n].readonly, n)
        self.assertTrue(params["info"].readonly)
        self.assertTrue(params["hw_created"].hidden)
        self.assertEqual(sorted(params["device"].choice_values()), sorted(PDKS["sky130A"]["devices"]))
        self.assertEqual(sorted(params["bus"].choice_values()), ["L_buses", "none"])
        self.assertEqual(sorted(params["gate_strap"].choice_values()), ["frame_only", "met1_mesh"])

    def test_zero_means_minimum(self):
        from klayout_power_pcells.pcell import EDITABLE, HWFetPCell, params_of_values
        v = {p.name: p.default for p in HWFetPCell().get_parameters()}
        p = params_of_values({n: v[n] for n in EDITABLE})
        self.assertIsNone(p.L)
        self.assertIsNone(p.N)
        self.assertIsNone(p.bus_w)
        self.assertIsNone(p.tap_w)
        self.assertTrue(p.source_taps)


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


if __name__ == "__main__":
    unittest.main()
