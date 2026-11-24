# Gap tables

One table per PDK compares Magic's DRC rules with the PDK's KLayout DRC decks and shows where they disagree. `tools/build_gaps.py` generates the tables in the pinned Docker image (`scripts/in_image.sh`). `scripts/gaps.sh` rebuilds all four; `scripts/gaps.sh --check` fails when a table would change, for example after a PDK or Magic update. The alias files `tests/gaps/aliases-<pdk>.json` are the only part typed by hand.

In the table below, each status column counts the rules with that status, `rules` is their total, and `cases` is the number of test cases in the PDK's `gaps` set. Each page says what the statuses mean.

| PDK | both | both, values differ | folded | measured on other shapes | same name for another check | in the deck, did not fire on its case | Magic only | KLayout only | rules | cases |
|---|---|---|---|---|---|---|---|---|---|---|
| [sky130A](sky130A.md) | 72 | 2 | 5 | 0 | 2 | 11 | 93 | 213 | 398 | 130 |
| [gf180mcuD](gf180mcuD.md) | 89 | 9 | 2 | 2 | 1 | 6 | 38 | 421 | 568 | 69 |
| [ihp-sg13g2](ihp-sg13g2.md) | 199 | 0 | 12 | 0 | 0 | 4 | 17 | 151 | 383 | 151 |
| [ihp-sg13cmos5l](ihp-sg13cmos5l.md) | 143 | 0 | 10 | 0 | 0 | 3 | 12 | 129 | 297 | 49 |

Each page also has a `.json` file with the same rows. The plugin's DRC check (`drc`) reads `python/klayout_magic_pcells/data/gaps-<pdk>.json`, built at the same time, for the descriptions of its report categories.
