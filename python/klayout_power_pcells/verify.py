"""DRC and LVS of a hybrid-waffle GDS (spec section 8), with the PDK's tools:

* KLayout DRC: the PDK's deck, ``sky130A_mr.drc`` with feol, beol and
  offgrid on (floating_met and seal off), as klayout-magic-pcells' harness
  runs it. Results come from the report database.
* Magic DRC: ``drc(full)`` with ``drc catchup`` (without it batch Magic
  reports nothing), on the cell and a 10 um margin.
* LVS: Magic extraction (labels made ports), then netgen with the PDK's
  setup against a schematic of one device of W = W_total, L = L. netgen
  merges the parallel devices. Every extracted device is also checked
  directly: model, L, S != D, gate on G, and the sum of W.

Needs klayout, magic and netgen on PATH and the PDK under PDK_ROOT
(the iic-osic-tools image has all of them).
"""

import collections
import os
import re
import shutil
import subprocess
import tempfile

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")

KLAYOUT_FLAGS = {"feol": "true", "beol": "true", "offgrid": "true", "floating_met": "false",
                 "seal": "false", "thr": "1"}

MAGIC_DRC = r'''
catch {crashbackups stop}
drc off
gds read {gds}
load {top}
select top cell
box grow c 10um
drc euclidean on
drc style drc(full)
drc check
drc catchup
set fh [open {out} w]
foreach {{why boxes}} [drc listall why] {{
    foreach b $boxes {{ puts $fh "[string map {{\t { } \n { }}} $why]" }}
}}
close $fh
puts stdout "MDRC_DONE"
quit -noprompt
'''

MAGIC_EXTRACT = r'''
catch {{crashbackups stop}}
drc off
gds read {gds}
load {top}
select top cell
port makeall
cd {dir}
extract no capacitance
extract no coupling
extract no resistance
extract all
ext2spice lvs
ext2spice -o {top}.spice
puts stdout "EXT_DONE"
quit -noprompt
'''


def tools():
    """{tool: path or None} for what verification needs."""
    return {t: shutil.which(t) for t in ("klayout", "magic", "netgen")}


def _rc(pdk):
    return os.path.join(PDK_ROOT, pdk, "libs.tech", "magic", pdk + ".magicrc")


def klayout_drc(gds, top, work, pdk="sky130A", timeout=3600):
    """{rule: count} from the PDK's KLayout deck."""
    deck = os.path.join(PDK_ROOT, pdk, "libs.tech", "klayout", "drc", pdk + "_mr.drc")
    report = os.path.join(work, "klayout.lyrdb")
    cmd = ["klayout", "-b", "-r", deck, "-rd", "input=" + os.path.abspath(gds), "-rd", "top_cell=" + top,
           "-rd", "report=" + report]
    for k, v in KLAYOUT_FLAGS.items():
        cmd += ["-rd", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=work)
    if not os.path.isfile(report):
        raise RuntimeError("KLayout DRC wrote no report (status %d): %s" % (p.returncode, p.stdout[-500:]))
    import klayout.db  # noqa: F401
    import klayout.rdb as rdb
    r = rdb.ReportDatabase("")
    r.load(report)
    out = collections.Counter()
    for item in r.each_item():
        out[r.category_by_id(item.category_id()).name()] += 1
    return dict(out)


def magic_drc(gds, top, work, pdk="sky130A", timeout=3600):
    """{rule: count} from Magic's drc(full)."""
    out = os.path.join(work, "magic_drc.txt")
    tcl = os.path.join(work, "drc.tcl")
    with open(tcl, "w") as f:
        f.write(MAGIC_DRC.replace("{gds}", os.path.abspath(gds)).replace("{top}", top).replace("{out}", out)
                .replace("{{", "{").replace("}}", "}"))
    p = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", _rc(pdk), tcl], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=timeout, cwd=work)
    if "MDRC_DONE" not in p.stdout:
        raise RuntimeError("Magic DRC did not finish: %s" % p.stdout[-500:])
    rules = collections.Counter()
    with open(out, errors="replace") as f:
        for line in f:
            m = re.search(r"\(([^()]*)\)\s*$", line.strip())
            rules[m.group(1) if m else line.strip()] += 1
    return dict(rules)


def extract(gds, top, work, pdk="sky130A", timeout=3600):
    """Path of the extracted SPICE netlist and its devices
    [{d, g, s, b, model, w, l}] (lengths in um)."""
    tcl = os.path.join(work, "extract.tcl")
    with open(tcl, "w") as f:
        f.write(MAGIC_EXTRACT.format(gds=os.path.abspath(gds), top=top, dir=work))
    p = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", _rc(pdk), tcl], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=timeout, cwd=work)
    spice = os.path.join(work, top + ".spice")
    if "EXT_DONE" not in p.stdout or not os.path.isfile(spice):
        raise RuntimeError("Magic extraction failed: %s" % p.stdout[-500:])
    devs = []
    with open(spice) as f:
        text = f.read().replace("\n+", " ")
    for line in text.splitlines():
        t = line.split()
        if t and t[0][0] in "Xx" and len(t) > 5:
            kv = dict(x.split("=", 1) for x in t if "=" in x)
            plain = [x for x in t if "=" not in x]
            devs.append({"d": plain[1], "g": plain[2], "s": plain[3], "b": plain[4], "model": plain[5],
                         "w": float(kv.get("w", "nan")), "l": float(kv.get("l", "nan"))})
    return spice, devs


def netgen_lvs(spice, top, model, w_total, l, work, pdk="sky130A", timeout=3600):
    """(matched, text) of netgen against one device of W = w_total."""
    sch = os.path.join(work, "reference.spice")
    with open(sch, "w") as f:
        f.write(".subckt %s S D G B\nXM1 D G S B %s w=%g l=%g\n.ends\n" % (top, model, w_total, l))
    rep = os.path.join(work, "lvs.out")
    setup = os.path.join(PDK_ROOT, pdk, "libs.tech", "netgen", pdk + "_setup.tcl")
    p = subprocess.run(["netgen", "-batch", "lvs", "%s %s" % (spice, top), "%s %s" % (sch, top), setup, rep],
                       capture_output=True, text=True, timeout=timeout, cwd=work)
    text = p.stdout
    if os.path.isfile(rep):
        with open(rep) as f:
            text = f.read() + text
    return "Circuits match uniquely" in text, text


def verify(gds, report, top="HW_FET", pdk="sky130A", lvs=True, work=None):
    """Run everything on ``gds`` (drawn with ``report``, a Waffle report).
    Returns {"klayout": {...}, "magic": {...}, "devices": ..., "lvs": bool,
    "problems": [...]}."""
    own = work is None
    work = work or tempfile.mkdtemp(prefix="hw_verify_")
    try:
        res = {"klayout": klayout_drc(gds, top, work, pdk), "magic": magic_drc(gds, top, work, pdk)}
        probs = []
        if res["klayout"]:
            probs.append("KLayout DRC: %s" % res["klayout"])
        if res["magic"]:
            probs.append("Magic DRC: %s" % res["magic"])
        if lvs:
            spice, devs = extract(gds, top, work, pdk)
            res["devices"] = len(devs)
            models = {d["model"] for d in devs}
            if len(devs) != report["n_gates"]:
                probs.append("extracted %d devices, drew %d gates" % (len(devs), report["n_gates"]))
            if models != {report["model"]}:
                probs.append("models %s, expected %s" % (sorted(models), report["model"]))
            if any(abs(d["l"] - report["L_um"]) > 0.0051 for d in devs):
                probs.append("a device's L differs from %.3f" % report["L_um"])
            if any(d["s"] == d["d"] for d in devs):
                probs.append("a device has S and D on one net")
            if any(d["g"] != "G" for d in devs):
                probs.append("a gate is not on G")
            w_sum = sum(d["w"] for d in devs)
            res["W_extracted_um"] = round(w_sum, 4)
            if abs(w_sum - report["W_total_um"]) > 0.001 * max(1, report["n_gates"]):
                probs.append("extracted W %.3f, drew %.3f" % (w_sum, report["W_total_um"]))
            if report.get("bus", "L_buses") == "L_buses":
                ok, text = netgen_lvs(spice, top, report["model"], report["W_total_um"], report["L_um"], work, pdk)
                res["lvs"] = ok
                if not ok:
                    final = [ln.strip() for ln in text.splitlines() if "Final result" in ln or "match" in ln]
                    probs.append("netgen: %s" % (" | ".join(final[-3:]) or "no result"))
            else:
                res["lvs"] = None      # stripes are separate nets until the top level joins them
        res["problems"] = probs
        return res
    finally:
        if own:
            shutil.rmtree(work, ignore_errors=True)
