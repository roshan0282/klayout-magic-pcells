"""Audit a layout file for HW_FET cells without registering the library.

A cell is an HW_FET by its title, ``<defunct>sky130_power.HW_FET...``.
Reports cells that hold the error marker, empty cells, cells with no
generated-by stamp, stamps from another generator, Magic, PDK or
klayout-magic-pcells digest than the installed ones, a file dbu that doesn't
divide 5 nm, and cells whose output lies on a finer grid (from the stamp)
than the file's dbu. With ``regen=True`` it keeps a copy of every cell's
stored geometry, registers the library with every lookup drawing again
(not the memo or the disk cache), and reports each cell whose regenerated
geometry differs; a disk-cache entry that differs from what is drawn now is
reported too, and replaced.

klayout-magic-pcells' own audit (``python3 -m klayout_magic_pcells audit``)
covers the sky130_magic cells.
"""

import os
from fractions import Fraction

from . import backend
from .pcell import ERROR_LAYER, LIBRARY_NAME, PCELL_NAME

DEFUNCT = "<defunct>%s.%s" % (LIBRARY_NAME, PCELL_NAME)


def _divides(dbu, grid_um):
    q = Fraction(str(grid_um)) / Fraction("%.12g" % dbu)
    return q.denominator == 1


def current_stamp(notes=None):
    """The parsed stamp the installed Magic, PDK and generator would write,
    or None (with a note) when sky130A's Magic can't start."""
    from klayout_magic_pcells.audit import current_stamps
    cur = current_stamps([backend.PDK], notes).get(backend.PDK)
    if cur is None:
        return None
    return dict(cur, code=backend.code_digest())


def audit(path, current=None, regen=False, notes=None):
    from klayout_magic_pcells.audit import _diff_layers, _gds_diff, _snapshot
    import klayout.db as db
    ly = db.Layout()
    ly.read(path)
    rep = {"file": path, "dbu": ly.dbu, "dbu_divides_5nm": _divides(ly.dbu, 0.005), "cells": []}
    cells = [c for c in ly.each_cell() if c.display_title().startswith(DEFUNCT)]
    if current is None and cells:
        current = current_stamp(notes)
    err = ly.find_layer(*ERROR_LAYER)
    snaps = {}
    indices = [c.cell_index() for c in cells]
    for c in cells:
        rec = {"cell": c.name, "title": c.display_title(), "problems": []}
        if err is not None and not c.shapes(err).is_empty():
            texts = [s.text_string for s in c.shapes(err).each() if s.is_text()]
            rec["problems"].append("error marker (not drawn when this file was saved): %s"
                                   % (texts[0] if texts else "?"))
        empty = all(c.shapes(li).is_empty() for li in ly.layer_indices())
        if empty:
            rec["problems"].append("empty cell")
        st = backend.read_stamp(c)
        rec["stamp"] = st
        if st is None:
            if not empty and not rec["problems"]:
                rec["problems"].append("no generated-by stamp")
        elif current and not backend.same_versions(st, current):
            rec["problems"].append("generated with %s; installed is %s"
                                   % (backend.describe(st), backend.describe(current)))
        if st is not None and st.get("grid"):
            try:
                g = int(st["grid"]) / 1000.0
                if not _divides(ly.dbu, g):
                    rec["problems"].append("this cell's output lies on a %s nm grid, which the file's "
                                           "dbu %g um can't hold" % (st["grid"], ly.dbu))
            except ValueError:
                pass
        rep["cells"].append(rec)
        if regen:
            snaps[c.cell_index()] = _snapshot(ly, c)
    if not rep["dbu_divides_5nm"]:
        rep["file_problems"] = ["dbu %g um doesn't divide 5 nm: Magic's coordinates get rounded" % ly.dbu]
    if regen and cells:
        from .pcell import register
        try:
            backend.start()
            backend.state.generator.fresh = True
        except Exception as e:
            rep.setdefault("file_problems", []).append("--regen: %s could not be registered (%s)"
                                                         % (LIBRARY_NAME, e))
            return rep
        if register() is None:
            rep.setdefault("file_problems", []).append("--regen: %s could not be registered (%s)"
                                                         % (LIBRARY_NAME, backend.state.last_error))
            return rep
        for rec, ci in zip(rep["cells"], indices):
            live = ly.cell(ci)
            old_ly, old_c = snaps[ci]
            diff = _diff_layers(old_ly, old_c, ly, live)
            rec["regen"] = "same as stored" if not diff else "differs on " + ", ".join(diff)
            rec["live_after_register"] = live.is_pcell_variant()
            if diff:
                rec["problems"].append("regenerated geometry differs on " + ", ".join(diff))
            el = ly.find_layer(*ERROR_LAYER)
            if el is not None and not live.shapes(el).is_empty():
                texts = [s.text_string for s in live.shapes(el).each() if s.is_text()]
                rec["problems"].append("regenerates as the error marker: %s" % (texts[0] if texts else "?"))
        g = backend.state.generator
        for key, old in sorted(g.replaced.items()):
            res = g._memo.get(key)
            if res is None:
                continue
            try:
                diff = _gds_diff(old, res.gds_path)
            except Exception as e:
                diff = ["unreadable (%s)" % e]
            if diff:
                rep.setdefault("file_problems", []).append(
                    "the disk cache held a stale HW_FET (differs on %s); replaced with what is drawn now"
                    % ", ".join(diff))
            try:
                os.remove(old)
            except OSError:
                pass
        g.replaced.clear()
        g.fresh = False
    return rep


def format_report(rep):
    lines = ["%s: dbu %g um%s" % (rep["file"], rep["dbu"],
                                  "" if rep["dbu_divides_5nm"] else " (does NOT divide 5 nm)")]
    for p in rep.get("file_problems", []):
        lines.append("  file: " + p)
    if not rep["cells"]:
        lines.append("  no %s.%s cells" % (LIBRARY_NAME, PCELL_NAME))
    for c in rep["cells"]:
        lines.append("  %s  %s" % (c["cell"], "; ".join(c["problems"]) or "ok"))
        if "regen" in c:
            lines.append("      regenerated: %s" % c["regen"])
    n_bad = sum(1 for c in rep["cells"] if c["problems"])
    lines.append("%d %s cells, %d with problems" % (len(rep["cells"]), LIBRARY_NAME, n_bad))
    return "\n".join(lines)
