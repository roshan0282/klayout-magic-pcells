# sky130_gen / gf180mcu_gen: supporting generators

`python/klayout_gen` registers one KLayout library per PDK, `sky130_gen`
and `gf180mcu_gen` (autorun macro `pymacros/klayout_gen.lym`). Its generators draw from raw layers and
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

Limits: shapes must be Manhattan (tap is 0/90 degrees only in both PDKs).
Deep n-well rings are sky130A only.

## VIA_STACK

A via stack from any metal to any higher one (li, met1 to met5).

| Parameter | Meaning |
|---|---|
| Bottom metal, Top metal | the span, e.g. li to met5 |
| Width, Height | the stack's size; 0 = the smallest that holds one cut of every layer and meets every metal's width and area (met5: 1.6 um, 4 um²) |
| DC current | 0 = no EM sizing; otherwise every cut layer gets at least ceil(I / I_cut) cuts, and a stack of size 0 grows until it has them |
| EM limit per cut | I_cut in mA |
| Label | text on the bottom and top metals |

- **Shape.** Every metal is one rectangle. Every cut layer is the largest
  centred array that fits, using the larger of its two metals'
  enclosures on all sides.
- **EM limits.** sky130A has no EM table here. The open PDK publishes the
  guideline (rule x.4) but no numbers, so a current needs **EM limit per
  cut**. The table `em_ma_per_cut` in `python/klayout_gen/rules.py` is
  where the foundry's values go.
- **Result line.** It shows the size and every cut array.

Checked by `tests/gen/test_via_stack.py`: li–met1, met1–met2, li–met5, a
4 x 1.5 um met1–met3 stack and a met2–met4 stack sized for 3 mA at
0.25 mA per cut are all clean in the KLayout deck and Magic DRC.

## gf180mcuD

`gf180mcu_gen` has the same two PCells:

- **Rules.** They are in `rules.py` (`GF180MCUD`): COMP 0.22/0.28,
  Contact 0.22 at 0.25 with 0.07 COMP enclosure, Nplus/Pplus 0.16 around
  COMP, n-well 0.12 around an n-tap and at least 0.86 wide, Metal1-4 and
  Via1-3.
- **No li.** The ring's contacts land on Metal1 directly, so the ring
  always has Metal1.
- **Via stacks.** They span met1 to met4.

`tests/gen/test_gf180.py` runs every case through the PDK's
`gf180mcu.drc` (decks=all,-density, variant D) and Magic's gf180mcuD
DRC: p-tap, n-tap and L-shaped rings, and met1-met2, met1-met4 and a
3 x 1.2 um met1-met3 stack are clean in both. A negative control (a
0.1 um Metal1 wire) fails M1.1 in both, which shows the deck runs.
