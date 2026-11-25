#!/bin/bash
# Open the CC_ARRAY form in KLayout's GUI under Xvfb, switch the Unit cell
# dropdown and take screenshots (docs/centroid.md). Same set-up as
# power_shots.sh: this repository linked into ~/.klayout/salt.
#
#   tools/screenshots/cc_shots.sh            # writes docs/img/cc-*.png
set -eu
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$REPO/docs/img}"
WORK="$(mktemp -d)"
mkdir -p "$OUT" "$WORK/raw"
env KMP_PDKS=sky130A KMP_SHOT_WORK="$WORK" timeout 600 \
  xvfb-run -a -s "-screen 0 1440x900x24 -dpi 96" \
  klayout -e -rm "$REPO/tools/screenshots/cc_gui.py" > "$WORK/klayout.log" 2>&1 || true
if [ ! -f "$WORK/done-cc" ]; then
  echo "cc_gui.py failed:" >&2; tail -n 30 "$WORK/cc-gui.log" "$WORK/klayout.log" >&2 || true
  echo "work directory: $WORK" >&2; exit 1
fi
cp "$WORK"/raw/cc-*.png "$OUT"/
cat "$WORK/notes-cc.json"
rm -rf "$WORK"
