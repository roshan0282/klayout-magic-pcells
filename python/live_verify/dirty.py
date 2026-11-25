"""Dirty areas: what changed in a view since the last look."""

import klayout.db as db


def snapshot(layout, cell, box):
    """{(layer, datatype): merged Region} of ``cell`` inside DBox ``box``."""
    ibox = box.to_itype(layout.dbu)
    snap = {}
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        reg = db.Region(cell.begin_shapes_rec_touching(li, ibox)) & db.Region(ibox)
        if not reg.is_empty():
            snap[(info.layer, info.datatype)] = reg.merged()
    return snap


def changed(before, after, dbu):
    """DBox around everything that differs between two snapshots, or None."""
    bb = db.Box()
    for key in set(before) | set(after):
        a = before.get(key, db.Region())
        b = after.get(key, db.Region())
        x = a ^ b
        if not x.is_empty():
            bb += x.bbox()
    return None if bb.empty() else bb.to_dtype(dbu)
