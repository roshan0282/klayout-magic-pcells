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


def _rotated_copy(gds, top, out):
    """``gds`` turned by 180 degrees (flattened), written to ``out``."""
    import klayout.db as db
    ly = db.Layout()
    ly.read(gds)
    cell = ly.cell(top)
    cell.flatten(True)
    cell.transform(db.Trans(db.Trans.R180))
    ly.write(out)
    return out


def extract_ld(gds, top, work, model, pdk="sky130A"):
    """Extraction of an extended-drain (LDMOS) FET, around a Magic limit.

    Magic (8.3.685, sky130A tech) extracts an extended-drain device only
    when its drift region lies west of a vertical gate or north of a
    horizontal one; turned the other way (drift east or south) the same
    gate comes out as a g5v0d10v5 of twice the length with S on both
    sides. The PDK's own single-finger device does the same when mirrored.
    A waffle has gates facing all four ways, so the cell is extracted as
    drawn and turned by 180 degrees: each gate faces the working way in
    exactly one of them. The devices of ``model`` from both are merged into
    one netlist (net names come from the labels, which turn with the
    shapes). Returns (spice, devices, {"as_drawn": n0, "turned": n1,
    "other": [devices of another model in either]})."""
    spice0, devs0 = extract(gds, top, work, pdk)
    w1 = os.path.join(work, "r180")
    os.makedirs(w1, exist_ok=True)
    spice1, devs1 = extract(_rotated_copy(gds, top, os.path.join(w1, top + ".gds")), top, w1, pdk)
    good0 = [d for d in devs0 if d["model"] == model]
    good1 = [d for d in devs1 if d["model"] == model]
    other = [d for d in devs0 + devs1 if d["model"] != model]
    with open(spice0) as f:
        lines0 = f.read().replace("\n+", " ").splitlines()
    with open(spice1) as f:
        lines1 = f.read().replace("\n+", " ").splitlines()

    def is_dev(ln):
        t = ln.split()
        return bool(t) and t[0][0] in "Xx" and len(t) > 5

    def keep(ln):
        return [x for x in ln.split() if "=" not in x][5] == model
    out = []
    for ln in lines0:
        if is_dev(ln) and not keep(ln):
            continue
        if ln.strip().lower().startswith(".ends"):
            out += ["XR" + l1.split(None, 1)[0][1:] + " " + l1.split(None, 1)[1]
                    for l1 in lines1 if is_dev(l1) and keep(l1)]
        out.append(ln)
    merged = os.path.join(work, top + "_merged.spice")
    with open(merged, "w") as f:
        f.write("\n".join(out) + "\n")
    return merged, good0 + good1, {"as_drawn": len(good0), "turned": len(good1), "other": other}


# The PDKs' own KLayout LVS decks, run directly (their run_lvs.py wrappers
# need docopt and pass the same -rd variables). Settings each deck needs for
# a schematic written the way xschem writes it (docs/klayout-lvs.md):
#   sky130A: xschem keeps the X prefix of the device subcircuits, which the
#     deck turns into devices only with convert_subckts=true; W and L come
#     without units (the models set .option scale=1e-6).
#   gf180mcuD: xschem's lvs_format writes M elements with units (W=1u).
# Both: schematic_simplify=true, or the deck combines parallel devices on
# the layout side only.
KLAYOUT_LVS = {
    "sky130A": {"deck": ("libs.tech", "klayout", "lvs", "sky130.lvs"), "top": "top_cell",
                "flags": {"convert_subckts": "true", "schematic_simplify": "true"}, "scale": "1e-6"},
    "gf180mcuD": {"deck": ("libs.tech", "klayout", "tech", "lvs", "gf180mcu.lvs"), "top": "topcell",
                  "flags": {"variant": "D", "schematic_simplify": "true"}, "scale": None},
}


def klayout_lvs(gds, top, schematic, work, pdk="sky130A", substrate=None, timeout=3600):
    """(matched, info) of the PDK's KLayout LVS deck: ``gds``/``top`` against
    the SPICE file ``schematic`` (a .subckt named like ``top``).

    ``substrate`` names the substrate net (``lvs_sub``) when the schematic
    connects bulks to a net that is not a pin, e.g. Magic's ``VSUBS``. On
    sky130A, a schematic without ``.option scale`` gets ``scale=1e-6``
    prepended in a copy. ``info``: ``report`` (.lvsdb), ``extracted``
    (netlist), ``circuits`` ({layout circuit: status}) and ``log``.
    """
    cfg = KLAYOUT_LVS[pdk]
    os.makedirs(work, exist_ok=True)
    sch = os.path.abspath(schematic)
    if cfg["scale"]:
        with open(sch) as f:
            text = f.read()
        if not re.search(r"^\s*\.options?\s+.*\bscale\s*=", text, re.I | re.M):
            sch = os.path.join(work, "schematic_scaled.spice")
            with open(sch, "w") as f:
                f.write(".option scale=%s\n%s" % (cfg["scale"], text))
    report = os.path.join(work, top + ".lvsdb")
    extracted = os.path.join(work, top + "_extracted.cir")
    for p in (report, extracted):
        if os.path.exists(p):
            os.remove(p)
    rd = {"input": os.path.abspath(gds), cfg["top"]: top, "report": report, "schematic": sch,
          "target_netlist": extracted, "run_mode": "deep"}
    rd.update(cfg["flags"])
    if substrate:
        rd["lvs_sub"] = substrate
    cmd = ["klayout", "-b", "-r", os.path.join(PDK_ROOT, pdk, *cfg["deck"])]
    for k, v in rd.items():
        cmd += ["-rd", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=work)
    log = p.stdout + p.stderr
    if not os.path.isfile(report):
        raise RuntimeError("KLayout LVS wrote no report (status %d): %s" % (p.returncode, log[-800:]))
    import klayout.db as db
    lvs = db.LayoutVsSchematic()
    lvs.read(report)
    circuits = {}
    for cp in lvs.xref().each_circuit_pair():
        a, b = cp.first(), cp.second()
        circuits[(a or b).name] = str(cp.status())
    good = {"Match", "MatchWithWarning", "Skipped"}
    matched = bool(circuits) and all(s.split(".")[-1] in good for s in circuits.values())
    return matched, {"report": report, "extracted": extracted, "circuits": circuits, "log": log}


def netgen_lvs(spice, top, model, w_total, l, work, pdk="sky130A", timeout=3600, body="B"):
    """(matched, text) of netgen against one device of W = w_total, its body
    on ``body`` (B, its own pin, or S with taps in the source squares)."""
    sch = os.path.join(work, "reference.spice")
    pins = "S D G" if body == "S" else "S D G %s" % body
    with open(sch, "w") as f:
        f.write(".subckt %s %s\nXM1 D G S %s %s w=%g l=%g\n.ends\n" % (top, pins, body, model, w_total, l))
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
            if report.get("ld"):
                spice, devs, how = extract_ld(gds, top, work, report["model"], pdk)
                res["ld_extraction"] = {k: (len(v) if k == "other" else v) for k, v in how.items()}
                # every gate must extract right in exactly one orientation
                if len(how["other"]) != report["n_gates"]:
                    probs.append("orientation split: %d + %d right, %d other (expected %d other)"
                                 % (how["as_drawn"], how["turned"], len(how["other"]), report["n_gates"]))
            else:
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
            body = report.get("body")
            joined = report.get("sd_joined", report.get("bus", "L_buses") == "L_buses")
            if body and joined and any(d["b"] != body for d in devs):
                probs.append("a device's body is not on %s: %s" % (body, sorted({d["b"] for d in devs})))
            w_sum = sum(d["w"] for d in devs)
            res["W_extracted_um"] = round(w_sum, 4)
            if abs(w_sum - report["W_total_um"]) > 0.001 * max(1, report["n_gates"]):
                probs.append("extracted W %.3f, drew %.3f" % (w_sum, report["W_total_um"]))
            if joined:
                ok, text = netgen_lvs(spice, top, report["model"], report["W_total_um"], report["L_um"], work, pdk,
                                      body=report.get("body") or "B")
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
