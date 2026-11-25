"""Per-PDK data: the KLayout deck and the tier-0 rule table (um)."""

import os

import pdk_rules

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")

# tier 0: (layer, datatype): (name, min width, min space), from the shared
# rule table pdk_rules. The names are the ones the markers show.
_TIER0_LAYERS = {
    "sky130A": [(n, n) for n in ("nwell", "diff", "tap", "poly", "licon", "li", "mcon", "met1", "via", "met2",
                                 "via2", "met3", "via3", "met4", "via4", "met5")],
    "gf180mcuD": [("nwell", "Nwell"), ("comp", "COMP"), ("poly2", "Poly2"), ("contact", "Contact"),
                  ("metal1", "Metal1"), ("via1", "Via1"), ("metal2", "Metal2"), ("via2", "Via2"),
                  ("metal3", "Metal3"), ("via3", "Via3"), ("metal4", "Metal4")],
}


def _tier0(pdk):
    t = pdk_rules.get(pdk)
    return {t.layer(n): (shown,) + t.width_space(n) for n, shown in _TIER0_LAYERS[pdk]}


TIER0 = {p: _tier0(p) for p in _TIER0_LAYERS}

# (deck under the PDK, its top-cell variable, {variable: value})
DECKS = {
    "sky130A": ("libs.tech/klayout/drc/sky130A_mr.drc", "top_cell",
                {"feol": "true", "beol": "true", "offgrid": "true", "floating_met": "false", "seal": "false",
                 "thr": "1"}),
    "gf180mcuD": ("libs.tech/klayout/tech/drc/gf180mcu.drc", "topcell",
                  {"decks": "all,-density", "variant": "D", "threads": "1", "run_mode": "deep"}),
}

# the farthest any deck rule looks, um: the halo around a checked area
HALO = {"sky130A": 2.0, "gf180mcuD": 2.0}


def current(technology=None):
    """The PDK to check with: the layout's technology when it is one we
    know, else $PDK, else sky130A."""
    for name in (technology, os.environ.get("PDK")):
        if name and name in TIER0:
            return name
    return technology or os.environ.get("PDK") or "sky130A"


def deck(pdk):
    """(deck path, top-cell variable, {variable: value}) or None."""
    d = DECKS.get(pdk)
    if not d:
        return None
    path = os.path.join(PDK_ROOT, pdk, d[0])
    return (path, d[1], d[2]) if os.path.isfile(path) else None
