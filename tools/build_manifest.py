#!/usr/bin/env python3
"""Build the device manifest from the installed Magic and PDK.

Run inside the pinned image (Magic, the sky130A PDK and the klayout Python
module are needed)::

    python3 tools/build_manifest.py                 # rewrite the shipped manifest
    python3 tools/build_manifest.py --check         # compare with the shipped one
    python3 tools/build_manifest.py --out other.json

``scripts/manifest.sh`` runs either form in the image. Exit status: 0 when
written or when ``--check`` finds no difference, 1 when ``--check`` finds a
difference, 2 on errors.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "python"))

from klayout_magic_pcells import backend  # noqa: E402
from klayout_magic_pcells.config import Config, SHIPPED_MANIFEST, TCL_DIR  # noqa: E402

COUNT_KEYS = {"nf", "m", "nx", "ny"}
HELPER_REASON = ("internal helper _draw proc with no _defaults proc: the device _draw procs call it, "
                 "and Magic's menus don't offer it")
MENU_REASON = ("in Magic's \"%s\" menu as \"%s\", a command that paints into the current box; it has "
               "no _defaults proc and no parameter dialog, so magic::gencell can't build it as a "
               "parameterized cell, and this version has no PCell for it")


def menu_commands(tcl_path):
    """{helper: (menu label, entry label)} for the _draw procs that
    sky130A.tcl puts in Magic's toolkit menus as box-paint commands."""
    try:
        with open(tcl_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {}
    menus = dict((tag, label) for label, tag in
                 re.findall(r'add_toolkit_menu\s+\$\w+\s+"([^"]+)"\s+(\w+)', text))
    out = {}
    for entry, helper, tag in re.findall(
            r'add_toolkit_command\s+\$\w+\s+"([^"]+)"\s*\\?\s*"sky130::(\w+)_draw"\s+(\w+)', text):
        out[helper] = (menus.get(tag, tag), entry)
    return out


def numeric(text):
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def same_value(a, b):
    if a == b:
        return True
    if numeric(a) and numeric(b):
        return float(a) == float(b)
    return False


def family(name, defaults):
    d = dict(defaults)
    if "nocell" in d:
        return "fixed"
    cls = d.get("class", "")
    if "cap_var" in name:
        return "varactor"
    if cls == "mosfet" or "fet" in name:
        # nfet_g5v0d16v0 has no "class" key in its defaults
        return "mos"
    if cls == "resistor":
        return "res"
    if cls == "capacitor":
        return "mim_cap"
    if "photodiode" in name:
        return "photodiode"
    if cls == "diode":
        return "diode"
    return cls or "other"


def param_type(widget, name, default):
    if widget is None:
        return "internal"
    kind = widget["kind"]
    if kind == "checkbox":
        return "bool01"
    if kind == "message":
        return "readonly"
    if kind in ("selectlist", "selectindex"):
        return "enum"
    if "[+/-]" in widget["label"]:
        return "signed"
    if name in COUNT_KEYS:
        return "int"
    return "float" if numeric(default) else "string"


def gds_info(path):
    from klayout_magic_pcells._kl import db
    ly = db.Layout()
    ly.read(path)
    tops = ly.top_cells()
    top = tops[0]
    layers, texts = set(), []
    box = db.Box()
    g = 0  # gcd of every vertex and text coordinate, in dbu
    for li in ly.layer_indices():
        info = ly.get_info(li)
        ld = "%d/%d" % (info.layer, info.datatype)
        it = top.begin_shapes_rec(li)
        has = False
        while not it.at_end():
            sh = it.shape()
            has = True
            if sh.is_text():
                t = sh.text.transformed(it.trans())
                texts.append([t.string, ld, round(t.x * ly.dbu, 4), round(t.y * ly.dbu, 4)])
                g = math.gcd(g, abs(t.x), abs(t.y))
            else:
                box += sh.bbox().transformed(it.trans())
                pol = sh.polygon
                if pol is not None:
                    pol = pol.transformed(it.trans())
                    pts = list(pol.each_point_hull())
                    for h in range(pol.holes()):
                        pts += list(pol.each_point_hole(h))
                    for pt in pts:
                        g = math.gcd(g, abs(pt.x), abs(pt.y))
            it.next()
        if has:
            layers.add(ld)
    bbox = None if box.empty() else [round(box.left * ly.dbu, 4), round(box.bottom * ly.dbu, 4),
                                     round(box.right * ly.dbu, 4), round(box.top * ly.dbu, 4)]
    return {
        "top_cells": [c.name for c in tops],
        "cells": ly.cells(),
        "dbu": ly.dbu,
        "gds_bbox_um": bbox,
        "layers": sorted(layers, key=lambda s: tuple(int(x) for x in s.split("/"))),
        "texts": sorted(texts),
        # The coarsest grid all coordinates lie on, in nm; audit flags a file
        # whose dbu doesn't divide it (vendor cells with 1 nm coordinates).
        "grid_nm": int(round(g * ly.dbu * 1000)) if g else None,
    }


def run_magic(cfg, out_dir):
    env = dict(os.environ)
    env["KMP_MANIFEST_OUT"] = out_dir
    env["PDK_ROOT"] = cfg.pdk_root
    env["PDK"] = cfg.pdk
    cmd = [cfg.magic, "-dnull", "-noconsole", "-rcfile", cfg.magicrc,
           os.path.join(TCL_DIR, "kmp_manifest.tcl")]
    p = subprocess.run(cmd, cwd=out_dir, env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    text = p.stdout.decode("utf-8", errors="replace")
    if "KMP_MANIFEST_DONE" not in text:
        sys.stderr.write(text[-4000:])
        raise SystemExit("error: kmp_manifest.tcl did not finish (status %d)" % p.returncode)


def count_draw_definitions(tcl_path):
    try:
        with open(tcl_path, encoding="utf-8", errors="replace") as f:
            names = re.findall(r"^\s*proc\s+(?:::)?sky130::(\S+)_draw\s", f.read(), re.M)
    except OSError:
        return None, []
    dups = sorted({n for n in names if names.count(n) > 1})
    return len(names), dups


def build(cfg, work):
    run_magic(cfg, work)
    with open(os.path.join(work, "raw.json"), encoding="utf-8") as f:
        raw = json.load(f)
    with open(os.path.join(work, "versions.json"), encoding="utf-8") as f:
        vi = json.load(f)
    with open(os.path.join(work, "defaults.json"), encoding="utf-8") as f:
        defaults = json.load(f)
    code = backend.sha256_file(os.path.join(work, "procs.txt"))
    tech_file = vi.get("tech_file", "")
    try:
        import klayout.db as kdb
        kl_version = getattr(kdb, "__version__", "")
    except ImportError:
        kl_version = ""

    devices = []
    for d in raw["devices"]:
        name = d["name"]
        fam = family(name, d["defaults"])
        widgets = {w["name"]: w for w in d["widgets"] if w["kind"] != "dependency"}
        deps = [{"callback": w["name"], "params": w["extra"].split()}
                for w in d["widgets"] if w["kind"] == "dependency"]
        probes = {}
        for pr in d["probes"]:
            probes.setdefault(pr["param"], {})[pr["value"]] = pr
        params = []
        for k, v in d["defaults"]:
            w = widgets.get(k)
            t = param_type(w, k, v)
            p = {"name": k, "default": v, "type": t,
                 "editable": t in ("float", "int", "bool01", "signed", "string")}
            if w is not None:
                p["widget"] = w["kind"]
                p["label"] = w["label"]
            pr = probes.get(k)
            if pr and t in ("float", "signed", "int"):
                z, big, half = pr.get("0"), pr.get("10000"), pr.get("2.5")
                if z and not same_value(z["result"], "0"):
                    p["check_min"] = z["result"]
                if big and not same_value(big["result"], "10000"):
                    p["check_max"] = big["result"]
                if half:
                    p["check_int"] = not same_value(half["result"], "2.5")
                msgs = sorted({x["messages"].strip() for x in pr.values() if x["messages"].strip()})
                if msgs:
                    p["check_messages"] = msgs
            params.append(p)
        gsel = widgets.get("gencell")
        run = d["defaults_run"]
        dr = {"ok": run["ok"], "messages": run.get("messages", "")}
        if run["ok"]:
            info = gds_info(run["gds"])
            dr.update({"magic_cell": run["cell"], "top_cells": info["top_cells"],
                       "cells": info["cells"], "gds_bbox_um": info["gds_bbox_um"],
                       "grid_nm": info["grid_nm"],
                       "layers": info["layers"], "texts": info["texts"],
                       "checked": run["checked"]})
        else:
            dr["error"] = run.get("error", "")
        devices.append({
            "name": name,
            "family": fam,
            "nocell": d["nocell"],
            "form": d["form"],
            "has": {"check": bool(d["has_check"]), "convert": bool(d["has_convert"]),
                    "dialog": bool(d["has_dialog"])},
            "dialog_error": d["dialog_error"],
            "defaults": d["defaults"],
            "params": params,
            "device_type_switch": gsel["extra"].split() if gsel else None,
            "dialog_dependencies": deps,
            "check_on_defaults": {
                "changes": [c for c in d["check_on_defaults"]["changes"]],
                "messages": d["check_on_defaults"]["messages"],
                "error": d["check_on_defaults"]["error"],
            },
            "defaults_run": dr,
        })

    tcl_path = os.path.join(cfg.pdk_path, "libs.tech", "magic", cfg.pdk + ".tcl")
    ndef, dups = count_draw_definitions(tcl_path)
    menu = menu_commands(tcl_path)
    editable = []
    for d in devices:
        for p in d["params"]:
            if p["editable"] and p["name"] not in editable:
                editable.append(p["name"])
    manifest = {
        "format": 1,
        "pdk": cfg.pdk,
        "built_with": {
            "magic": backend.parse_magic_version(vi.get("magic_banner", "")),
            "magic_banner": vi.get("magic_banner", ""),
            "tech": vi.get("tech", ""),
            "tech_name": vi.get("tech_name", ""),
            "tcl": vi.get("tcl", ""),
            "open_pdks": backend.read_open_pdks(cfg.pdk_path),
            "klayout_module": kl_version,
        },
        "defaults_digest": backend.defaults_digest(defaults),
        "code_digest": code,
        "techfile_digest": backend.sha256_file(tech_file) if tech_file and os.path.isfile(tech_file) else "",
        "counts": {
            "draw_proc_definitions_in_source": ndef,
            "duplicate_draw_definitions": dups,
            "draw_procs": len(devices) + len(raw["helpers"]),
            "devices": len(devices),
            "helpers": len(raw["helpers"]),
            "editable_parameter_names": len(editable),
            "defaults_run_failures": sum(1 for d in devices if not d["defaults_run"]["ok"]),
        },
        "types": {
            "float": "number, PCell TypeDouble; sent as Magic's default string when equal to it, else rounded to 12 significant digits and written like a Python float",
            "int": "count (nf, m, nx, ny), PCell TypeInt",
            "bool01": "checkbox, PCell TypeBoolean, sent as 1 or 0",
            "signed": "coverage whose first character Magic reads as an anchor (+, - or none); PCell TypeString, sent verbatim when it is a decimal number with an optional + or - and optional whitespace, refused otherwise",
            "string": "other text entry, PCell TypeString, sent verbatim",
            "enum": "selectlist; not a PCell parameter",
            "readonly": "dialog message; not a PCell parameter",
            "internal": "no dialog widget; not a PCell parameter, Magic's default is used",
        },
        "excluded": [{"name": h, "proc": "sky130::%s_draw" % h,
                      "menu": ("%s / %s" % menu[h]) if h in menu else None,
                      "reason": (MENU_REASON % menu[h]) if h in menu else HELPER_REASON}
                     for h in raw["helpers"]],
        "devices": devices,
    }
    return manifest


def dumps(manifest):
    return json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"


def compare(a, b, path=""):
    """List the paths where two JSON values differ."""
    out = []
    if type(a) is not type(b):
        return ["%s: %r != %r" % (path or "/", a, b)]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append("%s/%s: only in %s" % (path, k, "built" if k in a else "shipped"))
            else:
                out += compare(a[k], b[k], "%s/%s" % (path, k))
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append("%s: %d items != %d" % (path, len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            name = x.get("name") if isinstance(x, dict) and "name" in x else i
            out += compare(x, y, "%s[%s]" % (path, name))
    elif a != b:
        out.append("%s: %r != %r" % (path, a, b))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=SHIPPED_MANIFEST)
    ap.add_argument("--check", action="store_true",
                    help="build into a temporary file and compare with --out")
    ap.add_argument("--keep", help="keep Magic's raw output in this directory")
    args = ap.parse_args(argv)
    cfg = Config.load()
    probs = [p for p in cfg.problems() if "manifest" not in p]
    if probs:
        for p in probs:
            sys.stderr.write("error: %s\n" % p)
        return 2
    work = args.keep or tempfile.mkdtemp(prefix="kmp-manifest-")
    os.makedirs(work, exist_ok=True)
    manifest = build(cfg, work)
    if not args.keep:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    if args.check:
        try:
            with open(args.out, encoding="utf-8") as f:
                shipped = json.load(f)
        except (OSError, ValueError) as e:
            sys.stderr.write("error: cannot read %s: %s\n" % (args.out, e))
            return 2
        diffs = compare(manifest, shipped)
        if diffs:
            print("MANIFEST DIFFERS from %s (%d differences):" % (args.out, len(diffs)))
            for line in diffs[:200]:
                print("  " + line)
            return 1
        print("MANIFEST OK: %s matches the installed Magic and PDK (%d devices)"
              % (args.out, len(manifest["devices"])))
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(dumps(manifest))
    c = manifest["counts"]
    print("wrote %s: %d devices, %d helpers excluded, %d editable parameter names, %d failures"
          % (args.out, c["devices"], c["helpers"], c["editable_parameter_names"],
             c["defaults_run_failures"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
