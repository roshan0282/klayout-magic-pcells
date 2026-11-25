"""Gate RC model of a hybrid-waffle FET (roadmap Phase 2.2).

The gate net is meshed like ron.py's metals: poly (48.2 ohm/sq), poly
contacts (152 ohm per cut), li, mcon and the met1 gate strap (sheet and
contact R from the PDK's Magic tech file). Every poly pixel over the
channel (poly on diffusion) carries C_ox times its area to the
source/body (ground). The G pin is driven by an ideal step, through an
optional driver resistance.

* Elmore delays: T = (G_ff)^-1 C 1, one sparse solve, the first moment of
  each node's step response. The spread over the channel pixels (max/min,
  max - min) says how unevenly the array turns on.
* Transient: backward Euler with a doubling time step gives t50 and t90 of
  every channel pixel.
* export_spice(): the same RC network as a SPICE deck for ngspice.

C_ox is a parameter. The default, 8.4 fF/um2, is eps_ox / t_ox for a
~4.1 nm gate oxide: an estimate for sky130's 1.8 V devices, not a PDK
number. It doesn't change the *relative* spread between gate straps, only
the absolute times.
"""

import math

import klayout.db as db

from .ron import SKY130A, Mesh, RonError

POLY = [("poly", 48.2)]
PCON = [("licon_poly", "poly", "li", 152.0, 0.17)]
COX_FF_UM2 = 8.4


def _gate_regions(w):
    poly = w.regions["poly"]
    regs = {"poly": poly, "licon_poly": w.regions.get("licon", db.Region()) & poly}
    for k in ("li", "mcon", "met1"):
        if k in w.regions:
            regs[k] = w.regions[k]
    channel = poly & w.regions["diff"]
    return regs, channel


def _g_pin(w):
    for (lay, dt), items in w.texts.items():
        for name, x, y in items:
            if name == "G":
                for p in w.pins.get("met1", db.Region()).each():
                    if p.bbox().contains(db.Point(x, y)):
                        return [("met1", db.Region(p))]
    raise RonError("the FET has no G pin on met1")


def network(params, pixel=0.05, cox=COX_FF_UM2, r_drive=0.0):
    """Gate RC network: {"mesh", "C" (F per node), "pin" (nodes), "chan"
    (nodes over the channel), "keep" (nodes connected to the pin), "w"}."""
    import numpy as np
    from .waffle import build
    w = build(params)
    regs, channel = _gate_regions(w)
    mesh = Mesh(regs, pixel, 0.001, {"metals": POLY + [m for m in SKY130A["metals"] if m[0] in ("li", "met1")],
                                     "cuts": PCON + [c for c in SKY130A["cuts"] if c[0] == "mcon"]})
    pin_parts = mesh.nodes_of(_g_pin(w))
    pin = np.unique(np.concatenate(pin_parts))
    if len(pin) == 0:
        raise RonError("the G pin covers no pixel")
    lab = mesh.components()
    keep = np.isin(lab, np.unique(lab[pin]))
    C = np.zeros(mesh.n)
    cov = mesh.raster(channel)                       # channel area per poly pixel (fraction)
    idx = mesh.index["poly"]
    on = (cov > 0) & (idx >= 0)
    C[idx[on]] = cov[on] * pixel * pixel * cox * 1e-15
    chan = idx[on]
    chan = chan[keep[chan]]
    lost = float(cov[(cov > 0) & (idx < 0)].sum()) * pixel * pixel
    return {"mesh": mesh, "C": C, "pin": pin, "chan": chan, "keep": keep, "w": w, "r_drive": r_drive,
            "C_total": float(C[keep].sum()), "channel_um2_unmeshed": lost}


def _system(net):
    """(A, b_col, free index): the free nodes' Laplacian and the column that
    couples them to the driven pin (through r_drive)."""
    import numpy as np
    import scipy.sparse as sp
    mesh = net["mesh"]
    Lap = mesh.laplacian()
    keep = net["keep"]
    if net["r_drive"] > 0:
        # one extra node: the source, behind r_drive to every pin node in parallel
        g = 1.0 / net["r_drive"] / len(net["pin"])
        free = np.where(keep)[0]
        A = Lap[free][:, free].tolil()
        pos = {n: k for k, n in enumerate(free)}
        b = np.zeros(len(free))
        for p in net["pin"]:
            A[pos[p], pos[p]] += g
            b[pos[p]] += g
        return A.tocsc(), b, free
    fixed = np.zeros(mesh.n, dtype=bool)
    fixed[net["pin"]] = True
    free = np.where(keep & ~fixed)[0]
    A = Lap[free][:, free].tocsc()
    b = -np.asarray(Lap[free][:, net["pin"]].sum(axis=1)).ravel()
    return A, b, free


def elmore(net):
    """Elmore delay (s) of every channel node."""
    import numpy as np
    import scipy.sparse.linalg as spla
    A, b, free = _system(net)
    T = np.zeros(net["mesh"].n)
    T[free] = spla.spsolve(A, net["C"][free])
    return T[net["chan"]]


def step_response(net, t_end=None, steps_per_octave=12):
    """(t50, t90) arrays (s) of the channel nodes for a 1 V step."""
    import numpy as np
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    A, b, free = _system(net)
    C = net["C"][free]
    pos = {n: k for k, n in enumerate(free)}
    ch = np.array([pos[n] for n in net["chan"]])
    te = elmore(net)
    t_end = t_end or 8 * te.max()
    dt = te.min() / 50.0 if te.min() > 0 else t_end / 1e4
    v = np.zeros(len(free))
    t = 0.0
    t50 = np.full(len(ch), np.nan)
    t90 = np.full(len(ch), np.nan)
    k = 0
    while t < t_end:
        if k % steps_per_octave == 0:
            lu = spla.splu((sp.diags(C / dt) + A).tocsc())
        vn = lu.solve(C / dt * v + b)
        tn = t + dt
        for arr, lvl in ((t50, 0.5), (t90, 0.9)):
            cross = np.isnan(arr) & (vn[ch] >= lvl)
            if cross.any():
                v0, v1 = v[ch][cross], vn[ch][cross]
                arr[cross] = t + dt * (lvl - v0) / np.maximum(v1 - v0, 1e-30)
        v, t = vn, tn
        k += 1
        if k % steps_per_octave == 0:
            dt *= 2
    return t50, t90


def export_spice(net, path, name="hw_gate"):
    """The gate RC network as a SPICE subcircuit with a step source on the
    pin, for ngspice. Node n<k> is mesh node k."""
    import numpy as np
    G = net["mesh"].G.tocoo()
    keep = net["keep"]
    with open(path, "w") as f:
        f.write("* hybrid-waffle gate RC network, %d nodes\n" % int(keep.sum()))
        f.write("VG drv 0 PWL(0 0 1f 1)\n")
        if net["r_drive"] > 0:
            f.write("RDRV drv pin %g\n" % net["r_drive"])
            src = "pin"
        else:
            src = "drv"
        pinset = set(net["pin"].tolist())
        k = 0

        def node(i):
            return src if i in pinset else "n%d" % i

        for a, b, g in zip(G.row, G.col, G.data):
            if a < b and keep[a] and g > 0 and not (a in pinset and b in pinset):
                f.write("R%d %s %s %.6g\n" % (k, node(a), node(b), 1.0 / g))
                k += 1
        for i in np.where((net["C"] > 0) & keep)[0]:
            f.write("C%d %s 0 %.6g\n" % (i, node(i), net["C"][i]))
    return path


def gate_delay(params, pixel=0.05, cox=COX_FF_UM2, r_drive=0.0, transient=False):
    """Summary of the gate's turn-on: Elmore delays over the channel and,
    with ``transient``, t50/t90."""
    import numpy as np
    net = network(params, pixel, cox, r_drive)
    te = elmore(net)
    out = {"C_gate_pF": net["C_total"] * 1e12, "nodes": int(net["keep"].sum()),
           "elmore_min_ps": float(te.min() * 1e12), "elmore_max_ps": float(te.max() * 1e12),
           "elmore_mean_ps": float(te.mean() * 1e12), "pixel": pixel,
           "channel_um2_unmeshed": net["channel_um2_unmeshed"]}
    if transient:
        t50, t90 = step_response(net)
        out.update({"t50_min_ps": float(np.nanmin(t50) * 1e12), "t50_max_ps": float(np.nanmax(t50) * 1e12),
                    "t90_min_ps": float(np.nanmin(t90) * 1e12), "t90_max_ps": float(np.nanmax(t90) * 1e12)})
    out["_net"] = net
    out["_elmore"] = te
    return out


def plot_compare(results, path):
    """Elmore delay maps of several gate_delay() results side by side
    (titles from their "label")."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    vmax = max(r["elmore_max_ps"] for r in results)
    fig, axes = plt.subplots(1, len(results), figsize=(5 * len(results), 4.6), squeeze=False)
    for ax, r in zip(axes[0], results):
        net = r["_net"]
        mesh = net["mesh"]
        img = np.full((mesh.ny, mesh.nx), np.nan)
        idx = mesh.index["poly"]
        flat = {int(n): k for k, n in enumerate(net["chan"])}
        iy, ix = np.where(idx >= 0)
        for y, x in zip(iy, ix):
            k = flat.get(int(idx[y, x]))
            if k is not None:
                img[y, x] = r["_elmore"][k] * 1e12
        im = ax.imshow(img, origin="lower", extent=mesh.extent(), cmap="magma", vmin=0, vmax=vmax)
        ax.set_title("%s\nElmore %.1f..%.1f ps" % (r.get("label", ""), r["elmore_min_ps"], r["elmore_max_ps"]),
                     fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
        fig.colorbar(im, ax=ax, fraction=0.046, label="ps")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
