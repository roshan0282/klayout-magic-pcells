"""Place a common-centroid letter grid as unit-cell instances (KLayout).

* Every instance is the same unit cell in the same orientation (R0), so
  current flows the same way in each unit.
* The pitch is the unit's bounding box plus a gap. With gap <= 0 ("auto")
  the gap is the smallest one, on the PDK grid, that keeps every "keep"
  layer (diffusion, poly, cuts, metals) of neighbouring units at least its
  spacing apart; it is computed from how far each layer sits inside the
  unit's bounding box.
* "merge" layers (wells, implants) of neighbouring units that end up
  closer than their spacing are bridged with fill shapes drawn in the
  array cell, so the array has no well or implant notches.
* Dummies: grid cells marked ``.``, plus an optional ring (``ring``) or
  extra left/right columns (``edge``) of the same unit cell.
* With ``labels``, each unit gets a text with its device name (``A``,
  ``dummy``) at its centre on the PDK's ``label_layer``, a layer that no
  extraction reads, so the texts never name nets.
* Each instance carries property 1 = "device=<name>;row=<i>;col=<j>"
  (dummies: device=dummy), which GDS keeps as a PROPATTR, for a later
  router or LVS step. Row 0 of the grid is the top row.
"""

import math

import klayout.db as db

from .pattern import DUMMY

PROP_KEY = 1
DUMMY_NAME = "dummy"


def _snap_up(v, grid):
    return math.ceil(v / grid - 1e-9) * grid


def layer_insets(layout, cell):
    """{(layer, datatype): (left, bottom, right, top)} insets in um of each
    layer's extent from the cell's bounding box."""
    bb = cell.dbbox()
    out = {}
    for li in layout.layer_indexes():
        lb = cell.dbbox_per_layer(li) if hasattr(cell, "dbbox_per_layer") else \
            db.DBox(cell.bbox_per_layer(li)) * layout.dbu
        if lb.empty():
            continue
        info = layout.get_info(li)
        out[(info.layer, info.datatype)] = (lb.left - bb.left, lb.bottom - bb.bottom, bb.right - lb.right,
                                           bb.top - lb.top)
    return out


def auto_gaps(layout, cell, rules):
    """(gap_x, gap_y) in um: the smallest gaps, on the rule grid, that keep
    every "keep" layer at its spacing across neighbouring units."""
    ins = layer_insets(layout, cell)
    space = {k: v[0] for k, v in rules["layers"].items() if v[1] == "keep"}
    for cap, (metal, s) in rules.get("bottom_plates", {}).items():
        if cap in ins:
            space[metal] = max(space.get(metal, 0.0), s)
    gx = gy = 0.0
    for key, (l, b, r, t) in ins.items():
        s = space.get(key)
        if s is None:
            continue
        gx = max(gx, s - l - r)
        gy = max(gy, s - b - t)
    g = rules["grid"]
    return _snap_up(max(gx, 0.0), g), _snap_up(max(gy, 0.0), g)


def ring_cells(rows, cols, dummies):
    """The full grid with the dummy ring or edge columns: (rows2, cols2,
    row offset, col offset)."""
    if dummies == "ring":
        return rows + 2, cols + 2, 1, 1
    if dummies == "edge":
        return rows, cols + 2, 0, 1
    return rows, cols, 0, 0


def place(layout, top, unit, grid, gap_x=0.0, gap_y=0.0, dummies="ring", rules=None, names=None, labels=True):
    """Instantiate ``unit`` in ``top`` for each cell of ``grid`` (rows of
    symbols, row 0 on top). gap <= 0 means automatic (needs ``rules``).
    ``names`` maps a symbol to the device name written in the property.
    Returns a dict describing the placement."""
    dbu = layout.dbu
    ub = unit.dbbox()
    if ub.empty():
        raise ValueError("the unit cell %s is empty" % unit.name)
    agx, agy = auto_gaps(layout, unit, rules) if rules else (None, None)
    if gap_x <= 0:
        if agx is None:
            raise ValueError("no spacing rules for this PDK yet: give gap x and gap y")
        gap_x = agx
    if gap_y <= 0:
        if agy is None:
            raise ValueError("no spacing rules for this PDK yet: give gap x and gap y")
        gap_y = agy
    grid_um = rules["grid"] if rules else 0.005
    px = round((ub.width() + gap_x) / grid_um) * grid_um
    py = round((ub.height() + gap_y) / grid_um) * grid_um
    rows, cols = len(grid), len(grid[0])
    R2, C2, ro, co = ring_cells(rows, cols, dummies)
    lab_li = None
    if labels and rules and rules.get("label_layer"):
        lab_li = layout.layer(*rules["label_layer"])
        size = max(0.1, min(ub.width(), ub.height()) * 0.3)
    # origin: the array's lower-left unit bbox corner at (0, 0)
    units = []
    for i2 in range(R2):
        for j2 in range(C2):
            i, j = i2 - ro, j2 - co
            sym = grid[i][j] if 0 <= i < rows and 0 <= j < cols else DUMMY
            dev = DUMMY_NAME if sym == DUMMY else (names or {}).get(sym, sym)
            x = j2 * px - ub.left
            y = (R2 - 1 - i2) * py - ub.bottom
            inst = top.insert(db.DCellInstArray(unit.cell_index(), db.DTrans(db.DVector(x, y))))
            units.append({"row": i2, "col": j2, "device": dev, "origin": db.DVector(x, y)})
            inst.set_property(PROP_KEY, "device=%s;row=%d;col=%d" % (dev, i, j))
            if lab_li is not None:
                c = db.DPoint(j2 * px + ub.width() / 2.0, (R2 - 1 - i2) * py + ub.height() / 2.0)
                # shrink long names (dummy) so they stay inside the unit
                tsize = min(size, 0.8 * ub.width() / (0.7 * max(1, len(dev))))
                t = db.DText(dev, db.DTrans(db.DVector(c.x, c.y)), tsize, -1)
                t.halign, t.valign = db.HAlign.HAlignCenter, db.VAlign.VAlignCenter
                top.shapes(lab_li).insert(t)
    fills = fill_merge_layers(layout, top, rules) if rules else 0
    return {"units": units, "labels": lab_li is not None, "pitch": (px, py), "gap": (gap_x, gap_y), "rows": R2, "cols": C2, "fills": fills,
            "size": ((C2 - 1) * px + ub.width(), (R2 - 1) * py + ub.height()), "dbu": dbu}


def fill_merge_layers(layout, top, rules):
    """Bridge gaps narrower than the spacing on "merge" layers. Returns the
    number of fill polygons drawn."""
    regions = {}
    for key, (s, mode) in rules["layers"].items():
        if mode != "merge":
            continue
        li = layout.find_layer(key[0], key[1])
        if li is None:
            continue
        r = db.Region(top.begin_shapes_rec(li))
        if r.is_empty():
            continue
        regions[key] = (li, r.merged(), s)
    fills = {}
    for key, (li, r, s) in regions.items():
        h = int(math.ceil(s / layout.dbu / 2.0)) + 1
        closed = r.sized(h).sized(-h)
        fill = closed - r
        fills[key] = fill
    for a, b in rules.get("exclusive", []):
        if a in fills and b in regions:
            fills[a] -= regions[b][1]
        if b in fills and a in regions:
            fills[b] -= regions[a][1]
    n = 0
    for key, fill in fills.items():
        if fill.is_empty():
            continue
        top.shapes(regions[key][0]).insert(fill)
        n += fill.count()
    return n
