"""Design rules and layers per PDK for the hybrid-waffle FET, in nm.

The values come from the shared table ``pdk_rules`` (which cites each rule
and where it was checked); this module only picks the rules the waffle
uses and converts them to nm, the drawing's database unit. No rule value
appears in the drawing code: it reads ``PDKS``.
"""

import pdk_rules

# the rules the waffle reads (keys of pdk_rules.sky130A.RULES)
_RULE_KEYS = (
    "diff_w", "diff_s", "diff_tap_s_mv", "poly_w", "poly_s", "poly_diff_s", "diff_past_gate", "poly_past_diff",
    "licon", "licon_s", "licon_diff_enc", "licon_diff_enc1", "licon_tap_enc1", "licon_poly_enc", "licon_poly_enc1",
    "licon_gate_s", "pcon_diff_s", "pcon_pdiff_s", "npc_enc", "npc_w", "npc_s",
    "li_w", "li_s", "li_enc1", "li_area",
    "mcon", "mcon_s", "met1_mcon_enc", "met1_mcon_enc1", "met1_w", "met1_s", "met1_s_wide", "met1_area",
    "via", "via_s", "via_enc", "via_enc1", "met2_w", "met2_s", "met2_s_wide", "met2_area",
    "via2", "via2_s", "via2_enc_lo", "via2_enc_hi", "met3_w", "met3_s", "met3_s_wide", "met3_area",
    "via3", "via3_s", "via3_enc_lo", "via3_enc_hi", "met4_w", "met4_s", "met4_s_wide", "met4_area",
    "via4", "via4_s", "via4_enc_lo", "via4_enc_hi", "met5_w", "met5_s", "met5_area",
    "sdm_enc", "nwell_pdiff_enc", "nwell_pdiff_enc_mv", "nwell_ntap_enc", "nwell_ntap_enc_mv", "nwell_w",
    "hvi_w", "hvi_s", "lu_max", "diff_s_mv", "ndiff_nwell_s_mv", "nwell_s_hv", "hvntm_enc", "hvntm_w",
    "dnwell_w", "nwell_dnwell_out", "nwell_dnwell_in",
    "ld_underlap", "ld_drift_n", "ld_drift_p", "ld_n_well_past_diff", "ld_n_well_enc_tap", "ld_p_hole_past_diff",
    "ld_p_hole_enc_tap", "ld_wmin", "ld_drain_to_source_n", "ld_drain_to_source_p",
)
_LAYER_KEYS = ("nwell", "diff", "tap", "poly", "licon", "npc", "nsdm", "psdm", "hvi", "lvtn", "hvtp", "edid",
               "hvntm", "dnwell", "li", "mcon", "met1", "via", "met2", "via2", "met3", "via3", "met4", "via4",
               "met5")


def _from_table(pdk):
    t = pdk_rules.get(pdk)
    return {
        "name": t.name,
        "grid": int(round(t.grid * 1000)),
        "layers": {k: t.layer(k) for k in _LAYER_KEYS},
        "pin": dict(t.pin),
        "label": dict(t.label),
        "rules": {k: t.nm(k) for k in _RULE_KEYS},
        "devices": {k: dict(v) for k, v in t.devices.items()},
        "allows_45_fet": t.allows_45_fet,
        "allows_45_metal": t.allows_45_metal,
        "model_prefix": t.model_prefix,
    }


SKY130 = _from_table("sky130A")
PDKS = {"sky130A": SKY130}
