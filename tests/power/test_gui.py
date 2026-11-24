"""The sky130_power library in KLayout's GUI (under Xvfb): runs
tools/screenshots/power_shots.sh and checks what its sessions saw.

Needs xvfb-run and the klayout binary, and this repository linked into
~/.klayout/salt (the library list comes from the Salt autorun).
Takes about a minute; skipped without xvfb-run or the Salt link.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, REPO

SALT = os.path.expanduser("~/.klayout/salt/klayout-power-pcells")


@unittest.skipUnless(HAVE_KLAYOUT and shutil.which("xvfb-run") and shutil.which("klayout")
                     and os.path.realpath(SALT) == os.path.realpath(REPO),
                     "needs xvfb-run, klayout and the Salt link %s -> %s" % (SALT, REPO))
class Gui(unittest.TestCase):
    def test_sessions(self):
        out = tempfile.mkdtemp(prefix="hw_gui_")
        try:
            p = subprocess.run([os.path.join(REPO, "tools", "screenshots", "power_shots.sh"), out],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
            text = p.stdout.decode(errors="replace")
            self.assertEqual(p.returncode, 0, text)
            main = json.load(open(os.path.join(out, "notes-main.json")))
            reopen = json.load(open(os.path.join(out, "notes-reopen.json")))
            defunct = json.load(open(os.path.join(out, "notes-defunct.json")))
        finally:
            shutil.rmtree(out, ignore_errors=True)
        self.assertTrue(any(l.startswith("sky130_power") for l in main["libraries"]))
        self.assertEqual(main["form_fields"], ["L", "N", "P", "bus", "bus_w", "device", "gate_strap", "info",
                                               "nx", "ny", "runner_style", "runners", "tap_w"])
        # the 10 x 10 default: body taps in the source squares, no warning
        self.assertEqual(main["form_icons_before"], [])
        self.assertTrue(main["form_info"].startswith("180 gates, W 628.20 um"), main["form_info"])
        self.assertIn("body S", main["form_info"])
        # without them: a latch-up warning on nx and ny, and the result line says why
        self.assertEqual(len(main["taps_off"]["icons"]), 2)
        self.assertIn("20.8 um", main["taps_off"]["icons"][0])
        self.assertIn("body B", main["taps_off"]["info"])
        self.assertEqual(main["after_p"]["icons"], ["P 0.500 um is too small for L 0.150 and N 0.550 um"])
        self.assertTrue(main["after_p"]["info"].startswith("not drawn:"))
        self.assertIn("below the minimum 0.550 um", main["after_n"]["icons"][0])
        self.assertEqual(main["before_place"]["icons"], [])
        self.assertTrue(main["placed"]["live"])
        self.assertIn("nfet_01v8 4x4", main["placed"]["title"])
        e = main["edited"]["params"]
        self.assertEqual((e["device"], e["gate_strap"], e["nx"], e["ny"]), ("pfet_01v8", "frame_only", 5, 5))
        self.assertTrue(e["info"].startswith("40 gates"))
        self.assertIn("N 0.300 um", e["info"])           # frame_only: the notch shrinks to L + 2 x poly.4
        (r,) = reopen["reopened"]
        self.assertTrue(r["live"])
        self.assertIn("pfet_01v8 5x5", r["title"])
        (d,) = defunct["reopened"]
        self.assertFalse(d["live"])
        self.assertEqual(d["title"], "<defunct>sky130_power.HW_FET")
        self.assertEqual(d["bbox"], r["bbox"])

if __name__ == "__main__":
    unittest.main()
