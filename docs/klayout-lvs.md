# LVS with the PDKs' KLayout decks

Roadmap Phase 0.4. Magic extraction + netgen LVS has worked from KLayout since
version 0.6; this note records what it takes to run the PDKs' **own KLayout LVS
decks** on layouts built from this package's PCells, and the helper that does it.

## Result (Nov 25, 2026, KLayout 0.30.14, the PDKs in IIC-OSIC-TOOLS)

| Layout | PDK | Deck | Result |
|---|---|---|---|
| PCell inverter of the case suite (`tests/cases`, `pcell_inverter`) | sky130A | `sky130.lvs` | match |
| PCell inverter (nfet_03v3 W 1, pfet_03v3 W 2, L 0.28) | gf180mcuD | `gf180mcu.lvs` (variant D) | match |
| CC_ARRAY diff pair `A:4,B:4`, routed, tapless units | sky130A | `sky130.lvs` | match |
| CC_ARRAY separate-source pair, dummies tied to `DUM` | sky130A | `sky130.lvs` | match |
| CC_ARRAY 1:3 pfet mirror, symmetric pattern | sky130A | `sky130.lvs` | match |

Each case also has a negative control that must fail: a doubled pfet W
(sky130A inverter), X-prefixed devices (gf180mcuD inverter, see below) and one A unit
whose gate is moved to `B_G` (diff pair). The array cases are the ones netgen
matches in `tests/centroid/test_router.py`, so both LVS engines now agree on them.

Not tried yet: HW_FET (180 parallel devices, deep n-well, LDMOS), gf180mcuD routed
arrays (the router is sky130A-only), and the IHP decks.

## Settings the decks need

Neither deck works on these schematics with its defaults. All four points are in
`verify.KLAYOUT_LVS`:

1. **sky130A: `convert_subckts=true`.** xschem's sky130 symbols keep the `X` prefix
   in LVS netlists (`XM1 … sky130_fd_pr__nfet_01v8`), because the models are
   subcircuits. The deck turns those into devices only with this flag; without it
   the reference circuit is **empty** and every net mismatches.
2. **sky130A: W and L without units.** xschem writes `w=0.65 l=0.15`, which the
   reader takes as metres unless the netlist sets `.option scale=1e-6` (the
   simulation models set it, LVS netlists don't include them).
   `klayout_lvs` prepends the option in a copy when the schematic has none.
3. **gf180mcuD: `M` elements, units on W/L.** The deck's reader has no `X`-to-device
   conversion. xschem's gf180mcu symbols already write `M1 … nfet_03v3 L=0.28u W=1u`
   through their `lvs_format`; a schematic with `XM1` fails (this is the negative
   control).
4. **Both: `schematic_simplify=true`.** The decks combine parallel devices on the
   extracted side (CC_ARRAY's 8 dummies become one W 41.6 device), but not in the
   schematic unless this is on.

Plus, for tapless units: the deck names the substrate `sky130_gnd` (sky130A).
When the schematic ties bulks to Magic's `VSUBS` without making it a pin, pass
`substrate="VSUBS"` (the deck's `lvs_sub`).

## Use

```python
from klayout_power_pcells import verify
ok, info = verify.klayout_lvs("cc_dp.gds", "cc_dp", "cc_dp.spice", "work/", pdk="sky130A", substrate="VSUBS")
# info: report (.lvsdb, open it in KLayout's netlist browser), extracted, circuits, log
```

Tests: `python3 -m unittest discover -s tests/lvs -t .` (about 35 s; skips a PDK
whose deck is missing).

## What this means for the plan

- The KLayout decks are usable as a **second LVS engine** next to Magic + netgen, and
  their `.lvsdb` opens in KLayout's netlist browser with cross-highlighting, which is
  what the Phase 5 LVS debug aids need.
- The SDL plugins (Phase 3) produce netlists from xschem, so the import path must
  apply the same per-PDK settings (X conversion, scale) or the decks will report
  empty references.
- The four settings are upstream material: the sky130A deck could default
  `convert_subckts` on, and either deck could read `.option scale` from the models.
  Add them to `docs/upstream-issues.md` when the drafted issues are filed (Phase 0.7).
