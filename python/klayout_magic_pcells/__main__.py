"""Command line: python3 -m klayout_magic_pcells <command> ...

  doctor                       resolved configuration, versions, manifest check, timing
  check DEVICE [k=v ...]       run Magic's _check once and show what it changes
  generate DEVICE [k=v ...] -o out.gds   place one PCell variant and write a file
  audit FILE [--regen]         report sky130_magic cells in a file
  cache {stats,prune,clear}    the disk cache
  devices                      list the PCells and their parameters
"""

import argparse
import json
import os
import sys
import time


def _cfg():
    from .config import Config
    return Config.load()


def _kv(items, spec):
    vals = {}
    for it in items:
        if "=" not in it:
            raise SystemExit("error: expected name=value, got %r" % it)
        k, v = it.split("=", 1)
        p = spec.param(k)
        if p is None:
            raise SystemExit("error: %s has no parameter %r (try: devices)" % (spec.name, k))
        vals[k] = p.parse(v)
    return vals


def cmd_doctor(args):
    from .backend import MagicServer
    from .manifest import Manifest, diff_defaults
    ok = True
    try:
        cfg = _cfg()
    except Exception as e:
        print("configuration error: %s" % e)
        return 2
    print("configuration (config file: %s)" % (cfg.config_file or "none"))
    for name, val, src in cfg.describe():
        print("  %-14s %-60s %s" % (name, val, src))
    for p in cfg.problems():
        ok = False
        print("PROBLEM: " + p)
    if not ok:
        return 1
    try:
        import klayout.db as kdb
        print("klayout module %s" % getattr(kdb, "__version__", "?"))
    except ImportError:
        print("klayout Python module: not importable (only needed outside KLayout)")
    man = Manifest.load(cfg.manifest)
    s = MagicServer(cfg)
    try:
        t = time.time()
        v = s.start()
        print("Magic started in %.2f s: %s" % (time.time() - t, v.magic_banner))
        print("  magic %s, tech %s (%s), open_pdks %s, Tcl %s" % (v.magic, v.tech, v.tech_name,
                                                                  v.open_pdks, v.tcl))
        if v.defaults_digest == man.defaults_digest:
            print("manifest %s matches the running Magic (%d devices)" % (cfg.manifest, len(man.devices)))
        else:
            ok = False
            print("MANIFEST MISMATCH: defaults digest %s, manifest has %s"
                  % (v.defaults_digest[:16], man.defaults_digest[:16]))
            for dev, why in diff_defaults(man.defaults_by_device(), v.defaults):
                print("  %s: %s" % (dev, why))
        out = os.path.join(s.run_dir, "doctor.gds")
        t = time.time()
        r = s.generate("sky130_fd_pr__nfet_01v8", {}, "cell", out)
        print("nfet_01v8 defaults generated in %.1f ms (%s)" % ((time.time() - t) * 1000, r.cell))
    except Exception as e:
        ok = False
        print("BACKEND ERROR: %s" % e)
    finally:
        s.close()
    return 0 if ok else 1


def cmd_check(args):
    from .backend import MagicServer
    from .manifest import InvalidValue, Manifest
    from .pcell import changed_params
    cfg = _cfg()
    man = Manifest.load(cfg.manifest)
    spec = man.get(args.device)
    if spec is None:
        raise SystemExit("error: unknown device %s" % args.device)
    vals = spec.defaults_values()
    vals.update(_kv(args.params, spec))
    try:
        req = spec.build_request(vals)
    except InvalidValue as e:
        print("error: %s" % e)
        return 2
    s = MagicServer(cfg)
    try:
        s.start()
        r = s.check(spec.name, req)
    finally:
        s.close()
    ch = changed_params(req, r.checked)
    if not ch:
        print("%s: _check changes nothing" % spec.name)
    for k, v in ch.items():
        print("%s: Magic draws %s=%s (entered %s)" % (spec.name, k, v, req[k]))
    for line in r.log.strip().splitlines():
        print("  message: " + line)
    return 0


def cmd_generate(args):
    from . import register, state
    lib = register()
    if lib is None:
        print("error: %s" % state.last_error)
        return 2
    from ._kl import db
    spec = state.manifest.get(args.device)
    if spec is None:
        raise SystemExit("error: unknown device %s" % args.device)
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell(args.top)
    pc = ly.create_cell(spec.name, lib.name(), _kv(args.params, spec))
    top.insert(db.CellInstArray(pc.cell_index(), db.Trans()))
    ly.write(args.output)
    print("wrote %s: %s (%s), bbox %s um" % (args.output, pc.name, pc.display_title(), pc.dbbox()))
    # Exit 1 when the file holds no device: the error marker, or Magic's
    # empty cell.
    from .pcell import PLACEHOLDER_LAYER
    ph = ly.find_layer(*PLACEHOLDER_LAYER)
    marker = [sh.text_string for sh in pc.shapes(ph).each() if sh.is_text()] if ph is not None else []
    if marker:
        print("error: generation failed; the cell holds the marker %r" % marker[0])
        return 1
    if pc.dbbox().empty():
        print("error: Magic drew nothing for these parameters; the cell is empty")
        return 1
    return 0


def cmd_audit(args):
    from .audit import audit, format_report
    cur = None
    try:
        from .backend import MagicServer
        from .stamp import make_stamp, parse_stamp
        s = MagicServer(_cfg())
        try:
            cur = parse_stamp(make_stamp(s.start()))
        finally:
            s.close()
    except Exception as e:
        print("note: cannot start Magic to read the installed versions (%s)" % e)
    try:
        from .manifest import Manifest
        man = Manifest.load(_cfg().manifest)
    except Exception as e:
        man = None
        print("note: cannot read the manifest (%s); the coordinate grid isn't checked" % e)
    rep = audit(args.file, cur, regen=args.regen, manifest=man)
    if args.json:
        print(json.dumps(rep, indent=1, default=str))
    else:
        print(format_report(rep))
    return 1 if any(c["problems"] for c in rep["cells"]) or rep.get("file_problems") else 0


def cmd_cache(args):
    from .cache import GdsCache, versions_fields
    cfg = _cfg()
    if args.action == "clear":
        GdsCache(cfg.cache_dir, {}, enabled=True).clear()
        print("cleared %s" % cfg.cache_dir)
        return 0
    from .backend import MagicServer
    s = MagicServer(cfg)
    try:
        v = s.start()
    finally:
        s.close()
    c = GdsCache(cfg.cache_dir, versions_fields(v, cfg.pdk), enabled=True)
    if args.action == "prune":
        for d in c.prune():
            print("removed %s" % d)
    print(json.dumps(dict(c.stats(), root=cfg.cache_dir), indent=1))
    return 0


def cmd_devices(args):
    from .manifest import Manifest
    man = Manifest.load(_cfg().manifest)
    for d in man.devices:
        print("%s  [%s%s]" % (d.name, d.family, ", fixed layout" if d.nocell else ""))
        if args.verbose:
            for p in d.params:
                print("    %-10s %-7s default %-8s %s" % (p.name, p.type, p.default, p.label))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m klayout_magic_pcells",
                                 description="KLayout PCells generated by Magic")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    p = sub.add_parser("check")
    p.add_argument("device")
    p.add_argument("params", nargs="*")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("generate")
    p.add_argument("device")
    p.add_argument("params", nargs="*")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--top", default="TOP")
    p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("audit")
    p.add_argument("file")
    p.add_argument("--regen", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("cache")
    p.add_argument("action", choices=("stats", "prune", "clear"))
    p.set_defaults(fn=cmd_cache)
    p = sub.add_parser("devices")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_devices)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
