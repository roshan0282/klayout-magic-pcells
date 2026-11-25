#!/bin/sh
# The plugin test suites in the pinned image, besides tests/power (parity.yml's
# power job runs that one):
#   tests/centroid      CC_ARRAY: pattern core, placement, routing with Magic + netgen LVS
#   tests/gen           sky130_gen / gf180mcu_gen guard rings and via stacks
#   tests/lvs           the PDKs' KLayout LVS decks on PCell inverters and routed arrays
#   tests/live_verify   live DRC: clipping, tier 0, the PDK deck as tier 1
# The image carries every PDK, so the gf180mcuD tests in these suites
# (test_gf180.py, the gf180mcuD inverter) run in the same job; each one skips
# only if its PDK files are missing.
exec "$(dirname "$0")/in_image.sh" 'set -e
export KMP_PDK=sky130A KMP_PDKS=sky130A
for s in centroid gen lvs; do
  echo "== tests/$s"
  python3 -m unittest discover -s tests/$s -t . "$@"
done
echo "== tests/live_verify"
python3 tests/live_verify/run.py' "$@"
