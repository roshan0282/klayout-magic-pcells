"""Audit a layout file for sky130_magic cells without registering the library.

Reports cells that hold a placeholder, cells with no stamp, empty cells,
stamps from a different Magic or PDK than the installed one (including a
locally edited sky130A.tcl, through the stamp's digest), a file dbu that
doesn't divide 5 nm, and devices whose Magic output lies on a finer grid
than the file's dbu (vendor cells with 1 nm coordinates in a 5 nm file).
With ``regen=True`` it keeps a copy of every cell's stored geometry,
registers the library (the cells revive and regenerate), and reports each
cell whose regenerated geometry differs as a problem.
"""

from fractions import Fraction

from .library import LIBRARY_NAME
from .pcell import PLACEHOLDER_LAYER
from .stamp import describe, read_stamp, same_versions

DEFUNCT = "<defunct>%s." % LIBRARY_NAME


def _divides(dbu, grid_um=0.005):
    q = Fraction(str(grid_um)) / Fraction("%.12g" % dbu)
    return q.denominator == 1


def device_of(cell_name):
    """'sky130_fd_pr__nfet_01v8__kmp_3f9a12c4' -> 'sky130_fd_pr__nfet_01v8'."""
    return cell_name.split("__kmp_")[0]


def _grid_problem(manifest, cell_name, dbu):
    """A message if the device's Magic output has coordinates on a grid that
    the file's dbu can't hold (from the manifest's defaults run)."""
    spec = manifest.get(device_of(cell_name)) if manifest is not None else None
    grid = spec.raw.get("defaults_run", {}).get("grid_nm") if spec is not None else None
    if not grid or _divides(dbu, grid / 1000.0):
        return None
    return ("Magic's output for this device has coordinates on a %d nm grid, which the file's "
            "dbu of %g um rounds" % (grid, dbu))


def _snapshot(layout, cell):
    from ._kl import db
    ly = db.Layout()
    ly.dbu = layout.dbu
    c = ly.create_cell(cell.name)
    for li in layout.layer_indices():
        info = layout.get_info(li)
        it = cell.begin_shapes_rec(li)
        if not it.at_end():
            c.shapes(ly.layer(info.layer, info.datatype)).insert(it)
    return ly, c


def _diff_layers(ly_a, cell_a, ly_b, cell_b):
    """Layers whose flattened geometry or texts differ (same dbu assumed)."""
    from ._kl import db
    pairs = {}
    for ly, c, side in ((ly_a, cell_a, 0), (ly_b, cell_b, 1)):
        for li in ly.layer_indices():
            info = ly.get_info(li)
            pairs.setdefault((info.layer, info.datatype), [None, None])[side] = (ly, c, li)
    out = []
    for ld in sorted(pairs):
        if ld == PLACEHOLDER_LAYER:
            continue
        regs, txts = [], []
        for item in pairs[ld]:
            if item is None:
                regs.append(db.Region())
                txts.append([])
                continue
            ly, c, li = item
            regs.append(db.Region(c.begin_shapes_rec(li)))
            txts.append(sorted((t.string, t.x, t.y) for t in db.Texts(c.begin_shapes_rec(li)).each()))
        if not (regs[0] ^ regs[1]).is_empty() or txts[0] != txts[1]:
            out.append("%d/%d" % ld)
    return out


def audit(path, current_stamp=None, regen=False, manifest=None):
    """Return a dict report. ``current_stamp`` is a parsed stamp dict,
    ``manifest`` a Manifest (for the per-device coordinate grid)."""
    from ._kl import db
    ly = db.Layout()
    ly.read(path)
    rep = {"file": path, "dbu": ly.dbu, "dbu_divides_5nm": _divides(ly.dbu), "cells": []}
    cells = [c for c in ly.each_cell() if c.display_title().startswith(DEFUNCT)]
    snaps = {}
    for c in cells:
        rec = {"cell": c.name, "title": c.display_title(), "problems": []}
        ph = ly.find_layer(*PLACEHOLDER_LAYER)
        if ph is not None and not c.shapes(ph).is_empty():
            rec["problems"].append("placeholder (generation failed when this file was saved)")
        if c.is_empty() or all(c.shapes(li).is_empty() for li in ly.layer_indices()):
            rec["problems"].append("empty cell")
        st = read_stamp(c)
        rec["stamp"] = st
        if st is None:
            if "empty cell" not in rec["problems"]:
                rec["problems"].append("no generated-by stamp")
        elif current_stamp and not same_versions(st, current_stamp):
            rec["problems"].append("generated with %s; installed is %s"
                                   % (describe(st), describe(current_stamp)))
        gp = _grid_problem(manifest, c.name, ly.dbu)
        if gp:
            rec["problems"].append(gp)
        rep["cells"].append(rec)
        if regen:
            snaps[c.cell_index()] = _snapshot(ly, c)
    if not rep["dbu_divides_5nm"]:
        rep["file_problems"] = ["dbu %g um doesn't divide 5 nm: Magic's coordinates get rounded"
                                % ly.dbu]
    indices = [c.cell_index() for c in cells]
    if regen and cells:
        from . import register, state
        if register() is None:
            rep["regen"] = "library could not be registered"
            rep.setdefault("file_problems", []).append(
                "--regen: the library could not be registered (%s)" % state.last_error)
        else:
            for rec, ci in zip(rep["cells"], indices):
                live = ly.cell(ci)
                old_ly, old_c = snaps[ci]
                diff = _diff_layers(old_ly, old_c, ly, live)
                rec["regen"] = "same as stored" if not diff else "differs on " + ", ".join(diff)
                rec["live_after_register"] = live.is_pcell_variant()
                if diff:
                    rec["problems"].append("regenerated geometry differs on " + ", ".join(diff))
                ph = ly.find_layer(*PLACEHOLDER_LAYER)
                if ph is not None and not live.shapes(ph).is_empty():
                    texts = [sh.text_string for sh in live.shapes(ph).each() if sh.is_text()]
                    rec["problems"].append("regenerates as the error marker: %s"
                                           % (texts[0] if texts else "?"))
    return rep


def format_report(rep):
    lines = ["%s: dbu %g um%s" % (rep["file"], rep["dbu"],
                                  "" if rep["dbu_divides_5nm"] else " (does NOT divide 5 nm)")]
    for p in rep.get("file_problems", []):
        lines.append("  file: " + p)
    if not rep["cells"]:
        lines.append("  no %s cells" % LIBRARY_NAME)
    for c in rep["cells"]:
        state = "; ".join(c["problems"]) or "ok"
        lines.append("  %s  %s" % (c["cell"], state))
        if "regen" in c:
            lines.append("      regenerated: %s" % c["regen"])
    n_bad = sum(1 for c in rep["cells"] if c["problems"])
    lines.append("%d %s cells, %d with problems" % (len(rep["cells"]), LIBRARY_NAME, n_bad))
    return "\n".join(lines)
