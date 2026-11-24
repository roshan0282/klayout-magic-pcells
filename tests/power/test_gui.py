"""The sky130_power library in KLayout's GUI (under Xvfb): runs
tools/screenshots/power_shots.sh and checks what its sessions saw.

Needs xvfb-run, the klayout binary, Magic and sky130A, and this repository
linked into ~/.klayout/salt (the library list comes from the Salt autorun).
Takes about a minute; skipped without xvfb-run or the Salt link.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.power._util import HAVE_MAGIC, REPO

SALT = os.path.expanduser("~/.klayout/salt/klayout-power-pcells")


@unittest.skipUnless(HAVE_MAGIC and shutil.which("xvfb-run") and shutil.which("klayout")
                     and os.path.realpath(SALT) == os.path.realpath(REPO),
                     "needs xvfb-run, klayout, Magic, sky130A and the Salt link %s -> %s" % (SALT, REPO))
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
        self.assertEqual(main["form_fields"], ["bulk", "device", "info", "l", "nf", "nx", "ny",
                                               "pitch", "strap_w", "w"])
        self.assertEqual(main["form_icons_before"], [])
        self.assertTrue(main["form_info"].startswith("pitch "))
        self.assertTrue(main["after_strap"]["icons"][0].startswith("strap width 1.000 um is below"))
        self.assertEqual(main["after_l"]["l"], "0.15")
        self.assertEqual(main["after_l"]["icons"], ["Magic's dialog shows 0.15 (entered 0.1)"])
        self.assertTrue(main["placed"]["live"])
        self.assertEqual(main["placed"]["params"]["l"], 0.15)
        e = main["edited"]["params"]
        self.assertEqual((e["device"], e["bulk"], e["nx"], e["ny"]),
                         ("sky130_fd_pr__pfet_01v8", "source", 5, 5))
        self.assertIn("120 fingers", e["info"])
        (r,) = reopen["reopened"]
        self.assertTrue(r["live"])
        self.assertIn("pfet_01v8 5x5", r["title"])
        (d,) = defunct["reopened"]
        self.assertFalse(d["live"])
        self.assertEqual(d["title"], "<defunct>sky130_power.HW_FET")
        self.assertEqual(d["bbox"], r["bbox"])


if __name__ == "__main__":
    unittest.main()
