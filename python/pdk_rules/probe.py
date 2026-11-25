"""Rule probes: check a table's values against the PDK's own KLayout DRC deck.

For every rule with a probe kind, draw the smallest shape the rule allows
(``pass`` layout, which must not be flagged for that rule) and the same shape
one grid step under the value (``fail`` layout, which must be). All probes of
a PDK go into one layout, each in its own slot, so the deck runs twice per
PDK; a marker belongs to the probe whose slot it lies in, and counts for a
rule when its category is the rule's id (``Rule.rule``, or ``Rule.probe_ids``).

    python3 -m pdk_rules.probe sky130A [--work DIR]

Needs the klayout Python module and the PDK under $PDK_ROOT.
"""

import math
import os
import re
import subprocess
import sys
import tempfile

from . import get

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")
SLOT = 40.0       # um between probe origins (the widest probe is about 22 um)


def _snap(x, grid):
    return round(round(x / grid) * grid, 6)


def _ceil(x, grid):
    return round(math.ceil(x / grid - 1e-9) * grid, 6)


def shapes(t, r, value):
    """[(layer name, (x1, y1, x2, y2))] that probe rule ``r`` at ``value``, near the origin."""
    g = t.grid
    layer = r.on[0]
    w_min, _ = t.width_space(layer)
    w_min = w_min or 0.5
    if r.kind == "width":
        return [(layer, (0, 0, value, max(2.0, _ceil(10 * value, g))))]
    if r.kind == "exact":
        return [(layer, (0, 0, value, value))]
    if r.kind == "space":
        cut = layer in t.rules and t.rules[layer].kind == "exact"
        if cut:
            w = h = t.um(layer)
        elif r.wide:
            # one wide shape and a narrow one beside it: gf180mcu.drc's M*.2b
            # finds no violation between two wide shapes (docs/rule-table.md)
            n = max(_ceil(2 * w_min, g), 0.5)
            return [(layer, (0, 0, r.wide, r.wide)), (layer, (r.wide + value, 0, r.wide + value + n, r.wide))]
        else:
            w, h = max(_ceil(2 * w_min, g), 0.5), max(_ceil(4 * w_min, g), 2.0)
        return [(layer, (0, 0, w, h)), (layer, (w + value, 0, 2 * w + value, h))]
    if r.kind == "enc":
        outer, inner = r.on
        s = r.size or t.um(inner)
        return [(inner, (value, value, value + s, value + s)), (outer, (0, 0, s + 2 * value, s + 2 * value))]
    if r.kind == "area":
        w = _snap(w_min, g)
        h = _ceil(r.value / w, g)
        if value < r.value:          # the fail probe: one grid step shorter
            h = round(h - g, 6)
        return [(layer, (0, 0, w, h))]
    raise ValueError(r.kind)


def build(t, which):
    """(klayout.db.Layout, {slot index: rule key}) of the pass or fail probes."""
    import klayout.db as db
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell("PROBES")
    slots = {}
    for i, (key, r) in enumerate(sorted(t.probed().items())):
        value = r.value if which == "pass" else round(r.value - t.grid, 6)
        if r.kind == "area":
            value = r.value if which == "pass" else r.value - 1e-9
        ox = i * SLOT
        for name, (x1, y1, x2, y2) in shapes(t, r, value):
            top.shapes(ly.layer(*t.layer(name))).insert(db.DBox(ox + x1, y1, ox + x2, y2))
        slots[i] = key
    return ly, slots


def run_deck(t, gds, work, timeout=1800):
    """[(category, x um)] of every marker the PDK's deck reports on ``gds``."""
    import klayout.db  # noqa: F401
    import klayout.rdb as rdb
    path, top_var, flags = t.drc_deck
    report = os.path.join(work, os.path.basename(gds) + ".lyrdb")
    cmd = ["klayout", "-b", "-r", os.path.join(PDK_ROOT, t.name, path), "-rd", "input=" + gds,
           "-rd", "%s=PROBES" % top_var, "-rd", "report=" + report]
    for k, v in flags.items():
        cmd += ["-rd", "%s=%s" % (k, v)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=work)
    if not os.path.isfile(report):
        raise RuntimeError("the deck wrote no report (status %d): %s" % (p.returncode, (p.stdout + p.stderr)[-800:]))
    r = rdb.ReportDatabase("")
    r.load(report)
    out = []
    for item in r.each_item():
        cat = r.category_by_id(item.category_id()).name()
        for v in item.each_value():
            box = None
            if v.is_box():
                box = v.box()
            elif v.is_polygon():
                box = v.polygon().bbox()
            elif v.is_edge_pair():
                box = v.edge_pair().bbox()
            elif v.is_edge():
                box = v.edge().bbox()
            if box is not None:
                out.append((cat, box.center().x))
    return out


def matches(rule, category):
    """Whether a deck category reports ``rule``: the same id, or the id plus a
    suffix the deck adds ("ct.1" -> "ct.1_a/b", "via.4a" -> "via.4a_a")."""
    c = category.strip().lower()
    for rid in rule.probe_ids or (rule.rule,):
        rid = rid.lower()
        if c == rid or re.match(re.escape(rid) + r"(_|/|\s|$)", c):
            return True
    return False


def probe(pdk, work=None):
    """{rule key: (status, detail)}; status "ok", "flagged_at_value" (the
    deck reports the rule on the pass probe: the value is too small or the
    probe breaks it otherwise) or "not_caught" (no report one grid step under:
    the value is too large, or the id differs from the deck's)."""
    import klayout.db  # noqa: F401
    t = get(pdk)
    work = work or tempfile.mkdtemp(prefix="probe_%s_" % pdk)
    os.makedirs(work, exist_ok=True)
    found = {}
    slots = None
    for which in ("pass", "fail"):
        ly, slots = build(t, which)
        gds = os.path.join(work, "%s_%s.gds" % (pdk, which))
        ly.write(gds)
        per_slot = {}
        for cat, x in run_deck(t, gds, work):
            i = int(math.floor((x + SLOT / 4) / SLOT))
            per_slot.setdefault(i, set()).add(cat)
        found[which] = per_slot
    out = {}
    for i, key in slots.items():
        r = t.rules[key]
        hit_pass = sorted(c for c in found["pass"].get(i, ()) if matches(r, c))
        hit_fail = sorted(c for c in found["fail"].get(i, ()) if matches(r, c))
        if hit_pass:
            out[key] = ("flagged_at_value", "pass probe flagged: %s" % ", ".join(hit_pass))
        elif not hit_fail:
            out[key] = ("not_caught", "fail probe categories: %s" % ", ".join(sorted(found["fail"].get(i, ()))))
        else:
            out[key] = ("ok", ", ".join(hit_fail))
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdk")
    ap.add_argument("--work")
    a = ap.parse_args(argv)
    res = probe(a.pdk, a.work)
    t = get(a.pdk)
    bad = 0
    for key, (status, detail) in sorted(res.items()):
        r = t.rules[key]
        bad += status != "ok"
        print("%-18s %-16s %-10s %8g  %s" % (status, key, r.rule, r.value, detail))
    print("%d/%d rules confirmed" % (len(res) - bad, len(res)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
