#!/bin/bash
# Runs inside the image (see take.sh). Installs the package as the guide
# does, runs gui.py's three sessions and writes the PNGs to /out.
set -eu
R=/foss/designs/klayout-magic-pcells
ln -s /foss/designs/klayout-magic-pcells ~/.klayout/salt/klayout-magic-pcells
mkdir -p /work/raw

run() {
  local session=$1
  KMP_SHOT_SESSION=$session KMP_SHOT_WORK=/work timeout 600 \
    xvfb-run -a -s "-screen 0 1440x900x24 -dpi 96" \
    klayout -e -rm "$R/tools/screenshots/gui.py" > "/work/klayout-$session.log" 2>&1 || true
  if [ ! -f "/work/done-$session" ]; then
    echo "session $session failed; gui.py's log:" >&2
    tail -40 "/work/gui-$session.log" >&2 || true
    exit 1
  fi
  echo "session $session: done"
}

run main
run reopen
# sky130_magic missing: only gf180mcuD registers.
KMP_PDKS=gf180mcuD run defunct
python3 "$R/tools/screenshots/finish.py" /work/raw /out
