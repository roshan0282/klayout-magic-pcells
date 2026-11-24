# Hybrid-waffle nfet (klayout_power_pcells, milestone 1)

A sky130A `nfet_01v8` power FET in the hybrid-waffle (HW) layout of Yoo,
Chang, Trescases and Ng, "High Performance Low-Voltage Power MOSFETs with
Hybrid Waffle Layout Structure in a 0.25 um Standard CMOS Process" (ISPSD
2008). Every device in it is Magic's own `sky130_fd_pr__nfet_01v8`, drawn
through this repository's `sky130_magic` library; every via and the tap ring
are Magic's box-paint generators (`via1` to `via4`, `subconn_guard`).

```sh
KMP_PDKS=sky130A PYTHONPATH=python python3 -m klayout_power_pcells hw \
    --l 0.5 --w 2 --nf 3 --nx 3 --ny 3 --strap 3 -o hw.gds
# HW 3x3, pitch 7.830 um, 12 blocks x nf 3 = 36 fingers of W 2.000 L 0.500, total W 72.000 um, strap 3.012 um
```

From Python: `klayout_power_pcells.write_gds(HWParams(...), path)` or
`generate(layout, HWParams(...))`, which return an `HWResult` with the pitch,
the number of blocks and devices, and the total W.

## Geometry

| Parameter | Meaning |
|---|---|
| `l`, `w` | gate length and width of one finger (um) |
| `nf` | fingers per cell: the `nf` of the nfet on each internal tile edge |
| `nx`, `ny` | tiles per row and column (N x M) |
| `strap_w` | width of the 45 degree S/D straps, perpendicular (um) |
| `pitch` | tile pitch (um); default the smallest that fits |

- **Tiles.** An N x M checkerboard. Tile (i, j) is a source tile when i + j
  is even, so every internal edge separates S from D. A tile's interior is a
  met2 plate with a via2/via3/via4 stack in the middle; it has no active
  area (the "hybrid" part: area traded for wide metal).
- **Unit cell (block).** Each of the (N-1)M + N(M-1) internal edges holds one
  Magic nfet (`guard 0`), centred on the edge, fingers parallel to it: as
  drawn on vertical edges, rotated 90 degrees on horizontal edges, so each
  tile is ringed by the same block in four orientations.
- **Source/drain.** The block's S/D strips alternate between its two tiles.
  A met2 comb crosses the block: lines alternate between the tiles, each
  with a via1 on its own tile's strips only, and runs into that tile's plate.
- **Straps.** met3, met4 and met5, stacked, at 45 degrees through the tile
  centres. Diagonal neighbours share a type, so one strap joins all tiles of
  a diagonal, and S and D straps alternate. S straps run up/right into an L
  bus (top, right), D straps down/left into the D bus (left, bottom). Where a
  strap meets a bus, a 1.7 um triangle fills the 45 degree notch.
- **Gate.** met1: a bar over each row of gate-contact pads, a spine to the
  grid crossing, a rail beside each block joining its two crossings, and a
  ring along the array's outer grid lines. The rails matter below
  L ~0.33 um, where Magic contacts each finger at one end only.
- **Substrate.** A `subconn_guard` tap ring 0.5 um outside the tile array.
- **Labels.** `S` and `D` on the met5 buses, `G` on met1 at a crossing, `B`
  on the ring's li. Magic's own port labels in the unit nfet are removed.

The paper reserves metal 2 for the gate mesh. Here met2 carries the S/D
combs and plates, and the gate mesh is on met1.

## Limits (milestone 1)

- At least two tiles; finger W >= 0.92 um (two comb lines); strap width >=
  2.4 um. Below 2.4 um, Magic's met3.3c / met4.5a (spacing within the halo of
  metal wider than 3 um) fire where the straps meet the buses: 2.2 and 2.3
  failed and 2.4 to 3.5 passed on 2x2, 3x3 and 2x3 grids.
- Taps only around the array: the generator refuses an array in which
  n-diff would lie more than 14.5 um from the ring (Magic's LU.2 allows
  15 um). With W = 2 um, L = 0.5 um, nf = 3 (pitch 7.83 um) that is 4x4
  tiles: 4x4 is clean, 5x4 is refused, and 5x5 drawn without the check fails
  LU.2 in Magic.
- Only sky130A `nfet_01v8`. KLayout's sky130A DRC deck has not been run on
  it; only Magic's `drc(full)`.

## Test

`tests/power/test_hybrid_waffle.py` uses the parity harness's runners
(`tests/parity/drc.py`): `run_magic_drc` must return no errors, and
`run_magic_extract` must give blocks x nf devices of
`sky130_fd_pr__nfet_01v8`, each with Magic's checked W and L, summing to the
total W, with every gate on `G`, every source/drain on `S` and `D` and every
bulk on `B`. It covers six configurations: nf 1 to 5, L 0.15 to 0.5 um, a
set pitch, and a one-row array.

```sh
KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
```

In development, 48 further configurations (random L, W, nf, grid, strap
width and pitch) were also DRC clean and extracted correctly.
