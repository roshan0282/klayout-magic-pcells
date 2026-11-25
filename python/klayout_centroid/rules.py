"""Spacing rules the placer needs, per PDK: layer -> (space_um, mode).

mode "keep": shapes of neighbouring unit cells must stay at least
    ``space`` apart (conductors, diffusion, cuts: merging them would short
    devices). The auto pitch is chosen for these layers.
mode "merge": shapes of neighbours may touch, so gaps narrower than
    ``space`` are filled in (wells, implants, threshold and thick-oxide
    layers: same layer, same potential or no electrical meaning).

The values come from the shared table ``pdk_rules``, which cites each rule.
"""

import pdk_rules

# (layer name in the PDK table, its spacing rule key, mode), per PDK. Metals use
# their wide-metal spacing, which is conservative for unit cells.
_SPACING = {
    "sky130A": [
        ("diff", "diff_s", "keep"), ("tap", "tap_s", "keep"), ("poly", "poly_s", "keep"),
        ("licon", "licon_s", "keep"), ("li", "li_s", "keep"), ("mcon", "mcon_s", "keep"),
        ("met1", "met1_s_wide", "keep"), ("via", "via_s", "keep"), ("met2", "met2_s_wide", "keep"),
        ("via2", "via2_s", "keep"), ("met3", "met3_s_wide", "keep"), ("via3", "via3_s", "keep"),
        ("met4", "met4_s_wide", "keep"), ("via4", "via4_s", "keep"), ("met5", "met5_s", "keep"),
        ("nwell", "nwell_s", "merge"), ("dnwell", "dnwell_s", "merge"), ("nsdm", "nsdm_s", "merge"),
        ("psdm", "psdm_s", "merge"), ("npc", "npc_s", "merge"), ("lvtn", "lvtn_s", "merge"),
        ("hvtp", "hvtp_s", "merge"), ("hvi", "hvi_s", "merge"), ("hvntm", "hvntm_s", "merge"),
        ("rpm", "rpm_s", "merge"), ("urpm", "urpm_s", "merge"), ("capm", "capm_s", "keep"),
        ("cap2m", "cap2m_s", "keep"),
    ],
    "gf180mcuD": [
        ("comp", "comp_s", "keep"), ("poly2", "poly2_s", "keep"), ("contact", "contact_s", "keep"),
        ("metal1", "metal1_s_wide", "keep"), ("via1", "via1_s", "keep"), ("metal2", "metal2_s_wide", "keep"),
        ("via2", "via2_s", "keep"), ("metal3", "metal3_s_wide", "keep"),
        ("nwell", "nwell_s", "merge"), ("nplus", "nplus_s", "merge"), ("pplus", "pplus_s", "merge"),
        ("dualgate", "dualgate_s", "merge"),
    ],
}


def _spacing(t):
    return {t.layer(name): (t.um(key), mode) for name, key, mode in _SPACING[t.name]}


_S = pdk_rules.get("sky130A")
SKY130A = {
    "grid": _S.grid,
    # where the device-name labels go: areaid.analog. Magic ignores the
    # layer, the LVS deck doesn't read it, and the DRC deck only declares it
    # as polygons, so the texts can't become net names.
    "label_layer": _S.layer("areaid_analog"),
    "layers": _spacing(_S),
    # a MIM cap's bottom plate needs more space than plain metal:
    # cap layer present in the unit -> (metal, its spacing then)
    "bottom_plates": {_S.layer("capm"): (_S.layer("met3"), _S.um("capm_bottom_s")),
                      _S.layer("cap2m"): (_S.layer("met4"), _S.um("cap2m_bottom_s"))},
    # the router's metal stack (um): via1 on met1 pins, met2 row tracks,
    # via2 to met3 trunks. enc = all sides, enc2 = the larger enclosure on
    # two opposite sides. The track widths (met2_w, met3_w) and the trunk
    # margin are the router's choices, wider than the minimum.
    "route": {
        "met1": _S.layer("met1"), "via1": _S.layer("via"), "met2": _S.layer("met2"), "via2": _S.layer("via2"),
        "met3": _S.layer("met3"), "met3_label": _S.label["met3"], "met3_pin": _S.pin["met3"],
        "diff": _S.layer("diff"), "poly": _S.layer("poly"),
        "pin_labels": [_S.label["li"], _S.label["met1"]],
        "via1_size": _S.um("via"), "via1_m1_enc": _S.um("via_enc"), "via1_m1_enc2": _S.um("via_enc1"),
        "met2_w": 0.30, "met2_s": _S.um("met2_s"),
        "via2_size": _S.um("via2"), "via2_m2_enc2": _S.um("via2_enc_lo"),
        "met3_w": 0.40, "met3_s": _S.um("met3_s"),
        "trunk_margin": 0.50,
    },
    # implants that must not overlap each other after filling
    "exclusive": [(_S.layer("nsdm"), _S.layer("psdm"))],
}

# gf180mcuD: no label layer: there is no layer that extraction is known to
# ignore yet, so device labels are left out on gf180.
_G = pdk_rules.get("gf180mcuD")
GF180MCUD = {
    "grid": _G.grid,
    "layers": _spacing(_G),
    "exclusive": [(_G.layer("nplus"), _G.layer("pplus"))],
}

PDKS = {"sky130A": SKY130A, "gf180mcuD": GF180MCUD}

# which PDK a unit-cell library belongs to
LIBRARY_PDK = {"sky130_magic": "sky130A", "gf180mcu_magic": "gf180mcuD", "sg13g2_magic": "ihp-sg13g2",
               "sg13cmos5l_magic": "ihp-sg13cmos5l"}


def for_library(lib):
    """The rule table for a unit-cell library, or None if there is none yet
    (then the gaps must be given)."""
    return PDKS.get(LIBRARY_PDK.get(lib, ""))
