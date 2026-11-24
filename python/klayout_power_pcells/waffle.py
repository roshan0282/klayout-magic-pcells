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
# S/D runners on the upper metals:
#   diag45     45 degree stripes, one per diagonal of squares (all S or all D)
#   staircase  the same stripes drawn with 0/90 degree steps only
#   planes     0/90 only: the runner layers alternate S, D (, S) as plates,
#              with islands in holes where the other net's via stack passes
RUNNER_STYLES = ("diag45", "staircase", "planes")


class WaffleError(ValueError):
    """Parameters the generator can't draw clean; ``param`` names the culprit."""

    def __init__(self, param, message):
        super().__init__(message)
        self.param = param


def _um(v):
    return v / 1000.0


class WaffleParams:
    """nx, ny: squares per side. P: square pitch, L: gate length, N: notch side
    (um; L and N None = the device minimum and the computed minimum).
    source_taps: a body tap in every source square, tied to S (body = S);
    tap_w its side (None = the smallest that holds a contact).
    deep_nwell: p-LDMOS only (pfet_g5v0d16v0): a deep n-well under the
    array, so the drift regions (holes in the n-well, where the drains sit)
    are p-wells isolated from the substrate; without it every drain is on
    the substrate.
    bottom_net: planes only: the net on met3 (S or D); the runner layers
    then alternate, e.g. D on met3, S on met4."""

    def __init__(self, device="nfet_01v8", nx=10, ny=10, P=4.0, L=None, N=None,
                 gate_strap="met1_mesh", runners=("met3", "met4"), runner_style="diag45",
                 bus="L_buses", bus_w=None, guard_ring=True, frame_w=None, pdk="sky130A",
                 source_taps=True, tap_w=None, deep_nwell=True, bottom_net="S"):
        self.device, self.nx, self.ny = device, int(nx), int(ny)
        self.P, self.L, self.N = float(P), (None if L is None else float(L)), (None if N is None else float(N))
        self.gate_strap, self.runners, self.runner_style = gate_strap, tuple(runners), runner_style
        self.bus, self.bus_w, self.guard_ring = bus, (None if bus_w is None else float(bus_w)), bool(guard_ring)
        self.frame_w = None if frame_w is None else float(frame_w)
        self.pdk = pdk
        self.source_taps = bool(source_taps)
        self.tap_w = None if tap_w is None else float(tap_w)
        self.deep_nwell = bool(deep_nwell)
        self.bottom_net = bottom_net

    def as_dict(self):
        return dict(device=self.device, nx=self.nx, ny=self.ny, P=self.P, L=self.L, N=self.N,
                    gate_strap=self.gate_strap, runners=",".join(self.runners),
                    runner_style=self.runner_style, bus=self.bus, bus_w=self.bus_w,
                    guard_ring=self.guard_ring, frame_w=self.frame_w, pdk=self.pdk,
                    source_taps=self.source_taps, tap_w=self.tap_w, deep_nwell=self.deep_nwell,
                    bottom_net=self.bottom_net)


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


def ld_bridge_q(R):
    """Side of the squares whose convex hull joins two diagonal drift
    n-wells through a notch: the hull is then sqrt(2) q >= nwell.1 wide."""
    return _snap_up(R["nwell_w"] / math.sqrt(2.0), 5)


def _octagon(b, c):
    """Box b with its corners cut at 45 degrees, legs c."""
    return db.Polygon([db.Point(b.left + c, b.bottom), db.Point(b.right - c, b.bottom),
                       db.Point(b.right, b.bottom + c), db.Point(b.right, b.top - c),
                       db.Point(b.right - c, b.top), db.Point(b.left + c, b.top),
                       db.Point(b.left, b.top - c), db.Point(b.left, b.bottom + c)])


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
    if p.runner_style not in RUNNER_STYLES:
        raise WaffleError("runner_style", "runner_style %r is not one of %s"
                          % (p.runner_style, ", ".join(RUNNER_STYLES)))
    if p.bus not in ("L_buses", "none"):
        raise WaffleError("bus", "bus must be L_buses or none")
    if p.bottom_net not in ("S", "D"):
        raise WaffleError("bottom_net", "bottom_net must be S or D")

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
    ld = bool(dev.get("ld"))
    if ld:
        # extended drain: the source diffusion reaches a = L/2 - underlap past
        # its square's edge; diagonal source diffusions keep the MV spacing
        # across a notch, and (n) the drift n-well joining two diagonal D
        # squares through the notch keeps diff/tap.24 from the source n+
        a = L // 2 - R["ld_underlap"]
        c = 2 * (a + R["diff_s_mv"] / math.sqrt(2.0))
        if c > n_min:
            n_min, why = c, "MV diffusion spacing across the notch (diff/tap.15a)"
        # the gate strips over the drift side make every gate the full L
        # wide, so the ends of two gates meet across a notch corner
        c = L + math.sqrt(2.0) * R["diff_s_mv"]
        if c > n_min:
            n_min, why = c, "gate ends across a notch corner (diff/tap.15a)"
        if dev["kind"] == "n":
            c = 2 * (R["ndiff_nwell_s_mv"] * math.sqrt(2.0) + ld_bridge_q(R) - L / 2.0)
            if c > n_min:
                n_min, why = c, "drift n-well bridge to the source n+ (diff/tap.24)"
    n_min = _snap_up(n_min, 2 * G)
    n_fixed = None
    if ld and dev["kind"] == "n":
        # Magic regenerates HVNTM (0.185 um around the gates, then bridged to
        # 0.7 um) and flags its own result at a notch corner unless the two
        # gate ends' implants there just meet: N = L + 4 x 0.185
        n_fixed = L + 4 * R["hvntm_enc"]
        assert n_fixed >= n_min
        n_min, why = n_fixed, "set by Magic's HVNTM at the notch corners (hvntm.2): N = L + 4 x 0.185"
    N = n_min if p.N is None else int(round(p.N * 1000))
    if n_fixed is not None and N != n_fixed:
        raise WaffleError("N", "N %.3f um: for %s, N is L + 4 x 0.185 = %.3f um (leave N at 0); other values "
                          "make Magic's regenerated HVNTM fail hvntm.2 at the notch corners"
                          % (_um(N), p.device, _um(n_fixed)))
    if N < n_min:
        raise WaffleError("N", "N %.3f um is below the minimum %.3f um (%s)" % (_um(N), _um(n_min), why))
    if N % (2 * G):
        raise WaffleError("N", "N %.3f um must be a multiple of %.3f um" % (_um(N), _um(2 * G)))
    seg_min = R["diff_w"]
    if P - N < seg_min or P - L < 2 * R["diff_past_gate"]:
        raise WaffleError("P", "P %.3f um is too small for L %.3f and N %.3f um" % (_um(P), _um(L), _um(N)))
    if ld:
        if P - N < R["ld_wmin"]:
            raise WaffleError("P", "P %.3f um gives gates %.3f um wide; %s needs W >= %.3f um per gate "
                              "(denmos.2/depmos.2): P >= %.3f um" % (_um(P), _um(P - N), p.device,
                                                                    _um(R["ld_wmin"]), _um(R["ld_wmin"] + N)))
        drift = R["ld_drift_n"] if dev["kind"] == "n" else R["ld_drift_p"]
        td = P - L - 2 * (drift - R["ld_underlap"])          # the drain tap in the middle of a D square
        td_min = R["licon"] + 2 * R["licon_tap_enc1"]
        if td < td_min:
            raise WaffleError("P", "P %.3f um leaves no room for the drain tap: %s's drift is %.3f um on "
                              "each side; P >= %.3f um" % (_um(P), p.device, _um(drift),
                                                          _um(td_min + L + 2 * (drift - R["ld_underlap"]))))

    if ld and dev["kind"] == "p" and p.deep_nwell and not p.guard_ring:
        raise WaffleError("deep_nwell", "the deep n-well needs the guard ring: its n-well rings the deep n-well "
                          "(turn the guard ring on, or deep_nwell off and the drains on the substrate)")

    w = Waffle(p, pdk)
    w.L, w.N, w.P = L, N, P
    w.dev = dev
    nx, ny = p.nx, p.ny
    rep = w.report
    w.ld = ld
    rep.update({"nx": nx, "ny": ny, "P_um": _um(P), "L_um": _um(L), "N_um": _um(N), "N_min_um": _um(n_min),
                "N_rule": why, "device": p.device, "model": pdk["model_prefix"] + p.device, "bus": p.bus,
                # S and D each one net in the cell (stripes alone are separate nets)
                "sd_joined": p.bus == "L_buses" or p.runner_style == "planes",
                "body": "S" if p.source_taps else ("B" if p.guard_ring else None)})

    # -- step 1: diffusion, poly grid, notches, frame ---------------------------------
    diff_box = _box(L // 2, L // 2, nx * P - L // 2, ny * P - L // 2)
    diff = db.Region(diff_box)
    notches = db.Region()
    for k in range(1, nx):
        for l_ in range(1, ny):
            notches.insert(_box(k * P - N // 2, l_ * P - N // 2, k * P + N // 2, l_ * P + N // 2))
    w.drain_taps = db.Region()
    if ld:
        # the source squares' diffusion stops 'underlap' short of the far
        # side of each gate; the D squares are drift regions around a tap
        a = L // 2 - R["ld_underlap"]
        diff = db.Region()
        for i in range(nx):
            for j in range(ny):
                cell = _box(i * P, j * P, (i + 1) * P, (j + 1) * P)
                if (i + j) % 2 == 0:
                    diff.insert(cell.enlarged(a, a) & diff_box)
                else:
                    h = td // 2
                    cx, cy = i * P + P // 2, j * P + P // 2
                    w.drain_taps.insert(_box(cx - h, cy - h, cx + h, cy + h))
        diff.merge()
        rep.update({"ld": True, "drift_um": _um(drift), "drain_tap_um": _um(td)})
    diff -= notches
    # body taps: an island in the middle of every source square, in a hole in
    # the diffusion, field oxide between them (difftap.3, and room for both
    # implants' 0.125 enclosures)
    w.taps_sq = db.Region()
    if p.source_taps:
        T = _snap_up(R["licon"] + 2 * R["licon_tap_enc1"], 2 * G) if p.tap_w is None \
            else int(round(p.tap_w * 1000))
        if T < R["licon"] + 2 * R["licon_tap_enc1"] or T % (2 * G):
            raise WaffleError("tap_w", "tap_w %.3f um must hold a contact (>= %.3f um) and be a multiple of %.3f um"
                              % (_um(T), _um(R["licon"] + 2 * R["licon_tap_enc1"]), _um(2 * G)))
        gap = _snap_up(max(R["diff_tap_s_mv"] if dev["hv"] else R["diff_s"], 2 * R["sdm_enc"]), G)
        hh = T // 2 + gap
        ring_w = P // 2 - L // 2 - hh                 # diffusion left between the hole and a gate
        if ring_w < R["diff_past_gate"] + R["licon"] + 2 * R["licon_diff_enc1"]:
            raise WaffleError("tap_w", "a %.3f um tap leaves %.3f um of diffusion between it and the gates; "
                              "use a smaller tap_w or a larger P" % (_um(T), _um(ring_w)))
        holes = db.Region()
        for i in range(nx):
            for j in range(ny):
                if (i + j) % 2 == 0:
                    cx, cy = i * P + P // 2, j * P + P // 2
                    holes.insert(_box(cx - hh, cy - hh, cx + hh, cy + hh))
                    w.taps_sq.insert(_box(cx - T // 2, cy - T // 2, cx + T // 2, cy + T // 2))
        diff -= holes
        w.tap_w_nm = T
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
        lg = L - w.pdk["rules"]["ld_underlap"] if w.ld else L    # LDMOS: the diffusion stops short of the drain side
        assert min(b.width(), b.height()) == lg, "gate %s is not %d nm long" % (b, lg)
        c = b.center()
        if b.width() == lg:         # vertical gate on x = kP: squares left and right
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
    tap_sdm = w.taps_sq.sized(R["sdm_enc"])
    w.add("nsdm" if dev["kind"] == "n" else "psdm", sdm - tap_sdm)
    if not w.taps_sq.is_empty():
        w.add("tap", w.taps_sq)
        w.add("psdm" if dev["kind"] == "n" else "nsdm", tap_sdm)
    if dev["kind"] == "p":
        enc = R["nwell_pdiff_enc_mv"] if dev["hv"] else R["nwell_pdiff_enc"]
        w.add("nwell", db.Region(w.diff_box.enlarged(enc, enc)))
    for vt in dev["vt"]:
        w.add(vt, db.Region(w.diff_box.enlarged(R["sdm_enc"], R["sdm_enc"])))
    if dev["kind"] == "n" and dev["hv"]:
        # the MV n tip implant (Magic generates it on GDS output; a GDS taken
        # straight to the fab needs it drawn): over the active area, clear of
        # every p-tap by 0.185
        hv = db.Region(w.diff_box.enlarged(R["hvntm_enc"], R["hvntm_enc"])) - w.taps_sq.sized(R["hvntm_enc"])
        hv.merge()
        assert hv.width_check(R["hvntm_w"]).is_empty() and hv.space_check(R["hvntm_w"]).is_empty(), "hvntm"
        w.add("hvntm", hv)
    if w.ld:
        _ld_drift(w)
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
            enc = R["licon_diff_enc1"]
            if w.ld and (i + j) % 2:
                sd, enc = w.drain_taps & db.Region(cell), R["licon_tap_enc1"]     # the drain tap
            area = sd.sized(-enc) - gates_grown - keep_out_li.sized(R["li_enc1"])
            cuts = fill_cuts(area, R["licon"], R["licon_s"], 0, grid=G)
            if cuts.is_empty():
                raise WaffleError("P", "no diffusion contact fits in square (%d, %d)" % (i, j))
            tap = w.taps_sq & db.Region(cell)
            if not tap.is_empty():
                tcuts = fill_cuts(tap, R["licon"], R["licon_s"], R["licon_tap_enc1"], grid=G)
                assert not tcuts.is_empty(), "no contact on the tap of square (%d, %d)" % (i, j)
                cuts += tcuts                           # under the square's li: body tied to S
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


def _ld_drift(w):
    """Extended drain: the drain taps, the EDID marker over every D square
    (up to the source diffusion's edge under the gates, without the
    notches), and the drift region: for an n-LDMOS an n-well per D square,
    reaching under the gates past the diffusion edge, joined to its
    diagonal neighbours through the notches (nwell.8 wants HV n-wells 2 um
    apart); for a p-LDMOS a hole in the n-well per D square, corners cut so
    the n-well between diagonal holes stays nwell.1 wide."""
    R = w.pdk["rules"]
    P, L, N = w.P, w.L, w.N
    nx, ny = w.params.nx, w.params.ny
    a = L // 2 - R["ld_underlap"]
    w.add("tap", w.drain_taps)
    edid = db.Region()
    dcells = []
    for i in range(nx):
        for j in range(ny):
            if (i + j) % 2:
                cell = _box(i * P, j * P, (i + 1) * P, (j + 1) * P)
                dcells.append(cell)
                edid.insert(cell.enlarged(a, a) & w.diff_box)
    edid -= w.notches
    w.add("edid", edid)
    if w.dev["kind"] == "n":
        s_ = a - R["ld_n_well_past_diff"]          # the well's edge inside a D square's edge
        assert s_ > 0
        well = db.Region()
        for cell in dcells:
            well.insert(cell.enlarged(-s_, -s_))
        q = ld_bridge_q(R)
        for k in range(1, nx):
            for l_ in range(1, ny):
                X, Y = k * P, l_ * P
                sgn = 1 if (k + l_) % 2 == 0 else -1    # D squares upper left / lower right, or the other two
                A = _box(X + s_, Y - sgn * s_, X + s_ + q, Y - sgn * (s_ + q))
                B = _box(X - s_, Y + sgn * s_, X - s_ - q, Y + sgn * (s_ + q))
                pts = [db.Point(x, y) for b in (A, B) for x in (b.left, b.right) for y in (b.bottom, b.top)]
                well.insert(_hull(pts))
        well.merge()
        w.add("nwell", well)
        w.ld_holes = None
    else:
        s_ = a - R["ld_p_hole_past_diff"]
        assert s_ > 0
        c = max(0, _snap_up(R["nwell_w"] / math.sqrt(2.0) - 2 * s_, w.pdk["grid"]))
        assert s_ + c < N // 2, "the holes' cut corners reach the gates"
        holes = db.Region()
        for cell in dcells:
            holes.insert(_octagon(cell.enlarged(-s_, -s_), c))
        holes.merge()
        w.ld_holes = holes
        w.regions["nwell"] = w.regions["nwell"] - holes


def _hull(pts):
    """Convex hull of points (monotone chain), as a polygon."""
    pts = sorted(set((p.x, p.y) for p in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p_ in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p_) <= 0:
            lower.pop()
        lower.append(p_)
    for p_ in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p_) <= 0:
            upper.pop()
        upper.append(p_)
    return db.Polygon([db.Point(x, y) for x, y in lower[:-1] + upper[:-1]])


def _check_cuts(w):
    """Spec section 9: no cut outside its enclosures; layers clear of each other."""
    R = w.pdk["rules"]
    r = w.regions
    lic = r["licon"]
    active = r["diff"] + r.get("tap", db.Region())
    assert (lic - active.sized(-R["licon_diff_enc"])).is_empty(), "a licon is outside the diffusion enclosure"
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
DIAG_MAX_W = 3000     # wide-metal threshold (m3.3cd, m4.5ab): diag45 stripes stay below it
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


def _stair(cl, cr, s_lo, s_hi, width, grid):
    """The band of _diag drawn with 0/90 degree edges only: squares of side
    b = (cr - cl) / 2 centred on the band's centre line, stepped along it so
    that neighbours overlap by at least ``width``. The squares lie inside the
    45 degree band, so its spacing to the next band holds for the steps too.
    The steps sit on one lattice of x + y (multiples of the step), the same
    for every stripe and for a stripe redrawn longer into its bus, so all
    staircases have the same steps; only the two end squares are off it."""
    c = (cl + cr) // 2
    b = _snap_down((cr - cl) // 2, 2 * grid)
    h = _snap_down(min(b, 2 * (b - width)), 2 * grid)      # step of x + y; overlap b - h / 2 >= width
    assert h > 0, "staircase squares narrower than the metal width"
    lo, hi = s_lo + b, s_hi - b
    if hi < lo:
        lo = hi = _snap_down((s_lo + s_hi) // 2, 2 * grid)
    sigs = [lo]
    k = -(-lo // h) * h                                      # first lattice point >= lo
    while k < hi:
        if k > lo:
            sigs.append(k)
        k += h
    if hi > lo:
        sigs.append(hi)
    out = db.Region()
    for sig in sigs:
        x, y = (c + sig) // 2, (sig - c) // 2
        out.insert(_box(x - b // 2, y - b // 2, x + b // 2, y + b // 2))
    out.merge()
    return out


def _band(w, cl, cr, s_lo, s_hi):
    """A runner stripe in the FET's runner style (diag45 or staircase)."""
    if w.params.runner_style == "staircase":
        return _stair(cl, cr, s_lo, s_hi, w.runner_width, w.pdk["grid"])
    return db.Region(_diag(cl, cr, s_lo, s_hi))


def _close(region, r):
    """Fill notches and gaps narrower than 2r (Manhattan stays Manhattan)."""
    out = region.sized(r).sized(-r)
    out.merge()
    return out


def runner_plan(params, P=None):
    """(layers, delta, spacing) for the runners; raises WaffleError when P
    is too small for the chosen layers and style. delta is the stripes'
    horizontal width (diag45, staircase) or the margin between a square's
    edge and its island (planes)."""
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
    if params.runner_style == "planes":
        if len(layers) < 2:
            raise WaffleError("runners", "planes need two runner layers or more (S on met3, D on met4): "
                              "use met3,met4 or met3,met4,met5")
        # islands sit in holes of the layers below the top; the plane keeps a
        # neck of a metal width between the holes of diagonal neighbours
        holed = layers[:-1]
        margin = _snap_up(max(R.get(l + "_s_wide", R[l + "_s"]) + R[l + "_w"] for l in holed), G)
        need = max(R[VIA_BELOW[l]] + 2 * max(R[VIA_BELOW[l] + "_enc_lo"], R[VIA_BELOW[l] + "_enc_hi"])
                   for l in layers)
        if P - 2 * margin < need:
            raise WaffleError("P", "P %.3f um is too small for planes on %s: an island %.2f um wide must "
                              "hold a %.2f um via with its enclosures (needs P >= %.3f um)"
                              % (_um(P), ",".join(layers), _um(P - 2 * margin), _um(need),
                                 _um(_snap_up(need + 2 * margin, 2 * G))))
        return layers, margin, space
    delta = _snap_down(P - math.sqrt(2.0) * space, 4 * G)      # horizontal band width, corners on grid
    if params.runner_style == "diag45":
        # 45 degree stripes stay under 3 um wide: wider, Magic's met3.3c /
        # met4.5a halo of large metal flags their square caps (P >= 6.6)
        delta = min(delta, _snap_down((DIAG_MAX_W - 1) * math.sqrt(2.0), 4 * G))
    ok = delta / math.sqrt(2.0) >= width
    if params.runner_style == "staircase":
        ok = ok and _snap_down(delta // 2, 2 * G) > width
    if not ok:
        k = 2.0 if params.runner_style == "staircase" else math.sqrt(2.0)
        p_min = _snap_up(width * k + space * math.sqrt(2.0) + 4 * G, 2 * G)
        raise WaffleError("P", "P %.3f um is too small for %s runners on %s: needs about P >= %.3f um "
                          "(width %.2f and spacing %.2f um)"
                          % (_um(P), params.runner_style, ",".join(layers), _um(p_min), _um(width), _um(space)))
    return layers, delta, space


def _step_runners(w):
    """Step 4: via and met2 islands on every square, then the runners in
    their style, with via2 (and via3/via4) in each square where it meets
    its own net's metal."""
    R = w.pdk["rules"]
    G = w.pdk["grid"]
    nx, ny = w.params.nx, w.params.ny
    layers, delta, space = runner_plan(w.params, w.P)
    w.runner_layers, w.runner_space = layers, space
    w.runner_width = max(R[l + "_w"] for l in layers)
    for (i, j), isl in w.sq_m1.items():
        w.add("met2", isl)
        w.add("via", fill_cuts(isl, R["via"], R["via_s"], R["via_enc1"], R["via_enc1"], grid=G))
    if w.params.runner_style == "planes":
        _runner_planes(w, layers, delta)
    else:
        _runner_stripes(w, layers, delta, space)
    for v in [VIA_BELOW[l] for l in layers]:
        if v in w.regions:
            assert w.regions[v].space_check(R[v + "_s"]).is_empty(), "%s spacing" % v


def _vias(w, i, j, area, stack):
    """The via arrays of square (i, j) between consecutive layers of
    ``stack`` (from met2 up), all inside ``area``."""
    R = w.pdk["rules"]
    for lo, hi in zip(stack[:-1], stack[1:]):
        v = VIA_BELOW[hi]
        cuts = fill_cuts(area, R[v], R[v + "_s"], R[v + "_enc_lo"], R[v + "_enc_hi"], grid=w.pdk["grid"])
        if cuts.is_empty():
            k = R[v] + 2 * max(R[v + "_enc_lo"], R[v + "_enc_hi"])
            raise WaffleError("P", "no %s fits where square (%d, %d) meets its %s %s: a %.2f um square "
                              "must fit; increase P" % (v, i, j, hi, w.params.runner_style, _um(k)))
        w.add(v, cuts)


def _runner_stripes(w, layers, delta, space):
    """diag45 and staircase: one stripe per diagonal of squares."""
    P = w.P
    nx, ny = w.params.nx, w.params.ny
    half = delta // 2
    cap = _snap_down(P // 2, 2 * w.pdk["grid"])
    stripes = {"S": db.Region(), "D": db.Region()}
    w.stripe_of = {}
    w.stripe_defs = []
    for d in range(-(ny - 1), nx):
        sq = [(i, i - d) for i in range(nx) if 0 <= i - d < ny]
        svals = [(i + j + 1) * P for i, j in sq]
        band = _band(w, d * P - half, d * P + half, min(svals) - cap, max(svals) + cap)
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
    stack = ("met2",) + layers
    for (i, j), isl in w.sq_m1.items():
        _d, band = w.stripe_of[(i, j)]
        _vias(w, i, j, isl & band, stack)
    w.stripes = stripes
    w.report.update({"runners": ",".join(layers), "runner_style": w.params.runner_style,
                     "stripe_width_um": round(_um(delta) / math.sqrt(2.0), 3)})
    # spec section 9: S and D never touch, and keep their spacing, on every layer
    sp = stripes["S"].separation_check(stripes["D"], space)
    assert (stripes["S"] & stripes["D"]).is_empty() and sp.is_empty(), "S and D runners too close"


def _runner_planes(w, layers, margin):
    """planes: the runner layers alternate S, D, S (or D, S, D with
    bottom_net D) from met3 up. On each
    layer the owner's plane has a hole, with an island in it, over every
    square of the other net whose stack goes higher."""
    R = w.pdk["rules"]
    P = w.P
    nx, ny = w.params.nx, w.params.ny
    other = {"S": "D", "D": "S"}
    net_of = {lay: (w.params.bottom_net if k % 2 == 0 else other[w.params.bottom_net])
              for k, lay in enumerate(layers)}
    top_of = {n: max(k for k, lay in enumerate(layers) if net_of[lay] == n) for n in ("S", "D")}
    w.plane_net, w.plane_holes = net_of, {lay: db.Region() for lay in layers}
    w.plane_islands = {lay: db.Region() for lay in layers}
    for (i, j), isl in w.sq_m1.items():
        net = "S" if (i + j) % 2 == 0 else "D"
        cell = _box(i * P, j * P, (i + 1) * P, (j + 1) * P)
        ib = cell.enlarged(-margin, -margin)
        stack = ("met2",) + layers[:top_of[net] + 1]
        for lay in stack[1:-1]:
            if net_of[lay] != net:
                sp = R.get(lay + "_s_wide", R[lay + "_s"])
                w.plane_islands[lay].insert(ib)
                w.plane_holes[lay].insert(ib.enlarged(sp, sp))
        _vias(w, i, j, isl & db.Region(ib), stack)
    array = db.Region(_box(0, 0, nx * P, ny * P))
    for lay in layers:
        w.plane_holes[lay].merge()
        w.add(lay, w.plane_islands[lay])
        w.add(lay, array - w.plane_holes[lay])
    w.report.update({"runners": ",".join(layers), "runner_style": "planes",
                     "planes": ",".join("%s:%s" % (lay, net_of[lay]) for lay in layers)})


def _check_planes(w):
    """Every plane keeps its spacing to the islands in its holes."""
    R = w.pdk["rules"]
    for lay in w.runner_layers:
        isl = w.plane_islands[lay]
        if isl.is_empty():
            continue
        plane = w.regions[lay] - isl
        sp = R.get(lay + "_s_wide", R[lay + "_s"])
        assert plane.separation_check(isl, sp).is_empty() and (plane & isl).is_empty(), \
            "%s plane too close to its islands" % lay


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
        if getattr(w, "ld_holes", None) is not None and w.params.deep_nwell:
            # room for the n-well band over the deep n-well's edge outside the drift holes
            enc_ = R["nwell_ntap_enc_mv"]
            d = R["nwell_dnwell_out"] + R["nwell_dnwell_in"] - tw - enc_
            hb = w.ld_holes.bbox().enlarged(d, d)
            t_in = t_in + hb
            t_in = _box(_snap_down(t_in.left, 2 * G), _snap_down(t_in.bottom, 2 * G),
                        _snap_up(t_in.right, 2 * G), _snap_up(t_in.top, 2 * G))
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
        if w.taps_sq.is_empty():           # with source taps the ring is on S's net: no B pin
            w.texts.setdefault(lay_lbl["met1"], []).append(("B", x, y))
            w.add_pin("met1", _box(x - e, y - e, x + e, y + e))
        w.nwell_box = tap_box.enlarged(enc, enc) if dev["kind"] == "p" else None
        if getattr(w, "ld_holes", None) is not None:
            w.regions["nwell"] = w.regions["nwell"] - w.ld_holes
            if w.params.deep_nwell:
                # the drift holes become p-wells isolated in a deep n-well
                dn = w.nwell_box.enlarged(-R["nwell_dnwell_out"], -R["nwell_dnwell_out"])
                inner = db.Region(dn.enlarged(-R["nwell_dnwell_in"], -R["nwell_dnwell_in"]))
                assert (w.ld_holes - inner).is_empty(), "a drift hole is too close to the deep n-well's edge"
                assert min(dn.width(), dn.height()) >= R["dnwell_w"]
                w.add("dnwell", db.Region(dn))
                w.report["deep_nwell"] = True
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
    if not hasattr(w, "runner_layers"):
        return
    layers, space = w.runner_layers, w.runner_space
    top = layers[-1]
    bw = max(BUS_MIN_W, _snap_up(int((w.params.bus_w or 0) * 1000), 2 * G))
    fil = _snap_up(space + 100, 2 * G)
    if w.params.bus not in ("L_buses", "none"):
        raise WaffleError("bus", "bus must be L_buses or none")
    x0, y0, x1, y1 = outer.left, outer.bottom, outer.right, outer.top
    g = _snap_up(max(2 * space + 2 * fil, 1000), 2 * G)
    yt_in, xr_in, yt_out, xr_out = y1 + g, x1 + g, y1 + g + bw, x1 + g + bw
    xl_in, yb_in, xl_out, yb_out = x0 - g, y0 - g, x0 - g - bw, y0 - g - bw
    sx, sy = (x0 + xr_out) // 2, (yt_in + yt_out) // 2
    dx, dy = (xl_out + x1) // 2, (yb_out + yb_in) // 2
    hb = bw // 2
    if w.params.runner_style == "planes":
        # each net's planes cover the array and run on into its L bus
        net_of = w.plane_net
        top_of = {n: [l for l in layers if net_of[l] == n][-1] for n in ("S", "D")}
        if w.params.bus == "L_buses":
            ext = {"S": db.Region(_box(x0, y0, xr_out, yt_out)), "D": db.Region(_box(xl_out, yb_out, x1, y1))}
            pins = {"S": (sx, sy, hb), "D": (dx, dy, hb)}
        else:
            ext = {n: db.Region() for n in ("S", "D")}
            c = w.P // 2
            pins = {"S": (c, c, R[top_of["S"] + "_w"] // 2),
                    "D": (c + (w.P if w.params.nx > 1 else 0), c + (0 if w.params.nx > 1 else w.P),
                          R[top_of["D"] + "_w"] // 2)}
        for lay in layers:
            if not ext[net_of[lay]].is_empty():
                w.add(lay, ext[net_of[lay]] - w.plane_holes[lay])
        _check_planes(w)
        for n in ("S", "D"):
            x, y, h = pins[n]
            w.texts.setdefault(lay_lbl[top_of[n]], []).append((n, x, y))
            w.add_pin(top_of[n], _box(x - h, y - h, x + h, y + h))
        w.report["pin_layers"] = {"S": top_of["S"], "D": top_of["D"]}
    elif w.params.bus == "L_buses":
        stair = w.params.runner_style == "staircase"
        busS = db.Region(_box(x0, yt_in, xr_out, yt_out)) + db.Region(_box(xr_in, y0, xr_out, yt_out))
        busD = db.Region(_box(xl_out, yb_out, xl_in, y1)) + db.Region(_box(xl_out, yb_out, x1, yb_in))
        # the stripes run on past the array into their bus (far enough to reach it)
        far = 2 * (max(abs(xr_out), abs(xl_out)) + max(abs(yt_out), abs(yb_out)))
        far += far % (4 * G)
        # (the array's stripes too: a longer staircase steps through other points)
        mS, mD = busS + w.stripes["S"], busD + w.stripes["D"]
        for d, net, cl, cr, s_lo, s_hi in w.stripe_defs:
            if net == "S":
                mS += _band(w, cl, cr, s_lo, far) & db.Region(_box(-far, -far, xr_out, yt_out))
                if stair:
                    continue
                jx = cl + yt_in
                if jx < xr_in:
                    mS.insert(db.Polygon([db.Point(jx, yt_in), db.Point(jx - fil, yt_in), db.Point(jx - fil, yt_in - fil)]))
                jy = xr_in - cr
                if jy < yt_in:
                    mS.insert(db.Polygon([db.Point(xr_in, jy), db.Point(xr_in, jy - fil), db.Point(xr_in - fil, jy - fil)]))
            else:
                mD += _band(w, cl, cr, -far, s_hi) & db.Region(_box(xl_out, yb_out, far, far))
                if stair:
                    continue
                jx = cr + yb_in
                if jx > xl_in:
                    mD.insert(db.Polygon([db.Point(jx, yb_in), db.Point(jx + fil, yb_in), db.Point(jx + fil, yb_in + fil)]))
                jy = xl_in - cl
                if jy > yb_in:
                    mD.insert(db.Polygon([db.Point(xl_in, jy), db.Point(xl_in, jy + fil), db.Point(xl_in + fil, jy + fil)]))
        if stair:
            # a step that ends just short of a bus leaves a slot narrower than
            # the spacing: fill those (0/90 degree edges only)
            r = _snap_up(space // 2 + 1, G)
            mS = _close(mS, r) & db.Region(_box(-far, -far, xr_out, yt_out))
            mD = _close(mD, r) & db.Region(_box(xl_out, yb_out, far, far))
        mS.merge()
        mD.merge()
        for lay in layers:
            w.regions[lay] = mS + mD
            w.regions[lay].merge()
        assert (mS & mD).is_empty() and mS.separation_check(mD, space).is_empty(), "S and D metal too close"
        w.texts.setdefault(lay_lbl[top], []).extend([("S", sx, sy), ("D", dx, dy)])
        w.add_pin(top, _box(sx - hb, sy - hb, sx + hb, sy + hb))
        w.add_pin(top, _box(dx - hb, dy - hb, dx + hb, dy + hb))
    else:
        for d, net, cl, cr, s_lo, s_hi in w.stripe_defs:
            cx, cy = (d * w.P + (s_lo + s_hi) // 2) // 2, ((s_lo + s_hi) // 2 - d * w.P) // 2
            w.texts.setdefault(lay_lbl[top], []).append((net, cx, cy))
            pw = R[top + "_w"]
            w.add_pin(top, _box(cx - pw // 2, cy - pw // 2, cx + pw // 2, cy + pw // 2))
    _check_latchup(w)


def _check_latchup(w):
    """The largest distance from the diffusion to a tap (Magic's LU.2/LU.3
    want 15 um), sampled every P/4 over the diffusion, to the guard ring and
    to the source-square taps."""
    R = w.pdk["rules"]
    P = w.P
    t_in = getattr(w, "tap_inner", None)
    sq = {}
    for b in w.taps_sq.each():
        bb = b.bbox()
        sq[(bb.center().x // P, bb.center().y // P)] = bb
    if t_in is None and not sq:
        w.report["lu_max_um"] = None
        w.report["lu_ok"] = False
        return
    db_ = w.diff_box
    step = max(P // 4, 250)
    worst = 0
    y = db_.bottom
    while y <= db_.top:
        x = db_.left
        while x <= db_.right:
            best = min(x - t_in.left, t_in.right - x, y - t_in.bottom, t_in.top - y) if t_in is not None else 10 ** 12
            ci, cj = x // P, y // P
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    b = sq.get((ci + di, cj + dj))
                    if b is not None:
                        dx = max(b.left - x, 0, x - b.right)
                        dy = max(b.bottom - y, 0, y - b.top)
                        best = min(best, math.hypot(dx, dy))
            worst = max(worst, best)
            x += step
        y += step
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
