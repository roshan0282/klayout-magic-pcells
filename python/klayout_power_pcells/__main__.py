"""Command line: python3 -m klayout_power_pcells <command> ...

  doctor                          settings, tools, one timed drawing
  devices                         the devices and HW_FET's parameters
  check [k=v ...]                 what the form makes of these values: the summary, or why not
  generate [k=v ...] -o out.gds   place one HW_FET (through the library) in TOP and write a file
  hw [k=v ...] -o out.gds         draw the FET as a flat cell, no library
  verify [k=v ...]                draw it, then KLayout DRC, Magic DRC and netgen LVS
  ron [k=v ...] [--pixel 0.1] [--heatmap out.png]
                                  metal resistance R_S + R_D (Phase 2.1)
  audit FILE [--regen]            report the HW_FET cells in a file
  cache {stats,prune,clear}       this package's disk cache

Values are HW_FET's parameters (devices lists them), e.g.
  device=pfet_01v8 nx=6 ny=6 P=4 gate_strap=frame_only runners=met3,met4 bus=none guard_ring=0
P, L, N and bus_w of 0 mean "the minimum"; runner_w=0 the widest stripe that fits.
check also prints the minimums (and ranges) these values allow.

Exit status: 0 when the FET is drawn (and, for verify, DRC and LVS pass),
1 when it isn't or a check fails, 2 for a value that isn't a number or not
one of the choices.
"""

import argparse
import os
import sys
import tempfile
import time


def _decl():
    from .pcell import HWFetPCell
    return HWFetPCell()


def _kv(items):
    """{name: value} from name=value words, typed as the PCell declares
    them; exits 2 on a bad value."""
    import klayout.db as db
    decl = {p.name: p for p in _decl().get_parameters() if not p.hidden and not p.readonly}
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit("error: expected name=value, got %r" % it)
        k, v = it.split("=", 1)
        if k not in decl:
            raise SystemExit("error: HW_FET has no parameter %r (try: devices)" % k)
        p = decl[k]
        try:
            if p.type == db.PCellParameterDeclaration.TypeInt:
                out[k] = int(v)
            elif p.type == db.PCellParameterDeclaration.TypeDouble:
                out[k] = float(v)
            elif p.type == db.PCellParameterDeclaration.TypeBoolean:
                if v.lower() not in ("0", "1", "true", "false"):
                    raise ValueError("not 0 or 1")
                out[k] = v.lower() in ("1", "true")
            else:
                choices = list(p.choice_values())
                if choices and v not in choices:
                    raise ValueError("not one of %s" % ", ".join(choices))
                out[k] = v
        except ValueError as e:
            sys.stderr.write("error: %s=%r: %s\n" % (k, v, e))
            raise SystemExit(2)
    return out


def _params(vals):
    from .pcell import EDITABLE, params_of_values
    full = {p.name: p.default for p in _decl().get_parameters()}
    full.update(vals)
    return params_of_values({n: full[n] for n in EDITABLE})


def cmd_doctor(args):
    from klayout_magic_pcells.config import Config
    from . import __version__, backend
    from .verify import tools
    from .waffle import WaffleParams, build, summary
    ok = True
    cfg = Config.load(pdk="sky130A")
    print("klayout_power_pcells %s (generator code %s, rules %s)" % (__version__, backend.code_digest(),
                                                                     backend.rules_digest()))
    for name, val, src in cfg.describe():
        if name in ("pdk_root", "cache_dir", "cache_enabled", "lazy"):
            print("  %-14s %-60s %s" % (name, val, src))
    try:
        import klayout.db as kdb
        print("klayout module %s" % getattr(kdb, "__version__", "?"))
    except ImportError:
        ok = False
        print("PROBLEM: the klayout Python module is not importable")
    st = backend.start()
    print("stamp %s" % st.created_stamp)
    print("cache %s (%s)" % (st.cache.base, "on" if st.cache.enabled else "off: session only"))
    for t, path in tools().items():
        print("  %-8s %s" % (t, path or "not found (needed by verify only)"))
    t0 = time.time()
    try:
        w = build(WaffleParams(nx=3, ny=3))
        print("drew a 3x3 HW_FET in %.2f s: %s" % (time.time() - t0, summary(w)))
    except Exception as e:
        ok = False
        print("PROBLEM: drawing a 3x3 HW_FET failed: %s" % e)
    return 0 if ok else 1


def cmd_devices(args):
    from .rules import PDKS
    pdk = PDKS["sky130A"]
    print("HW_FET in sky130_power (sky130A); devices:")
    for n, d in sorted(pdk["devices"].items()):
        print("  %-16s %sfet%s, L >= %.3f um%s" % (n, d["kind"], " thick oxide (hvi)" if d["hv"] else "",
                                                  d["lmin"] / 1000.0,
                                                  (", " + "+".join(d["vt"])) if d["vt"] else ""))
    print("parameters:")
    for p in _decl().get_parameters():
        if p.hidden:
            continue
        ch = list(p.choice_values())
        print("  %-12s %-38s default %-12s%s%s" % (p.name, p.description, p.default,
                                                   ("  one of " + ", ".join(ch)) if ch else "",
                                                   "  (read-only)" if p.readonly else ""))
    return 0


def cmd_check(args):
    from .waffle import WaffleError, build, limits, limits_text, summary, why_not
    p = _params(_kv(args.values))
    print("minimums: %s" % limits_text(limits(p)))
    try:
        w = build(p)
    except WaffleError as e:
        print("HW_FET: not drawn: %s (parameter %s)" % (why_not(e, p), e.param))
        return 1
    print("HW_FET: %s" % summary(w))
    return 0


def cmd_generate(args):
    import klayout.db as db
    from . import form_values, register
    from .pcell import ERROR_LAYER
    vals = _kv(args.values)
    if register() is None:
        return 1
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
    from .waffle import WaffleError, summary, write_gds
    try:
        w = write_gds(_params(_kv(args.values)), args.out, name=args.name)
    except WaffleError as e:
        print("error: %s (parameter %s)" % (e, e.param), file=sys.stderr)
        return 1
    print(summary(w))
    print("wrote %s (cell %s)" % (args.out, args.name))
    return 0


def cmd_verify(args):
    from .verify import verify
    from .waffle import WaffleError, summary, write_gds
    work = args.keep or tempfile.mkdtemp(prefix="hw_verify_")
    os.makedirs(work, exist_ok=True)
    gds = os.path.join(work, "HW_FET.gds")
    try:
        w = write_gds(_params(_kv(args.values)), gds)
    except WaffleError as e:
        print("not drawn: %s (parameter %s)" % (e, e.param))
        return 1
    print(summary(w))
    res = verify(gds, w.report, work=work, lvs=not args.no_lvs)
    print("KLayout DRC (%s): %s" % ("sky130A_mr.drc", res["klayout"] or "clean"))
    print("Magic DRC (drc(full)): %s" % (res["magic"] or "clean"))
    if "devices" in res:
        print("extracted %d devices, W %.3f um; LVS against one device of W %.3f: %s"
              % (res["devices"], res["W_extracted_um"], w.report["W_total_um"],
                 {True: "match", False: "MISMATCH", None: "skipped (bus=none with stripes: one net per stripe)"}[res["lvs"]]))
    for p in res["problems"]:
        print("PROBLEM: " + p)
    if args.keep:
        print("files in %s" % work)
    else:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return 1 if res["problems"] else 0


def cmd_audit(args):
    from .audit import audit, format_report
    rep = audit(args.file, regen=args.regen, notes=print)
    print(format_report(rep))
    return 1 if any(c["problems"] for c in rep["cells"]) or rep.get("file_problems") else 0


def cmd_cache(args):
    from klayout_magic_pcells.cache import GdsCache
    from klayout_magic_pcells.config import Config
    from . import backend
    cfg = Config.load(pdk="sky130A")
    root = os.path.join(cfg.cache_dir, "power")
    c = GdsCache.__new__(GdsCache)
    c.root = root
    if args.action == "stats":
        n = size = 0
        for d in c.version_dirs():
            for dp, _, files in os.walk(d):
                for fn in files:
                    n += fn.endswith(".gds")
                    size += os.path.getsize(os.path.join(dp, fn))
        print("cache %s: %d entries, %.1f MB, %d versions directories" % (root, n, size / 1e6, len(c.version_dirs())))
        return 0
    if args.action == "clear":
        c.clear()
        print("cleared %s" % root)
        return 0
    st = backend.start()
    removed, _other = st.cache.prune(current={"sky130A": st.cache.vdigest})
    print("pruned %d directories; kept %s" % (len(removed), st.cache.base))
    return 0


def cmd_ron(args):
    from .ron import RonError, ron_metal
    from .waffle import WaffleError
    try:
        r = ron_metal(_params(_kv(args.values)), pixel=args.pixel, heatmap=args.heatmap)
    except (WaffleError, RonError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print("R_S %.4f ohm, R_D %.4f ohm, metal R_S + R_D %.4f ohm; licon contacts %.4f ohm"
          % (r["R_S"], r["R_D"], r["R_metal"], r["R_contacts"]))
    print("%d S and %d D squares, W %.2f um, %d nodes at %.3f um pixels"
          % (r["squares"][0], r["squares"][1], r["W_total_um"] or 0, r["nodes"], r["pixel"]))
    if args.heatmap:
        print("current density map: %s" % args.heatmap)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="klayout_power_pcells", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("devices")
    p = sub.add_parser("check")
    p.add_argument("values", nargs="*")
    p = sub.add_parser("generate")
    p.add_argument("values", nargs="*")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--top", default="TOP")
    p = sub.add_parser("hw")
    p.add_argument("values", nargs="*")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--name", default="HW_FET")
    p = sub.add_parser("verify")
    p.add_argument("values", nargs="*")
    p.add_argument("--no-lvs", action="store_true")
    p.add_argument("--keep", help="keep the GDS, reports and netlists in this directory")
    p = sub.add_parser("ron")
    p.add_argument("values", nargs="*")
    p.add_argument("--pixel", type=float, default=0.1, help="mesh pixel in um")
    p.add_argument("--heatmap", help="write a current-density PNG")
    p = sub.add_parser("audit")
    p.add_argument("file")
    p.add_argument("--regen", action="store_true")
    p = sub.add_parser("cache")
    p.add_argument("action", choices=("stats", "prune", "clear"))
    args = ap.parse_args(argv)
    return {"doctor": cmd_doctor, "devices": cmd_devices, "check": cmd_check, "generate": cmd_generate,
            "hw": cmd_hw, "verify": cmd_verify, "ron": cmd_ron, "audit": cmd_audit, "cache": cmd_cache}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
