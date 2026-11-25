#!/bin/bash
# Run tools/live_verify/gui_check.py in KLayout under Xvfb with this package's macros.
set -eu
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${1:-$(mktemp -d)}"
mkdir -p "$WORK"
QTDRIVE_DIR="${QTDRIVE_DIR:-$REPO/tools/screenshots}" LV_WORK="$WORK" timeout 300 \
  xvfb-run -a -s "-screen 0 1400x900x24 -dpi 96" \
  klayout -e -rm "$REPO/pymacros/live_verify.lym" -rm "$REPO/tools/live_verify/gui_check.py" > "$WORK/klayout.log" 2>&1 || true
cat "$WORK/notes.json" 2>/dev/null || { tail -n 30 "$WORK/gui.log" "$WORK/klayout.log"; exit 1; }
echo
echo "work: $WORK"
