"""Design-space sweep of the hybrid-waffle FET (roadmap Phase 2.3).

For every point (P, nx = ny, runner set, runner style) it draws the FET
and computes:

* W_total and the drawn area (bounding box, guard ring included)
* Ron = r_ch / W + R_metal (ron.py) + the licon contacts, where r_ch
  (ohm um) is the channel's linear-region resistance from ngspice with
  the PDK's models (tt, Vgs = 1.8 V, Vds = 50 mV)
* Qg = q_g x W, q_g (fC/um) from ngspice: a constant current charges the
  gate to Vgs with Vds = 50 mV (the model's full gate charge, overlaps
  included)
* the figures of merit Ron x area (mohm mm2) and Ron x Qg (mohm nC)

The baseline is Magic's own multi-finger device from klayout-magic-pcells
(sky130_magic) at the same total W: its drawn area, and Ron = r_ch / W
(channel only: no metal, so the finger FET is favoured).

Results go to a CSV and a PNG.
"""

import functools
import math
import os
import re
import subprocess
import tempfile

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")

DECK = """* channel of {model}
.lib {lib} tt
XM1 d g 0 0 {model} w={w} l={l}
VD d 0 {vds}
{gate}
.control
{ctl}
.endc
.end
"""


def _ngspice(text):
    d = tempfile.mkdtemp(prefix="hw_sweep_")
    path = os.path.join(d, "deck.sp")
    with open(path, "w") as f:
        f.write(text)
    p = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=600, cwd=d)
    return p.stdout + p.stderr


@functools.lru_cache(maxsize=32)
def channel(device="nfet_01v8", L=0.15, vgs=1.8, vds=0.05, pdk="sky130A"):
    """(r_ch ohm*um, q_g fC/um) of the device at L, from ngspice."""
    lib = os.path.join(PDK_ROOT, pdk, "libs.tech", "ngspice", "sky130.lib.spice")
    model = "sky130_fd_pr__" + device
    w = 10.0
    sgn = -1 if device.startswith("pfet") else 1
    op = _ngspice(DECK.format(model=model, lib=lib, w=w, l=L, vds=sgn * vds, gate="VG g 0 %g" % (sgn * vgs),
                              ctl="op\nprint -i(VD)"))
    m = re.search(r"-i\(vd\)\s*=\s*([-+0-9.eE]+)", op)
    if not m:
        raise RuntimeError("ngspice gave no drain current:\n" + op[-800:])
    i = abs(float(m.group(1)))
    r_ch = vds / i * w
    # gate charge: 10 uA into the gate until |Vg| = vgs
    ig = 10e-6
    tr = _ngspice(DECK.format(model=model, lib=lib, w=w, l=L, vds=sgn * vds,
                              gate="IG 0 g %g\n.ic v(g)=0" % (sgn * ig),
                              ctl="tran 1p 20n uic\nmeas tran tq when v(g)=%g\n" % (sgn * vgs)))
    m = re.search(r"tq\s*=\s*([-+0-9.eE]+)", tr)
    if not m:
        raise RuntimeError("ngspice gave no gate-charge time:\n" + tr[-800:])
    q_fc = ig * float(m.group(1)) * 1e15
    return r_ch, q_fc / w


def finger_area(device, W, w_finger=5.0, l=0.15):
    """Drawn area (um2) of Magic's multi-finger device of total W (needs
    klayout_magic_pcells registered)."""
    import klayout.db as db
    nf = max(1, int(round(W / w_finger)))
    ly = db.Layout()
    ly.dbu = 0.001
    c = ly.create_cell("sky130_fd_pr__" + device, "sky130_magic",
                       {"w": W / nf, "l": l, "nf": nf, "guard": 1})
    if c is None:
        raise RuntimeError("sky130_magic is not registered")
    bb = c.dbbox()
    return bb.width() * bb.height(), nf


def point(params, pixel=0.1):
    from .ron import ron_metal
    from .waffle import build
    w = build(params)
    rep = w.report
    W, L = rep["W_total_um"], rep["L_um"]
    area = rep["bbox_area_um2"]
    r_ch, q = channel(params.device, L)
    rm = ron_metal(params, pixel=pixel)
    ron = r_ch / W + rm["R_metal"] + rm["R_contacts"]
    qg = q * W * 1e-6                       # nC
    return {"P": rep["P_um"], "nx": params.nx, "runners": ",".join(params.runners),
            "style": params.runner_style, "W_um": W, "area_um2": area, "W_per_area": W / area,
            # the square array alone, without guard ring and buses
            "core_W_per_area": W / (params.nx * params.ny * rep["P_um"] ** 2),
            "R_ch": r_ch / W, "R_metal": rm["R_metal"], "R_contacts": rm["R_contacts"], "Ron": ron,
            "Qg_nC": qg, "Ron_area_mohm_mm2": ron * 1e3 * area * 1e-6, "Ron_Qg_mohm_nC": ron * 1e3 * qg}


def sweep(device="nfet_01v8", Ps=(None, 3.0, 4.0, 6.0), nxs=(2, 4, 6),
          runner_sets=(("met3", "met4"), ("met3", "met4", "met5")), styles=("diag45",), pixel=0.1,
          baseline=True, progress=None):
    from .waffle import WaffleError, WaffleParams
    rows = []
    for P in Ps:
        for nx in nxs:
            for rs in runner_sets:
                for st in styles:
                    p = WaffleParams(device=device, nx=nx, ny=nx, P=P, runners=rs, runner_style=st)
                    try:
                        r = point(p, pixel)
                    except WaffleError as e:
                        if progress:
                            progress("skip P=%s nx=%d %s %s: %s" % (P, nx, ",".join(rs), st, e))
                        continue
                    if baseline:
                        try:
                            a, nf = finger_area(device, r["W_um"], l=0.15)
                            rc, _ = channel(device, 0.15)
                            r.update({"finger_area_um2": a, "finger_nf": nf,
                                      "finger_W_per_area": r["W_um"] / a,
                                      "finger_Ron_area_mohm_mm2": rc / r["W_um"] * 1e3 * a * 1e-6})
                        except Exception as e:
                            if progress:
                                progress("no baseline: %s" % e)
                    rows.append(r)
                    if progress:
                        progress("P=%.2f nx=%d %s %s: Ron %.3f ohm, Ron*A %.4f mohm mm2"
                                 % (r["P"], nx, r["runners"], st, r["Ron"], r["Ron_area_mohm_mm2"]))
    return rows


def write_csv(rows, path):
    import csv
    keys = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=keys)
        wr.writeheader()
        wr.writerows(rows)


def plot(rows, path, title="hybrid-waffle design space"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    groups = {}
    for r in rows:
        groups.setdefault((r["P"], r["runners"], r["style"]), []).append(r)
    for (P, rs, st), g in sorted(groups.items()):
        g = sorted(g, key=lambda r: r["W_um"])
        lab = "P %.2f %s%s" % (P, rs, "" if st == "diag45" else " " + st)
        ls = "-" if rs.count(",") == 1 else "--"
        axes[0].plot([r["W_um"] for r in g], [r["Ron_area_mohm_mm2"] for r in g], ls, marker="o", label=lab)
        axes[1].plot([r["W_um"] for r in g], [r["Ron_Qg_mohm_nC"] for r in g], ls, marker="o", label=lab)
        axes[2].plot([r["W_um"] for r in g], [r["W_per_area"] for r in g], ls, marker="o", label=lab)
    base = sorted([r for r in rows if "finger_area_um2" in r], key=lambda r: r["W_um"])
    if base:
        axes[0].plot([r["W_um"] for r in base], [r["finger_Ron_area_mohm_mm2"] for r in base], "k:", marker="x",
                     label="Magic multi-finger, channel only")
        axes[2].plot([r["W_um"] for r in base], [r["finger_W_per_area"] for r in base], "k:", marker="x",
                     label="Magic multi-finger")
    for ax, yl in zip(axes, ("Ron x area (mohm mm2)", "Ron x Qg (mohm nC)", "W per area (um / um2)")):
        ax.set_xlabel("W total (um)")
        ax.set_ylabel(yl)
        ax.set_xscale("log")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
