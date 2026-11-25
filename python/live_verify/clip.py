"""Cut a window (plus a halo) out of a layout as a flat cell."""

import klayout.db as db


def clip(layout, cell, window, halo):
    """(Layout, top Cell, clip DBox): every layer's shapes of ``cell``
    (hierarchy flattened) inside ``window`` grown by ``halo``, cut at the
    clip box. Texts inside are kept."""
    cbox = window.enlarged(halo, halo)
    ibox = cbox.to_itype(layout.dbu)
    out = db.Layout()
    out.dbu = layout.dbu
    top = out.create_cell("CLIP")
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        it = cell.begin_shapes_rec_touching(li, ibox)
        reg = db.Region(it) & db.Region(ibox)
        texts = db.Texts(cell.begin_shapes_rec_touching(li, ibox))
        if reg.is_empty() and texts.is_empty():
            continue
        nl = out.layer(info)
        top.shapes(nl).insert(reg)
        for t in texts.each():
            if ibox.contains(t.position()):
                top.shapes(nl).insert(t)
    return out, top, cbox
