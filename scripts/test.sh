#!/bin/sh
# Unit tests (no Magic needed), then the backend tests (Magic needed) once
# per PDK, then the sky130_power tests, in the image.
exec "$(dirname "$0")/in_image.sh" 'set -e; python3 -m unittest discover -s tests/unit -t . "$@"; for p in sky130A gf180mcuD ihp-sg13g2 ihp-sg13cmos5l; do echo "backend tests: $p"; KMP_PDK=$p KMP_PDKS=$p python3 -m unittest discover -s tests/backend -t . "$@"; done; echo "power tests (sky130_power)"; KMP_PDK=sky130A KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t . "$@"' "$@"
