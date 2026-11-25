<!-- repo: fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pv -->
<!-- title: KLayout DRC: Mn.2b (space to wide metal) misses two wide metals -->

`Mn.2b` ("Space to wide Metal (length & width > 10um): 0.3µm") does not flag two wide metal shapes that are closer than 0.3 µm. It only fires when one of the two shapes is narrow.

**Where:** `klayout/drc/rule_decks/metal.rb`, lines 52-62 at 0df548b (the same file is in the gf180mcuD install of open_pdks):

```ruby
wide_m = metal_drawn.sized(-5.um, 0.um).sized(0.um, -5.um).sized(5.um, 0.um).sized(0.um, 5.um).and(metal_drawn)
m2b_l1 = metal_drawn.separation(wide_m, 0.3.um, euclidian, without_touching_edges)
```

**Repro** (KLayout 0.30.14, `gf180mcu.drc`, variant D, `decks=metal`): Metal1 (34/0), 0.25 µm gaps:

| Case | Shapes | M1.2b |
|---|---|---|
| wide / wide | two 10.5 × 10.5 µm squares | not reported |
| wide / wide | two 20 × 20 µm squares | not reported |
| wide / narrow | a 10.5 × 10.5 µm square and a 1 × 10.5 µm strip | reported |

```python
import klayout.db as db
ly = db.Layout(); ly.dbu = 0.001
top = ly.create_cell("TOP"); m1 = ly.layer(34, 0)
for ox, boxes in ((0, [(0, 0, 10.5, 10.5), (10.75, 0, 21.25, 10.5)]),
                  (40, [(0, 0, 10.5, 10.5), (10.75, 0, 11.75, 10.5)]),
                  (80, [(0, 0, 20, 20), (20.25, 0, 40.25, 20)])):
    for x1, y1, x2, y2 in boxes:
        top.shapes(m1).insert(db.DBox(ox + x1, y1, ox + x2, y2))
ly.write("m2b.gds")
# klayout -b -r gf180mcu.drc -rd input=m2b.gds -rd topcell=TOP -rd report=m2b.lyrdb -rd variant=D -rd decks=metal
```

Only the middle case (x = 40) gets an `M1.2b` marker.

**Cause:** shielding. Each wide polygon is in both inputs of `separation`, so the edge of `metal_drawn` that coincides with the `wide_m` edge shields it from the neighbour. The same thing with the Region API:

```python
m = db.Region([db.Box(0, 0, 10500, 10500), db.Box(10750, 0, 21250, 10500)])   # dbu 1 nm
w = m.sized(-5000, 0, 2).sized(0, -5000, 2).sized(5000, 0, 2).sized(0, 5000, 2) & m
m.separation_check(w, 300, False, db.Metrics.Euclidian, None, None, None, True).count()   # 0 (shielded, the default)
m.separation_check(w, 300, False, db.Metrics.Euclidian, None, None, None, False).count()  # 2
```

**Suggested fix:** turn shielding off for this check:

```ruby
m2b_l1 = metal_drawn.separation(wide_m, 0.3.um, euclidian, without_touching_edges, transparent)
```

(This reports the wide/wide pair from both sides; alternatively, `metal_drawn.space(0.3.um, euclidian)` filtered to the pairs that touch `wide_m`.) The same pattern may be in other rules that check a layer against a derived subset of itself; I only looked at Mn.2b.

Found while checking the design-rule values of a generator package against this deck with minimum-size probes.
