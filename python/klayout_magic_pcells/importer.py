"""Copy Magic's GDS into a PCell cell, flat and layer by layer."""


class GdsImportError(Exception):
    pass


def insert_gds_flat(layout, cell, gds_path):
    """Read ``gds_path`` into a fresh Layout and insert its single top cell,
    flattened, into ``cell``. Never reads into ``layout`` itself: reading into
    a layout with content would switch its dbu without rescaling."""
    from ._kl import db
    src = db.Layout()
    src.read(gds_path)
    tops = src.top_cells()
    if len(tops) != 1:
        raise GdsImportError("%s: expected one top cell, found %d" % (gds_path, len(tops)))
    ratio = src.dbu / layout.dbu
    mag = int(round(ratio))
    if mag < 1 or abs(ratio - mag) > 1e-9:
        raise GdsImportError("source dbu %g is not a multiple of %g" % (src.dbu, layout.dbu))
    t = db.ICplxTrans(mag)
    top = tops[0]
    n = 0
    for li in src.layer_indices():
        info = src.get_info(li)
        it = top.begin_shapes_rec(li)
        if it.at_end():
            continue
        dst = layout.layer(info.layer, info.datatype)
        cell.shapes(dst).insert(it, t)
        n += 1
    return n
