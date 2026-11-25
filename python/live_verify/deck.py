"""Tier 1: the PDK's KLayout deck on a clipped GDS."""

import os

from .pdk import deck


def command(gds, top, report, pdk, klayout="klayout"):
    """argv running the PDK deck, or None when the PDK has none."""
    d = deck(pdk)
    if d is None:
        return None
    path, topvar, flags = d
    cmd = [klayout, "-b", "-r", path, "-rd", "input=" + os.path.abspath(gds), "-rd", "%s=%s" % (topvar, top),
           "-rd", "report=" + os.path.abspath(report)]
    for k, v in flags.items():
        cmd += ["-rd", "%s=%s" % (k, v)]
    return cmd


def read_report(report):
    """[(rule, shape)] from a deck's .lyrdb; shapes are DPolygon, DEdgePair,
    DEdge or DBox in um."""
    import klayout.rdb as rdb
    r = rdb.ReportDatabase("")
    r.load(report)
    out = []
    for item in r.each_item():
        cat = r.category_by_id(item.category_id()).name()
        for v in item.each_value():
            for getter in ("polygon", "edge_pair", "edge", "box"):
                checker = "is_" + getter
                if getattr(v, checker)():
                    out.append((cat, getattr(v, getter)()))
                    break
    return out
