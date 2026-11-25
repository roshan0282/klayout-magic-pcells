"""Print a common-centroid pattern and its report.

    python -m klayout_centroid A:4,B:4 [--style optimized] [--rows R --cols C]
    python -m klayout_centroid 1:2:4:8 --compare
    python -m klayout_centroid A:2,B:2 --override ABBA/BAAB
"""

import argparse
import sys

from .metrics import evaluate, report_text, summary_line
from .pattern import STYLES, PatternError, build, parse_devices


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m klayout_centroid", description=__doc__.splitlines()[0])
    ap.add_argument("devices", help="A:4,B:4 or a ratio 1:2:4:8")
    ap.add_argument("--style", default="symmetric", choices=STYLES)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--cols", type=int, default=0)
    ap.add_argument("--aspect", type=float, default=1.0, help="unit pitch x / pitch y, for the auto shape")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rho", type=float, default=0.9, help="correlation per pitch for the sigma score")
    ap.add_argument("--override", help="hand-written grid, rows split by /")
    ap.add_argument("--compare", action="store_true", help="one summary line per style")
    a = ap.parse_args(argv)
    try:
        devs = parse_devices(a.devices)
        if a.compare:
            for s in STYLES:
                p = build(devs, a.rows, a.cols, s, a.aspect, a.seed, rho=a.rho)
                print("%-15s %s   %s" % (s, "/".join(p.grid), summary_line(evaluate(p, a.rho))))
            return 0
        p = build(devs, a.rows, a.cols, a.style, a.aspect, a.seed, a.override, rho=a.rho)
        print(report_text(p, evaluate(p, a.rho)))
        return 0
    except PatternError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
