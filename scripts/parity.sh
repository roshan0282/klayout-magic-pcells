#!/bin/sh
# The parity harness: everything runs in one container of the pinned image.
#
#   scripts/parity.sh                                  # full sweep (~2,100 points)
#   scripts/parity.sh --quick                          # the 60 device defaults
#   scripts/parity.sh --devices 'sky130_fd_pr__res_*' --keep
#   scripts/parity.sh --update-baseline                # rewrite the DRC baseline
#
# Writes out/parity/report.json and out/parity/report.md. Exit status: 0 when
# every check passes, 1 when a check fails, 2 when the harness itself fails.
# Arguments reach run_sweep.py as positional parameters of bash -c, so glob
# patterns arrive unexpanded.
exec "$(dirname "$0")/in_image.sh" 'python3 tests/parity/run_sweep.py --out /repo/out/parity "$@"' "$@"
