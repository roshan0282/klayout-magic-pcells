"""gf180mcuD (3.3 V devices): layers and design rules for this package's
generators, in um, from the GF180MCU design rule manual (google/gf180mcu-pdk
de3240d). Rules with a probe kind are re-checked by tests/rules against the
PDK's gf180mcu.drc (variant D); the generators that use them are tested
clean in that deck and in Magic.
"""

from ._rule import R

NAME = "gf180mcuD"
GRID = 0.005

LAYERS = {
    "nwell": (21, 0), "dnwell": (12, 0), "comp": (22, 0), "poly2": (30, 0), "nplus": (32, 0),
    "pplus": (31, 0), "dualgate": (55, 0), "contact": (33, 0),
    "metal1": (34, 0), "via1": (35, 0), "metal2": (36, 0), "via2": (38, 0), "metal3": (42, 0),
    "via3": (40, 0), "metal4": (46, 0), "via4": (41, 0), "metal5": (81, 0),
}
PIN = {"metal1": (34, 10), "metal2": (36, 10), "metal3": (42, 10), "metal4": (46, 10), "metal5": (81, 10)}
LABEL = dict(PIN)

STACK = [("metal1", "via1", "via1_enc", "via1_enc"), ("metal2", "via2", "via2_enc", "via2_enc"),
         ("metal3", "via3", "via3_enc", "via3_enc"), ("metal4", None, None, None)]

RULES = {
    "comp_w": R(0.22, "DF.1a", "drm", kind="width", on="comp"),
    "comp_s": R(0.28, "DF.3a", "drm", kind="space", on="comp"),
    "nwell_comp_enc": R(0.12, "DF.4c", "drm", note="n-well around an n-tap"),
    "poly2_w": R(0.18, "PL.1", "drm", kind="width", on="poly2"),
    "poly2_s": R(0.24, "PL.3a", "drm", kind="space", on="poly2"),
    "contact": R(0.22, "CO.1", "drm", kind="exact", on="contact"),
    "contact_s": R(0.25, "CO.2a", "drm", kind="space", on="contact"),
    "comp_contact_enc": R(0.07, "CO.4", "drm"),
    "metal1_contact_enc": R(0.06, "CO.6a", "drm", note="CO.6 0.005; CO.6a 0.06 on two opposite sides, used all round"),
    "sdm_enc": R(0.16, "NP.5a", "drm", note="also PP.5a"),
    "nplus_s": R(0.40, "NP.2", "drm", kind="space", on="nplus"),
    "pplus_s": R(0.40, "PP.2", "drm", kind="space", on="pplus"),
    "dualgate_s": R(0.44, "DV.2", "drm", kind="space", on="dualgate"),
    "nwell_w": R(0.86, "NW.1a", "drm", kind="width", on="nwell"),
    "nwell_s": R(0.60, "NW.2a", "drm", note="same potential (the placer merges n-wells closer than this); "
                 "two separate n-wells are different potential to the deck (NW.2b 1.4), so no probe"),
    "nwell_s_diff": R(1.40, "NW.2b", "drm", kind="space", on="nwell", probe_ids=("NW.2b_LV",),
                      note="different potential"),
    "metal1_w": R(0.23, "M1.1", "drm", kind="width", on="metal1"),
    "metal1_s": R(0.23, "M1.2a", "drm", kind="space", on="metal1"),
    "metal1_s_wide": R(0.30, "M1.2b", "drm", kind="space", on="metal1", wide=10.5, note="metal wider than 10 um"),
    "metal1_area": R(0.1444, "M1.3", "drm", kind="area", on="metal1"),
    "via1": R(0.26, "V1.1", "drm", kind="exact", on="via1"),
    "via1_s": R(0.26, "V1.2a", "drm", kind="space", on="via1"),
    "via1_enc": R(0.06, "V1.4a", "drm", note="V1.3c/V1.4a, the two-sided value used all round"),
    "metal2_w": R(0.28, "M2.1", "drm", kind="width", on="metal2"),
    "metal2_s": R(0.28, "M2.2a", "drm", kind="space", on="metal2"),
    "metal2_s_wide": R(0.30, "M2.2b", "drm", kind="space", on="metal2", wide=10.5),
    "metal2_area": R(0.1444, "M2.3", "drm", kind="area", on="metal2"),
    "via2": R(0.26, "V2.1", "drm", kind="exact", on="via2"),
    "via2_s": R(0.26, "V2.2a", "drm", kind="space", on="via2"),
    "via2_enc": R(0.06, "V2.4a", "drm"),
    "metal3_w": R(0.28, "M3.1", "drm", kind="width", on="metal3"),
    "metal3_s": R(0.28, "M3.2a", "drm", kind="space", on="metal3"),
    "metal3_s_wide": R(0.30, "M3.2b", "drm", kind="space", on="metal3", wide=10.5),
    "metal3_area": R(0.1444, "M3.3", "drm", kind="area", on="metal3"),
    "via3": R(0.26, "V3.1", "drm", kind="exact", on="via3"),
    "via3_s": R(0.26, "V3.2a", "drm", kind="space", on="via3"),
    "via3_enc": R(0.06, "V3.4a", "drm"),
    "metal4_w": R(0.28, "M4.1", "drm", kind="width", on="metal4"),
    "metal4_s": R(0.28, "M4.2a", "drm", kind="space", on="metal4"),
    "metal4_area": R(0.1444, "M4.3", "drm", kind="area", on="metal4"),
}

DEVICES = {}
MODEL_PREFIX = ""
ALLOWS_45_FET = True     # PL.7
ALLOWS_45_METAL = True

DRC_DECK = ("libs.tech/klayout/tech/drc/gf180mcu.drc", "topcell",
            {"decks": "all,-density", "variant": "D", "run_mode": "deep"})
EM_MA_PER_CUT = {}
