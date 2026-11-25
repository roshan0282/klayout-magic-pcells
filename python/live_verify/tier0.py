"""Tier 0: width and space of each layer, in process, on a clipped cell."""

import klayout.db as db

from .pdk import TIER0


def check(layout, cell, pdk):
    """[(rule, DEdgePair)] for every width/space violation in ``cell``."""
    table = TIER0.get(pdk, {})
    out = []
    for (l, d), (name, w, s) in table.items():
        li = layout.find_layer(l, d)
        if li is None:
            continue
        reg = db.Region(cell.begin_shapes_rec(li)).merged()
        if reg.is_empty():
            continue
        wu, su = int(round(w / layout.dbu)), int(round(s / layout.dbu))
        for ep in reg.width_check(wu, False, db.Metrics.Projection).each():
            out.append(("%s width < %g" % (name, w), ep.to_dtype(layout.dbu)))
        for ep in reg.space_check(su, False, db.Metrics.Projection).each():
            out.append(("%s space < %g" % (name, s), ep.to_dtype(layout.dbu)))
    return out
