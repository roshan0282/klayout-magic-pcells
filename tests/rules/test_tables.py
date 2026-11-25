"""The shared rule table (pdk_rules) and the per-package tables built from it.

legacy_tables.json is a snapshot of the four tables as they were written by
hand before version 0.9 (klayout_power_pcells, klayout_gen, klayout_centroid,
live_verify tier 0). Building them from pdk_rules must give the same values,
so moving to the shared table changed no geometry.

    python3 -m unittest discover -s tests/rules -t .
"""

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "python"))

import pdk_rules  # noqa: E402
from pdk_rules import mapped  # noqa: E402


def _j(o):
    """The snapshot's JSON form: tuple keys as repr strings, tuples as lists."""
    if isinstance(o, dict):
        return {k if isinstance(k, str) else repr(k): _j(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_j(x) for x in o]
    return o


def _close(test, a, b, path=""):
    """Equal, floats within 1e-9."""
    if isinstance(a, float) or isinstance(b, float):
        test.assertAlmostEqual(a, b, places=9, msg=path)
    elif isinstance(a, dict):
        test.assertEqual(sorted(a), sorted(b), path)
        for k in a:
            _close(test, a[k], b[k], path + "/" + k)
    elif isinstance(a, list):
        test.assertEqual(len(a), len(b), path)
        for i, (x, y) in enumerate(zip(a, b)):
            _close(test, x, y, "%s[%d]" % (path, i))
    else:
        test.assertEqual(a, b, path)


class TestLegacyTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, "legacy_tables.json")) as f:
            cls.legacy = json.load(f)

    def test_power(self):
        from klayout_power_pcells import rules
        _close(self, _j(rules.PDKS), self.legacy["power"], "power")

    def test_gen(self):
        from klayout_gen import rules
        _close(self, _j(rules.PDKS), self.legacy["gen"], "gen")
        self.assertEqual(rules.LIBRARIES, self.legacy["gen_libraries"])

    def test_centroid(self):
        from klayout_centroid import rules
        _close(self, _j(rules.PDKS), self.legacy["centroid"], "centroid")

    def test_live_verify_tier0(self):
        spec = importlib.util.spec_from_file_location("lv_pdk", os.path.join(REPO, "python", "live_verify", "pdk.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _close(self, _j(mod.TIER0), self.legacy["tier0"], "tier0")


class TestTable(unittest.TestCase):
    def test_every_rule_is_well_formed(self):
        for name, t in pdk_rules.tables().items():
            for key, r in t.rules.items():
                with self.subTest(pdk=name, rule=key):
                    self.assertGreaterEqual(r.value, 0)
                    if r.src != "use" and r.kind:
                        self.assertTrue(r.rule, "a probed rule needs its id")
                    for layer in r.on:
                        self.assertIn(layer, t.layers)
                    if r.kind == "enc":
                        self.assertEqual(len(r.on), 2)
                    if r.kind not in ("area", None) and r.src != "use":
                        # on the grid
                        self.assertAlmostEqual(round(r.value / t.grid) * t.grid, r.value, places=9)

    def test_stack_keys_exist(self):
        for name, t in pdk_rules.tables().items():
            for metal, cut, lo, hi in t.stack:
                self.assertIn(metal + "_w", t.rules)
                self.assertIn(metal + "_area", t.rules)
                if cut:
                    for k in (cut, cut + "_s", lo, hi):
                        self.assertIn(k, t.rules, (name, k))

    def test_unknown_pdk(self):
        with self.assertRaises(KeyError):
            pdk_rules.get("nope")


class TestMapped(unittest.TestCase):
    def test_glayout_schema(self):
        for name in pdk_rules.NAMES:
            with self.subTest(name):
                m = mapped.glayout(name)
                self.assertTrue(set(m["glayers"]) <= set(mapped.VALID_GLAYERS))
                self.assertEqual(set(m["grules"]), set(mapped.VALID_GLAYERS))
                for a, row in m["grules"].items():
                    self.assertEqual(set(row), set(mapped.VALID_GLAYERS))
                    for b, rule in row.items():
                        if rule:
                            self.assertTrue(set(rule) <= mapped.RULE_KEYS, (a, b, rule))
                met1 = m["grules"]["met1"]["met1"]
                self.assertGreater(met1["min_width"], 0)
                self.assertGreater(met1["min_separation"], 0)

    def test_sky130_name_shift(self):
        # gLayout calls sky130's li1 "met1" and licon "mcon" (its metal names are shifted by one)
        m = mapped.glayout("sky130A")
        self.assertEqual(m["glayers"]["met1"], (67, 20))
        self.assertEqual(m["glayers"]["mcon"], (66, 44))
        self.assertEqual(m["glayers"]["via1"], (67, 44))
        self.assertEqual(m["glayers"]["met2"], (68, 20))
        self.assertEqual(m["grules"]["met1"]["met1"], {"min_width": 0.17, "min_separation": 0.17})
        self.assertEqual(m["grules"]["via1"]["via1"], {"min_width": 0.17, "min_separation": 0.19, "width": 0.17})


if __name__ == "__main__":
    unittest.main()
