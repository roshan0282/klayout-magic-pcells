# The shared rule table (`pdk_rules`)

Roadmap Phase 0.3. Until version 0.9 four modules carried their own copies of the
same design rules: `klayout_power_pcells/rules.py` (HW_FET, in nm),
`klayout_gen/rules.py` (GUARD_RING, VIA_STACK), `klayout_centroid/rules.py`
(CC_ARRAY spacing and router) and `live_verify/pdk.py` (tier-0 width/space).
They now all read one table per PDK:

| File | Content |
|---|---|
| `python/pdk_rules/sky130A.py` | layers, pin/label layers, metal stack, 107 rules, HW_FET's device list, deck settings |
| `python/pdk_rules/gf180mcuD.py` | layers, pin/label layers, metal stack, 40 rules (3.3 V devices) |
| `python/pdk_rules/mapped.py` | export to gLayout's `MappedPDK` schema |
| `python/pdk_rules/probe.py` | rule probes against the PDK's KLayout DRC deck |

The package is KLayout-free (except `probe`), so scripts can import it without KLayout.

## A rule

```python
"met1_s_wide": R(0.28, "m1.3ab", kind="space", on="met1", wide=3.5, note="metal wider than 3 um"),
```

Each entry is a `Rule`: the value in um (um2 for areas), the rule id as the deck or the
foundry manual names it, where the value was read from (`kl` the KLayout deck, `mg`
Magic's tech file, `cif` Magic's generated layers, `tcl` Magic's device generator,
`drm` the foundry manual, `use` a choice of ours), and, for rules a probe can check,
the probe kind (`width`, `space`, `enc`, `area`, `exact`) and its layers.
`probe_ids` lists the deck's own name when it differs from the manual's.

```python
import pdk_rules
t = pdk_rules.get("sky130A")
t.um("met1_s"), t.nm("met1_s"), t.rule("met1_s").rule   # 0.14, 140, "m1.2"
t.layer("met1"), t.width_space("via")                   # (68, 20), (0.15, 0.17)
```

The four modules keep the dict shapes their code already used: each builds its
dict from the table, picking the keys it needs and mapping its own names (for
example `klayout_gen` calls gf180mcuD's `comp` "tap" and `contact` "licon").
`tests/rules/test_tables.py` checks that the built dicts equal a snapshot of the
hand-written tables they replaced (`tests/rules/legacy_tables.json`), so the move
changed no geometry (and no rule hash in the HW_FET cache stamps).

## Rule probes

`python3 -m pdk_rules.probe <pdk>` draws, for every rule with a probe kind, the
smallest shape the rule allows and the same shape one grid step under the value,
runs the PDK's KLayout deck once on each layout, and reports per rule whether the
deck passed the first and flagged the second under that rule's id. All probes of a
PDK sit in one layout, 40 um apart, so a run takes two deck runs.

Result, Nov 25, 2026 (open_pdks 1689ac3; gf180mcu.drc variant D):

| PDK | Probed | Confirmed |
|---|---|---|
| sky130A | 63 of 107 rules | 63 |
| gf180mcuD | 32 of 40 rules | 32 |

The first run confirmed 57 of 63 sky130A rules. The other six had the right value
under a name the deck doesn't use, and their ids were fixed: dnwell width and
spacing are `dnwell.1`/`dnwell.2` in the deck (the old tables cited `dnwell.1` and
`dnwell.3`), licon spacing is `MR_licon.SP.1`, m1.4 is `791_m1.4`, and the deck
reports nsdm/psdm spacing as `nsdm.1`/`psdm.1` where SkyWater's rules say nsd.2/psd.2.
No value had to change.

Not probed: rules that need a device around them (poly end caps, contact-to-gate,
implant enclosures, LDMOS geometry), one-direction enclosures, and Magic-only rules.
Those are covered by the generators' own DRC tests in the KLayout deck **and** Magic.
A Magic-deck probe is the obvious next step.

## Findings for upstream (add to `docs/upstream-issues.md`)

- **gf180mcu.drc `M*.2b` misses two wide metals.** The rule is "space to wide metal
  (length and width > 10 um): 0.3 um". The deck flags a narrow wire 0.25 um from a
  10.5 um square, but not two 10.5 um (or 20 um) squares 0.25 um apart:
  `separation(metal_drawn, wide_m)` reports nothing when the neighbour is wide too.
  The probe uses one wide and one narrow shape for this reason.
- **gf180mcuD n-well spacing depends on connectivity.** NW.2a (0.6 um) applies only
  to n-wells on one net; two unconnected n-wells get NW.2b (1.4 um). CC_ARRAY merges
  n-wells closer than 0.6 um, so it never relies on NW.2a between separate wells.
  The table keeps both (`nwell_s`, `nwell_s_diff`); only NW.2b is probed.
- **sky130A deck numbering.** nsdm/psdm spacing is reported as `nsdm.1`/`psdm.1` and
  their widths as `nsdm.2`/`psdm.2`, the reverse of SkyWater's nsd.1 (width) and
  nsd.2 (spacing). This makes deck results hard to match against the manual.

## gLayout export

`pdk_rules.mapped.glayout(pdk)` returns `{"glayers": ..., "grules": ...}` in
gLayout's `MappedPDK` schema (`grules[a][b]` with `min_width`, `min_separation`,
`min_enclosure`, `width`; values in um). It follows gLayout's sky130 naming, where
the metal names are shifted by one (gLayout's `met1` is li1, `mcon` is licon,
`via1` is mcon), so the dicts can be passed to `MappedPDK` as they are. Its values
agree with gLayout's own sky130 table where both have a rule (li 0.17/0.17, mcon
0.17/0.19, licon enclosures 0.08/0.05/0.06, met1 enclosure of mcon 0.06).

## Adding a PDK

Write `python/pdk_rules/<pdk>.py` with the same module variables (`NAME`, `GRID`,
`LAYERS`, `PIN`, `LABEL`, `STACK`, `RULES`, `DEVICES`, `MODEL_PREFIX`,
`ALLOWS_45_FET`, `ALLOWS_45_METAL`, `DRC_DECK`, `EM_MA_PER_CUT`), add it to `NAMES`,
give each rule a probe kind where one applies, and run `python3 -m pdk_rules.probe`
until every rule is confirmed. Then add the PDK to the adapters that should support it.
