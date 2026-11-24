#!/bin/bash
# Drive KLayout's GUI with the sky130_power library under Xvfb and take the
# screenshots of docs/guide-power.md. Runs where Magic, KLayout, xvfb-run and
# sky130A are installed (inside the iic-osic-tools image), with this
# repository linked into ~/.klayout/salt as the guide says:
#
#   tools/screenshots/power_shots.sh            # writes docs/img/power/*.png
#   tools/screenshots/power_shots.sh /tmp/shots # somewhere else
#
# Three sessions of power_gui.py: main (form, icons, place, edit, save),
# reopen (with the library) and defunct (Magic missing). Each writes
# notes-<session>.json with what it saw; tests/power/test_gui.py checks them.
# HW_SHOT_KEEP=1 keeps the work directory.
set -eu
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$REPO/docs/img/power}"
WORK="$(mktemp -d)"
mkdir -p "$OUT" "$WORK/raw"
run() {
  local session=$1; shift
  env "$@" KMP_PDKS=sky130A KMP_SHOT_SESSION=$session KMP_SHOT_WORK="$WORK" timeout 600 \
    xvfb-run -a -s "-screen 0 1440x900x24 -dpi 96" \
    klayout -e -rm "$REPO/tools/screenshots/power_gui.py" > "$WORK/klayout-$session.log" 2>&1 || true
  if [ ! -f "$WORK/done-$session" ]; then
    echo "session $session failed; power_gui.py's log:" >&2
    tail -30 "$WORK/power-gui-$session.log" >&2 || true
    echo "work directory: $WORK" >&2
    exit 1
  fi
  echo "session $session: done"
}
run main
run reopen
run defunct KMP_MAGIC=/nonexistent/magic
cp "$WORK"/raw/power-*.png "$OUT"/
cp "$WORK"/notes-*.json "$OUT"/ 2>/dev/null || true
echo "screenshots in $OUT"
if [ "${HW_SHOT_KEEP:-0}" = 1 ]; then echo "work directory: $WORK"; else rm -rf "$WORK"; fi
