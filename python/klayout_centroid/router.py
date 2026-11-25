"""Balanced routing of a placed CC_ARRAY of MOS unit cells (KLayout).

Topology (plan/centroid.md, "Routing and dummies"):

* Every grid row gets horizontal met2 tracks running over the whole row:
  D/S tracks over the band of the units' S/D met1 stripes, and one gate
  track over the top row of gate pads and one over the bottom row. A track
  drops a via1 (on a met1 landing pad) only onto the pins of its own net,
  so every unit of a device sees the same track, the same via count and
  the same wire.
* Track order is mirrored on alternate rows (and the two gate tracks
  swap), so no device always gets the outer track.
* Each net has a vertical met3 trunk left of the array; every track of the
  net ends on it with a via2. The trunk ends in a met3 pin and label with
  the net name: ``<dev>_D``, ``<dev>_G``, ``S`` (common source) or
  ``<dev>_S``, and ``DUM``.
* Dummy units get a met1 plate over all their pins (D = G = S, so they are
  off) tied to the source net, or to a ``DUM`` net of their own.

Only MOS units: S/D pins are the met1 shapes over the diffusion, gate pins
the met1 shapes over poly outside it. Two devices per row at most share
the gate tracks; the S/D band must be tall enough for the row's tracks
(the error says how tall).
"""

import collections

import klayout.db as db

from .pattern import PatternError

DUMMY = "dummy"


def _li(layout, key):
    return layout.layer(key[0], key[1])


def _boxes(layout, cell, key):
    li = layout.find_layer(key[0], key[1])
    if li is None:
        return []
    r = db.Region(cell.begin_shapes_rec(li)).merged()
    return [p.bbox().to_dtype(layout.dbu) for p in r.each()]


def analyze_unit(layout, unit, R):
    """Pins of a MOS unit in its own coordinates: {"stripes": [(DBox, "D"|"S")],
    "top": [DBox], "bottom": [DBox], "core": DBox}."""
    met1 = _boxes(layout, unit, R["met1"])
    diff = _boxes(layout, unit, R["diff"])
    poly = _boxes(layout, unit, R["poly"])
    if not met1 or not diff or not poly:
        raise PatternError("routing needs a MOS unit with met1 pins (full_metal), diffusion and poly", "unit")
    dbox = diff[0]
    for d in diff[1:]:
        dbox += d
    stripes, top, bottom = [], [], []
    for b in met1:
        if b.overlaps(dbox):
            stripes.append(b)
        elif any(b.overlaps(p) for p in poly):
            (top if b.center().y > dbox.center().y else bottom).append(b)
    if len(stripes) < 2 or not (top or bottom):
        raise PatternError("routing: the unit has %d S/D stripes and %d gate pads on met1; it needs the "
                           "S/D and gate contacts metallized" % (len(stripes), len(top) + len(bottom)), "unit")
    stripes.sort(key=lambda b: b.center().x)
    # kinds from the unit's port labels (D0, S1, D, S ...), alternating otherwise
    kinds = [None] * len(stripes)
    for key in R["pin_labels"]:
        li = layout.find_layer(key[0], key[1])
        if li is None:
            continue
        for sh in unit.shapes(li).each():
            if not sh.is_text() or sh.text_string[:1] not in "DS":
                continue
            p = sh.dtext.position()
            for i, b in enumerate(stripes):
                if b.contains(p):
                    kinds[i] = sh.text_string[0]
    ref = next((i for i, k in enumerate(kinds) if k), 0)
    k0 = kinds[ref] or "D"
    other = {"D": "S", "S": "D"}
    for i in range(len(stripes)):
        kinds[i] = k0 if (i - ref) % 2 == 0 else other[k0]
    core = met1[0]
    for b in met1[1:]:
        core += b
    return {"stripes": list(zip(stripes, kinds)), "top": top, "bottom": bottom, "core": core}


def _nets(dev, source, tie):
    if dev == DUMMY:
        return {"D": tie, "G": tie, "S": tie}
    return {"D": "%s_D" % dev, "G": "%s_G" % dev, "S": "S" if source == "common" else "%s_S" % dev}


def plan_rows(units, source="common", dummy_tie="S"):
    """{row: {"sd": [net ...], "gate_top": net|None, "gate_bottom": net|None}}
    with the order mirrored on odd rows."""
    if source not in ("common", "separate"):
        raise PatternError("source: common or separate", "route")
    tie = "S" if dummy_tie == "S" else "DUM"
    if tie == "S" and source != "common":
        raise PatternError("dummies can be tied to the source only with a common source", "route")
    rows = collections.defaultdict(list)
    for u in units:
        rows[u["row"]].append(u["device"])
    plan = {}
    for r, devs in sorted(rows.items()):
        act = sorted(set(d for d in devs if d != DUMMY))
        has_dummy = DUMMY in devs
        gates = ["%s_G" % d for d in act]
        if len(gates) > 2:
            raise PatternError("row %d holds %d devices (%s); the router has two gate tracks per row. "
                               "Use more rows or two devices" % (r, len(act), " ".join(act)), "devices")
        drains = ["%s_D" % d for d in act]
        if source == "common":
            srcs = ["S"] if act or (has_dummy and tie == "S") else []
        else:
            srcs = ["%s_S" % d for d in act]
        extra = ["DUM"] if has_dummy and tie == "DUM" else []
        # sources in the middle, drains split around them
        half = (len(drains) + 1) // 2
        sd = drains[:half] + srcs + extra + drains[half:]
        top, bottom = (gates + [None, None])[:2]
        if len(gates) == 1:
            top, bottom = gates[0], None
        if r % 2:
            sd = sd[::-1]
            top, bottom = bottom, top
        plan[r] = {"sd": sd, "gate_top": top, "gate_bottom": bottom}
    return plan


def _track_ys(pins, n, R):
    """Track centres (unit coordinates) for n S/D tracks, or raise."""
    w2, s2 = R["met2_w"], R["met2_s"]
    ph = R["via1_size"] + 2 * R["via1_m1_enc2"]
    y0 = max(b.bottom for b, _ in pins["stripes"])
    y1 = min(b.top for b, _ in pins["stripes"])
    lo, hi = y0 + ph / 2.0, y1 - ph / 2.0
    if pins["top"]:
        gy = sum(b.center().y for b in pins["top"]) / len(pins["top"])
        hi = min(hi, gy - w2 - s2)
    if pins["bottom"]:
        gy = sum(b.center().y for b in pins["bottom"]) / len(pins["bottom"])
        lo = max(lo, gy + w2 + s2)
    pitch = w2 + s2
    need = (n - 1) * pitch
    if n == 0:
        return []
    if hi - lo < need - 1e-9:
        more = need - (hi - lo)
        raise PatternError("the S/D stripes fit %d routing track(s), a row needs %d: make the unit's "
                           "fingers at least %.2f um wider (w)" % (int((hi - lo) / pitch + 1e-9) + 1, n, more),
                           "unit_params")
    c = (lo + hi) / 2.0
    g = 0.005
    return [round((c + (k - (n - 1) / 2.0) * pitch) / g) * g for k in range(n)]


def route(layout, top, unit, units, rules, source="common", dummy_tie="S"):
    """Draw the routing into ``top``. Returns {"nets": [...], "tracks": n,
    "vias1": n, "netlist": [(dev, D, G, S)] per unit}."""
    if not rules or "route" not in rules:
        raise PatternError("no routing rules for this PDK yet", "route")
    R = rules["route"]
    pins = analyze_unit(layout, unit, R)
    plan = plan_rows(units, source, dummy_tie)
    L = {k: _li(layout, R[k]) for k in ("met1", "via1", "met2", "via2", "met3", "met3_label", "met3_pin")}
    v1, e1, e2 = R["via1_size"], R["via1_m1_enc"], R["via1_m1_enc2"]
    w2 = R["met2_w"]
    v2 = R["via2_size"]
    ub = unit.dbbox()
    xl = min(u["origin"].x + ub.left for u in units)
    xr = max(u["origin"].x + ub.right for u in units)
    gy_top = sum(b.center().y for b in pins["top"]) / len(pins["top"]) if pins["top"] else None
    gy_bot = sum(b.center().y for b in pins["bottom"]) / len(pins["bottom"]) if pins["bottom"] else None

    # the nets and their trunks, left of the array (outermost first)
    order = []
    for r in sorted(plan):
        for n in plan[r]["sd"] + [plan[r]["gate_top"], plan[r]["gate_bottom"]]:
            if n and n not in order:
                order.append(n)
    order.sort(key=lambda n: (0 if n in ("S", "DUM") else 1, n))
    tp = R["met3_w"] + R["met3_s"]
    trunk_x = {n: xl - R["trunk_margin"] - (len(order) - 1 - k + 0.5) * tp for k, n in enumerate(order)}
    trunk_x = {n: round(x / 0.005) * 0.005 for n, x in trunk_x.items()}
    trunk_y = collections.defaultdict(list)

    by_row = collections.defaultdict(list)
    for u in units:
        by_row[u["row"]].append(u)
    n_tracks = n_via1 = 0

    def via1(x, y, pw, ph):
        nonlocal n_via1
        top.shapes(L["via1"]).insert(db.DBox(x - v1 / 2, y - v1 / 2, x + v1 / 2, y + v1 / 2))
        top.shapes(L["met1"]).insert(db.DBox(x - pw / 2, y - ph / 2, x + pw / 2, y + ph / 2))
        n_via1 += 1

    for r, row_units in sorted(by_row.items()):
        p = plan[r]
        oy = row_units[0]["origin"].y
        sd_y = dict(zip(p["sd"], _track_ys(pins, len(p["sd"]), R)))
        tracks = [(n, y) for n, y in sd_y.items()]
        if p["gate_top"]:
            tracks.append((p["gate_top"], gy_top))
        if p["gate_bottom"]:
            tracks.append((p["gate_bottom"], gy_bot))
        for net, y in tracks:
            if y is None:
                raise PatternError("the unit has no gate pads on that side for %s" % net, "unit")
            yy = oy + y
            x0 = trunk_x[net] - v2 / 2 - R["via2_m2_enc2"]
            top.shapes(L["met2"]).insert(db.DBox(x0, yy - w2 / 2, xr, yy + w2 / 2))
            top.shapes(L["via2"]).insert(db.DBox(trunk_x[net] - v2 / 2, yy - v2 / 2, trunk_x[net] + v2 / 2,
                                                 yy + v2 / 2))
            trunk_y[net].append(yy)
            n_tracks += 1
        for u in row_units:
            o = u["origin"]
            nets = _nets(u["device"], source, "S" if dummy_tie == "S" else "DUM")
            if u["device"] == DUMMY:
                top.shapes(L["met1"]).insert(pins["core"].moved(o))
                y = sd_y[nets["S"]]
                for b, _ in pins["stripes"]:
                    via1(o.x + b.center().x, o.y + y, v1 + 2 * e1, v1 + 2 * e2)
                continue
            for b, kind in pins["stripes"]:
                y = sd_y[nets[kind]]
                via1(o.x + b.center().x, o.y + y, v1 + 2 * e1, v1 + 2 * e2)
            for side, net in (("top", p["gate_top"]), ("bottom", p["gate_bottom"])):
                if net != nets["G"]:
                    continue
                for b in pins[side]:
                    via1(o.x + b.center().x, o.y + b.center().y, max(b.width(), v1 + 2 * e2), v1 + 2 * e1)
    # trunks with a pin and label at the top
    wt = R["met3_w"]
    ext = v2 / 2 + 0.1
    for net in order:
        ys = trunk_y[net]
        x = trunk_x[net]
        y0, y1 = min(ys) - ext, max(ys) + ext + wt
        top.shapes(L["met3"]).insert(db.DBox(x - wt / 2, y0, x + wt / 2, y1))
        top.shapes(L["met3_pin"]).insert(db.DBox(x - wt / 2, y1 - wt, x + wt / 2, y1))
        top.shapes(L["met3_label"]).insert(db.DText(net, db.DTrans(db.DVector(x, y1 - wt / 2))))
    netlist = []
    for u in units:
        n = _nets(u["device"], source, "S" if dummy_tie == "S" else "DUM")
        netlist.append((u["device"], n["D"], n["G"], n["S"]))
    return {"nets": order, "tracks": n_tracks, "vias1": n_via1, "netlist": netlist,
            "fingers": [k for _, k in pins["stripes"]]}


def reference_spice(name, route_info, model, w, l, nf, body="VSUBS", body_pin=False):
    """A SPICE subcircuit with one device per finger of every unit, for
    netgen (which merges the parallel fingers). The body is an internal net
    (the substrate of tapless units) unless ``body_pin``."""
    pins = list(route_info["nets"]) + ([body] if body_pin else [])
    lines = [".subckt %s %s" % (name, " ".join(pins))]
    k = 0
    kinds = route_info["fingers"]
    for dev, d, g, s in route_info["netlist"]:
        net = {"D": d, "S": s}
        for f in range(nf):
            a, b = net[kinds[f]], net[kinds[f + 1]]
            lines.append("XM%d %s %s %s %s %s w=%g l=%g" % (k, a, g, b, body, model, w, l))
            k += 1
    lines.append(".ends")
    return "\n".join(lines) + "\n"
