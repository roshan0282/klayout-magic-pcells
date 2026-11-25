"""A guard ring that follows any Manhattan outline (roadmap Phase 3.3).

ring(shape, ...) returns {layer name: Region} in database units of the
given dbu: the tap ring at ``clearance`` outside the shape, its implant
(psdm for a p-tap, nsdm and the n-well for an n-tap), licon and li along
the whole ring, and optionally mcon and met1. Contacts sit on the ring's
centre line at the minimum pitch; each one is checked to be enclosed by
the tap and spaced from the others, so corners and notches stay clean.

A deep n-well option (n-tap only) draws the dnwell under the inside and
the ring, with the n-well ring as its edge, which isolates the p-well
inside (for isolated nfets / p-LDMOS drains).
"""

import math

import klayout.db as db

from .rules import PDKS


class RingError(ValueError):
    def __init__(self, msg, param=None):
        super().__init__(msg)
        self.param = param


def _u(v, dbu):
    return int(round(v / dbu))


def min_width(rules):
    return rules["licon"] + 2 * rules["licon_tap_enc"]


def _region_of(shape, dbu):
    """Region (dbu) of a DBox, DPolygon, DSimplePolygon or DPath."""
    if isinstance(shape, db.DBox):
        return db.Region(shape.to_itype(dbu))
    if isinstance(shape, (db.DPolygon, db.DSimplePolygon)):
        return db.Region(db.DPolygon(shape).to_itype(dbu)) if isinstance(shape, db.DSimplePolygon) \
            else db.Region(shape.to_itype(dbu))
    if isinstance(shape, db.DPath):
        return db.Region(shape.polygon().to_itype(dbu))
    if isinstance(shape, db.Region):
        return shape.dup()
    raise RingError("the shape must be a box, polygon or path", "shape")


def _contacts(center_region, ring, size, space, enc, grid):
    """Squares of ``size`` on the centre line of ``ring``, at least
    ``space`` apart and enclosed by ``enc`` in ``ring``."""
    half = size // 2
    pitch = size + space
    allowed = ring.sized(-enc)
    out = []
    taken = []

    def ok(cx, cy):
        for (x, y) in taken:
            if abs(x - cx) < pitch and abs(y - cy) < pitch:
                return False
        return True

    for poly in center_region.each():
        loops = [list(poly.each_point_hull())] + [list(poly.each_point_hole(h)) for h in range(poly.holes())]
        for pts in loops:
            n = len(pts)
            for k in range(n):
                a, b = pts[k], pts[(k + 1) % n]
                length = abs(b.x - a.x) + abs(b.y - a.y)
                if length == 0:
                    continue
                dx, dy = (b.x - a.x) / length, (b.y - a.y) / length
                steps = int(length // pitch)
                # spread the contacts evenly along the edge, ends included
                for s in range(steps + 1):
                    t = s * length / steps if steps else 0
                    cx = int(round((a.x + dx * t) / grid)) * grid
                    cy = int(round((a.y + dy * t) / grid)) * grid
                    box = db.Box(cx - half, cy - half, cx + half, cy + half)
                    if not ok(cx, cy):
                        continue
                    if not (db.Region(box) - allowed).is_empty():
                        continue
                    taken.append((cx, cy))
                    out.append(box)
    return db.Region(out)


def ring(shape, dbu=0.001, kind="ptap", width=0.0, clearance=0.3, met1=True, deep_nwell=False, pdk="sky130A"):
    """{layer name: Region} for a guard ring around ``shape``. width 0 =
    the narrowest ring a contact fits in. Raises RingError."""
    R = PDKS[pdk]
    if kind not in ("ptap", "ntap"):
        raise RingError("kind: ptap or ntap", "kind")
    if deep_nwell and "dnwell_w" not in R:
        raise RingError("no deep n-well rules for %s yet" % pdk, "deep_nwell")
    if deep_nwell and kind != "ntap":
        raise RingError("a deep n-well needs an n-tap ring (its n-well is the deep n-well's edge)", "deep_nwell")
    wmin = min_width(R)
    w = width if width > 0 else wmin
    if w < wmin - 1e-9:
        raise RingError("ring width %.3f um: a contact needs %.3f um" % (w, wmin), "width")
    if clearance < 0:
        raise RingError("clearance must be 0 or more", "clearance")
    g = _u(R["grid"], dbu)
    src = _region_of(shape, dbu).merged()
    if src.is_empty():
        raise RingError("the shape is empty", "shape")
    for poly in src.each():
        if not poly.is_box() and any(e.dx() and e.dy() for e in poly.each_edge()):
            raise RingError("the shape must be Manhattan (sky130 tap is 0/90 degrees only)", "shape")
    inner = src.sized(_u(clearance, dbu)) if clearance > 0 else src
    wu = _u(w, dbu)
    outer = inner.sized(wu)
    tap = outer - inner
    out = {"tap": tap}
    sdm = tap.sized(_u(R["sdm_enc"], dbu))
    out["psdm" if kind == "ptap" else "nsdm"] = sdm
    center = inner.sized(wu // 2)
    out["licon"] = _contacts(center, tap, _u(R["licon"], dbu), _u(R["licon_s"], dbu),
                             _u(R["licon_tap_enc"], dbu), g)
    if out["licon"].is_empty():
        raise RingError("no contact fits on the ring", "width")
    if R["contact_to"] == "li":
        out["li"] = tap.dup()
        if met1:
            out["mcon"] = _contacts(center, tap, _u(R["mcon"], dbu), _u(R["mcon_s"], dbu),
                                    _u(R["met1_mcon_enc"], dbu), g)
            out["met1"] = tap.dup()
    else:
        # the contact lands on met1 directly (gf180): met1 always, enclosing it
        e = _u(R["met1_mcon_enc"], dbu)
        out["met1"] = (tap + out["licon"].sized(e)).merged()
    if kind == "ntap":
        enc = _u(R["nwell_ntap_enc"], dbu)
        # an n-well ring at least nwell.1 wide: grow it inward if the tap is narrow
        extra = max(0, _u(R["nwell_w"], dbu) - (wu + 2 * enc))
        nw = outer.sized(enc) - inner.sized(-(enc + extra))
        if deep_nwell:
            # the n-well ring sits on the deep n-well's edge: nwell.5a/nwell.6
            dn = outer.sized(_u(R["nwell_ntap_enc"], dbu) - _u(R["nwell_dnwell_out"], dbu))
            hole = dn.sized(-_u(R["nwell_dnwell_in"], dbu))
            nw = (nw + (dn - hole)).merged()
            out["dnwell"] = dn
        # fill n-well notches narrower than its width
        h = _u(R["nwell_w"], dbu) // 2 + g
        nw = nw.sized(h).sized(-h) if not deep_nwell else nw
        out["nwell"] = nw
    return out


def draw(layout, cell, shape, label="B", **kw):
    """Draw ring(shape, **kw) into ``cell`` with a pin/label on li (and
    met1). Returns the layer regions."""
    pdk = kw.get("pdk", "sky130A")
    R = PDKS[pdk]
    regs = ring(shape, layout.dbu, **kw)
    for name, reg in regs.items():
        cell.shapes(layout.layer(*R["layers"][name])).insert(reg)
    if label:
        lic = next(regs["licon"].each()).bbox()
        c = lic.center()
        top_metal = "met1" if "met1" in regs else "li"
        if top_metal + "_label" not in R["layers"]:
            top_metal = "met1"
        cell.shapes(layout.layer(*R["layers"][top_metal + "_label"])).insert(db.Text(label, db.Trans(c)))
        cell.shapes(layout.layer(*R["layers"][top_metal + "_pin"])).insert(lic)
    return regs
