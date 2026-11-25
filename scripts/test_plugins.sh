#!/bin/sh
# The centroid (CC_ARRAY) and sky130_gen/gf180mcu_gen test suites in the
# pinned image: pattern core, placement, routing with Magic + netgen LVS,
# guard rings and via stacks through the sky130A and gf180mcuD decks.
exec "$(dirname "$0")/in_image.sh" 'set -e; KMP_PDK=sky130A KMP_PDKS=sky130A python3 -m unittest discover -s tests/centroid -t . "$@"; KMP_PDK=sky130A KMP_PDKS=sky130A python3 -m unittest discover -s tests/gen -t . "$@"' "$@"
