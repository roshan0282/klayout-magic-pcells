"""DRC and extraction runners for the parity harness.

KLayout runs the PDK deck ``sky130A_mr.drc`` with feol, beol and offgrid on
(without feol and beol the deck checks nothing), floating_met off and seal
off; the deck exits 0 even with violations, so results come from the report
database. Magic runs ``mdrc.tcl`` (drc(full) with drc catchup). Only sets of
rule IDs are compared, never counts, and never Magic's IDs against KLayout's.
"""

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")
PDK = "sky130A"
DECK = os.path.join(PDK_ROOT, PDK, "libs.tech", "klayout", "drc", PDK + "_mr.drc")
MAGICRC = os.path.join(PDK_ROOT, PDK, "libs.tech", "magic", PDK + ".magicrc")
KLAYOUT_FLAGS = {"feol": "true", "beol": "true", "offgrid": "true", "floating_met": "false",
                 "seal": "false", "thr": "1"}

_RULE_RE = re.compile(r"\(([^()]*)\)\s*$")


def magic_rule_id(message):
    m = _RULE_RE.search(message.strip())
    return m.group(1).strip() if m else message.strip()


def run_klayout_drc(gds, top, report, log_path, timeout=3600):
    cmd = ["klayout", "-b", "-r", DECK, "-rd", "input=" + gds, "-rd", "top_cell=" + top,
           "-rd", "report=" + report]
    for k, v in KLAYOUT_FLAGS.items():
        cmd += ["-rd", "%s=%s" % (k, v)]
    with open(log_path, "w") as lf:
        p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode != 0 or not os.path.isfile(report):
        raise RuntimeError("KLayout DRC failed (status %d), see %s" % (p.returncode, log_path))
    return parse_rdb(report)


def _value_bbox(v):
    for test, get in (("is_box", "box"), ("is_polygon", "polygon"), ("is_edge_pair", "edge_pair"),
                      ("is_edge", "edge"), ("is_path", "path"), ("is_text", "text")):
        if hasattr(v, test) and getattr(v, test)():
            shape = getattr(v, get)()
            b = shape.bbox()
            return [b.left, b.bottom, b.right, b.top]
    return None


def parse_rdb(path):
    """[(rule, cell, [l, b, r, t] um), ...] from a KLayout report database.

    The deck runs hierarchically, so a marker found inside a device cell is
    reported in that cell, in the cell's own coordinates.
    """
    import klayout.db  # noqa: F401  (binds the db types that rdb values return)
    import klayout.rdb as rdb
    db = rdb.ReportDatabase("")
    db.load(path)
    out = []
    for item in db.each_item():
        cat = db.category_by_id(item.category_id())
        name = cat.name()
        cell = db.cell_by_id(item.cell_id()).name()
        box = None
        for v in item.each_value():
            b = _value_bbox(v)
            if b is None:
                continue
            box = b if box is None else [min(box[0], b[0]), min(box[1], b[1]),
                                         max(box[2], b[2]), max(box[3], b[3])]
        out.append((name, cell, box))
    return out


def run_magic_drc(gds, top, out_tsv, log_path, timeout=3600):
    env = dict(os.environ, KMP_GDS=gds, KMP_TOP=top, KMP_OUT=out_tsv)
    cmd = ["magic", "-dnull", "-noconsole", "-rcfile", MAGICRC, os.path.join(HERE, "mdrc.tcl")]
    with open(log_path, "w") as lf:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                           env=env, timeout=timeout, cwd=os.path.dirname(out_tsv))
    with open(log_path, errors="replace") as lf:
        if "MDRC_DONE" not in lf.read():
            raise RuntimeError("Magic DRC did not finish (status %d), see %s" % (p.returncode, log_path))
    out = []
    with open(out_tsv, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "\t" not in line:
                continue
            msg, box = line.rstrip("\n").split("\t", 1)
            vals = [float(x) for x in box.split()]
            if len(vals) == 4:
                out.append((magic_rule_id(msg), None, vals))
    return out


def run_magic_extract(gds, cells, out_dir, log_path, timeout=3600):
    """Extract each flat cell; return {cell: [(model, w, l), ...]}."""
    os.makedirs(out_dir, exist_ok=True)
    env = dict(os.environ, KMP_GDS=gds, KMP_CELLS=" ".join(cells), KMP_OUT=out_dir)
    cmd = ["magic", "-dnull", "-noconsole", "-rcfile", MAGICRC, os.path.join(HERE, "extract.tcl")]
    with open(log_path, "w") as lf:
        subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                       env=env, timeout=timeout, cwd=out_dir)
    with open(log_path, errors="replace") as lf:
        text = lf.read()
    if "EXTRACT_DONE" not in text:
        raise RuntimeError("Magic extraction did not finish, see %s" % log_path)
    out = {}
    for c in cells:
        path = os.path.join(out_dir, c + ".spice")
        out[c] = parse_spice(path) if os.path.isfile(path) else None
    return out


def parse_spice(path):
    """Device lines of an ext2spice netlist as (model, w, l) tuples."""
    lines = []
    with open(path, errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if raw.startswith("+") and lines:
                lines[-1] += " " + raw[1:]
            else:
                lines.append(raw)
    devs = []
    for line in lines:
        s = line.strip()
        if not s or s[0] not in "XxMm" or s.lower().startswith(".subckt"):
            continue
        toks = s.split()
        params = dict(t.split("=", 1) for t in toks if "=" in t)
        plain = [t for t in toks if "=" not in t]
        if len(plain) < 2:
            continue
        model = plain[-1]

        def num(v):
            try:
                return round(float(v), 4)
            except (TypeError, ValueError):
                return v
        devs.append((model, num(params.get("w")), num(params.get("l"))))
    return devs
