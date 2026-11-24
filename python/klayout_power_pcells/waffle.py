"""Hybrid-waffle (HW) power FET, drawn from raw layers.

After Yoo, Chang, Trescases, Ng, "High Performance Low-Voltage Power MOSFETs
with Hybrid Waffle Layout Structure in a 0.25 um Standard CMOS Process",
ISPSD 2008, Fig. 3(a).

The source/drain regions are squares in a checkerboard: square (i, j), centred
at ((i + 1/2) P, (j + 1/2) P), is S when i + j is even and D when it is odd.
A poly grid runs on the square boundaries, so every edge two squares share is
one straight gate segment, with S on one side and D on the other. The
diffusion is one rectangle minus a square notch at every interior poly
crossing: every gate (poly AND diff) is then a plain L-wide rectangle, the
poly crossings lie on field oxide (sky130's poly.11 forbids bends on
diffusion), and the notches leave room for poly contacts that strap the gate
to a met1 mesh. Every square gets the same contact and via stack up to met2;
45 degree runners on the upper metals join the squares of each diagonal,
which are all S or all D, and alternate S and D.

All coordinates are integer nm (database unit 1 nm), on the PDK's grid.
Rule values come from rules.py only.
"""

import math

import klayout.db as db

from .rules import PDKS

STEPS = ("poly", "contacts", "gate", "runners", "bus")   # build order (spec section 8)


class WaffleError(ValueError):
    """Parameters the generator can't draw clean; ``param`` names the culprit."""

    def __init__(self, param, message):
        super().__init__(message)
        self.param = param


def _um(v):
    return v / 1000.0


class WaffleParams:
    """nx, ny: squares per side. P: square pitch, L: gate length, N: notch side
    (um; L and N None = the device minimum and the computed minimum)."""

    def __init__(self, device="nfet_01v8", nx=10, ny=10, P=4.0, L=None, N=None,
                 gate_strap="met1_mesh", runners=("met3", "met4"), runner_style="diag45",
                 bus="L_buses", bus_w=None, guard_ring=True, frame_w=None, pdk="sky130A"):
        self.device, self.nx, self.ny = device, int(nx), int(ny)
        self.P, self.L, self.N = float(P), (None if L is None else float(L)), (None if N is None else float(N))
        self.gate_strap, self.runners, self.runner_style = gate_strap, tuple(runners), runner_style
        self.bus, self.bus_w, self.guard_ring = bus, (None if bus_w is None else float(bus_w)), bool(guard_ring)
        self.frame_w = None if frame_w is None else float(frame_w)
        self.pdk = pdk

    def as_dict(self):
        return dict(device=self.device, nx=self.nx, ny=self.ny, P=self.P, L=self.L, N=self.N,
                    gate_strap=self.gate_strap, runners=",".join(self.runners),
                    runner_style=self.runner_style, bus=self.bus, bus_w=self.bus_w,
                    guard_ring=self.guard_ring, frame_w=self.frame_w, pdk=self.pdk)


class Waffle:
    """The drawn FET: ``regions[layer name]`` (merged db.Region in nm),
    ``texts[(layer, datatype)]`` (list of (string, x, y)), and ``report``."""

    def __init__(self, params, pdk):
        self.params = params
        self.pdk = pdk
        self.regions = {}
        self.texts = {}
        self.pins = {}
        self.report = {}

    def add(self, layer, shapes):
        r = self.regions.setdefault(layer, db.Region())
        r += shapes if isinstance(shapes, db.Region) else db.Region(shapes)
        r.merge()

    def add_pin(self, layer, box):
        self.pins.setdefault(layer, db.Region()).insert(box)

    def write(self, layout, cell):
        for name, reg in self.regions.items():
            if reg.is_empty():
                continue
            cell.shapes(layout.layer(*self.pdk["layers"][name])).insert(reg)
        for name, reg in self.pins.items():
            cell.shapes(layout.layer(*self.pdk["pin"][name])).insert(reg)
        for (lay, dt), items in self.texts.items():
            li = layout.layer(lay, dt)
            for s, x, y in items:
                cell.shapes(li).insert(db.Text(s, db.Trans(x, y)))


# -- helpers -------------------------------------------------------------------------

def _snap_up(v, g):
    return int(math.ceil(v / float(g) - 1e-9)) * g


def _snap_down(v, g):
    return int(math.floor(v / float(g) + 1e-9)) * g


def _box(x1, y1, x2, y2):
    return db.Box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def fill_cuts(region, cut, space, encl_lower, encl_upper=0, grid=5):
    """A centred grid of ``cut`` x ``cut`` squares at ``space`` in each
    polygon of ``region``, keeping only cuts whose square enlarged by
    max(encl_lower, encl_upper) lies fully inside the polygon. The enclosure
    is tested with an axis-aligned square, as Magic measures it, so it also
    holds next to 45 degree edges. Cut positions are on the grid. Returns the
    cuts as a Region."""
    out = db.Region()
    enc = max(encl_lower, encl_upper)
    pitch = cut + space
    src = region.dup()
    src.merge()
    for poly in src.each():
        b = poly.bbox().enlarged(-enc, -enc)
        if b.empty() or b.width() < cut or b.height() < cut:
            continue
        nxc = (b.width() - cut) // pitch + 1
        nyc = (b.height() - cut) // pitch + 1
        x0 = _snap_down(b.left + (b.width() - (nxc - 1) * pitch - cut) // 2, grid)
        y0 = _snap_down(b.bottom + (b.height() - (nyc - 1) * pitch - cut) // 2, grid)
        big = db.Region()
        big.merged_semantics = False
        for ix in range(nxc):
            for iy in range(nyc):
                x, y = x0 + ix * pitch, y0 + iy * pitch
                big.insert(db.Box(x - enc, y - enc, x + cut + enc, y + cut + enc))
        keep = big.inside(db.Region(poly))
        keep.merged_semantics = False
        keep = keep.sized(-enc) if enc else keep
        out += keep
    return out


# -- the generator -----------------------------------------------------------------------

def build(params, steps=STEPS):
    """Draw the FET up to (and including) the named steps; returns a Waffle."""
    p = params
    if p.pdk not in PDKS:
        raise WaffleError("pdk", "unknown PDK %r" % p.pdk)
    pdk = PDKS[p.pdk]
    R = pdk["rules"]
    G = pdk["grid"]
    if p.device not in pdk["devices"]:
        raise WaffleError("device", "device %r is not one of %s" % (p.device, ", ".join(sorted(pdk["devices"]))))
    dev = pdk["devices"][p.device]
    if p.nx < 1 or p.ny < 1 or p.nx * p.ny < 2:
        raise WaffleError("nx", "the array needs at least two squares")
    if p.runner_style != "diag45":
        raise WaffleError("runner_style", "runner_style %r: only diag45 is drawn (the 45 degree runners "
                          "pass both DRC decks, so the staircase fallback isn't needed)" % p.runner_style)
    if p.bus not in ("L_buses", "none"):
        raise WaffleError("bus", "bus must be L_buses or none")

    L = dev["lmin"] if p.L is None else int(round(p.L * 1000))
    if L < dev["lmin"]:
        raise WaffleError("L", "L %.3f um is below the %s minimum %.3f um" % (_um(L), p.device, _um(dev["lmin"])))
    if L % (2 * G):
        raise WaffleError("L", "L %.3f um must be a multiple of %.3f um (its half on the %d nm grid)"
                          % (_um(L), _um(2 * G), G))
    P = int(round(p.P * 1000))
    if P % (2 * G):
        raise WaffleError("P", "P %.3f um must be a multiple of %.3f um" % (_um(P), _um(2 * G)))

    # Notch side: poly crossings on field oxide; with in-array gate contacts,
    # also the poly contact's distance to diffusion.
    n_min = L + 2 * R["poly_diff_s"]
    why = "L + 2 x poly.4"
    if p.gate_strap == "met1_mesh":
        pc = R["licon"] + 2 * R["pcon_diff_s"]
        if dev["kind"] == "p":
            pc = max(pc, R["licon"] + 2 * R["pcon_pdiff_s"])
        if pc > n_min:
            n_min, why = pc, "poly contact + 2 x licon.14"
    elif p.gate_strap != "frame_only":
        raise WaffleError("gate_strap", "gate_strap must be met1_mesh or frame_only")
    n_min = _snap_up(n_min, 2 * G)
    N = n_min if p.N is None else int(round(p.N * 1000))
    if N < n_min:
        raise WaffleError("N", "N %.3f um is below the minimum %.3f um (%s)" % (_um(N), _um(n_min), why))
    if N % (2 * G):
        raise WaffleError("N", "N %.3f um must be a multiple of %.3f um" % (_um(N), _um(2 * G)))
    seg_min = R["diff_w"]
    if P - N < seg_min or P - L < 2 * R["diff_past_gate"]:
        raise WaffleError("P", "P %.3f um is too small for L %.3f and N %.3f um" % (_um(P), _um(L), _um(N)))

    w = Waffle(p, pdk)
    w.L, w.N, w.P = L, N, P
    w.dev = dev
    nx, ny = p.nx, p.ny
    rep = w.report
    rep.update({"nx": nx, "ny": ny, "P_um": _um(P), "L_um": _um(L), "N_um": _um(N), "N_min_um": _um(n_min),
                "N_rule": why, "device": p.device, "model": pdk["model_prefix"] + p.device, "bus": p.bus})

    # -- step 1: diffusion, poly grid, notches, frame ---------------------------------
    diff_box = _box(L // 2, L // 2, nx * P - L // 2, ny * P - L // 2)
    diff = db.Region(diff_box)
    notches = db.Region()
    for k in range(1, nx):
        for l_ in range(1, ny):
            notches.insert(_box(k * P - N // 2, l_ * P - N // 2, k * P + N // 2, l_ * P + N // 2))
    diff -= notches
    w.add("diff", diff)
    w.diff_box = diff_box
    w.notches = notches

    fg = R["poly_past_diff"]                      # interior lines reach the frame: poly.8 overshoot
    pcon_s = R["pcon_pdiff_s"] if dev["kind"] == "p" else R["pcon_diff_s"]
    w.pcon_s = pcon_s
    # the frame holds a row of poly contacts clear of the diffusion (licon.14)
    frame_min = _snap_up(max(R["licon"] + 2 * R["licon_poly_enc1"],
                             pcon_s - fg + R["licon"] + R["licon_poly_enc1"]), 2 * G)
    frame_w = frame_min if p.frame_w is None else int(round(p.frame_w * 1000))
    if frame_w < frame_min:
        raise WaffleError("frame_w", "frame_w %.3f um is below %.3f um" % (_um(frame_w), _um(frame_min)))
    frame_in = diff_box.enlarged(fg, fg)
    frame_out = frame_in.enlarged(frame_w, frame_w)
    poly = db.Region(frame_out) - db.Region(frame_in)
    lines = db.Region()
    for k in range(1, nx):
        lines.insert(_box(k * P - L // 2, frame_in.bottom, k * P + L // 2, frame_in.top))
    for l_ in range(1, ny):
        lines.insert(_box(frame_in.left, l_ * P - L // 2, frame_in.right, l_ * P + L // 2))
    poly += lines
    w.add("poly", poly)
    w.frame_in, w.frame_out, w.frame_w = frame_in, frame_out, frame_w

    _check_gates(w)
    _plan_gate(w)
    if "contacts" in steps:
        _step_contacts(w)
    if "gate" in steps:
        _step_gate(w)
    if "runners" in steps:
        _step_runners(w)
    if "bus" in steps:
        _step_bus(w)
    bb = db.Box()
    for reg in w.regions.values():
        bb += reg.bbox()
    rep["bbox_um"] = [_um(bb.left), _um(bb.bottom), _um(bb.right), _um(bb.top)]
    rep["bbox_area_um2"] = round(bb.area() / 1e6, 3)
    rep["W_per_bbox_area"] = round(w.w_total / (bb.area() / 1e3), 4) if bb.area() else 0.0
    return w


def _square_of(w, x, y):
    return int(x // w.P), int(y // w.P)


def _check_gates(w):
    """Spec section 9: every gate is a plain L-wide rectangle between an S
    and a D square; no poly crossing on diffusion; the count and total W."""
    P, L = w.P, w.L
    nx, ny = w.params.nx, w.params.ny
    gates = w.regions["poly"] & w.regions["diff"]
    gates.merge()
    n_expect = (nx - 1) * ny + nx * (ny - 1)
    polys = list(gates.each())
    assert len(polys) == n_expect, "gate count %d, expected (nx-1)ny + nx(ny-1) = %d" % (len(polys), n_expect)
    w_total = 0
    segs = {}
    for g in polys:
        assert g.is_box(), "gate %s is not a rectangle" % g
        b = g.bbox()
        assert min(b.width(), b.height()) == L, "gate %s is not %d nm long" % (b, L)
        c = b.center()
        if b.width() == L:          # vertical gate on x = kP: squares left and right
            a, d = _square_of(w, c.x - P // 2, c.y), _square_of(w, c.x + P // 2, c.y)
            wseg = b.height()
        else:
            a, d = _square_of(w, c.x, c.y - P // 2), _square_of(w, c.x, c.y + P // 2)
            wseg = b.width()
        assert (sum(a) + sum(d)) % 2 == 1, "gate %s joins two squares of the same net" % b
        w_total += wseg
        segs[wseg] = segs.get(wseg, 0) + 1
    # crossings: where vertical and horizontal lines (and the frame) meet
    vert = db.Region()
    horz = db.Region()
    for k in range(1, nx):
        vert.insert(_box(k * P - L // 2, w.frame_out.bottom, k * P + L // 2, w.frame_out.top))
    for l_ in range(1, ny):
        horz.insert(_box(w.frame_out.left, l_ * P - L // 2, w.frame_out.right, l_ * P + L // 2))
    crossings = (vert & horz)
    assert (crossings & w.regions["diff"]).is_empty(), "a poly crossing lies on diffusion"
    area = w.regions["diff"].area()
    bbox = w.frame_out
    w.report.update({
        "n_gates": len(polys), "W_total_um": _um(w_total), "W_seg_um": {_um(k): v for k, v in sorted(segs.items())},
        "active_area_um2": area / 1e6, "W_per_active_um": w_total / (area / 1e3) if area else 0.0,
        "bbox_area_um2": bbox.area() / 1e6,
    })
    w.gates = gates
    w.w_total = w_total


def _plan_gate(w):
    """The gate strap's geometry, worked out before the squares' contacts so
    those keep clear of it (step 3 draws it): a row of poly contacts in the
    frame with an li ring and a met1 ring over them; with met1_mesh also a
    poly pad, poly contact, li pad and mcon at every notch, and met1 lines
    along every poly line."""
    R = w.pdk["rules"]
    P = w.P
    nx, ny = w.params.nx, w.params.ny
    db_ = w.diff_box
    lc, le1 = R["licon"], R["licon_poly_enc1"]
    fg = R["poly_past_diff"]
    a0 = max(fg + le1, w.pcon_s)                 # contact band, measured out from the diffusion edge
    a1 = fg + w.frame_w - le1
    assert a1 - a0 >= lc, "frame too narrow for its contacts"
    c = _snap_down((a0 + a1) // 2, w.pdk["grid"])  # contact centre line offset
    h = lc // 2
    o = db_.enlarged(c, c)                        # the frame contacts' centre line
    strips = db.Region()
    strips.insert(_box(o.left - h, o.bottom - h, o.right + h, o.bottom + h))
    strips.insert(_box(o.left - h, o.top - h, o.right + h, o.top + h))
    strips.insert(_box(o.left - h, o.bottom + h + R["licon_s"], o.left + h, o.top - h - R["licon_s"]))
    strips.insert(_box(o.right - h, o.bottom + h + R["licon_s"], o.right + h, o.top - h - R["licon_s"]))
    pcon = db.Region()
    for b in strips.each():
        pcon += fill_cuts(db.Region(b), lc, R["licon_s"], 0, grid=w.pdk["grid"])
    # li ring (and met1 ring): a clean band around the contact centre line,
    # enclosing every frame contact by li.5's 0.08 on all sides
    e = h + R["li_enc1"]
    li_ring = db.Region(o.enlarged(e, e)) - db.Region(o.enlarged(-e, -e))
    w.gate_ring_centre, w.gate_ring_half = o, e
    m1 = li_ring.dup()                            # mcon on the li ring; met1 ring = li ring (enc 0.08)
    # mcons on the centre line (a grid over the ring's bounding box would miss
    # a band this narrow)
    mcon = _ring_contacts(w, o, R["mcon"], R["mcon_s"], w.pdk["grid"], corner=R["mcon"] + R["mcon_s"])
    assert mcon.count() >= 4, "no mcon on the gate ring"
    poly_pads = db.Region()
    li_pads = db.Region()
    mesh_w = R["mcon"] + 2 * R["met1_mcon_enc1"]
    if w.params.gate_strap == "met1_mesh":
        pad = lc + 2 * le1
        for k in range(1, nx):
            for l_ in range(1, ny):
                x, y = k * P, l_ * P
                pcon.insert(_box(x - h, y - h, x + h, y + h))
                poly_pads.insert(_box(x - pad // 2, y - pad // 2, x + pad // 2, y + pad // 2))
                li_pads.insert(_box(x - h - R["li_enc1"], y - h - R["li_enc1"], x + h + R["li_enc1"],
                                    y + h + R["li_enc1"]))
                mh = R["mcon"] // 2
                mcon.insert(_box(x - mh, y - mh, x + mh, y + mh))
        assert (poly_pads & w.regions["diff"]).is_empty() and \
            poly_pads.separation_check(w.regions["diff"], R["poly_diff_s"]).is_empty(), \
            "notch poly pads too close to the diffusion"
        ym0, ym1 = o.bottom, o.top
        xm0, xm1 = o.left, o.right
        for k in range(1, nx):
            m1.insert(_box(k * P - mesh_w // 2, ym0, k * P + mesh_w // 2, ym1))
        for l_ in range(1, ny):
            m1.insert(_box(xm0, l_ * P - mesh_w // 2, xm1, l_ * P + mesh_w // 2))
    m1.merge()
    w.gate_pcon = pcon
    w.gate_poly_pads = poly_pads
    w.gate_li = li_ring + li_pads
    w.gate_li.merge()
    w.gate_mcon = mcon
    w.gate_m1 = m1
    # npc: a band over the frame contacts (like the li ring), and a square
    # around each notch contact
    en = h + R["npc_enc"]
    npc = db.Region(o.enlarged(en, en)) - db.Region(o.enlarged(-en, -en))
    notch_pcon = pcon & db.Region(o.enlarged(-en, -en))   # the contacts inside the frame band
    npc += notch_pcon.sized(R["npc_enc"])
    npc.merge()
    assert npc.width_check(R["npc_w"]).is_empty() and npc.space_check(R["npc_s"]).is_empty(), "npc width/spacing"
    w.gate_npc = npc


def _square_sd(w, i, j):
    """The source/drain diffusion of square (i, j): diff minus gates, in its cell."""
    cell = _box(i * w.P, j * w.P, (i + 1) * w.P, (j + 1) * w.P)
    sd = (w.regions["diff"] - w.regions["poly"]) & db.Region(cell)
    sd.merge()
    return sd, cell


def _step_contacts(w):
    """Step 2: implants and wells over the active area, then the same stack
    in every square: licon array, li pad, mcon array, met1 island."""
    R = w.pdk["rules"]
    G = w.pdk["grid"]
    dev = w.dev
    nx, ny = w.params.nx, w.params.ny
    # implants: the source/drain implant over the diffusion (and the notches,
    # so it stays one rectangle)
    sdm = db.Region(w.diff_box.enlarged(R["sdm_enc"], R["sdm_enc"]))
    w.add("nsdm" if dev["kind"] == "n" else "psdm", sdm)
    if dev["kind"] == "p":
        enc = R["nwell_pdiff_enc_mv"] if dev["hv"] else R["nwell_pdiff_enc"]
        w.add("nwell", db.Region(w.diff_box.enlarged(enc, enc)))
    for vt in dev["vt"]:
        w.add(vt, db.Region(w.diff_box.enlarged(R["sdm_enc"], R["sdm_enc"])))
    # contacts per square
    d_gate = max(R["licon_gate_s"], _snap_up((R["li_s"] + 2 * R["li_enc1"] - w.L) / 2.0, G))
    keep_out_li = w.gate_li.sized(R["li_s"])            # square li must stay this far from the gate li
    keep_out_m1 = w.gate_m1.sized(R["met1_s_wide"])
    gates_grown = w.gates.sized(d_gate)
    counts = []
    w.sq_m1 = {}
    for i in range(nx):
        for j in range(ny):
            sd, cell = _square_sd(w, i, j)
            area = sd.sized(-R["licon_diff_enc1"]) - gates_grown - keep_out_li.sized(R["li_enc1"])
            cuts = fill_cuts(area, R["licon"], R["licon_s"], 0, grid=G)
            if cuts.is_empty():
                raise WaffleError("P", "no diffusion contact fits in square (%d, %d)" % (i, j))
            li = db.Region(cuts.bbox().enlarged(R["li_enc1"], R["li_enc1"])) - keep_out_li
            li.merge()
            isl = db.Region(cell.enlarged(-R["met1_s_wide"] // 2, -R["met1_s_wide"] // 2)) - keep_out_m1
            isl.merge()
            mcon = fill_cuts(li & isl.sized(-R["met1_mcon_enc1"]), R["mcon"], R["mcon_s"], 0, grid=G)
            if mcon.is_empty():
                raise WaffleError("P", "no mcon fits in square (%d, %d)" % (i, j))
            w.add("licon", cuts)
            w.add("li", li)
            w.add("mcon", mcon)
            w.add("met1", isl)
            w.sq_m1[(i, j)] = isl
            counts.append(cuts.count())
    w.report["licon_per_square"] = sorted(set(counts))
    _check_cuts(w)


def _check_cuts(w):
    """Spec section 9: no cut outside its enclosures; layers clear of each other."""
    R = w.pdk["rules"]
    r = w.regions
    lic = r["licon"]
    assert (lic - r["diff"].sized(-R["licon_diff_enc"])).is_empty(), "a licon is outside the diffusion enclosure"
    assert (lic & w.gates.sized(R["licon_gate_s"])).is_empty(), "a licon is too close to a gate"
    assert (lic - r["li"]).is_empty(), "a licon is not covered by li"
    assert (r["mcon"] - r["li"]).is_empty(), "an mcon is not covered by li"
    assert (r["mcon"] - r["met1"].sized(-R["met1_mcon_enc"])).is_empty(), "an mcon is outside the met1 enclosure"
    assert r["li"].space_check(R["li_s"]).is_empty(), "li spacing"
    assert r["licon"].space_check(R["licon_s"]).is_empty(), "licon spacing"
    assert r["mcon"].space_check(R["mcon_s"]).is_empty(), "mcon spacing"


def _step_gate(w):
    """Step 3: draw the gate strap planned by _plan_gate."""
    w.add("poly", w.gate_poly_pads)
    w.add("licon", w.gate_pcon)
    w.add("npc", w.gate_npc)
    w.add("li", w.gate_li)
    w.add("mcon", w.gate_mcon)
    w.add("met1", w.gate_m1)
    R = w.pdk["rules"]
    m1 = w.regions["met1"]
    assert m1.space_check(R["met1_s"]).is_empty(), "met1 spacing"
    assert w.regions["li"].space_check(R["li_s"]).is_empty(), "li spacing (gate strap)"


RUNNER_ORDER = ("met3", "met4", "met5")
VIA_BELOW = {"met3": "via2", "met4": "via3", "met5": "via4"}


def _diag(c_lo, c_hi, s_lo, s_hi):
    """The region c_lo <= x - y <= c_hi, s_lo <= x + y <= s_hi (45 degree band
    with square caps); its corners are on the grid when c and s are
    multiples of twice the grid."""
    pts = []
    for c, s_ in ((c_lo, s_lo), (c_hi, s_lo), (c_hi, s_hi), (c_lo, s_hi)):
        assert (c + s_) % 2 == 0
        pts.append(db.Point((c + s_) // 2, (s_ - c) // 2))
    return db.Polygon(pts)


def runner_plan(params, P=None):
    """(layers, delta, spacing) for the diagonal runners; raises WaffleError
    when P is too small for the chosen layers."""
    pdk = PDKS[params.pdk]
    R = pdk["rules"]
    G = pdk["grid"]
    layers = tuple(params.runners)
    if not layers or layers != RUNNER_ORDER[:len(layers)]:
        raise WaffleError("runners", "runners must be met3, met3,met4 or met3,met4,met5 (got %s)"
                          % ",".join(layers))
    P = int(round(params.P * 1000)) if P is None else P
    space = max(R.get(l + "_s_wide", R[l + "_s"]) for l in layers)
    width = max(R[l + "_w"] for l in layers)
    delta = _snap_down(P - math.sqrt(2.0) * space, 4 * G)      # horizontal band width, corners on grid
    if delta / math.sqrt(2.0) < width:
        p_min = _snap_up((width + space) * math.sqrt(2.0), 2 * G)
        raise WaffleError("P", "P %.3f um is too small for runners %s: needs P >= %.3f um "
                          "(width %.2f and spacing %.2f um at 45 degrees)"
                          % (_um(P), ",".join(layers), _um(p_min), _um(width), _um(space)))
    return layers, delta, space


def _step_runners(w):
    """Step 4: via and met2 islands on every square, then the 45 degree
    stripes and, in each square, via2 (and via3/via4) where the square meets
    its own stripe."""
    R = w.pdk["rules"]
    G = w.pdk["grid"]
    P = w.P
    nx, ny = w.params.nx, w.params.ny
    layers, delta, space = runner_plan(w.params, P)
    for (i, j), isl in w.sq_m1.items():
        w.add("met2", isl)
        w.add("via", fill_cuts(isl, R["via"], R["via_s"], R["via_enc1"], R["via_enc1"], grid=G))
    half = delta // 2
    cap = _snap_down(P // 2, 2 * G)
    stripes = {"S": db.Region(), "D": db.Region()}
    w.stripe_of = {}
    w.stripe_defs = []
    w.runner_layers, w.runner_space = layers, space
    for d in range(-(ny - 1), nx):
        sq = [(i, i - d) for i in range(nx) if 0 <= i - d < ny]
        svals = [(i + j + 1) * P for i, j in sq]
        band = db.Region(_diag(d * P - half, d * P + half, min(svals) - cap, max(svals) + cap))
        net = "S" if d % 2 == 0 else "D"
        w.stripe_defs.append((d, net, d * P - half, d * P + half, min(svals) - cap, max(svals) + cap))
        stripes[net] += band
        for ij in sq:
            w.stripe_of[ij] = (d, band)
    for net in stripes:
        stripes[net].merge()
    for lay in layers:
        for net in ("S", "D"):
            w.add(lay, stripes[net])
    # cuts: per square, inside its met2 island and its own stripe
    stack = ("met2",) + layers
    for (i, j), isl in w.sq_m1.items():
        _d, band = w.stripe_of[(i, j)]
        area = isl & band
        for lo, hi in zip(stack[:-1], stack[1:]):
            v = VIA_BELOW[hi]
            cuts = fill_cuts(area, R[v], R[v + "_s"], R[v + "_enc_lo"], R[v + "_enc_hi"], grid=G)
            if cuts.is_empty():
                k = R[v] + 2 * max(R[v + "_enc_lo"], R[v + "_enc_hi"])
                raise WaffleError("P", "no %s fits where square (%d, %d) meets its %s stripe: a %.2f um "
                                  "square must fit in a stripe %.2f um wide; increase P"
                                  % (v, i, j, hi, _um(k), _um(delta) / math.sqrt(2.0)))
            w.add(v, cuts)
    w.stripes = stripes
    w.report.update({"runners": ",".join(layers), "stripe_width_um": round(_um(delta) / math.sqrt(2.0), 3)})
    # spec section 9: S and D never touch, and keep their spacing, on every layer
    sp = stripes["S"].separation_check(stripes["D"], space)
    assert (stripes["S"] & stripes["D"]).is_empty() and sp.is_empty(), "S and D runners too close"
    for v in [VIA_BELOW[l] for l in layers]:
        if v in w.regions:
            assert w.regions[v].space_check(R[v + "_s"]).is_empty(), "%s spacing" % v


BUS_MIN_W = 3200      # buses wider than 3 um: Magic's met3.3c/met4.5a halo stays clean at the junctions


def _ring(inner, width):
    return db.Region(inner.enlarged(width, width)) - db.Region(inner)


def _ring_contacts(w, centre, cut, space, grid, corner):
    """Cuts along the four sides of box ``centre`` (their centre line),
    none within ``corner`` of a corner of the centre line."""
    h = cut // 2
    o = centre
    strips = [_box(o.left + corner, o.bottom - h, o.right - corner, o.bottom + h),
              _box(o.left + corner, o.top - h, o.right - corner, o.top + h),
              _box(o.left - h, o.bottom + corner, o.left + h, o.top - corner),
              _box(o.right - h, o.bottom + corner, o.right + h, o.top - corner)]
    out = db.Region()
    for b in strips:
        out += fill_cuts(db.Region(b), cut, space, 0, grid=grid)
    return out


def _step_bus(w):
    """Step 5: guard ring, perimeter buses, pins and labels."""
    R = w.pdk["rules"]
    G = w.pdk["grid"]
    dev = w.dev
    lay_lbl = w.pdk["label"]
    outer = w.frame_out
    # -- guard ring: p-tap (nfet) or n-tap in the n-well (pfet), li and met1 over it
    if w.params.guard_ring:
        gap = _snap_up(R["met1_s_wide"] + R["li_enc1"] + R["mcon"], 2 * G)   # met1 ring clear of the gate's
        tw = R["licon"] + 2 * R["licon_diff_enc1"]
        t_in = outer.enlarged(gap, gap)
        tap = _ring(t_in, tw)
        w.add("tap", tap)
        centre = t_in.enlarged(tw // 2, tw // 2)
        cuts = _ring_contacts(w, centre, R["licon"], R["licon_s"], G,
                              corner=tw // 2 + R["licon_tap_enc1"] + R["licon"] // 2)
        w.add("licon", cuts)
        e = R["licon"] // 2 + R["li_enc1"]
        li = db.Region(centre.enlarged(e, e)) - db.Region(centre.enlarged(-e, -e))
        w.add("li", li)
        rm = _ring_contacts(w, centre, R["mcon"], R["mcon_s"], G, corner=R["mcon"] + R["mcon_s"])
        assert rm.count() >= 4 and cuts.count() >= 4, "no contacts on the guard ring"
        w.add("mcon", rm)
        w.add("met1", li)
        tap_box = t_in.enlarged(tw, tw)
        w.add("psdm" if dev["kind"] == "n" else "nsdm",
              db.Region(tap_box.enlarged(R["sdm_enc"], R["sdm_enc"])) - db.Region(t_in.enlarged(-R["sdm_enc"], -R["sdm_enc"])))
        if dev["kind"] == "p":
            enc = R["nwell_ntap_enc_mv"] if dev["hv"] else R["nwell_ntap_enc"]
            w.add("nwell", db.Region(tap_box.enlarged(enc, enc)))
        x, y = centre.left, centre.center().y
        w.texts.setdefault(lay_lbl["met1"], []).append(("B", x, y))
        w.add_pin("met1", _box(x - e, y - e, x + e, y + e))
        w.nwell_box = tap_box.enlarged(enc, enc) if dev["kind"] == "p" else None
        outer = tap_box
        w.tap_inner = t_in
    if dev["hv"]:
        # hvi over every thick-oxide diffusion and tap, and over the n-well (nwell.9)
        hb = outer.enlarged(R["sdm_enc"] + R["licon_tap_enc1"], R["sdm_enc"] + R["licon_tap_enc1"])
        nb = getattr(w, "nwell_box", None)
        if nb is not None:
            hb = hb + nb
        w.add("hvi", db.Region(hb))
    # -- gate pin on the met1 ring (left side, mid-height)
    o, e = w.gate_ring_centre, w.gate_ring_half
    gy = _snap_down(o.center().y, G)
    w.texts.setdefault(lay_lbl["met1"], []).append(("G", o.left, gy))
    w.add_pin("met1", _box(o.left - e, gy - e, o.left + e, gy + e))
    # -- runners and buses
    if not hasattr(w, "stripe_defs"):
        return
    layers, space = w.runner_layers, w.runner_space
    top = layers[-1]
    bw = max(BUS_MIN_W, _snap_up(int((w.params.bus_w or 0) * 1000), 2 * G))
    fil = _snap_up(space + 100, 2 * G)
    if w.params.bus == "L_buses":
        g = _snap_up(max(2 * space + 2 * fil, 1000), 2 * G)
        x0, y0, x1, y1 = outer.left, outer.bottom, outer.right, outer.top
        yt_in, xr_in, yt_out, xr_out = y1 + g, x1 + g, y1 + g + bw, x1 + g + bw
        xl_in, yb_in, xl_out, yb_out = x0 - g, y0 - g, x0 - g - bw, y0 - g - bw
        busS = db.Region(_box(x0, yt_in, xr_out, yt_out)) + db.Region(_box(xr_in, y0, xr_out, yt_out))
        busD = db.Region(_box(xl_out, yb_out, xl_in, y1)) + db.Region(_box(xl_out, yb_out, x1, yb_in))
        far = 4 * (abs(x1) + abs(y1) + abs(x0) + abs(y0) + bw + g)
        far += far % 2
        mS, mD = busS.dup(), busD.dup()
        for d, net, cl, cr, s_lo, s_hi in w.stripe_defs:
            if net == "S":
                band = db.Region(_diag(cl, cr, s_lo, far)) & db.Region(_box(-far, -far, xr_out, yt_out))
                mS += band
                jx = cl + yt_in
                if jx < xr_in:
                    mS.insert(db.Polygon([db.Point(jx, yt_in), db.Point(jx - fil, yt_in), db.Point(jx - fil, yt_in - fil)]))
                jy = xr_in - cr
                if jy < yt_in:
                    mS.insert(db.Polygon([db.Point(xr_in, jy), db.Point(xr_in, jy - fil), db.Point(xr_in - fil, jy - fil)]))
            else:
                band = db.Region(_diag(cl, cr, -far, s_hi)) & db.Region(_box(xl_out, yb_out, far, far))
                mD += band
                jx = cr + yb_in
                if jx > xl_in:
                    mD.insert(db.Polygon([db.Point(jx, yb_in), db.Point(jx + fil, yb_in), db.Point(jx + fil, yb_in + fil)]))
                jy = xl_in - cl
                if jy > yb_in:
                    mD.insert(db.Polygon([db.Point(xl_in, jy), db.Point(xl_in, jy + fil), db.Point(xl_in + fil, jy + fil)]))
        mS.merge()
        mD.merge()
        for lay in layers:
            w.regions[lay] = mS + mD
            w.regions[lay].merge()
        assert (mS & mD).is_empty() and mS.separation_check(mD, space).is_empty(), "S and D metal too close"
        sx, sy = (x0 + xr_out) // 2, (yt_in + yt_out) // 2
        dx, dy = (xl_out + x1) // 2, (yb_out + yb_in) // 2
        w.texts.setdefault(lay_lbl[top], []).extend([("S", sx, sy), ("D", dx, dy)])
        hb = bw // 2
        w.add_pin(top, _box(sx - hb, sy - hb, sx + hb, sy + hb))
        w.add_pin(top, _box(dx - hb, dy - hb, dx + hb, dy + hb))
    elif w.params.bus == "none":
        for d, net, cl, cr, s_lo, s_hi in w.stripe_defs:
            cx, cy = (d * w.P + (s_lo + s_hi) // 2) // 2, ((s_lo + s_hi) // 2 - d * w.P) // 2
            w.texts.setdefault(lay_lbl[top], []).append((net, cx, cy))
            pw = R[top + "_w"]
            w.add_pin(top, _box(cx - pw // 2, cy - pw // 2, cx + pw // 2, cy + pw // 2))
    else:
        raise WaffleError("bus", "bus must be L_buses or none")
    _check_latchup(w)


def _check_latchup(w):
    """Report the largest distance from the diffusion to the tap ring
    (Magic's LU.2 and LU.3 want 15 um): the centre of the diffusion is the
    worst point, its distance to the nearest side of the ring."""
    R = w.pdk["rules"]
    t_in = getattr(w, "tap_inner", None)
    if t_in is None:
        w.report["lu_max_um"] = None
        w.report["lu_ok"] = False
        return
    c = w.diff_box.center()
    worst = min(c.x - t_in.left, t_in.right - c.x, c.y - t_in.bottom, t_in.top - c.y)
    w.report["lu_max_um"] = round(_um(worst), 2)
    w.report["lu_ok"] = worst <= R["lu_max"]


def summary(w):
    """Spec section 9's summary line."""
    r = w.report
    lu = r.get("lu_max_um")
    return ("HW %s %dx%d, P %.3f, L %.3f, N %.3f um: %d gates, W_total %.2f um, bbox %.1f um2 "
            "(W/area %.3f um/um2), active %.1f um2, licon/square %s%s"
            % (r["device"], r["nx"], r["ny"], r["P_um"], r["L_um"], r["N_um"], r["n_gates"], r["W_total_um"],
               r["bbox_area_um2"], r["W_per_bbox_area"], r["active_area_um2"],
               "/".join(str(x) for x in r.get("licon_per_square", [])) or "-",
               "" if lu is None else ", diff-to-tap %.1f um%s" % (lu, "" if r.get("lu_ok") else
                                                                  " (Magic LU.2/LU.3 want <= 15)")))


def write_gds(params, path, name="HW_FET", steps=STEPS):
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell(name)
    w = build(params, steps)
    w.write(ly, top)
    ly.write(path)
    return w
