"""Rule probes: every rule of the shared table with a probe kind passes the
PDK's KLayout DRC deck at its value and fails one grid step under it.

    python3 -m unittest tests.rules.test_probes      (about a minute per PDK)
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "python"))

import pdk_rules  # noqa: E402

try:
    import klayout.db  # noqa: F401
    HAVE_KLAYOUT = shutil.which("klayout") is not None
except ImportError:  # pragma: no cover
    HAVE_KLAYOUT = False
PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")


def _have(pdk):
    return HAVE_KLAYOUT and os.path.isfile(os.path.join(PDK_ROOT, pdk, pdk_rules.get(pdk).drc_deck[0]))


class TestProbes(unittest.TestCase):
    def check(self, pdk):
        from pdk_rules import probe
        work = tempfile.mkdtemp(prefix="probe_")
        try:
            res = probe.probe(pdk, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(set(res), set(pdk_rules.get(pdk).probed()))
        bad = {k: v for k, v in res.items() if v[0] != "ok"}
        self.assertEqual(bad, {})

    @unittest.skipUnless(_have("sky130A"), "needs klayout and sky130A")
    def test_sky130A(self):
        self.check("sky130A")

    @unittest.skipUnless(_have("gf180mcuD"), "needs klayout and gf180mcuD")
    def test_gf180mcuD(self):
        self.check("gf180mcuD")


if __name__ == "__main__":
    unittest.main()
