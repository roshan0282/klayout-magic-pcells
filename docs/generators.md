# sky130_gen: supporting generators

`python/klayout_gen` registers the KLayout library `sky130_gen` (autorun
macro `pymacros/klayout_gen.lym`). Its generators draw from raw layers and
need nothing but KLayout. They come from Phase 3 of
`/foss/designs/plan/roadmap.md`.

## GUARD_RING

A tap ring that follows any Manhattan outline: a box, a polygon (L, U,
with notches) or a path. The tap ring sits outside the outline at
**Clearance**.

| Parameter | Meaning |
|---|---|
| Outline to enclose | box, polygon or path; or select a drawn shape and use Edit > Selection > Convert To PCell |
| Tap | `ptap` (psdm; around nfets, ties the substrate) or `ntap` (nsdm and an n-well ring at least 0.84 um wide) |
| Ring width | 0 = 0.41 um, the narrowest that holds a licon with 0.12 um enclosure |
| Clearance | from the outline to the ring's inside edge |
| met1 | mcon and met1 over the ring (otherwise li only) |
| Deep n-well | `ntap` only: a dnwell under the inside, with the n-well ring 0.4 um past its edge and 1.03 um inside (nwell.5a, nwell.6). The p-well inside is isolated |
| Pin name | li/met1 pin and label (`B`) |

Contacts sit on the ring's centre line at the minimum pitch. Each is
checked for enclosure by the tap and for spacing from the others, so
inside and outside corners stay clean.

Checked by `tests/gen/test_guard_ring.py`:

- **DRC.** Boxes, an L, a U, a path, an `ntap` U with a 0.6 um ring, an
  li-only ring and a deep n-well ring are all clean in the PDK's KLayout
  deck and in Magic's DRC.
- **As a body tap.** A tapless `sky130_magic` nfet inside a p-tap ring is
  Magic-DRC clean, so the ring satisfies the latch-up rules. Magic
  extracts both fingers with body `B`.

Limits: sky130A only. Shapes must be Manhattan, because sky130 tap is 0/90
degrees only.
