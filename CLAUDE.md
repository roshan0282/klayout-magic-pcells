# klayout-live-verify

KLayout Salt package adding live DRC and LVS to KLayout, with Magic + netgen as
signoff backends. Sits next to `../klayout-magic-pcells` (Magic-backed device PCells)
and reads the same config (`KMP_PDKS`, `KMP_MAGIC`, `PDK_ROOT`).

## Environment
- Runs inside the IIC-OSIC-TOOLS container. `/foss/designs` is the only persistent dir.
- Switch PDK: `iic-pdk sky130A` / `iic-pdk gf180mcuD` (sets `PDK`, `PDK_ROOT`, `KLAYOUT_PATH`).
- Launch GUI with packages linked: `/foss/designs/dev-klayout.sh`.
- Tools on PATH: klayout, magic, netgen, xschem, ngspice.

## Layout
- `python/live_verify/` – library code (runner, drc tiers, lvs, ui)
- `pymacros/` – autorun macros that register the dock panel and menu entries
- `tests/` – headless tests, run with `klayout -b -r tests/run.py`

## Design rules
- One long-lived Magic per PDK (`magic -dnull -noconsole`), fed Tcl on stdin. Never spawn per check.
- All external processes async (QProcess); never block the GUI thread.
- Write temp GDS inside the container FS, not on Windows mounts.
- Results go to one `.lyrdb`, tagged by tier (0 = in-process Region, 1 = PDK KLayout deck, 2 = Magic).
- LVS default backend: Magic extract -> ext2spice lvs -> netgen -batch lvs; reference netlist from xschem `.spice`.

## Milestones
1. Runner + Magic DRC on demand (smoke test: sky130 inverter)
2. Tier 0/1 live DRC with dirty-area clipping
3. Full netgen LVS + dock panel (good inverter passes, shorted copy fails)
4. Fast connectivity check; KLayout LVS backend for gf180/IHP
5. Parity tests using klayout-magic-pcells' fixture cells

## Testing
Every change must pass `klayout -b -r tests/run.py` for sky130A before committing.
