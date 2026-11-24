"""python3 -m klayout_power_pcells hw [--device ... --bulk ring|source --l 0.5 --w 2 --nf 3
                                     --nx 3 --ny 3 --strap 3] -o hw.gds"""

import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="klayout_power_pcells")
    sub = ap.add_subparsers(dest="cmd", required=True)
    hw = sub.add_parser("hw", help="sky130A hybrid-waffle power MOSFET")
    hw.add_argument("--device", default="sky130_fd_pr__nfet_01v8",
                    help="Magic sky130A MOSFET (see hybrid_waffle.DEVICES)")
    hw.add_argument("--bulk", default="ring", choices=("ring", "source"),
                    help="tap ring around the array (pin B), or a tap in every source tile tied to S")
    hw.add_argument("--l", type=float, default=0.5, help="gate length (um)")
    hw.add_argument("--w", type=float, default=2.0, help="finger width (um)")
    hw.add_argument("--nf", type=int, default=3, help="fingers per cell (per tile edge)")
    hw.add_argument("--nx", type=int, default=3, help="tiles per row (N)")
    hw.add_argument("--ny", type=int, default=3, help="tiles per column (M)")
    hw.add_argument("--strap", type=float, default=3.0, help="diagonal strap width (um)")
    hw.add_argument("--pitch", type=float, default=None, help="tile pitch (um); default: minimum")
    hw.add_argument("--name", default="HW_FET")
    hw.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)

    from .hybrid_waffle import HWParams, write_gds
    p = HWParams(l=args.l, w=args.w, nf=args.nf, nx=args.nx, ny=args.ny,
                 strap_w=args.strap, pitch=args.pitch, device=args.device, bulk=args.bulk)
    try:
        res = write_gds(p, args.out, name=args.name)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print(res.summary())
    print("wrote %s (cell %s)" % (args.out, args.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
