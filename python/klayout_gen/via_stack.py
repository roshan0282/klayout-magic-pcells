"""A via stack between any two metals (roadmap Phase 3.4).

stack(bottom, top, width, height, current_ma, ma_per_cut) returns
{layer name: Region} and a report. Every metal from ``bottom`` to ``top``
is one rectangle; every cut layer between them is the largest array that
fits inside both metals with their enclosures. With a current, each cut
layer needs ceil(I / I_cut) cuts and the stack grows (when width/height
are 0) until it has them; I_cut comes from ``ma_per_cut`` or the PDK's
table (empty for sky130A: see rules.py).
"""

import math

import klayout.db as db

from .rules import PDKS


class StackError(ValueError):
    def __init__(self, msg, param=None):
        super().__init__(msg)
        self.param = param


def _snap_up(v, g):
    return math.ceil(v / g - 1e-9) * g


def _levels(R, bottom, top):
    names = [s[0] for s in R["stack"]]
    if bottom not in names or top not in names:
        raise StackError("metals are %s" % ", ".join(names), "bottom")
    i, j = names.index(bottom), names.index(top)
    if j <= i:
        raise StackError("the top metal must be above the bottom metal", "top")
    return R["stack"][i:j + 1]


def _fit(span, cut, space, enc):
    """How many cuts of ``cut`` at ``space`` fit in ``span`` with ``enc``."""
    room = span - 2 * enc
    if room < cut - 1e-9:
        return 0
    return int((room - cut) // (cut + space) + 1 + 1e-9)


def plan(bottom, top, width=0.0, height=0.0, current_ma=0.0, ma_per_cut=0.0, pdk="sky130A"):
    """(width, height, [(cut layer, nx, ny, cut, space)]) for the stack."""
    R = PDKS[pdk]
    g = R["grid"]
    lv = _levels(R, bottom, top)
    # (cut layer, size, space, enclosure: the larger of the metal below's and above's)
    cuts = [(lv[k][3], lv[k][4], lv[k][5], max(lv[k][6], lv[k][7])) for k in range(len(lv) - 1)]
    # the minimum box: every metal's width and area, and one cut of every layer
    wmin = max(max(l[1] for l in lv), max(c + 2 * e for _, c, _, e in cuts))
    amin = max(l[2] for l in lv)
    need = {}
    if current_ma > 0:
        for name, _, _, _ in cuts:
            per = ma_per_cut or R["em_ma_per_cut"].get(name)
            if not per:
                raise StackError("no EM limit for %s cuts in the PDK table: give the current per cut" % name,
                                 "ma_per_cut")
            need[name] = int(math.ceil(current_ma / per - 1e-9))
    auto = width <= 0 and height <= 0
    w = width if width > 0 else wmin
    h = height if height > 0 else wmin
    if width > 0 and width < wmin - 1e-9 or height > 0 and height < wmin - 1e-9:
        raise StackError("%s to %s needs at least %.3f um" % (bottom, top, wmin), "width")
    while True:
        if w * h < amin - 1e-9:
            if auto:
                w = h = _snap_up(math.sqrt(amin), g)
            else:
                raise StackError("the stack is %.3f um2, %s needs %.3f um2" % (w * h, "a metal", amin), "width")
        arr = [(name, _fit(w, c, s, e), _fit(h, c, s, e), c, s) for name, c, s, e in cuts]
        short = [a for a in arr if a[1] * a[2] < need.get(a[0], 1)]
        if not short:
            return _snap_up(w, g), _snap_up(h, g), arr
        if not auto:
            a = short[0]
            raise StackError("%d %s cuts fit, %d needed for %.3g mA: make the stack larger"
                             % (a[1] * a[2], a[0], need.get(a[0], 1), current_ma), "width")
        w = h = _snap_up(w + max(c + s for _, c, s, _ in cuts) / 2.0, g)


def stack(bottom="met1", top="met2", width=0.0, height=0.0, current_ma=0.0, ma_per_cut=0.0, dbu=0.001,
          pdk="sky130A"):
    """({layer name: Region in dbu}, report)."""
    R = PDKS[pdk]
    w, h, arr = plan(bottom, top, width, height, current_ma, ma_per_cut, pdk)
    lv = _levels(R, bottom, top)
    out = {}
    box = db.DBox(-w / 2, -h / 2, w / 2, h / 2)
    for l in lv:
        out[l[0]] = db.Region(box.to_itype(dbu))
    g = R["grid"]
    for name, nx, ny, c, s in arr:
        boxes = []
        x0 = -((nx - 1) * (c + s)) / 2.0
        y0 = -((ny - 1) * (c + s)) / 2.0
        for i in range(nx):
            for j in range(ny):
                cx = round((x0 + i * (c + s)) / g) * g
                cy = round((y0 + j * (c + s)) / g) * g
                # keep cut edges on the grid
                lx = round((cx - c / 2) / g) * g
                ly = round((cy - c / 2) / g) * g
                boxes.append(db.DBox(lx, ly, lx + c, ly + c).to_itype(dbu))
        out[name] = db.Region(boxes)
    rep = {"width": w, "height": h, "cuts": {n: nx * ny for n, nx, ny, _, _ in arr}}
    return out, rep


def draw(layout, cell, label="", **kw):
    pdk = kw.get("pdk", "sky130A")
    R = PDKS[pdk]
    regs, rep = stack(dbu=layout.dbu, **kw)
    for name, reg in regs.items():
        cell.shapes(layout.layer(*R["layers"][name])).insert(reg)
    if label:
        for m in (kw.get("bottom", "met1"), kw.get("top", "met2")):
            if m + "_label" in R["layers"]:
                cell.shapes(layout.layer(*R["layers"][m + "_label"])).insert(db.DText(label, db.DTrans()))
    return rep
