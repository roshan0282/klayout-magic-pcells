"""Hybrid-waffle (HW) power MOSFET for sky130A, after Yoo, Chang, Trescases and
Ng, "High Performance Low-Voltage Power MOSFETs with Hybrid Waffle Layout
Structure in a 0.25 um Standard CMOS Process" (ISPSD 2008).

Geometry (all coordinates in um, tile pitch P):

* Tiles form an N x M checkerboard. Tile (i, j), centred at
  ((i + 1/2) P, (j + 1/2) P), is a source tile when i + j is even and a
  drain tile otherwise, so every internal tile edge separates S from D.
* Every internal edge carries one *block*: Magic's own MOSFET (one of
  ``DEVICES``; ``w`` = finger W, ``l`` = L, ``nf`` = fingers per cell, no
  guard ring), generated through the ``sky130_magic`` library.
  Vertical edges get it as drawn (fingers parallel to the edge), horizontal
  edges rotated by 90 degrees, so each tile is ringed by the same block in
  four orientations.
* Inside a block, the S/D strips alternate between the two tiles. A met2
  comb crosses the block perpendicular to the fingers: lines alternate
  between the tiles, each with a via1 (Magic's ``via1`` generator) on its own
  tile's strips only, and runs into that tile's met2 plate.
* Every tile centre has a met2-met3-met4-met5 stack (Magic's ``via2``,
  ``via3``, ``via4`` generators) under a 45 degree strap of stacked met3,
  met4 and met5. Diagonal neighbours have the same type, so one strap joins
  every tile of a diagonal; S and D straps alternate. S straps run up and
  right into an L-shaped S bus (top and right), D straps down and left into
  the D bus (left and bottom).
* The gate is met1: a bar over each row of gate-contact pads, a spine to
  the grid crossing, a rail beside each block joining its two crossings, and
  a ring on the outer grid lines.
* Body: ``bulk="ring"`` puts Magic's ``subconn_guard`` (p-tap) or ``nwell``
  (n-well with n-tap ring) around the array, labelled B; Magic's LU rules
  then limit the array size. ``bulk="source"`` puts a tap (Magic's
  ``subconn``; for a pfet the same with nsdm for psdm) under every source
  tile, tied to S through Magic's ``mcon`` and ``via1``, so any size is
  latch-up clean and the body is S.
* Well and threshold layers that Magic draws per device (nwell, hvi, lvtn,
  hvtp, ...) are drawn once over the whole array instead, so neighbouring
  blocks' copies never leave gaps narrower than their spacing rules.

Every polygon vertex is on the 5 nm grid: P, the strap half-widths and the
cut positions are multiples of 10 nm, so the 45 degree edges meet the
axis-parallel ones on grid points.
"""

import math

import klayout.db as db

PDK = "sky130A"
LIBRARY = "sky130_magic"
DEVICE = "sky130_fd_pr__nfet_01v8"

# Magic's sky130A MOSFETs whose source and drain are interchangeable, which
# the waffle needs: kind ("n" or "p") and whether they are thick-oxide (hvi) devices.
# Left out: the g5v0d16v0 drain-extended FETs (asymmetric) and the SONOS cell.
DEVICES = {
    "sky130_fd_pr__nfet_01v8": ("n", False),
    "sky130_fd_pr__nfet_01v8_lvt": ("n", False),
    "sky130_fd_pr__nfet_03v3_nvt": ("n", True),
    "sky130_fd_pr__nfet_05v0_nvt": ("n", True),
    "sky130_fd_pr__nfet_g5v0d10v5": ("n", True),
    "sky130_fd_pr__pfet_01v8": ("p", False),
    "sky130_fd_pr__pfet_01v8_lvt": ("p", False),
    "sky130_fd_pr__pfet_01v8_hvt": ("p", False),
    "sky130_fd_pr__pfet_g5v0d10v5": ("p", True),
}
BULK_MODES = ("ring", "source")

DBU = 0.001

L_MET1 = (68, 20)
L_MET2 = (69, 20)
L_MET3 = (70, 20)
L_MET4 = (71, 20)
L_MET5 = (72, 20)
L_DIFF = (65, 20)
L_NSDM = (93, 44)
L_PSDM = (94, 20)
L_HVI = (75, 20)
# Layers kept per block; every other layer of the unit cell is drawn once
# over the array (wells, hvi, threshold implants, id layers).
PER_BLOCK = {(65, 20), (66, 20), (66, 44), (67, 20), (67, 44), (68, 20), L_NSDM, L_PSDM, (95, 20)}
T_LI = (67, 5)
T_MET1 = (68, 5)
T_MET5 = (72, 5)

# Choices and the sky130 rules behind them, in nm.
VIA1_BOX = 260          # Magic's minimum via1 box; draws met1 360 x 260, met2 260 x 360
COMB_W = 360            # met2 comb line width (the via1's met2 height)
COMB_SPACE = 200        # met2 spacing is 140
BLOCK_GAP = 400         # between the bounding boxes of two blocks (nsdm spacing 380)
PLATE_GAP = 300         # met2 plate to a block's bounding box
PLATE_OVERLAP = 500     # comb line run into the plate
STACK_ENCL = 240        # via4's met5 sticks out 120 per side of its box
VIA4_MIN = 1180         # Magic's minimum via4 box
MET5_SPACE = 1600
MET5_WIDTH = 1600
CAP_MARGIN = 200        # strap end cap beyond the end tile's via stack
STRAP_MIN = 2400        # below this, Magic's met3.3c / met4.5a (spacing within the halo
                        # of > 3 um metal) fire where straps meet the buses; 2.2 and 2.3
                        # fail and 2.4 to 3.5 pass on 2x2, 3x3 and 2x3 grids
BUS_MIN_W = 3200        # buses are "huge" (> 3 um) metal, so the met3.3c / met4.5a
                        # halo around them stays clear at the strap junctions
GATE_W = 400            # met1 gate spines and rails
GATE_SPACE = 300        # met1 spacing is 140
BUS_GAP = 3000          # array edge to the S/D buses (fillets stay 1.6 um from strap ends)
FILLET = 1700           # fills the 45 degree notch where a strap meets a bus, down to
                        # where the notch is as wide as the met5 spacing
RING_OFFSET = 500       # tap ring centre line outside the tile array
RING_MCON_W = 2000      # met1 contact on the ring (nwell.4 wants metal-connected taps)
TAP = 1000              # mcon and via1 box side on an interior tap
TAP_GAP = 500           # interior tap box to a block's bounding box
LU_MAX = 14500          # Magic's LU.2 / LU.3: diff within 15 um of a tap


class HWParamError(ValueError):
    """A parameter value the generator can't draw clean. ``param`` names
    the parameter to blame (the GUI form puts its error icon there)."""

    def __init__(self, param, message):
        super().__init__(message)
        self.param = param


def _ceil10(v):
    return int(math.ceil(v / 10.0 - 1e-9)) * 10


def _floor10(v):
    return int(math.floor(v / 10.0 + 1e-9)) * 10


def _nm(um):
    return int(round(um * 1000))


class HWParams:
    """Parameters of the HW FET.

    l, w      gate length and finger width (um), per finger
    nf        fingers per block (each internal tile edge)
    nx, ny    tiles per row and per column (N x M)
    strap_w   width of the diagonal met3-met5 straps, perpendicular (um)
    pitch     tile pitch (um); None picks the smallest that fits
    device    one of DEVICES
    bulk      "ring" (tap ring around the array, body pin B) or "source"
              (a tap in every source tile, body tied to S)
    """

    def __init__(self, l=0.5, w=2.0, nf=3, nx=3, ny=3, strap_w=3.0, pitch=None,
                 device=DEVICE, bulk="ring"):
        self.l, self.w, self.nf = float(l), float(w), int(nf)
        self.nx, self.ny = int(nx), int(ny)
        self.strap_w = float(strap_w)
        self.pitch = None if pitch is None else float(pitch)
        self.device = device
        self.bulk = bulk

    def as_dict(self):
        return dict(l=self.l, w=self.w, nf=self.nf, nx=self.nx, ny=self.ny,
                    strap_w=self.strap_w, pitch=self.pitch, device=self.device, bulk=self.bulk)


class HWResult:
    """What generate() made: the cell and the numbers a netlist must show."""

    def __init__(self, cell, params, magic_values, pitch, strap_w, blocks):
        self.cell = cell
        self.cell_name = cell.name
        self.params = params
        self.magic_values = magic_values  # Magic's checked values of the unit nfet
        self.pitch = pitch                # um
        self.strap_w = strap_w            # um, as drawn (>= the requested width)
        self.blocks = blocks              # number of unit nfets
        self.w = float(magic_values["w"])
        self.l = float(magic_values["l"])
        self.nf = int(magic_values["nf"])
        self.devices = blocks * self.nf
        self.total_w = self.devices * self.w

    def summary(self):
        return ("HW %s %dx%d, pitch %.3f um, %d blocks x nf %d = %d fingers of W %.3f L %.3f, "
                "total W %.3f um, strap %.3f um, bulk %s"
                % (self.params.device, self.params.nx, self.params.ny, self.pitch, self.blocks,
                   self.nf, self.devices, self.w, self.l, self.total_w, self.strap_w,
                   self.params.bulk))


# -- Magic's cells -------------------------------------------------------------

def _library():
    lib = db.Library.library_by_name(LIBRARY)
    if lib is not None:
        return lib
    import klayout_magic_pcells as kmp
    lib = kmp.register(PDK)
    if lib is None:
        raise RuntimeError("the %s library (klayout-magic-pcells, %s) could not register; "
                           "run 'python3 -m klayout_magic_pcells doctor'" % (LIBRARY, PDK))
    return lib


def _magic_cell(ly, name, values, plain_name):
    """Magic's cell for ``name`` copied into a plain cell, texts removed."""
    proxy = ly.create_cell(name, LIBRARY, values)
    if proxy is None:
        raise RuntimeError("%s has no PCell %s" % (LIBRARY, name))
    for li in ly.layer_indexes():
        if ly.get_info(li).datatype == 0 and ly.get_info(li).layer == 255:
            if not proxy.shapes(li).is_empty():
                raise RuntimeError("Magic failed to draw %s %s (placeholder drawn)" % (name, values))
    cell = ly.create_cell(plain_name)
    cell.copy_shapes(proxy)
    for li in ly.layer_indexes():
        texts = [s for s in cell.shapes(li).each() if s.is_text()]
        for s in texts:
            cell.shapes(li).erase(s)
    if cell.bbox().empty():
        raise RuntimeError("Magic drew nothing for %s %s" % (name, values))
    return cell


def _unit_values(p):
    import klayout_magic_pcells as kmp
    typed = {"w": p.w, "l": p.l, "nf": p.nf, "guard": False}
    vals = kmp.dialog_values(p.device, typed, pdk=PDK)
    for k in ("w", "l", "nf"):
        if abs(float(vals[k]) - float(typed[k])) > 1e-9:
            raise HWParamError(k, "Magic's dialog changes %s from %s to %s for %s"
                             % (k, typed[k], vals[k], p.device))
    return vals


# -- geometry helpers ----------------------------------------------------------

def _box(x1, y1, x2, y2):
    return db.Box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _diag_rect(c_lo, c_hi, s_lo, s_hi):
    """The region c_lo <= x - y <= c_hi, s_lo <= x + y <= s_hi."""
    pts = []
    for c, s in ((c_lo, s_lo), (c_hi, s_lo), (c_hi, s_hi), (c_lo, s_hi)):
        if (c + s) % 2:
            raise AssertionError("diagonal corner off the 1 nm grid")
        pts.append(db.Point((c + s) // 2, (s - c) // 2))
    return db.Polygon(pts)


def _tri(*pts):
    return db.Polygon([db.Point(x, y) for x, y in pts])


# -- the generator -------------------------------------------------------------

def generate(layout, params, name="HW_FET"):
    """Draw the HW FET into ``layout`` (dbu 0.001) as one flat cell.

    Returns an HWResult. Raises ValueError for parameters the geometry
    can't take.
    """
    p = params
    if abs(layout.dbu - DBU) > 1e-12:
        raise ValueError("the layout's dbu must be %g" % DBU)
    if p.nx < 1 or p.ny < 1 or p.nx * p.ny < 2:
        raise HWParamError("nx", "the grid needs at least two tiles")
    if p.nf < 1:
        raise HWParamError("nf", "nf must be >= 1")
    if p.device not in DEVICES:
        raise HWParamError("device", "device %r is not one of %s" % (p.device, ", ".join(sorted(DEVICES))))
    if p.bulk not in BULK_MODES:
        raise HWParamError("bulk", "bulk must be one of %s" % ", ".join(BULK_MODES))
    kind, hv = DEVICES[p.device]
    DEV = p.device
    _library()
    ly = layout
    vals = _unit_values(p)
    W = _nm(float(vals["w"]))

    # Unit nfet, fingers vertical, centred on the origin.
    unit = _magic_cell(ly, DEV, vals, name + "_UNIT")
    ub = unit.bbox()
    if ub.left != -ub.right or ub.bottom != -ub.top:
        raise RuntimeError("Magic's %s is not centred on the origin: %s" % (DEV, ub))
    hxb, hyb = ub.right, ub.top
    # Well, hvi and threshold layers leave the block; they are drawn once
    # over the whole array below.
    covers = []
    for li in ly.layer_indexes():
        info = ly.get_info(li)
        if (info.layer, info.datatype) not in PER_BLOCK and not unit.shapes(li).is_empty():
            covers.append((info.layer, info.datatype))
            unit.shapes(li).clear()
    m1 = ly.layer(*L_MET1)
    strips, pads = [], []
    for s in unit.shapes(m1).each():
        b = s.bbox()
        (strips if b.height() >= W else pads).append(b)
    xs = sorted(b.center().x for b in strips)
    # Gate-contact pads: one row at each end. Below L ~0.33 um Magic contacts
    # each finger at one end only, alternating, so the rows can differ.
    rows = {}
    for sgn in (1, -1):
        row = [b for b in pads if (b.bottom > 0 if sgn > 0 else b.top < 0)]
        if row:
            rows[sgn] = (min(min(abs(b.bottom), abs(b.top)) for b in row),
                         max(max(abs(b.bottom), abs(b.top)) for b in row),
                         min(b.left for b in row), max(b.right for b in row))
    if len(xs) != p.nf + 1 or not rows or sum(1 for b in pads if b.bottom > 0 or b.top < 0) != len(pads):
        raise RuntimeError("unexpected met1 in Magic's %s: %d strips, %d pads"
                           % (DEV, len(xs), len(pads)))
    if min(r[0] for r in rows.values()) - W // 2 < 140:
        raise RuntimeError("Magic's gate pads sit closer than 0.14 um to the S/D strips")

    # Comb lines across the strips.
    lo, hi = -W // 2 + COMB_W // 2, W // 2 - COMB_W // 2
    n_lines = (hi - lo) // (COMB_W + COMB_SPACE) + 1 if hi >= lo else 0
    if n_lines < 2:
        raise HWParamError("w", "finger W %.3f um is too narrow for two met2 comb lines (needs >= %.2f um)"
                         % (W / 1000.0, (2 * COMB_W + COMB_SPACE) / 1000.0))
    ys = [int(round((lo + k * (hi - lo) / float(n_lines - 1)) / 10.0)) * 10 for k in range(n_lines)]

    # Strap, via stack and pitch.
    if _nm(p.strap_w) < STRAP_MIN:
        raise HWParamError("strap_w", "strap width %.3f um is below %.2f um: narrower straps meet the buses with "
                         "met3.3c / met4.5a errors in Magic" % (p.strap_w, STRAP_MIN / 1000.0))
    hx = _ceil10(_nm(p.strap_w) / math.sqrt(2.0))   # horizontal half-width of a strap
    a = _floor10(hx - STACK_ENCL - 100)             # via2/3/4 box side
    if a < VIA4_MIN or 2 * hx / math.sqrt(2.0) < MET5_WIDTH:
        raise HWParamError("strap_w", "strap width %.3f um is too narrow for the via4 stack (needs >= %.2f um)"
                         % (p.strap_w, (VIA4_MIN + STACK_ENCL + 100) * math.sqrt(2.0) / 1000.0))
    pitch_min = max(2 * hxb + 2 * hyb + BLOCK_GAP,
                    2 * hx + MET5_SPACE * math.sqrt(2.0),
                    2 * hxb + 2 * PLATE_GAP + a + 400,
                    2 * (hxb + hyb + 2 * GATE_SPACE + GATE_W),
                    2 * (hxb + 2 * GATE_SPACE + GATE_W + TAP // 2 + 60) if p.bulk == "source" else 0)
    P = _ceil10(pitch_min)
    if p.pitch is not None:
        if _nm(p.pitch) < P:
            raise HWParamError("pitch", "pitch %.3f um is below the minimum %.3f um" % (p.pitch, P / 1000.0))
        P = _ceil10(_nm(p.pitch))
    N, M = p.nx, p.ny

    # Block: the unit nfet plus its comb (A = local -x side, B = local +x side).
    via1 = _magic_cell(ly, "via1", {"w": VIA1_BOX / 1000.0, "h": VIA1_BOX / 1000.0}, name + "_VIA1")
    block = ly.create_cell(name + "_BLOCK")
    block.insert(db.CellInstArray(unit.cell_index(), db.Trans()))
    m2 = ly.layer(*L_MET2)
    reach = hxb + PLATE_GAP + PLATE_OVERLAP
    xa, xb = xs[0::2], xs[1::2]
    for k, y in enumerate(ys):
        own = xa if k % 2 == 0 else xb
        if k % 2 == 0:
            block.shapes(m2).insert(_box(-reach, y - COMB_W // 2, max(xa) + VIA1_BOX // 2, y + COMB_W // 2))
        else:
            block.shapes(m2).insert(_box(min(xb) - VIA1_BOX // 2, y - COMB_W // 2, reach, y + COMB_W // 2))
        for x in own:
            block.insert(db.CellInstArray(via1.cell_index(),
                                          db.Trans(x - VIA1_BOX // 2, y - VIA1_BOX // 2)))
    # Gate, on met1, in the block's frame (its ends' crossings at y = +-P/2):
    # a bar over each row of gate-contact pads, a spine from it to the
    # crossing, and a rail on the +x side joining the two crossings. Below
    # L ~0.33 um Magic contacts each finger at one end only, so the rails,
    # not the poly, are what join the crossings.
    gate = db.Region()
    xr = hxb + GATE_SPACE
    hg = GATE_W // 2
    for sgn in (1, -1):
        if sgn in rows:
            py0, py1, x0, x1 = rows[sgn]
            gate.insert(_box(min(x0, -hg), sgn * py0, max(x1, hg), sgn * py1))
            gate.insert(_box(-hg, sgn * py0, hg, sgn * (P // 2 + hg)))
        gate.insert(_box(-hg, sgn * (P // 2 - hg), xr + GATE_W, sgn * (P // 2 + hg)))
    gate.insert(_box(xr, -(P // 2 + hg), xr + GATE_W, P // 2 + hg))
    block.shapes(m1).insert(gate.merged())

    top = ly.create_cell(name)

    def tile_is_source(i, j):
        return (i + j) % 2 == 0

    # Blocks on the internal edges.
    blocks = []   # (centre x, centre y, vertical?)
    for i in range(1, N):
        for j in range(M):
            blocks.append((i * P, j * P + P // 2, True))
    for i in range(N):
        for j in range(1, M):
            blocks.append((i * P + P // 2, j * P, False))
    for cx, cy, vert in blocks:
        rot = db.Trans.R0 if vert else db.Trans.R90
        top.insert(db.CellInstArray(block.cell_index(), db.Trans(rot, cx, cy)))

    # Tile plates and via stacks.
    stack = []
    for vname in ("via2", "via3", "via4"):
        stack.append(_magic_cell(ly, vname, {"w": a / 1000.0, "h": a / 1000.0}, "%s_%s" % (name, vname.upper())))
    inset = hxb + PLATE_GAP
    for i in range(N):
        for j in range(M):
            top.shapes(m2).insert(_box(i * P + inset, j * P + inset, (i + 1) * P - inset, (j + 1) * P - inset))
            cx, cy = i * P + P // 2, j * P + P // 2
            for c in stack:
                top.insert(db.CellInstArray(c.cell_index(), db.Trans(cx - a // 2, cy - a // 2)))

    # Gate ring on the outer grid lines: joins the perimeter crossings, which
    # a one-row or one-column array has no other path between.
    ring_g = db.Region()
    ring_g.insert(_box(-hg, -hg, N * P + hg, hg))
    ring_g.insert(_box(-hg, M * P - hg, N * P + hg, M * P + hg))
    ring_g.insert(_box(-hg, -hg, hg, M * P + hg))
    ring_g.insert(_box(N * P - hg, -hg, N * P + hg, M * P + hg))
    top.shapes(m1).insert(ring_g.merged())

    # The gate label sits on the crossing at one end of the first block.
    cx, cy, vert = blocks[0]
    gate_label = (cx, cy - P // 2) if vert else (cx - P // 2, cy)

    # Diagonal straps and buses on met3, met4 and met5.
    q = a + STACK_ENCL
    ds = _ceil10(q + CAP_MARGIN * math.sqrt(2.0))
    bw = max(_ceil10(_nm(p.strap_w)), BUS_MIN_W)
    xt_out, yt_out = N * P + BUS_GAP + bw, M * P + BUS_GAP + bw   # S bus outer edges
    xl_out = yb_out = -(BUS_GAP + bw)                            # D bus outer edges
    yt_in, xr_in = M * P + BUS_GAP, N * P + BUS_GAP
    xl_in = yb_in = -BUS_GAP
    s_bus = db.Region()
    s_bus.insert(_box(0, yt_in, xt_out, yt_out))
    s_bus.insert(_box(xr_in, 0, xt_out, yt_out))
    d_bus = db.Region()
    d_bus.insert(_box(xl_out, yb_out, xl_in, M * P))
    d_bus.insert(_box(xl_out, yb_out, N * P, yb_in))
    far = 4 * (N + M + 2) * P + 4 * bw
    metal = db.Region()
    metal += s_bus
    metal += d_bus
    for d in range(-(M - 1), N):
        tiles = [(i, i - d) for i in range(N) if 0 <= i - d < M]
        svals = [(i + j + 1) * P for i, j in tiles]
        c0 = d * P
        cl, cr = c0 - hx, c0 + hx
        if tile_is_source(*tiles[0]):
            band = db.Region(_diag_rect(cl, cr, min(svals) - ds, far))
            band &= db.Region(_box(-far, -far, xt_out, yt_out))
            metal += band
            jx = cl + yt_in                      # upper-left edge meets the top bar
            if jx < xr_in:
                metal.insert(_tri((jx, yt_in), (jx - FILLET, yt_in), (jx - FILLET, yt_in - FILLET)))
            jy = xr_in - cr                      # lower-right edge meets the right bar
            if jy < yt_in:
                metal.insert(_tri((xr_in, jy), (xr_in, jy - FILLET), (xr_in - FILLET, jy - FILLET)))
        else:
            band = db.Region(_diag_rect(cl, cr, -far, max(svals) + ds))
            band &= db.Region(_box(xl_out, yb_out, far, far))
            metal += band
            jx = cr + yb_in                      # lower-right edge meets the bottom bar
            if jx > xl_in:
                metal.insert(_tri((jx, yb_in), (jx + FILLET, yb_in), (jx + FILLET, yb_in + FILLET)))
            jy = xl_in - cl                      # upper-left edge meets the left bar
            if jy > yb_in:
                metal.insert(_tri((xl_in, jy), (xl_in, jy + FILLET), (xl_in + FILLET, jy + FILLET)))
    metal.merge()
    for lyr in (L_MET3, L_MET4, L_MET5):
        top.shapes(ly.layer(*lyr)).insert(metal)

    # Body: wells and implants over the array, then the taps.
    # The ring's met1 (B pin) must clear the met1 gate ring on the array edge.
    e = max(RING_OFFSET, _ceil10(GATE_W // 2 + GATE_SPACE + 115))
    for lyr in covers:
        top.shapes(ly.layer(*lyr)).insert(_box(-e, -e, N * P + e, M * P + e))
    taps = []
    if p.bulk == "ring":
        gen = {("n", False): "subconn_guard", ("n", True): "mvsubconn_guard",
               ("p", False): "nwell", ("p", True): "mvnwell"}[(kind, hv)]
        ring = _magic_cell(ly, gen, {"w": (N * P + 2 * e) / 1000.0, "h": (M * P + 2 * e) / 1000.0},
                           name + "_RING")
        top.insert(db.CellInstArray(ring.cell_index(), db.Trans(-e, -e)))
        # met1 on the bottom side, which carries the B pin.
        rc = _magic_cell(ly, "mcon", {"w": RING_MCON_W / 1000.0, "h": 0.17}, name + "_RING_MCON")
        bx = N * P // 2 - RING_MCON_W // 2
        top.insert(db.CellInstArray(rc.cell_index(), db.Trans(bx, -e - 85)))
        taps = [_box(-e, -e, N * P + e, -e), _box(-e, M * P + e, N * P + e, M * P + e),
                _box(-e, -e, -e, M * P + e), _box(N * P + e, -e, N * P + e, M * P + e)]
    else:
        # The tap fills the tile interior, so a block's diffusion is never
        # further from a tap than the block's own width.
        ts = P - 2 * (hxb + TAP_GAP)
        tap = _magic_cell(ly, "mvsubconn" if hv else "subconn",
                          {"w": ts / 1000.0, "h": ts / 1000.0}, name + "_TAP")
        if kind == "p":   # an n-tap: the same contact with nsdm for psdm
            ps, ns = ly.layer(*L_PSDM), ly.layer(*L_NSDM)
            tap.shapes(ns).insert(tap.shapes(ps))
            tap.shapes(ps).clear()
        tmc = _magic_cell(ly, "mcon", {"w": TAP / 1000.0, "h": TAP / 1000.0}, name + "_TAP_MCON")
        tv1 = _magic_cell(ly, "via1", {"w": TAP / 1000.0, "h": TAP / 1000.0}, name + "_TAP_VIA1")
        for i in range(N):
            for j in range(M):
                if not tile_is_source(i, j):
                    continue
                cx, cy = i * P + P // 2, j * P + P // 2
                top.insert(db.CellInstArray(tap.cell_index(), db.Trans(cx - ts // 2, cy - ts // 2)))
                for c in (tmc, tv1):
                    top.insert(db.CellInstArray(c.cell_index(), db.Trans(cx - TAP // 2, cy - TAP // 2)))
                taps.append(_box(cx - ts // 2, cy - ts // 2, cx + ts // 2, cy + ts // 2))
    _check_latchup(ly, unit, blocks, taps)

    # Labels.
    top.shapes(ly.layer(*T_MET5)).insert(db.Text("S", db.Trans(xt_out // 2, yt_in + bw // 2)))
    top.shapes(ly.layer(*T_MET5)).insert(db.Text("D", db.Trans(N * P // 2, yb_out + bw // 2)))
    top.shapes(ly.layer(*T_MET1)).insert(db.Text("G", db.Trans(*gate_label)))
    if p.bulk == "ring":
        top.shapes(ly.layer(*T_MET1)).insert(db.Text("B", db.Trans(N * P // 2, -e)))

    top.flatten(-1, True)   # also deletes the helper cells
    return HWResult(top, p, vals, P / 1000.0, 2 * hx / math.sqrt(2.0) / 1000.0, len(blocks))


def _check_latchup(ly, unit, blocks, taps):
    """Magic's LU.2 / LU.3: every point of the blocks' diffusion within
    15 um of a tap (checked on an 11 x 11 grid of points per block)."""
    diff = db.Region(unit.begin_shapes_rec(ly.layer(*L_DIFF))).bbox()
    worst = 0
    for cx, cy, vert in blocks:
        t = db.Trans(db.Trans.R0 if vert else db.Trans.R90, cx, cy)
        b = diff.transformed(t)
        for k in range(11):
            for m in range(11):
                x = b.left + (b.right - b.left) * k // 10
                y = b.bottom + (b.top - b.bottom) * m // 10
                near = min(math.hypot(max(tb.left - x, 0, x - tb.right), max(tb.bottom - y, 0, y - tb.top))
                           for tb in taps)
                worst = max(worst, near)
    if worst > LU_MAX:
        raise HWParamError("nx", "diffusion lies %.2f um from the nearest tap; Magic's LU rules allow 15 um. "
                         "Use a smaller grid or bulk='source' (a tap in every source tile)"
                         % (worst / 1000.0))


def write_gds(params, path, name="HW_FET"):
    """Generate into a fresh layout and write only the HW cell to ``path``."""
    ly = db.Layout()
    ly.dbu = DBU
    res = generate(ly, params, name=name)
    opt = db.SaveLayoutOptions()
    opt.format = "GDS2"
    opt.clear_cells()
    opt.add_cell(res.cell.cell_index())
    ly.write(path, opt)
    return res
