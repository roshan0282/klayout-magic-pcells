"""Gate resistance of a HW FET (or any cell) from Magic's extresist.

    python3 tools/power/gate_resistance.py hw.gds HW_FET [--net G] [--pdk sky130A]

Prints, from the extracted resistor network between the net's pin and the
gate terminal of every device:

  R_finger  pin to one device's gate (min and max over the devices)
  R_short   pin to all gates tied together: the mesh plus every finger's
            own path in parallel (a lower bound for switching)
  R_elmore  the Elmore-equivalent series resistance for equal gate
            capacitance per device: tau = R_elmore * C_gate,total

Needs Magic and numpy.
"""

import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")


def extract(gds, top, net, pdk, out_dir):
    env = dict(os.environ, KMP_GDS=os.path.abspath(gds), KMP_TOP=top, KMP_NET=net, KMP_OUT=out_dir)
    rc = os.path.join(PDK_ROOT, pdk, "libs.tech", "magic", pdk + ".magicrc")
    log = os.path.join(out_dir, "extresist.log")
    with open(log, "w") as lf:
        subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", rc, os.path.join(HERE, "extresist.tcl")],
                       stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT, env=env,
                       cwd=out_dir, timeout=3600)
    spice = os.path.join(out_dir, top + "_res.spice")
    if "EXTRESIST_DONE" not in open(log, errors="replace").read() or not os.path.isfile(spice):
        raise RuntimeError("Magic extresist failed, see %s" % log)
    return spice


def analyse(spice, net="G"):
    def on_net(n):
        return n == net or n.startswith(net + ".")
    res, gates = [], []
    for line in open(spice, errors="replace"):
        t = line.split()
        if not t:
            continue
        if t[0][0] in "Rr" and len(t) >= 4 and on_net(t[1]) and on_net(t[2]):
            res.append((t[1], t[2], float(t[3])))
        elif t[0][0] in "Xx" and len(t) > 2 and on_net(t[2]):
            gates.append(t[2])
    if not gates:
        raise RuntimeError("no device gate on net %s in %s" % (net, spice))
    nodes = sorted({n for a, b, _ in res for n in (a, b)} | set(gates) | {net})
    idx = {n: i for i, n in enumerate(nodes)}
    Y = np.zeros((len(nodes), len(nodes)))
    for a, b, r in res:
        if a != b:
            g = 1.0 / max(r, 1e-6)
            i, j = idx[a], idx[b]
            Y[i, i] += g
            Y[j, j] += g
            Y[i, j] -= g
            Y[j, i] -= g
    keep = [i for i, n in enumerate(nodes) if n != net]      # the pin is the reference
    pos = {nodes[k]: m for m, k in enumerate(keep)}
    Ys = Y[np.ix_(keep, keep)]
    gi = [pos[g] for g in gates]
    Z = np.linalg.inv(Ys)
    Rg = Z[np.ix_(gi, gi)]
    # all gates tied: a node that every gate joins through 1 nano-ohm
    big = 1e9
    T = np.zeros((len(keep) + 1, len(keep) + 1))
    T[:-1, :-1] = Ys
    for k in gi:
        T[k, k] += big
        T[-1, -1] += big
        T[k, -1] -= big
        T[-1, k] -= big
    rhs = np.zeros(len(keep) + 1)
    rhs[-1] = 1.0
    r_short = np.linalg.solve(T, rhs)[-1]
    return {"devices": len(gi), "resistors": len(res), "r_finger_min": float(np.min(np.diag(Rg))),
            "r_finger_max": float(np.max(np.diag(Rg))), "r_short": float(r_short),
            "r_elmore": float(Rg.mean())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("gds")
    ap.add_argument("cell")
    ap.add_argument("--net", default="G")
    ap.add_argument("--pdk", default="sky130A")
    ap.add_argument("--keep", help="directory for Magic's files (default: a temporary one)")
    a = ap.parse_args(argv)
    out = a.keep or tempfile.mkdtemp(prefix="gate_r_")
    os.makedirs(out, exist_ok=True)
    r = analyse(extract(a.gds, a.cell, a.net, a.pdk, out), a.net)
    print("%s %s: %d devices, %d resistors; R_finger %.1f to %.1f ohm, R_short %.2f ohm, "
          "R_elmore %.2f ohm" % (a.cell, a.net, r["devices"], r["resistors"], r["r_finger_min"],
                                 r["r_finger_max"], r["r_short"], r["r_elmore"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
