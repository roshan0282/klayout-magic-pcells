#!/usr/bin/env python3
"""Write the parity sweep: a list of parameter points per device.

    python3 tests/parity/gen_sweep.py --manifest M --out sweep.json \
        [--seed 1121] [--random 5] [--max-per-device 60] [--quick] [--devices GLOB ...]

Each point holds only the parameters it changes, as the strings Magic gets
on path A. Numbers go through the plugin's own parse/format functions
(``ParamSpec.canonical``), because the plugin's number formatting (12
significant digits, Magic's default text) is documented behaviour. Coverage
strings ("signed") are used exactly as typed and never go through the
plugin: the PCell promises to send them verbatim, and the harness's
``request`` check compares what path B actually sent with this text. Points
whose request repeats an earlier one of the same device are dropped, and the
kinds they stood for are kept in ``aliases``.

No point may give a MOSFET or varactor both w and l above 28 um: Magic's
mos_check then loops forever (sky130A.tcl, the tap-spacing loop), on path A
as in Magic's own dialog. The backend stops that loop (see kmp_common.tcl)
and tests/backend covers it; path A has a watchdog in case one slips in.
"""

import argparse
import fnmatch
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "python"))

from klayout_magic_pcells.manifest import Manifest  # noqa: E402

GRID = 0.005
OFFGRID = 0.0034
# Kinds dropped first when a device has more points than --max-per-device.
DROP_ORDER = ("random", "anchor", "space", "offgrid", "int", "below", "flip", "min", "max")


def num(text):
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def limits(spec, p, cfg):
    """(min, max, min_from_magic) for a numeric parameter, or Nones."""
    lo = hi = None
    lo_magic = False
    if p.type == "float":
        v = num(spec.internal(p.name + "min"))
        if v is not None:
            lo, lo_magic = v, True
        v = num(spec.internal(p.name + "max"))
        if v is not None:
            hi = v
        if lo is None and num(p.check_min) is not None:
            lo, lo_magic = num(p.check_min), True
        if hi is None and num(p.check_max) is not None:
            hi = num(p.check_max)
    key = "signed" if p.type == "signed" else p.name
    fam = cfg.get("by_family", {}).get(spec.family, {}).get(key, {})
    gen = cfg.get("by_name", {}).get(key, {})
    if lo is None:
        lo = fam.get("min", gen.get("min"))
    if hi is None:
        hi = fam.get("max", gen.get("max"))
    return lo, hi, lo_magic


def snap(v):
    return round(round(v / GRID) * GRID, 6)


def fmt(v):
    """A float as short text: 0.42 not 0.42000000000000004."""
    return repr(round(v, 6))


def device_points(spec, cfg, rng, n_random, quick):
    pts = [("default", {})]
    if quick:
        return pts
    for p in spec.params:
        if p.type == "float":
            lo, hi, lo_magic = limits(spec, p, cfg)
            if lo is not None:
                pts.append(("min:" + p.name, {p.name: fmt(lo)}))
                if lo_magic:
                    below = lo / 2 if lo > 0 else lo - 1
                    pts.append(("below:" + p.name, {p.name: fmt(below)}))
            if hi is not None:
                pts.append(("max:" + p.name, {p.name: fmt(hi)}))
        elif p.type == "signed":
            pts.append(("min:" + p.name, {p.name: "0"}))
            pts.append(("max:" + p.name, {p.name: "100"}))
            pts.append(("anchor:+" + p.name, {p.name: "+50"}))
            pts.append(("anchor:-" + p.name, {p.name: "-50"}))
        elif p.type == "bool01":
            pts.append(("flip:" + p.name, {p.name: "0" if p.default_value() else "1"}))
        elif p.type == "int":
            pts.append(("int:%s=1" % p.name, {p.name: "1"}))
            pts.append(("int:%s=4" % p.name, {p.name: "4"}))
            pts.append(("below:" + p.name, {p.name: "0"}))
    signed = [p for p in spec.params if p.type == "signed"]
    if signed:
        # Whitespace before the anchor: Magic reads the first character, so
        # " -50" has no anchor and must reach Magic unchanged.
        pts.append(("space:" + signed[0].name, {signed[0].name: " -50"}))
        pts.append(("space:" + signed[-1].name, {signed[-1].name: "\t+30"}))
    for n in ("w", "l"):
        p = spec.param(n)
        if p is not None and p.type == "float":
            pts.append(("offgrid:" + n, {n: fmt(float(p.default) + OFFGRID)}))
    # Zero sizes: for 17 resistors (l), 6 resistors (w) and 5 diodes (w, l)
    # Magic's _draw fails and Magic writes an empty cell; the others clamp.
    if spec.family in ("res", "diode"):
        for n in ("l", "w"):
            if spec.param(n) is not None:
                pts.append(("zero:" + n, {n: "0"}))
    large = cfg.get("large_nf", {}).get(spec.name)
    if large and spec.param("nf") is not None:
        pts.append(("large", {"w": "31", "nf": str(large)}))
    for k in range(n_random):
        req = {}
        for p in spec.params:
            if p.type == "float":
                lo, hi, _ = limits(spec, p, cfg)
                if lo is None or hi is None or hi <= lo:
                    continue
                req[p.name] = fmt(snap(rng.uniform(lo, hi)))
            elif p.type == "int":
                req[p.name] = str(rng.randint(1, 4))
            elif p.type == "bool01":
                req[p.name] = str(rng.randint(0, 1))
            elif p.type == "signed":
                req[p.name] = rng.choice(("", "+", "-")) + str(rng.randint(0, 100))
        pts.append(("random:%d" % (k + 1), req))
    return pts


def canonical(spec, req):
    out = {}
    for k, v in req.items():
        p = spec.param(k)
        out[k] = v if p.type in ("signed", "string") else p.canonical(v)
    return out


def gen(manifest, cfg, seed, n_random, max_per_device, quick, patterns):
    points = []
    summary = {}
    for di, spec in enumerate(manifest.devices):
        if patterns and not any(fnmatch.fnmatchcase(spec.name, g) for g in patterns):
            continue
        rng = random.Random("%d:%s" % (seed, spec.name))
        seen = {}
        dev_pts = []
        for kind, req in device_points(spec, cfg, rng, n_random, quick):
            creq = canonical(spec, req)
            # A request that only restates defaults is the default point.
            creq = {k: v for k, v in creq.items() if v != spec.param(k).default}
            sig = json.dumps(creq, sort_keys=True)
            if sig in seen:
                seen[sig]["aliases"].append(kind)
                continue
            pt = {"device": spec.name, "family": spec.family, "kind": kind,
                  "request": creq, "aliases": []}
            seen[sig] = pt
            dev_pts.append(pt)
        dropped = 0
        for fam in DROP_ORDER:
            while len(dev_pts) > max_per_device:
                idx = [i for i, pt in enumerate(dev_pts) if pt["kind"].split(":")[0] == fam]
                if not idx:
                    break
                dev_pts.pop(idx[-1])
                dropped += 1
        summary[spec.name] = {"points": len(dev_pts), "dropped": dropped}
        points.extend(dev_pts)
    for i, pt in enumerate(points):
        pt["id"] = "%04d" % (i + 1)
    return points, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default=os.path.join(
        REPO, "python", "klayout_magic_pcells", "data", "manifest-sky130A.json"))
    ap.add_argument("--limits", default=os.path.join(HERE, "sweep_limits.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1121)
    ap.add_argument("--random", type=int, default=5)
    ap.add_argument("--max-per-device", type=int, default=60)
    ap.add_argument("--quick", action="store_true", help="only the default point of each device")
    ap.add_argument("--devices", nargs="*", default=[], help="fnmatch patterns of device names")
    args = ap.parse_args(argv)
    manifest = Manifest.load(args.manifest)
    with open(args.limits, encoding="utf-8") as f:
        cfg = json.load(f)
    points, summary = gen(manifest, cfg, args.seed, args.random, args.max_per_device,
                          args.quick, args.devices)
    doc = {"seed": args.seed, "random": args.random, "max_per_device": args.max_per_device,
           "quick": args.quick, "devices": args.devices, "summary": summary, "points": points}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print("sweep: %d points over %d devices -> %s" % (len(points), len(summary), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
