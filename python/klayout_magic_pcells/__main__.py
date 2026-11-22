"""Command line: python3 -m klayout_magic_pcells <command> ...

  doctor [--pdk P]                     configuration, versions, manifest check, timing
  check DEVICE [k=v ...]               run Magic's _check once and show what it changes
  generate DEVICE [k=v ...] -o out.gds place one PCell variant and write a file
  audit FILE [--regen]                 report the Magic-generated cells in a file
  cache {stats,prune,clear}            the disk cache (prune: the selected PDKs' old entries)
  devices [-v]                         list the PCells and their parameters

A device is found in the manifests of the selected PDKs (KMP_PDKS); a name
that more than one PDK has (rm1) needs --pdk.
"""

import argparse
import json
import os
import sys
import time


def _cfg(pdk=None):
    from .config import Config
    return Config.load(pdk=pdk)


def _pdks(args, cfg=None):
    """The PDKs a command works on: --pdk, else the selected ones."""
    if getattr(args, "pdk", None):
        return [args.pdk]
    cfg = cfg or _cfg()
    return list(cfg.pdks)


def _find_device(args):
    """(Config, Manifest, DeviceSpec) for args.device; exits on errors."""
    from .config import SUPPORTED_PDKS
    from .manifest import Manifest
    base = _cfg(getattr(args, "pdk", None))
    cands = [args.pdk] if getattr(args, "pdk", None) else (list(base.pdks) or list(SUPPORTED_PDKS))
    hits = []
    for p in cands:
        c = base.for_pdk(p)
        try:
            man = Manifest.load(c.manifest)
        except Exception:
            continue
        spec = man.get(args.device)
        if spec is not None:
            hits.append((c, man, spec))
    if not hits:
        raise SystemExit("error: unknown device %s in %s (try: devices)" % (args.device, ", ".join(cands)))
    if len(hits) > 1:
        raise SystemExit("error: %s is a device of %s; choose one with --pdk"
                         % (args.device, ", ".join(h[0].pdk for h in hits)))
    return hits[0]


def _kv(items, spec):
    vals = {}
    for it in items:
        if "=" not in it:
            raise SystemExit("error: expected name=value, got %r" % it)
        k, v = it.split("=", 1)
        p = spec.param(k)
        if p is None:
            raise SystemExit("error: %s has no parameter %r (try: devices -v)" % (spec.name, k))
        try:
            vals[k] = p.parse(v)
        except ValueError as e:
            # A refused value exits 2, as check does for one Magic must not see.
            sys.stderr.write("error: %s=%r is not a %s: %s\n" % (
                k, v, {"int": "whole number", "float": "number", "bool01": "0 or 1"}.get(p.type, p.type), e))
            raise SystemExit(2)
    return vals


def cmd_doctor(args):
    from .backend import MagicServer
    from .manifest import Manifest, diff_defaults
    ok = True
    try:
        base = _cfg(args.pdk)
    except Exception as e:
        print("configuration error: %s" % e)
        return 2
    print("configuration (config file: %s)" % (base.config_file or "none"))
    for name, val, src in base.describe():
        if name in ("pdk", "magicrc", "manifest"):
            continue
        print("  %-14s %-60s %s" % (name, val, src))
    for p, why in base.pdk_errors.items():
        ok = False
        print("PROBLEM: %s" % why)
    try:
        import klayout.db as kdb
        print("klayout module %s" % getattr(kdb, "__version__", "?"))
    except ImportError:
        print("klayout Python module: not importable (only needed outside KLayout)")
    pdks = [args.pdk] if args.pdk else base.pdks
    if not pdks:
        ok = False
        print("PROBLEM: no PDK selected (KMP_PDKS) or installed under %s" % base.pdk_root)
    for pdk in pdks:
        cfg = base.for_pdk(pdk)
        print("\n%s -> library %s" % (pdk, cfg.library_name))
        for name in ("magicrc", "manifest"):
            print("  %-14s %-60s %s" % (name, getattr(cfg, name), cfg.sources.get(name, "")))
        probs = cfg.problems()
        for p in probs:
            ok = False
            print("PROBLEM: " + p)
        if probs:
            continue
        man = Manifest.load(cfg.manifest)
        s = MagicServer(cfg, vendor_cells=man.vendor_cells())
        try:
            t = time.time()
            v = s.start()
            print("  Magic started in %.2f s: %s" % (time.time() - t, v.magic_banner))
            print("  magic %s, tech %s (%s), PDK commit %s, namespace %s, Tcl %s"
                  % (v.magic, v.tech, v.tech_name, v.pdk_commit or "?", v.namespace, v.tcl))
            if v.defaults_digest == man.defaults_digest:
                print("  manifest matches the running Magic (%d devices, %d box-paint generators)"
                      % (sum(1 for d in man.devices if d.kind == "device"),
                         sum(1 for d in man.devices if d.kind == "box")))
            else:
                ok = False
                print("  MANIFEST MISMATCH: defaults digest %s, manifest has %s"
                      % (v.defaults_digest[:16], man.defaults_digest[:16]))
                for dev, why in diff_defaults(man.defaults_by_device(), v.defaults):
                    print("    %s: %s" % (dev, why))
            missing = [d.name for d in man.devices if d.kind == "box" and d.name not in v.boxpaint]
            if missing:
                ok = False
                print("  MISSING box-paint generators: %s" % ", ".join(missing))
            spec = next((d for d in man.devices if d.family == "mos"), man.devices[0])
            out = os.path.join(s.run_dir, "doctor.gds")
            t = time.time()
            r = s.generate(spec.name, {}, spec.form, out)
            print("  %s defaults generated in %.1f ms (%s)" % (spec.name, (time.time() - t) * 1000, r.cell))
        except Exception as e:
            ok = False
            print("  BACKEND ERROR: %s" % e)
        finally:
            s.close()
    return 0 if ok else 1


def cmd_check(args):
    """Run _check once and show what it changes, then generate the device
    once to see whether Magic draws anything with the checked values (a
    _check can hand _draw a value it fails on, such as the SPICE string
    "68.465u"). Exits 1 when Magic draws nothing, 2 for a refused value."""
    from .backend import BackendError, MagicServer
    from .importer import gds_has_shapes
    from .manifest import InvalidValue
    from .pcell import changed_params
    cfg, man, spec = _find_device(args)
    vals = spec.defaults_values()
    vals.update(_kv(args.params, spec))
    try:
        req = spec.build_request(vals)
    except InvalidValue as e:
        print("error: %s" % e)
        return 2
    s = MagicServer(cfg, vendor_cells=man.vendor_cells())
    try:
        s.start()
        r = s.check(spec.name, req, spec.form if spec.kind == "box" else None)
        out = os.path.join(s.run_dir, "check.gds")
        g = s.generate(spec.name, req, spec.form, out)
        drawn = gds_has_shapes(out)
    except BackendError as e:
        print("error: %s" % e)
        return 1
    finally:
        s.close()
    ch = changed_params(req, r.checked)
    messages = [ln for ln in (g.log if not drawn else r.log).strip().splitlines() if ln.strip()]
    if spec.kind == "box":
        size = "%s x %s um" % (r.checked.get("w", req["w"]), r.checked.get("h", req["h"]))
        entered = " (entered %s x %s)" % (req["w"], req["h"]) if ch else ""
        if drawn:
            print("%s: Magic paints a %s box%s" % (spec.name, size, entered))
        else:
            print("%s: Magic paints nothing on a %s box%s" % (spec.name, size, entered))
    else:
        verb = "Magic draws" if drawn else "_check sets"
        if r.kv.get("check") == "none":
            print("%s: the PDK has no _check proc for it; Magic draws the values unchecked" % spec.name)
        elif r.kv.get("check") == "failed":
            print("%s: _check failed (%s); Magic draws the values unchecked"
                  % (spec.name, r.kv.get("check_error", "")))
        elif not ch:
            print("%s: _check changes nothing" % spec.name)
        for k, v in ch.items():
            print("%s: %s %s=%s (entered %s)" % (spec.name, verb, k, v, req[k]))
        if not drawn:
            print("%s: Magic draws nothing for these values" % spec.name)
    for line in messages:
        print("  message: " + line)
    return 0 if drawn else 1


def cmd_generate(args):
    from . import register, state_for
    cfg, man, spec = _find_device(args)
    lib = register(cfg.pdk)
    if lib is None:
        print("error: %s" % state_for(cfg.pdk).last_error)
        return 2
    from ._kl import db
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
    rep = audit(args.file, regen=args.regen, notes=print)
    if args.json:
        print(json.dumps(rep, indent=1, default=str))
    else:
        print(format_report(rep))
    return 1 if any(c["problems"] for c in rep["cells"]) or rep.get("file_problems") else 0


def cmd_cache(args):
    from .backend import MagicServer
    from .cache import GdsCache, versions_fields
    from .manifest import Manifest
    base = _cfg(args.pdk)
    if args.action == "clear":
        GdsCache(base.cache_dir, {}, enabled=True).clear()
        print("cleared %s" % base.cache_dir)
        return 0
    # The current versions directory of each PDK this command works on
    # (--pdk, else KMP_PDKS); prune keeps those and leaves other PDKs alone.
    caches = []
    for pdk in ([args.pdk] if args.pdk else base.pdks):
        cfg = base.for_pdk(pdk)
        if cfg.problems():
            print("note: %s is not usable (%s); its entries are left alone" % (pdk, cfg.problems()[0]))
            continue
        s = MagicServer(cfg, vendor_cells=Manifest.load(cfg.manifest).vendor_cells())
        try:
            v = s.start()
        finally:
            s.close()
        caches.append((pdk, GdsCache(base.cache_dir, versions_fields(v, pdk), enabled=True)))
    if not caches:
        print("error: no usable PDK to read the current versions from")
        return 1
    current = {p: c.vdigest for p, c in caches}
    if args.action == "prune":
        removed, other = caches[0][1].prune(current=current)
        for d in removed:
            print("removed %s" % d)
        for d, pdk in sorted(other.items()):
            print("kept %s: entries of %s, which this prune doesn't work on (it works on %s; "
                  "use --pdk %s, or KMP_PDKS)" % (d, pdk, ", ".join(sorted(current)), pdk))
    st = caches[0][1].stats()
    st.update(root=base.cache_dir, current=current)
    print(json.dumps(st, indent=1))
    return 0


def cmd_devices(args):
    from .manifest import Manifest
    base = _cfg(args.pdk)
    for pdk in ([args.pdk] if args.pdk else base.pdks):
        cfg = base.for_pdk(pdk)
        try:
            man = Manifest.load(cfg.manifest)
        except Exception as e:
            print("%s: %s" % (pdk, e))
            continue
        print("%s (library %s)" % (pdk, cfg.library_name))
        for d in man.devices:
            extra = ", fixed layout" if d.nocell else ", box paint: %s" % d.label if d.kind == "box" else ""
            print("  %s  [%s%s]" % (d.name, d.family, extra))
            if args.verbose:
                for p in d.params:
                    print("      %-10s %-7s default %-8s %s" % (p.name, p.type, p.default, p.label))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m klayout_magic_pcells",
                                 description="KLayout PCells generated by Magic")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn):
        p = sub.add_parser(name)
        p.add_argument("--pdk", help="the PDK (default: the selected ones, KMP_PDKS)")
        p.set_defaults(fn=fn)
        return p
    add("doctor", cmd_doctor)
    p = add("check", cmd_check)
    p.add_argument("device")
    p.add_argument("params", nargs="*")
    p = add("generate", cmd_generate)
    p.add_argument("device")
    p.add_argument("params", nargs="*")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--top", default="TOP")
    p = add("audit", cmd_audit)
    p.add_argument("file")
    p.add_argument("--regen", action="store_true")
    p.add_argument("--json", action="store_true")
    p = add("cache", cmd_cache)
    p.add_argument("action", choices=("stats", "prune", "clear"))
    p = add("devices", cmd_devices)
    p.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    # "devices -v | head" closes the pipe early: exit quietly (status 141)
    # instead of printing a BrokenPipeError traceback. Linux only, as is the
    # plugin.
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    sys.exit(main())
