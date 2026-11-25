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
}

DECKS = {
    "sky130A": ("libs.tech/klayout/drc/sky130A_mr.drc",
                {"feol": "true", "beol": "true", "offgrid": "true", "floating_met": "false", "seal": "false",
                 "thr": "1"}),
}

# the farthest any deck rule looks, um: the halo around a checked area
HALO = {"sky130A": 2.0}


def current():
    return os.environ.get("PDK", "sky130A")


def deck(pdk):
    """(deck path, {variable: value}) or None."""
    d = DECKS.get(pdk)
    if not d:
        return None
    path = os.path.join(PDK_ROOT, pdk, d[0])
    return (path, d[1]) if os.path.isfile(path) else None
