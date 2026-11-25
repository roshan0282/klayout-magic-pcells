"""Rules and layers for the generators, per PDK, in um.

sky130A values from libs.tech/klayout/drc/sky130A_mr.drc and the Magic
tech file, the same numbers as klayout_power_pcells.rules (which quotes
each rule) where both have them.
"""

SKY130A = {
    "grid": 0.005,
    "layers": {
        "tap": (65, 44), "nwell": (64, 20), "dnwell": (64, 18), "nsdm": (93, 44), "psdm": (94, 20),
        "licon": (66, 44), "li": (67, 20), "mcon": (67, 44), "met1": (68, 20),
        "via": (68, 44), "met2": (69, 20), "via2": (69, 44), "met3": (70, 20), "via3": (70, 44),
        "met4": (71, 20), "via4": (71, 44), "met5": (72, 20),
        "li_label": (67, 5), "li_pin": (67, 16), "met1_label": (68, 5), "met1_pin": (68, 16),
    },
    "tap_w": 0.15,             # difftap.1
    "licon": 0.17, "licon_s": 0.17,          # licon.1, licon.2
    "licon_tap_enc": 0.12,     # licon.7 (0.12 one direction; used on all sides)
    "sdm_enc": 0.125,          # nsd/psd.5a
    "nwell_ntap_enc": 0.18,    # diff/tap.10
    "nwell_w": 0.84,           # nwell.1
    "dnwell_w": 3.0,           # dnwell.1
    "nwell_dnwell_out": 0.4,   # nwell.5a: n-well past the deep n-well's edge
    "nwell_dnwell_in": 1.03,   # nwell.6
    "li_w": 0.17,
    "mcon": 0.17, "mcon_s": 0.19,            # ct.1, ct.2
    "met1_mcon_enc": 0.06,     # m1.5 (0.06 two adjacent edges; used on all sides)
    "met1_w": 0.14,
}

PDKS = {"sky130A": SKY130A}
