# Hybrid-waffle power MOSFET (klayout_power_pcells)

A sky130A power MOSFET in the hybrid-waffle (HW) layout of Yoo, Chang,
Trescases and Ng, "High Performance Low-Voltage Power MOSFETs with Hybrid
Waffle Layout Structure in a 0.25 um Standard CMOS Process" (ISPSD 2008).
Every transistor in it is one of Magic's own sky130A MOSFETs, drawn through
this repository's `sky130_magic` library. Every via, tap and well ring comes
from Magic's box-paint generators: `via1` to `via4`, `mcon`, `subconn`,
`mvsubconn`, `subconn_guard`, `mvsubconn_guard`, `nwell` and `mvnwell`.

Milestone 1 added the nfet_01v8 generator. Milestone 2 added:
- the other symmetric MOSFETs;
- taps inside the array;
- the KLayout PCell;
- a measurement of the gate resistance.

```sh
KMP_PDKS=sky130A PYTHONPATH=python python3 -m klayout_power_pcells hw \
    --device sky130_fd_pr__pfet_01v8 --bulk source --l 0.5 --w 2 --nf 3 --nx 6 --ny 6 -o hw.gds
```

From Python, call `klayout_power_pcells.write_gds(HWParams(...), path)` or
`generate(layout, HWParams(...))`. Both return an `HWResult` with the pitch,
the number of blocks and devices, and the total W.

## The PCell

`klayout_power_pcells.register()` registers the KLayout library
`sky130_power`, which has one PCell, `HW_FET`. In KLayout,
`pymacros/klayout_power_pcells.lym` (autorun) does the same. When the repository
is a Salt package, both libraries appear in the GUI. In batch, name both
macros:

```sh
klayout -b -rm pymacros/klayout_magic_pcells.lym -rm pymacros/klayout_power_pcells.lym -r script.py
```

The PCell takes the parameters below; `pitch = 0` picks the minimum. Its
geometry is exactly what `write_gds` draws for the same values. Parameters
the generator refuses draw a marker on 255/0, carrying the reason as text,
instead of raising, as klayout-magic-pcells does. Each KLayout process
keeps its 16 most recent variants in memory.

## Parameters

| Parameter | Meaning |
|---|---|
| `device` | one of `DEVICES` (below) |
| `bulk` | `ring`: tap ring around the array, body pin `B`. `source`: a tap in every source tile, body tied to `S` |
| `l`, `w` | gate length and width of one finger (um) |
| `nf` | fingers per cell: the `nf` of the MOSFET on each internal tile edge |
| `nx`, `ny` | tiles per row and column (N x M) |
| `strap_w` | width of the 45 degree S/D straps, perpendicular (um) |
| `pitch` | tile pitch (um); default the smallest that fits |

`DEVICES` lists Magic's sky130A MOSFETs whose source and drain are
interchangeable, which the waffle needs:
- nfet: `nfet_01v8`, `nfet_01v8_lvt`, `nfet_03v3_nvt`, `nfet_05v0_nvt`,
  `nfet_g5v0d10v5`;
- pfet: `pfet_01v8`, `pfet_01v8_lvt`, `pfet_01v8_hvt`, `pfet_g5v0d10v5`;
- all with the `sky130_fd_pr__` prefix.

The drain-extended `g5v0d16v0` FETs are asymmetric and are refused, as is
the SONOS cell.

## Geometry

- **Tiles.** An N x M checkerboard. Tile (i, j) is a source tile when i + j
  is even, so every internal edge separates S from D. A tile's interior is a
  met2 plate with a via2/via3/via4 stack in the middle. It has no active
  area: that is the "hybrid" part, area traded for wide metal.
- **Unit cell (block).** Each of the (N-1)M + N(M-1) internal edges holds one
  Magic MOSFET (`guard 0`), centred on the edge with its fingers parallel to
  it. Vertical edges get it as drawn and horizontal edges rotated 90 degrees,
  so each tile is ringed by the same block in four orientations.
- **Source/drain.** The block's S/D strips alternate between its two tiles.
  A met2 comb crosses the block. Its lines alternate between the tiles; each
  line has a via1 on its own tile's strips only and runs into that tile's
  plate.
- **Straps.** Stacked met3, met4 and met5 at 45 degrees through the tile
  centres. Diagonal neighbours share a type, so one strap joins all the tiles
  of a diagonal, and S and D straps alternate.
  - S straps run up and right into an L-shaped bus (top and right); D straps
    run down and left into the D bus (left and bottom).
  - Where a strap meets a bus, a 1.7 um triangle fills the 45 degree notch.
- **Gate.** On met1:
  - a bar over each row of gate-contact pads;
  - a spine from the bar to the grid crossing;
  - a rail beside each block joining its two crossings;
  - a ring along the array's outer grid lines.

  The rails matter below L ~0.33 um, where Magic contacts each finger at one
  end only.
- **Wells and implant layers.** Magic draws nwell, hvi, lvtn, hvtp and the id
  layers per device. Here they are drawn once over the whole array instead,
  so neighbouring blocks' copies never leave a gap narrower than their
  spacing rule. nsdm and psdm stay per block.
- **Body, `bulk="ring"`.** A ring 0.5 um outside the tile array. It is
  Magic's `subconn_guard` for nfets, or `mvsubconn_guard` for 5 V nfets
  (`hvi`); for pfets it is `nwell` or `mvnwell`, which is an n-well over the
  array with an n-tap ring. A 2 um `mcon` on the bottom side carries the met1
  `B` pin, and it is also what makes the n-tap metal-connected for Magic's
  `nwell.4`. Magic's latch-up rules then limit the array size (see Limits).
- **Body, `bulk="source"`.** Every source tile gets a tap that fills the tile
  interior. It is Magic's `subconn` or `mvsubconn` for nfets; for pfets it is
  the same contact with nsdm in place of psdm, since Magic has no n-tap
  box-paint generator. A 1 um `mcon` and `via1` at the centre tie it to the
  tile's met2 plate. Every block touches a source tile, so every diffusion is
  within about one block width of a tap, at any array size. The body is S.
  For an nfet that means S must be the substrate potential (ground). For a
  pfet in its n-well, it is the usual high-side connection.
- **Labels.** `S` and `D` sit on the met5 buses, `G` on met1 at a crossing,
  and `B` on the ring's met1 (ring mode only). Magic's own port labels in the
  unit device are removed.

The paper reserves metal 2 for the gate mesh. Here met2 carries the S/D
combs and plates, so the gate mesh is on met1.

## Gate resistance

`tools/power/gate_resistance.py <gds> <cell>` runs Magic's resistance
extraction (`extresist`) on the gate net and solves the resulting network.
Magic skips nets with no source/drain on them, so `tools/power/extresist.tcl`
first turns the labels into ports. The tool prints:
- the resistance from G to each finger;
- G to all fingers tied together;
- the Elmore-equivalent series resistance for equal gate capacitance per
  finger (tau = R x C_gate,total).

Magic's sky130A extraction values set what matters:
- li: 12.8 ohm/sq;
- met1: 0.125 ohm/sq;
- poly: 48.2 ohm/sq;
- poly contact: 152 ohm;
- mcon: 9.3 ohm.

Measured on 3x3 nfet_01v8 arrays (Elmore-equivalent gate R, ohm):

| Case | R per finger | met1 rails 0.4 um (as drawn) | + li mesh under the met1, mcon-stitched | met1 rails 0.8 um |
|---|---|---|---|---|
| L 0.5, W 2, nf 3 | 143-145 | 5.52 | 5.48 (-0.7 %) | 4.79 (-13 %) |
| L 0.15, W 1.5, nf 2 | 462-465 | 20.49 | 20.41 (-0.4 %) | 19.87 (-3 %) |
| L 0.15, W 4, nf 6 | 864-869 | 14.03 | 14.00 (-0.2 %) | 13.07 (-7 %) |

- **li meshed with met1 is not worth having.** li's sheet resistance is
  about 100 times met1's, so in parallel it lowers the mesh resistance by
  about 1 %, and the whole gate resistance by under 1 %. The prototype also
  needed extra DRC work at its stitches (`met1.2`, `mcon.1`). It was taken
  out again.
- **Each finger's own poly and poly contact dominate.** The spread between
  the best and the worst finger is 1 to 5 ohm, against 143 to 869 ohm per
  finger. Below L ~0.33 um Magic contacts each finger at one end only, which
  is why those fingers are 3 to 6 times worse.
- **Better levers:**
  - L >= 0.33 um, so both finger ends are contacted;
  - shorter fingers (smaller W, more nf);
  - wider met1 rails, which cost pitch: 0.8 um rails cost 0.8 um of pitch
    and save 3-13 %.

## Limits

- At least two tiles.
- Finger W >= 0.92 um, so each block fits two comb lines.
- Strap width >= 2.4 um. Below that, Magic's met3.3c / met4.5a (spacing
  within the halo of metal wider than 3 um) fire where the straps meet the
  buses: 2.2 and 2.3 um failed, and 2.4 to 3.5 um passed, on 2x2, 3x3 and 2x3
  grids.
- `bulk="ring"`: the generator refuses an array in which diffusion would lie
  more than 14.5 um from the ring (Magic's LU.2 and LU.3 allow 15 um).
  - With nfet_01v8 at W = 2 um, L = 0.5 um, nf = 3 (pitch 7.83 um), that
    allows up to 4x4 tiles.
  - A 5x5 drawn without the check fails LU.2 in Magic.
  - Use `bulk="source"` for larger arrays.
- KLayout's sky130A DRC deck has not been run on these layouts, only Magic's
  `drc(full)`.

## Tests

`tests/power/test_hybrid_waffle.py` uses the parity harness's runners
(`tests/parity/drc.py`) on 13 configurations:
- nf 1 to 6 and L 0.15 to 1.5 um;
- a set pitch and one-row arrays;
- pfet, 3.3 V and 5 V devices;
- both body modes, up to 6x6 tiles.

For each configuration:
- `run_magic_drc` must return no errors;
- `run_magic_extract` must give blocks x nf devices of the chosen model,
  each with Magic's checked W and L, summing to the total W;
- every gate must be on `G`, every source/drain on `S` and `D`, and every
  body on `B` (ring) or `S` (source).

It also checks that bad parameters are refused.

`tests/power/test_pcell.py` checks that:
- the PCell's geometry is identical (by XOR) to `write_gds`;
- a placed pfet is DRC clean and extracts correctly;
- the parameters and geometry survive a GDS save and reopen;
- refused parameters draw the error marker;
- the autorun macros work under `klayout -b`.

```sh
KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
```

During development, these also came out DRC clean and extracted correctly:
- all 9 devices in both body modes;
- 50 random configurations: device, body, L, W, nf, grid, strap width and
  pitch;
- source-body arrays of 8x7 tiles.
