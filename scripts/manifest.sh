#!/bin/sh
# Rebuild the shipped manifest from the Magic and PDK in the pinned image:
#   scripts/manifest.sh            rewrite python/klayout_magic_pcells/data/manifest-sky130A.json
#   scripts/manifest.sh --check    exit 1 if the committed manifest differs
exec "$(dirname "$0")/in_image.sh" 'python3 tools/build_manifest.py "$@"' "$@"
