"""Markers: keep those that belong to the window, put them in a report."""

import klayout.db as db


def _bbox(shape):
    return shape.bbox()


def keep(markers, window, cbox, band):
    """Markers that touch ``window`` and stay ``band`` away from the clip
    box's edges (those come from cutting the layout, not from it). Edges
    of the clip box that are the layout's own extent don't count."""
    inner = cbox.enlarged(-band, -band)
    out = []
    for rule, shape in markers:
        b = _bbox(shape)
        if not b.overlaps(window) and not window.contains(b.center()):
            continue
        if not inner.contains(b.p1) or not inner.contains(b.p2):
            continue
        out.append((rule, shape))
    return out


def to_rdb(rdb, cell_name, results, title="Live DRC"):
    """Fill ``rdb`` (a klayout.rdb.ReportDatabase) with {tier: markers}."""
    rdb.description = title
    rdb.top_cell_name = cell_name
    cell = rdb.create_cell(cell_name)
    cats = {}
    for tier, markers in sorted(results.items()):
        for rule, shape in markers:
            name = "T%d %s" % (tier, rule)
            if name not in cats:
                cats[name] = rdb.create_category(name)
            item = rdb.create_item(cell.rdb_id(), cats[name].rdb_id())
            item.add_value(shape)
    return rdb
