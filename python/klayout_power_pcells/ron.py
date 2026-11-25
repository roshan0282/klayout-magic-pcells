"""Metallization resistance of a hybrid-waffle FET (roadmap Phase 2.1).

The FET's own drawn geometry becomes a resistor network: every metal
(li, met1 ... met5) is rasterized into square pixels (one node each,
conductance 1 / R_sheet to each 4-neighbour), every cut layer (mcon, via
... via4) joins the pixels above and below with (cut area in the pixel /
one cut's area) / R_cut. The S and D pins are grounded; each S (D) square
injects an equal share of 1 A at the li over its licon cuts. That is the
usual assumption that the channel dominates, so the squares carry equal
current. A sparse solve gives every node's voltage, and

    R_net = sum_k I_k V_k / I^2          (power-equivalent resistance)

for the S and the D network. The licon contacts add sum_sq I_sq^2 R_c / n_sq.
Rds_on(metal) = R_S + R_D (+ contacts).

Sheet and contact resistances are Magic's extraction values from the
PDK's tech file (sky130A.tech, "extract" style ngspice): li 12.8 ohm/sq,
met1/met2 0.125, met3/met4 0.047, met5 0.029; mcon 9.3 ohm, via 4.5,
via2/via3 3.41, via4 0.38; licon 185 (n) / 585 (p) ohm per cut.

Needs numpy and scipy (both in the iic-osic-tools image); matplotlib for
the heatmap.
"""

import math

import klayout.db as db

SKY130A = {
    "metals": [("li", 12.8), ("met1", 0.125), ("met2", 0.125), ("met3", 0.047), ("met4", 0.047),
               ("met5", 0.029)],
    # cut layer, metal below, metal above, R per cut (ohm), cut size (um)
    "cuts": [("mcon", "li", "met1", 9.3, 0.17), ("via", "met1", "met2", 4.5, 0.15),
             ("via2", "met2", "met3", 3.41, 0.20), ("via3", "met3", "met4", 3.41, 0.20),
             ("via4", "met4", "met5", 0.38, 0.80)],
    "licon": {"n": 185.0, "p": 585.0, "size": 0.17},
}


class RonError(RuntimeError):
    pass


class Mesh:
    """Rasterized metals as a conductance matrix.

    ``index[layer]`` maps a pixel [iy][ix] to its node (or -1); ``G`` is
    the symmetric conductance matrix (siemens) between nodes; ``nodes_of``
    turns (layer, Region) items into node arrays."""

    def __init__(self, regions, pixel=0.1, dbu=0.001, tech=SKY130A, extra_metals=(), extra_cuts=()):
        import numpy as np
        import scipy.sparse as sp
        self.np = np
        metal_rs = list(tech["metals"]) + list(extra_metals)
        cuts = list(tech["cuts"]) + list(extra_cuts)
        self.rs = dict(metal_rs)
        self.metals = [m for m, _ in metal_rs if m in regions and not regions[m].is_empty()]
        if not self.metals:
            raise RonError("no metal to solve")
        bb = db.Box()
        for m in self.metals:
            bb += regions[m].bbox()
        self.bbox, self.dbu, self.pixel = bb, dbu, pixel
        pu = int(round(pixel / dbu))
        self.nx = bb.width() // pu + 1
        self.ny = bb.height() // pu + 1
        self.org = db.Point(bb.left, bb.bottom)
        self.step = db.Vector(pu, pu)
        self.pa = float(pu * pu)
        occ = {m: self.raster(regions[m]) >= 0.5 for m in self.metals}
        self.index = {}
        n = 0
        for m in self.metals:
            idx = -np.ones((self.ny, self.nx), dtype=np.int64)
            k = int(occ[m].sum())
            idx[occ[m]] = np.arange(n, n + k)
            self.index[m] = idx
            n += k
        self.n = n
        rows, cols, vals = [], [], []

        def add(a, b, g):
            rows.extend(a.tolist() + b.tolist())
            cols.extend(b.tolist() + a.tolist())
            vals.extend(list(g) * 2 if hasattr(g, "__len__") else [g] * (2 * len(a)))

        for m in self.metals:
            idx, g = self.index[m], 1.0 / self.rs[m]
            h = (idx[:, :-1] >= 0) & (idx[:, 1:] >= 0)
            add(idx[:, :-1][h], idx[:, 1:][h], g)
            v = (idx[:-1, :] >= 0) & (idx[1:, :] >= 0)
            add(idx[:-1, :][v], idx[1:, :][v], g)
        for cut, lo, hi, rc, size in cuts:
            if cut not in regions or lo not in self.index or hi not in self.index or regions[cut].is_empty():
                continue
            cov = np.array(regions[cut].rasterize(self.org, self.step, self.nx, self.ny), dtype=float) \
                / ((size / dbu) ** 2)
            both = (cov > 0) & (self.index[lo] >= 0) & (self.index[hi] >= 0)
            add(self.index[lo][both], self.index[hi][both], (cov[both] / rc).tolist())
        self.G = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))

    def raster(self, reg):
        """Pixel coverage (0..1) of ``reg``, [iy][ix]."""
        return self.np.array(reg.rasterize(self.org, self.step, self.nx, self.ny), dtype=float) / self.pa

    def laplacian(self):
        import scipy.sparse as sp
        deg = self.np.asarray(self.G.sum(axis=1)).ravel()
        return (sp.diags(deg) - self.G).tocsr()

    def nodes_of(self, items):
        out = []
        for lay, reg in items:
            if lay not in self.index:
                out.append(self.np.array([], dtype=self.np.int64))
                continue
            c = self.raster(reg) > 0
            out.append(self.index[lay][c & (self.index[lay] >= 0)])
        return out

    def components(self):
        import scipy.sparse.csgraph as csg
        return csg.connected_components(self.G, directed=False)[1]

    def extent(self):
        bb, d = self.bbox, self.dbu
        return (bb.left * d, bb.right * d, bb.bottom * d, bb.top * d)


def solve(regions, injections, grounds, pixel=0.1, dbu=0.001, tech=SKY130A, want_currents=False):
    """Generic network solve.

    regions:    {layer name: Region (dbu)} for metals and cuts
    injections: {net: [(layer, Region), ...]} one entry per injection site;
                the net's 1 A is shared equally between its sites
    grounds:    {net: [(layer, Region), ...]} held at 0 V
    Returns {"R": {net: ohm}, ...}.
    """
    import numpy as np
    import scipy.sparse.linalg as spla

    mesh = Mesh(regions, pixel, dbu, tech)
    n = mesh.n
    Lap = mesh.laplacian()
    ground_nodes = {}
    for net, items in grounds.items():
        parts = mesh.nodes_of(items)
        ids = np.concatenate(parts) if parts else np.array([], dtype=np.int64)
        if len(ids) == 0:
            raise RonError("the %s pin covers no metal pixel (pixel too coarse?)" % net)
        ground_nodes[net] = np.unique(ids)
    lab = mesh.components()
    comp_net = {}
    for net, ids in ground_nodes.items():
        for c in set(lab[ids].tolist()):
            if c in comp_net and comp_net[c] != net:
                raise RonError("the %s and %s metal touch at this pixel size; use a smaller pixel"
                               % (comp_net[c], net))
            comp_net[c] = net
    I = np.zeros(n)
    sites = {}
    for net, items in injections.items():
        site_ids = mesh.nodes_of(items)
        k = len(site_ids)
        if k == 0:
            raise RonError("no injection site for %s" % net)
        sites[net] = site_ids
        for ids in site_ids:
            if len(ids) == 0:
                raise RonError("an injection site of %s covers no metal pixel (pixel too coarse?)" % net)
            if comp_net.get(lab[ids[0]]) != net:
                raise RonError("an injection site of %s is not connected to its pin" % net)
            I[ids] += 1.0 / k / len(ids)
    keep = np.array([comp_net.get(c) is not None for c in lab])
    fixed = np.zeros(n, dtype=bool)
    for ids in ground_nodes.values():
        fixed[ids] = True
    free = keep & ~fixed
    fi = np.where(free)[0]
    V = np.zeros(n)
    V[fi] = spla.spsolve(Lap[fi][:, fi].tocsc(), I[fi])
    R = {net: float(sum((I[ids] * V[ids]).sum() for ids in site_ids)) for net, site_ids in sites.items()}
    out = {"R": R, "pixel": pixel, "nodes": int(free.sum()), "metals": mesh.metals}
    if want_currents:
        dens = {}
        for m in mesh.metals:
            idx = mesh.index[m]
            vm = np.where(idx >= 0, V[np.maximum(idx, 0)], np.nan)
            g = 1.0 / mesh.rs[m]
            jx = np.zeros(idx.shape)
            jy = np.zeros(idx.shape)
            dx = np.nan_to_num(np.abs(np.diff(vm, axis=1)) * g)
            dy = np.nan_to_num(np.abs(np.diff(vm, axis=0)) * g)
            jx[:, :-1] += dx / 2
            jx[:, 1:] += dx / 2
            jy[:-1, :] += dy / 2
            jy[1:, :] += dy / 2
            # current per um of width (A/um) for 1 A into each net
            dens[m] = np.where(idx >= 0, np.hypot(jx, jy) / pixel, np.nan)
        out["density"] = dens
        out["extent"] = mesh.extent()
    return out


def _squares(w):
    """{"S": [Region of the licon cuts in each S square], "D": [...]}."""
    P, nx, ny = w.P, w.params.nx, w.params.ny
    # licon on diffusion or tap only: the gate's poly contacts in the notches aren't S/D
    active = w.regions.get("diff", db.Region()) + w.regions.get("tap", db.Region())
    lic = w.regions.get("licon", db.Region()) & active
    out = {"S": [], "D": []}
    for i in range(nx):
        for j in range(ny):
            cell = db.Region(db.Box(i * P, j * P, (i + 1) * P, (j + 1) * P))
            cuts = lic & cell
            if cuts.is_empty():
                continue
            out["S" if (i + j) % 2 == 0 else "D"].append(cuts)
    return out


def _pins(w):
    """{"S": [(layer, Region)], "D": [...]} from the FET's labelled pins."""
    out = {"S": [], "D": []}
    lbl = {v: k for k, v in w.pdk["label"].items()}
    for (lay, dt), items in w.texts.items():
        metal = lbl.get((lay, dt))
        if metal is None or metal not in w.pins:
            continue
        for name, x, y in items:
            if name not in out:
                continue
            for p in w.pins[metal].each():
                if p.bbox().contains(db.Point(x, y)):
                    out[name].append((metal, db.Region(p)))
    return out


def ron_metal(params, pixel=0.1, heatmap=None):
    """Metal resistance of a HW_FET (WaffleParams). Returns {"R_S", "R_D",
    "R_contacts", "R_metal", "squares": (n_S, n_D), "nodes", "pixel"}; with
    ``heatmap`` a PNG path, also draws the current density per layer."""
    from .waffle import build
    w = build(params)
    sq = _squares(w)
    pins = _pins(w)
    if not pins["S"] or not pins["D"]:
        raise RonError("the FET has no S and D pins")
    regions = {k: v for k, v in w.regions.items()}
    inj = {net: [("li", reg) for reg in sq[net]] for net in ("S", "D")}
    res = solve(regions, inj, pins, pixel=pixel, want_currents=bool(heatmap))
    kind = w.pdk["devices"][params.device]["kind"]
    rc = SKY130A["licon"][kind]
    cut_area = (SKY130A["licon"]["size"] * 1000) ** 2
    contacts = 0.0
    for net in ("S", "D"):
        k = len(sq[net])
        for reg in sq[net]:
            ncut = reg.area() / cut_area
            contacts += (1.0 / k) ** 2 * rc / ncut
    out = {"R_S": res["R"]["S"], "R_D": res["R"]["D"], "R_contacts": contacts,
           "R_metal": res["R"]["S"] + res["R"]["D"], "squares": (len(sq["S"]), len(sq["D"])),
           "nodes": res["nodes"], "pixel": pixel, "W_total_um": w.report.get("W_total_um")}
    if heatmap:
        _plot(res, heatmap, "%s %dx%d P=%.2f: R_S %.3g, R_D %.3g ohm" % (
            params.device, params.nx, params.ny, w.P / 1000.0, out["R_S"], out["R_D"]))
    return out


def _plot(res, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    ms = res["metals"]
    cols = min(3, len(ms))
    rows = int(math.ceil(len(ms) / float(cols)))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 4 * rows), squeeze=False)
    for k, m in enumerate(ms):
        ax = axes[k // cols][k % cols]
        d = res["density"][m]
        im = ax.imshow(d, origin="lower", extent=res["extent"], cmap="viridis",
                       vmin=0, vmax=np.nanpercentile(d, 99.5) if np.isfinite(d).any() else 1)
        ax.set_title("%s (A/um per A)" % m, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, fraction=0.046)
    for k in range(len(ms), rows * cols):
        axes[k // cols][k % cols].axis("off")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
