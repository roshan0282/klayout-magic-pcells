"""Gate RC model (gate.py): analytic RC line, straps, and ngspice agreement.

    python3 -m unittest tests.power.test_gate
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, PY  # noqa: F401

if PY not in sys.path:
    sys.path.insert(0, PY)

try:
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:  # pragma: no cover
    HAVE_SCIPY = False

needs = unittest.skipUnless(HAVE_KLAYOUT and HAVE_SCIPY, "needs klayout and scipy")


@needs
class TestRCLine(unittest.TestCase):
    def test_elmore_of_a_uniform_line(self):
        """A 20 x 0.5 um poly line driven at one end, C spread evenly:
        Elmore delay at the far end = R C / 2."""
        import numpy as np
        import klayout.db as db
        from klayout_power_pcells import gate
        from klayout_power_pcells.ron import Mesh
        line = db.Region(db.Box(0, 0, 20000, 500))
        mesh = Mesh({"poly": line}, 0.05, 0.001, {"metals": gate.POLY, "cuts": []})
        pin = np.unique(np.concatenate(mesh.nodes_of([("poly", db.Region(db.Box(0, 0, 50, 500)))])))
        C = np.full(mesh.n, 1e-15)
        C[pin] = 0
        net = {"mesh": mesh, "C": C, "pin": pin, "keep": np.ones(mesh.n, dtype=bool), "r_drive": 0.0,
               "chan": np.arange(mesh.n)}
        te = gate.elmore(net)
        R = 48.2 * 19.95 / 0.5
        Ctot = C.sum()
        self.assertAlmostEqual(te.max(), R * Ctot / 2, delta=0.03 * R * Ctot / 2)


@needs
class TestStraps(unittest.TestCase):
    def test_mesh_beats_frame(self):
        from klayout_power_pcells import gate
        from klayout_power_pcells.waffle import WaffleParams
        mesh = gate.gate_delay(WaffleParams(nx=3, ny=3, P=4.0, gate_strap="met1_mesh"))
        frame = gate.gate_delay(WaffleParams(nx=3, ny=3, P=4.0, gate_strap="frame_only"))
        self.assertLess(mesh["elmore_max_ps"], frame["elmore_max_ps"])
        self.assertEqual(mesh["channel_um2_unmeshed"], 0.0)
        # C_gate = W L C_ox
        from klayout_power_pcells.waffle import build
        w = build(WaffleParams(nx=3, ny=3, P=4.0))
        c = w.report["W_total_um"] * w.report["L_um"] * gate.COX_FF_UM2 * 1e-3
        self.assertAlmostEqual(mesh["C_gate_pF"], c, delta=0.05 * c)


@needs
@unittest.skipUnless(shutil.which("ngspice"), "needs ngspice")
class TestNgspice(unittest.TestCase):
    def test_transient_matches_ngspice(self):
        import numpy as np
        from klayout_power_pcells import gate
        from klayout_power_pcells.waffle import WaffleParams
        net = gate.network(WaffleParams(nx=2, ny=2, P=4.0, gate_strap="frame_only"), pixel=0.1, r_drive=50.0)
        te = gate.elmore(net)
        t50, t90 = gate.step_response(net)
        k = int(np.argmax(te))
        work = tempfile.mkdtemp(prefix="gate_")
        try:
            sp = gate.export_spice(net, os.path.join(work, "gate.sp"))
            deck = os.path.join(work, "run.sp")
            tend = 8 * te.max()
            with open(deck, "w") as f:
                f.write("* run\n.include %s\n.tran %g %g\n.control\nrun\nmeas tran t50 when v(n%d)=0.5 rise=1\n"
                        "meas tran t90 when v(n%d)=0.9 rise=1\n.endc\n.end\n"
                        % (sp, tend / 500, tend, net["chan"][k], net["chan"][k]))
            out = subprocess.run(["ngspice", "-b", deck], capture_output=True, text=True, timeout=600).stdout
            vals = {l.split()[0]: float(l.split("=")[1]) for l in out.splitlines()
                    if l.strip().startswith(("t50", "t90")) and "=" in l}
            self.assertAlmostEqual(t50[k], vals["t50"], delta=0.06 * vals["t50"])
            self.assertAlmostEqual(t90[k], vals["t90"], delta=0.06 * vals["t90"])
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
