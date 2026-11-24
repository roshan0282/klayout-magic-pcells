"""Command line: python3 -m klayout_power_pcells <command> ...

  doctor                                 configuration, Magic, versions, one timed generation
  devices [-v]                           the devices HW_FET takes, and its parameters
  check [k=v ...]                        what the GUI form makes of these values, and why not
  generate [k=v ...] -o out.gds          place one HW_FET variant (through the library), write a file
  hw [--l ... --nx ...] -o out.gds       draw the HW FET as a flat cell (no library)
  audit FILE [--regen]                   report the HW_FET cells in a file
  cache {stats,prune,clear}              this package's disk cache

Exit status: 0 when the FET is drawn (or the check passes), 1 when it isn't
(the generator refuses the values, Magic fails, or audit finds a problem),
2 for a value that isn't a number or not one of the choices.
"""

import argparse
import os
import sys
import time

PARAMS = ("device", "bulk", "l", "w", "nf", "nx", "ny", "strap_w", "pitch")


def _kv(items):
    """{name: value} from name=value words; exits 2 on a bad one."""
    from .hybrid_waffle import BULK_MODES, DEVICES
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit("error: expected name=value, got %r" % it)
        k, v = it.split("=", 1)
        if k not in PARAMS:
            raise SystemExit("error: HW_FET has no parameter %r (try: devices)" % k)
        try:
            if k in ("nf", "nx", "ny"):
                out[k] = int(v)
            elif k == "device":
                full = v if v.startswith("sky130_fd_pr__") else "sky130_fd_pr__" + v
                if full not in DEVICES:
                    raise ValueError("not one of %s" % ", ".join(sorted(DEVICES)))
                out[k] = full
            elif k == "bulk":
                if v not in BULK_MODES:
                    raise ValueError("not one of %s" % ", ".join(BULK_MODES))
                out[k] = v
            else:
                out[k] = float(v)
        except ValueError as e:
            sys.stderr.write("error: %s=%r: %s\n" % (k, v, e))
            raise SystemExit(2)
    return out


def _register():
    from . import register
    from . import backend
    lib = register()
    if lib is None:
        print("error: sky130_power is not registered: %s" % backend.state.last_error, file=sys.stderr)
        raise SystemExit(1)
    return lib


def cmd_doctor(args):
    from klayout_magic_pcells.config import Config
    from . import __version__, backend
    from .hybrid_waffle import HWParams, DEVICES
    ok = True
    try:
        cfg = Config.load(pdk=backend.PDK)
    except Exception as e:
        print("configuration error: %s" % e)
        return 2
    print("klayout_power_pcells %s (generator code %s)" % (__version__, backend.code_digest()))
    print("configuration (config file: %s)" % (cfg.config_file or "none"))
    for name, val, src in cfg.describe():
        if name in ("magic", "pdk_root", "magicrc", "cache_dir", "cache_enabled", "lazy", "timeout"):
            print("  %-14s %-60s %s" % (name, val, src))
    for p in cfg.problems():
        ok = False
        print("PROBLEM: " + p)
    try:
        import klayout.db as kdb
        print("klayout module %s" % getattr(kdb, "__version__", "?"))
    except ImportError:
        print("klayout Python module: not importable (only needed outside KLayout)")
    t = time.time()
    try:
        st = backend.start()
    except Exception as e:
        print("PROBLEM: %s" % e)
        return 1
    v = st.versions
    print("sky130A Magic ready in %.2f s: magic %s, tech %s, PDK commit %s"
          % (time.time() - t, v.magic, v.tech, getattr(v, "pdk_commit", "?")))
    print("stamp %s" % st.created_stamp)
    print("cache %s (%s)" % (st.cache.base, "on" if st.cache.enabled else "off: session only"))
    print("%d devices: %s" % (len(DEVICES), ", ".join(n.replace("sky130_fd_pr__", "") for n in sorted(DEVICES))))
    for dev in sorted(DEVICES):
        try:
            import klayout_magic_pcells as kmp
            kmp.dialog_values(dev, {"guard": False}, pdk=backend.PDK)
        except Exception as e:
            ok = False
            print("PROBLEM: Magic has no working %s: %s" % (dev, e))
    p = HWParams(nx=2, ny=2, nf=1)
    t = time.time()
    try:
        st.generator.fresh = True
        r = st.generator.get(p)
        print("drew a 2x2 HW_FET in %.2f s: %s" % (time.time() - t, r.info["summary"]))
    except Exception as e:
        ok = False
        print("PROBLEM: drawing a 2x2 HW_FET failed: %s" % e)
    finally:
        st.generator.fresh = False
    return 0 if ok else 1


def cmd_devices(args):
    from .hybrid_waffle import DEVICES
    from .pcell import HWFetPCell
    from klayout_magic_pcells.config import Config
    from klayout_magic_pcells.manifest import Manifest
    man = None
    if args.verbose:
        try:
            man = Manifest.load(Config.load(pdk="sky130A").manifest)
        except Exception as e:
            print("(cannot read the sky130A manifest: %s)" % e)
    print("HW_FET in sky130_power (sky130A); devices:")
    for n in sorted(DEVICES):
        kind, hv = DEVICES[n]
        line = "  %-32s %sfet%s" % (n, kind, ", thick oxide (hvi)" if hv else "")
        if man is not None and man.get(n) is not None:
            spec = man.get(n)
            lims = []
            for pn in ("w", "l"):
                pp = spec.param(pn)
                if pp is not None and pp.check_min:
                    lims.append("%s >= %s um" % (pn, pp.check_min))
            if lims:
                line += "   Magic: " + ", ".join(lims)
        print(line)
    print("parameters:")
    for pd in HWFetPCell().get_parameters():
        if pd.hidden:
            continue
        print("  %-8s %-36s default %s%s" % (pd.name, pd.description, pd.default,
                                             "  (read-only)" if pd.readonly else ""))
    return 0


def cmd_check(args):
    from . import backend
    from .hybrid_waffle import HWParamError
    from .pcell import EDITABLE, HWFetPCell, magic_corrections
    vals = _kv(args.values)
    _register()
    full = {p.name: p.default for p in HWFetPCell().get_parameters()}
    full.update(vals)
    for k, (typed, shown) in magic_corrections(full).items():
        print("HW_FET: Magic's dialog shows %s=%s (entered %s)" % (k, shown, typed))
        full[k] = shown
    try:
        r = backend.state.generator.get(HWFetPCell._params({n: full[n] for n in EDITABLE}))
    except HWParamError as e:
        print("HW_FET: not drawn: %s (parameter %s)" % (e, e.param))
        return 1
    except Exception as e:
        print("HW_FET: not drawn: %s" % e)
        return 1
    print("HW_FET: %s" % r.info["summary"])
    return 0


def cmd_generate(args):
    import klayout.db as db
    from . import form_values
    from .pcell import ERROR_LAYER
    vals = _kv(args.values)
    _register()
    v = form_values(vals)
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell(args.top)
    c = ly.create_cell("HW_FET", "sky130_power", v)
    top.insert(db.CellInstArray(c.cell_index(), db.Trans()))
    ly.write(args.out)
    el = ly.find_layer(*ERROR_LAYER)
    if el is not None and not c.shapes(el).is_empty():
        texts = [s.text_string for s in c.shapes(el).each() if s.is_text()]
        print("wrote %s with the error marker: %s" % (args.out, texts[0] if texts else "?"))
        return 1
    print("%s: %s" % (args.out, v.get("info", "")))
    return 0


def cmd_hw(args):
    from .hybrid_waffle import HWParams, write_gds
    p = HWParams(l=args.l, w=args.w, nf=args.nf, nx=args.nx, ny=args.ny, strap_w=args.strap,
                 pitch=args.pitch, device=args.device, bulk=args.bulk)
    try:
        res = write_gds(p, args.out, name=args.name)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print(res.summary())
    print("wrote %s (cell %s)" % (args.out, args.name))
    return 0


def cmd_audit(args):
    from .audit import audit, format_report
    rep = audit(args.file, regen=args.regen, notes=print)
    print(format_report(rep))
    return 1 if any(c["problems"] for c in rep["cells"]) or rep.get("file_problems") else 0


def cmd_cache(args):
    from klayout_magic_pcells.cache import GdsCache
    from klayout_magic_pcells.config import Config
    cfg = Config.load(pdk="sky130A")
    root = os.path.join(cfg.cache_dir, "power")
    if args.action == "stats":
        if not os.path.isdir(root):
            print("cache %s: empty" % root)
            return 0
        c = GdsCache.__new__(GdsCache)
        c.root = root
        n = size = 0
        for d in c.version_dirs():
            for dp, _, files in os.walk(d):
                for fn in files:
                    n += fn.endswith(".gds")
                    size += os.path.getsize(os.path.join(dp, fn))
        print("cache %s: %d entries, %.1f MB, %d versions directories"
              % (root, n, size / 1e6, len(c.version_dirs())))
        return 0
    if args.action == "clear":
        c = GdsCache.__new__(GdsCache)
        c.root = root
        c.clear()
        print("cleared %s" % root)
        return 0
    # prune: keep the current versions directory only
    from . import backend
    try:
        st = backend.start()
    except Exception as e:
        print("error: cannot learn the current versions (%s)" % e, file=sys.stderr)
        return 1
    removed, _other = st.cache.prune(current={"sky130A": st.cache.vdigest})
    print("pruned %d directories; kept %s" % (len(removed), st.cache.base))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="klayout_power_pcells",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p = sub.add_parser("devices")
    p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("values", nargs="*")
    p = sub.add_parser("generate")
    p.add_argument("values", nargs="*")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--top", default="TOP")
    hw = sub.add_parser("hw", help="draw the HW FET as a flat cell, without the library")
    hw.add_argument("--device", default="sky130_fd_pr__nfet_01v8")
    hw.add_argument("--bulk", default="ring", choices=("ring", "source"))
    hw.add_argument("--l", type=float, default=0.5)
    hw.add_argument("--w", type=float, default=2.0)
    hw.add_argument("--nf", type=int, default=3)
    hw.add_argument("--nx", type=int, default=3)
    hw.add_argument("--ny", type=int, default=3)
    hw.add_argument("--strap", type=float, default=3.0)
    hw.add_argument("--pitch", type=float, default=None)
    hw.add_argument("--name", default="HW_FET")
    hw.add_argument("-o", "--out", required=True)
    p = sub.add_parser("audit")
    p.add_argument("file")
    p.add_argument("--regen", action="store_true")
    p = sub.add_parser("cache")
    p.add_argument("action", choices=("stats", "prune", "clear"))
    args = ap.parse_args(argv)
    return {"doctor": cmd_doctor, "devices": cmd_devices, "check": cmd_check, "generate": cmd_generate,
            "hw": cmd_hw, "audit": cmd_audit, "cache": cmd_cache}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
