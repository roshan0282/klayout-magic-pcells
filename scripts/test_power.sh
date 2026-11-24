#!/bin/sh
# The sky130_power tests (tests/power) in the pinned image: unit tests, the
# generator's DRC/extraction cases, the PCell, and the backend scenarios
# (cache, stamps, round trips, audit, CLI, form, registration).
# Inside an iic-osic-tools container already, run the command directly:
#   KMP_PDKS=sky130A python3 -m unittest discover -s tests/power -t .
exec "$(dirname "$0")/in_image.sh" 'KMP_PDKS=sky130A KMP_PDK=sky130A python3 -m unittest discover -s tests/power -t . "$@"' "$@"
