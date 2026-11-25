"""Per-PDK data: the KLayout deck and the tier-0 rule table (um)."""

import os

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")

# tier 0: (layer, datatype): (name, min width, min space); sky130A_mr.drc values
TIER0 = {
    "sky130A": {
        (64, 20): ("nwell", 0.84, 1.27), (65, 20): ("diff", 0.15, 0.27), (65, 44): ("tap", 0.15, 0.27),
        (66, 20): ("poly", 0.15, 0.21), (66, 44): ("licon", 0.17, 0.17), (67, 20): ("li", 0.17, 0.17),
        (67, 44): ("mcon", 0.17, 0.19), (68, 20): ("met1", 0.14, 0.14), (68, 44): ("via", 0.15, 0.17),
        (69, 20): ("met2", 0.14, 0.14), (69, 44): ("via2", 0.20, 0.20), (70, 20): ("met3", 0.30, 0.30),
        (70, 44): ("via3", 0.20, 0.20), (71, 20): ("met4", 0.30, 0.30), (71, 44): ("via4", 0.80, 0.80),
        (72, 20): ("met5", 1.60, 1.60),
    },
    # GF180MCU 3.3 V values (DF.1a/3a, PL.1/3a, CO.1/2a, M1.1/2a, V1, M2...)
    "gf180mcuD": {
        (21, 0): ("Nwell", 0.86, 0.60), (22, 0): ("COMP", 0.22, 0.28), (30, 0): ("Poly2", 0.18, 0.24),
        (33, 0): ("Contact", 0.22, 0.25), (34, 0): ("Metal1", 0.23, 0.23), (35, 0): ("Via1", 0.26, 0.26),
        (36, 0): ("Metal2", 0.28, 0.28), (38, 0): ("Via2", 0.26, 0.26), (42, 0): ("Metal3", 0.28, 0.28),
        (40, 0): ("Via3", 0.26, 0.26), (46, 0): ("Metal4", 0.28, 0.28),
    },
}

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
