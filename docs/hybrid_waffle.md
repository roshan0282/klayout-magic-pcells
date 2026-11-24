# Hybrid-waffle power MOSFET (sky130A)

`klayout_power_pcells.waffle` draws a hybrid-waffle (HW) power MOSFET after
Yoo, Chang, Trescases and Ng, "High Performance Low-Voltage Power MOSFETs
with Hybrid Waffle Layout Structure in a 0.25 um Standard CMOS Process"
(ISPSD 2008), Fig. 3(a). It is drawn from raw layers with the rule table in
`rules.py`. Drawing needs only KLayout; verification uses the PDK's KLayout
deck, Magic and netgen. [guide-power.md](guide-power.md) covers the
`HW_FET` PCell, the command line and the plugin.

Versions 0.2 and 0.3 placed a Magic MOSFET with `nf` fingers on every tile
edge. That was not a waffle and has been removed. In a waffle the squares
*are* the source/drain diffusion, and every shared edge is exactly one
gate.

```sh
PYTHONPATH=python python3 -m klayout_power_pcells check nx=10 ny=10 P=4
# HW_FET: HW nfet_01v8 10x10, P 4.000, L 0.150, N 0.550 um: 180 gates, W_total 628.20 um, bbox 2746.8 um2
#         (W/area 0.229 um/um2), active 1518.4 um2, licon/square 109/111/112/117/119/120, diff-to-tap 3.7 um
PYTHONPATH=python python3 -m klayout_power_pcells verify nx=3 ny=3 device=pfet_01v8
```

## Geometry

All coordinates are integer nm on the 5 nm grid. P, L and N are multiples
of 10 nm, so their halves are on the grid.

- **Squares.** Square (i, j) has its centre at ((i + 1/2) P, (j + 1/2) P). It
  is S when i + j is even and D when it is odd; square (0, 0) is S.
- **Poly.** Lines of width L run at x = kP and y = lP, for interior k and l.
  They extend 0.13 um past the diffusion (poly.8) into a poly frame around
  the array.
- **Diffusion.** One rectangle, [L/2, nx P - L/2] x [L/2, ny P - L/2], minus a
  square notch of side N centred on every interior poly crossing. Every
  gate (poly AND diff) is then a plain L-wide rectangle, and every crossing
  sits on field oxide (poly.11 forbids bends on diffusion).
  - Interior gate segments have W = P - N.
  - Segments that end at the diffusion edge have W = P - N/2 - L/2.
  - There are (nx - 1) ny + nx (ny - 1) gates.
- **Minimum notch N.**
  - With in-array gate contacts (`met1_mesh`): a poly contact plus twice
    licon.14, which is 0.55 um. For a pfet it is 0.64 um, because the
    p-diffusion rule is 0.235.
  - With `frame_only`: L + 2 x poly.4.
  - Both are rounded up to 10 nm.
- **Per square**, identical for S and D, from the bottom up:
  - a licon array, kept 0.06 from the diffusion edges and 0.09 from the
    gates (licon.11's 0.055, raised so that neighbouring squares' li pads
    keep li.3 across the gate);
  - an li pad;
  - an mcon array;
  - a met1 island and, above it, a met2 island on the same footprint, joined
    by a via array. The islands keep 0.28 um (wide-metal spacing) from the
    gate's met1.
  - via2 (and via3, via4) only where the square meets its own diagonal
    stripe.
- **Gate strap.**
  - `met1_mesh`: in every notch a poly pad, poly contact, npc, li pad and
    mcon; met1 lines 0.29 um wide along every poly line.
  - Both modes: a row of poly contacts in the frame, under an li ring and a
    met1 ring.
  - `frame_only`: the frame contacts alone; poly is about 48 ohm/sq, so a
    large array then has a high distributed gate resistance.
- **Runners.**
  - The layers are met3, met3+met4 or met3+met4+met5, stacked and identical.
  - Stripe d = i - j runs through the centres of squares (i, i - d) as a
    45 degree band. All squares on a stripe have the same parity, and
    neighbouring stripes alternate S and D.
  - The band's horizontal width Δ = P - √2 x spacing, rounded down to
    20 nm, so that every corner is on the grid. The spacing used is the
    wide-metal one: 0.4 um on met3/met4, 1.6 um on met5.
- **Buses** (`L_buses`).
  - The S bus runs on the top and right, and the D bus on the bottom and
    left, on every runner layer, at least 3.2 um wide. There are gaps at the
    top-left and bottom-right corners.
  - S stripes run into the S bus and stop short of the D bus; D stripes do
    the reverse.
  - Where a stripe meets a bus, a triangle fills the 45 degree notch.
  - With `bus=none`, each stripe gets its own pin instead.
- **Source-square body taps** (`source_taps`, on by default). Every S
  square has a tap island at its centre, in a hole in the diffusion:
  - the island is `tap_w` square, 0.41 um by default, which holds one
    contact with licon.7's 0.12 um;
  - field oxide of 0.27 um surrounds it (difftap.3; 0.37 um for 5 V devices,
    diff/tap.15b), enough for both implants' 0.125 um enclosures;
  - its implant is the opposite one: p-tap for an nfet, n-tap inside the
    n-well for a pfet;
  - its contact sits under the square's li pad, so the body is tied to S.
    This is the usual connection for a power switch, and the netlist's body
    terminal is S.

  Every diffusion is then within about 3 um of a tap, at any array size.
  The hole stays more than poly.7's 0.25 um from every gate, so the gates
  and W don't change. A tap needs P large enough to leave diffusion around
  it (P = 2 um is refused, with the reason).
- **Body ring.**
  - nfet: a p-tap guard ring (psdm), with li and met1 over it. It is
    labelled B only without source taps; with them it is on S's net.
  - pfet: an n-tap ring (nsdm) inside an n-well that encloses the p-diff by
    0.18 um (0.33 um for 5 V).
  - 5 V devices: hvi over everything, including the n-well (nwell.9).
- **Pins and labels.** G on the met1 gate ring, S and D on the buses (top
  runner layer), B on the guard ring. Pins use datatype 16, labels
  datatype 5.

### Self-checks (spec section 9)

`build()` refuses to finish (assertion) if any of these fail:
- the gate count is wrong;
- a gate is not an L-wide rectangle;
- a gate joins two squares of the same type;
- a poly crossing lies on diffusion;
- a licon is outside its enclosure or within licon.11 of a gate;
- a cut is outside its li or met1;
- li, licon, mcon or via spacing is violated;
- npc width or spacing is violated;
- S and D metal touch or come closer than the runner spacing;
- a square gets no cut on some via layer, or a ring gets no contacts.

`fill_cuts(region, cut, space, encl_lower, encl_upper)` places every cut
array. It keeps only cuts whose square, enlarged by the enclosure, lies
inside the metal. That square test is how Magic measures an enclosure, and
it matters next to the 45 degree edges.

## The rule table

`rules.py` holds every value, each with its source in the installed PDK:
the KLayout deck `sky130A_mr.drc`, or Magic's `sky130A.tech` (for rules the
deck doesn't check, and for npc and the implants, which Magic generates).
The values given in the spec were checked against both. These were
missing or needed correcting:

| Rule | Value | Note |
|---|---|---|
| li.5 | li overlaps a contact by 0.08 um in one direction | missing from the spec |
| m1.3ab, m2.3ab | metal wider than 3 um needs 0.28 um spacing | met1/met2 islands are about 3.3 um wide at P = 4 |
| m3.3cd, m4.5ab | metal wider than 3 um needs 0.4 um spacing | used for the runners |
| via2.4 / via2.5 | 0.04 um, and 0.085 um on two adjacent edges | 0.085 used on all sides |
| 5 V n-well | encloses p-diff and n-tap by 0.33 um | 0.18 um is the 1.8 V value |
| diff/tap.15b | 5 V n-diffusion to p-tap: 0.37 um | from Magic; used around the source-square taps of 5 V devices |
| npc | 0.27 um minimum width and spacing, kept off diffusion contacts | |
| minimum areas | li 0.0561, m1 0.083, m2 0.0676, m3/m4 0.24, m5 4.0 um² | |

## Runner styles

`runner_style` picks how the S/D runners on met3 (met4, met5) are drawn.
All three pass both DRC decks and LVS.

- **`diag45`** (default): the 45 degree stripes above.
- **`staircase`**: the same stripes drawn only with 0/90 degree edges.
  Each stripe is a run of squares of side Δ/2 on its centre line, stepped
  so that neighbours overlap by at least the metal width. The squares lie
  inside the 45 degree band, so the band spacing holds. Where a stripe meets
  its bus, gaps narrower than the spacing are filled (a closing).
- **`planes`**: the runner layers alternate S, D, S from met3 up, as
  plates over the whole array. On each layer the plate has a hole, with an
  island in it, over every square of the other net whose via stack goes
  higher. The islands sit (spacing + width) in from the square's edges, so
  the plate keeps a neck of a metal width between diagonal holes. S and D
  are then each one net, even with `bus=none`, and LVS runs there too. It
  needs two runner layers, and S and D use different layers.
  `bottom_net` picks the net on met3: `S` (the default) gives S on met3,
  D on met4 and S on met5; `D` gives D on met3, S on met4 and D on met5.
  Each net's top layer is a solid plate, and its lower layers are meshes
  (a plate with a hole and island over each of the other net's squares).

## Extended-drain (LDMOS) devices

`nfet_g5v0d16v0` and `pfet_g5v0d16v0` (10 V gate-drain / 16 V drain) are
drawn as Magic's generator draws a single finger (`sky130A.tcl`
`draw_ldnmos_drain`/`draw_ldpmos_drain`), with every D square as a drift
region:

- The S squares' diffusion stops 0.13 um short of each gate's far edge,
  so each gate is L - 0.13 on diffusion, plus L wide in Magic's reading.
  Diagonal S diffusions are separate islands across the notches.
- Every D square holds a drain tap (TAP layer, n+ or p+) at its centre,
  with the fixed drift to the source diffusion on all four sides: 1.585 um
  (n) or 1.19 um (p). The tap side is P - L - 2 (drift - 0.13).
- EDID (81/57) covers each D square up to the source diffusion's edge,
  without the notches.
- **n-LDMOS:** an n-well per D square, reaching 0.225 um past the
  diffusion edge under the gates. Diagonal D squares' wells are joined
  through every notch by the convex hull of two 0.595 um squares, at least
  nwell.1 wide, because nwell.8 wants separate HV n-wells 2 um apart.
- **p-LDMOS:** a hole in the n-well per D square, reaching 0.26 um past
  the diffusion edge, with corners cut at 45 degrees so the n-well between
  diagonal holes stays 0.84 um wide. With `deep_nwell` (the default), a
  deep n-well under the array makes the holes isolated p-wells. Without
  it the drains sit on the substrate, as in a lone Magic-drawn device.
- **Limits.**
  - Each gate needs W >= 5 um (denmos.2/depmos.2), so P >= N + 5. The
    minimum L is 1.06 um for the n device (1.055 on the 10 nm grid) and
    1.05 um for the p device.
  - For the n device, N is fixed at L + 4 x 0.185 = 1.8 um at L = 1.06.
    Magic regenerates HVNTM (0.185 um around gates and diffusion, then
    bridged to 0.7 um) and flags its own result at the notch corners for
    any other N short of about L + 2.1.
- **HVNTM** (125/20, the MV n tip implant) is now drawn for every
  thick-oxide nfet (5 V and 16 V): the active area grown 0.185 um, minus
  0.185 um around every p-tap. Magic adds it on GDS output, but a GDS taken
  straight to the fab needs it drawn. Versions before 0.6.0 left it out
  of the 5 V nfet.

### Magic extracts extended-drain devices one way round only

With Magic 8.3.685 and the sky130A tech file, an extended-drain device
extracts only when its drift region lies west of a vertical gate or north
of a horizontal one. Turned the other way, the same gate comes out as a
`g5v0d10v5` of length 2L with S on both sides. The PDK's own single-finger
`nfet_g5v0d16v0`, mirrored or rotated by 90 degrees, shows this, as does
Magic's nf=2 device. A waffle has gates facing all four ways, so:

- `verify.extract_ld` extracts the cell as drawn and turned by 180 degrees.
  Each gate faces the working way in exactly one of the two.
- It merges the right devices from both into one netlist, which netgen
  compares as usual. It also checks that the other devices number exactly
  the gate count.
- A flow that extracts the layout once with Magic (Efabless-style
  precheck LVS, for example) will report half the LDMOS gates wrong. That
  is Magic's limit, not the layout's; it needs a fix in Magic's extraction.

## Verification

`verify.py` runs three checks on a GDS:
- the PDK's KLayout deck (feol, beol and offgrid on; floating_met and seal
  off);
- Magic's `drc(full)`;
- Magic extraction followed by netgen LVS, against a schematic of one device
  of W = W_total and L = L.

It also checks every extracted device directly: the model, L, S ≠ D, the
gate on G, and the sum of W.

`tests/power/test_waffle.py` runs this on 15 cases. All are clean in both
DRC decks and match in LVS ("Circuits match uniquely"), with body S, or B
without source taps. `bus=none` is the exception: LVS is skipped there (see
below). The cases:
- nfet and pfet 3x3;
- `frame_only`;
- nfet and pfet 5 V;
- pfet lvt at L 0.35 and nfet lvt at P 3;
- pfet hvt at L 0.3;
- a one-column array;
- met3+met4+met5 at P 6;
- met3 only;
- `bus=none`;
- a wider notch and bus;
- a 1 um tap;
- no source taps.

The 10 x 10 default is checked too: clean in both decks and matching in
LVS, with 180 devices.

## Limits

- **Latch-up.** The source-square taps keep every diffusion within about
  3 um of a tap, so Magic's LU.2/LU.3 (15 um) pass at any size. A 16 x 16
  array with 480 gates is clean.
  - With `source_taps=False` (body on its own pin B), only the guard ring
    taps, and the array's centre lies nx P / 2 + about 1 um from it. The
    10 x 10, P = 4 default is then 20.8 um, and Magic flags LU.2.
  - The generator reports the distance (`lu_max_um`, `lu_ok`), and the
    PCell form puts a warning icon on nx and ny.
- **met5 runners.** A via4 must land on the grid inside the 45 degree
  stripe, so met5 needs about P ≥ 5.8 um, more than the 4.53 um that width
  and spacing alone suggest. Below that, the generator refuses with the
  reason.
- **`bus=none`.** Each stripe is its own net until the top level connects
  them, so LVS against one device doesn't apply. Magic names repeated labels
  `S_uq0`, `D_uq0` and so on. Every device still joins one S stripe to one
  D stripe.
- **`diag45` at a large pitch.** The 45 degree stripes are kept under 3 um
  wide. Wider ones (P >= 6.6 um before 0.6.0) made Magic's met3.3c/met4.5a
  wide-metal halo flag their square caps.
- **45 degree FETs.** A rotated waffle (45 degree gates, so the runners
  could be horizontal and vertical) needs 45 degree poly and diffusion.
  sky130A's x.2 allows only 0/90 there (`rules.PDKS["sky130A"]
  ["allows_45_fet"]` is False); gf180mcu (PL.7) and IHP SG13G2 (Gat.g)
  allow it, so it belongs with those ports.
- **20 V devices** (nfet_20v0, pfet_20v0). sky130A has no generator for
  them, only fixed RF cells. Magic extracts no device from those cells
  (`rf_nfet_20v0_withptap`, `rf_pfet_20v0_withptap`), and they aren't
  clean in Magic's DRC, so a 20 V waffle couldn't be verified with this
  flow.
- **PDKs.** sky130A only. gf180mcu goes into `rules.PDKS` as another entry
  later.

`tools/power/gate_resistance.py <gds> <cell>` (Magic's extresist on the
gate net) works on any HW_FET GDS. Its figures for the version 0.2 device
no longer apply and haven't been redone for this one.
