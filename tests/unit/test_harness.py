"""The parity harness's own logic (no Magic needed)."""

import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest

from tests.unit._util import REPO  # noqa: F401  (puts tests/parity on sys.path)
import run_sweep  # noqa: E402

# Stands in for "magic ... magic_ref.tcl": one index line per point from
# KMP_START on; the device name says how the point behaves.
FAKE_MAGIC = textwrap.dedent("""
    import json, os, sys, time
    pts = json.load(open(os.environ["KMP_SWEEP"]))["points"]
    start = int(os.environ.get("KMP_START", "0"))
    os.makedirs(os.environ["KMP_OUT"], exist_ok=True)
    ix = open(os.path.join(os.environ["KMP_OUT"], "index.jsonl"), "a" if start else "w")
    for pt in pts[start:]:
        if pt["device"] == "crash":
            os._exit(139)
        if pt["device"] == "hang":
            time.sleep(120)
        ix.write(json.dumps({"id": pt["id"], "device": pt["device"], "rc": 0, "top": "T",
                             "magic_cell": "X", "log": "", "error": "", "checked": {}}) + "\\n")
        ix.flush()
    print("REF_DONE")
""")


class PathAWatchdog(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kmp-patha-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_fake(self, devices):
        fake = os.path.join(self.d, "fake_magic.py")
        with open(fake, "w") as f:
            f.write(FAKE_MAGIC)
        sweep = os.path.join(self.d, "sweep.json")
        with open(sweep, "w") as f:
            json.dump({"points": [{"id": "%04d" % (i + 1), "device": d} for i, d in enumerate(devices)]}, f)
        return run_sweep.path_a(self.d, sweep, cmd=[sys.executable, fake], stall=2)[0]

    def test_a_crash_and_a_hang_become_errors_and_the_sweep_goes_on(self):
        recs = self.run_fake(["ok", "crash", "ok", "hang", "ok"])
        self.assertEqual(sorted(recs), ["0001", "0002", "0003", "0004", "0005"])
        self.assertEqual([recs[k]["rc"] for k in sorted(recs)], [0, 1, 0, 1, 0])
        self.assertIn("Magic exited (status 139)", recs["0002"]["error"])
        self.assertIn("no point finished for 2 s", recs["0004"]["error"])

    def test_a_crash_on_the_last_point(self):
        recs = self.run_fake(["ok", "crash"])
        self.assertEqual((recs["0001"]["rc"], recs["0002"]["rc"]), (0, 1))

    def test_a_broken_harness_is_a_harness_error(self):
        with self.assertRaises(run_sweep.HarnessError):
            self.run_fake(["crash"] * 5 + ["ok"])


if __name__ == "__main__":
    unittest.main()
