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

# The metal stack for VIA_STACK, bottom to top: (metal, min width, min area um2,
# cut between it and the next metal, cut size, cut spacing, enclosure of the
# cut by the metal below, by the metal above). Enclosures are the larger,
# "two adjacent/opposite edges" values (m1.5, via.5a/m2.5, via2.5, via3.5,
# via4.4/m5.3), used on all sides.
SKY130A["stack"] = [
    ("li", 0.17, 0.0561, "mcon", 0.17, 0.19, 0.0, 0.06),
    ("met1", 0.14, 0.083, "via", 0.15, 0.17, 0.085, 0.085),
    ("met2", 0.14, 0.0676, "via2", 0.20, 0.20, 0.085, 0.085),
    ("met3", 0.30, 0.24, "via3", 0.20, 0.20, 0.09, 0.065),
    ("met4", 0.30, 0.24, "via4", 0.80, 0.80, 0.19, 0.31),
    ("met5", 1.60, 4.0, None, 0, 0, 0, 0),
]
# DC current per cut (mA) for electromigration sizing. Left empty: the open
# sky130 PDK publishes no EM table (rule x.4 names the guideline without
# numbers), so the current per cut must be given; fill this in from the
# foundry's reliability tables, e.g. {"mcon": ..., "via": ...}.
SKY130A["em_ma_per_cut"] = {}

# What the guard-ring contact lands on: sky130 has li between the cut and met1.
SKY130A["contact_to"] = "li"
SKY130A["label_layer"] = {"li": "li", "met1": "met1"}

# gf180mcuD (3.3 V devices), from the GF180MCU design rule manual; every
# value is checked by tests/gen against the PDK's gf180mcu.drc deck and Magic.
GF180MCUD = {
    "grid": 0.005,
    "layers": {
        "tap": (22, 0), "nwell": (21, 0), "dnwell": (12, 0), "nsdm": (32, 0), "psdm": (31, 0),
        "licon": (33, 0), "met1": (34, 0), "via": (35, 0), "met2": (36, 0), "via2": (38, 0), "met3": (42, 0),
        "via3": (40, 0), "met4": (46, 0), "via4": (41, 0), "met5": (81, 0),
        "met1_label": (34, 10), "met1_pin": (34, 10),
    },
    "contact_to": "met1",
    "tap_w": 0.22,             # DF.1a
    "licon": 0.22, "licon_s": 0.25,          # CO.1, CO.2a
    "licon_tap_enc": 0.07,     # CO.4
    "sdm_enc": 0.16,           # NP.5a / PP.5a
    "nwell_ntap_enc": 0.12,    # DF.4c
    "nwell_w": 0.86,           # NW.1a
    "met1_mcon_enc": 0.06,     # CO.6 0.005, CO.6a 0.06 on two opposite sides: 0.06 all round
    "met1_w": 0.23,
}
GF180MCUD["stack"] = [
    ("met1", 0.23, 0.1444, "via", 0.26, 0.26, 0.06, 0.06),     # M1.1, M1.3; V1.1, V1.2a; V1.3c/V1.4a
    ("met2", 0.28, 0.1444, "via2", 0.26, 0.26, 0.06, 0.06),
    ("met3", 0.28, 0.1444, "via3", 0.26, 0.26, 0.06, 0.06),
    ("met4", 0.28, 0.1444, None, 0, 0, 0, 0),
]
GF180MCUD["em_ma_per_cut"] = {}

PDKS = {"sky130A": SKY130A, "gf180mcuD": GF180MCUD}
LIBRARIES = {"sky130A": "sky130_gen", "gf180mcuD": "gf180mcu_gen"}
