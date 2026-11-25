"""Rules and layers for the generators, per PDK, in um.

The values come from the shared table ``pdk_rules`` (which cites each
rule). The generators use generic names on every PDK (``tap``, ``licon``,
``met1``, ``via`` ...); ``_NAMES`` maps them to the PDK's own layer names and
``_RULES`` to its rule keys.
"""

import pdk_rules

# generic generator layer name -> the PDK table's layer name
_NAMES = {
    "sky130A": {"tap": "tap", "nwell": "nwell", "dnwell": "dnwell", "nsdm": "nsdm", "psdm": "psdm",
                "licon": "licon", "li": "li", "mcon": "mcon", "met1": "met1", "via": "via", "met2": "met2",
                "via2": "via2", "met3": "met3", "via3": "via3", "met4": "met4", "via4": "via4", "met5": "met5"},
    "gf180mcuD": {"tap": "comp", "nwell": "nwell", "dnwell": "dnwell", "nsdm": "nplus", "psdm": "pplus",
                  "licon": "contact", "met1": "metal1", "via": "via1", "met2": "metal2", "via2": "via2",
                  "met3": "metal3", "via3": "via3", "met4": "metal4", "via4": "via4", "met5": "metal5"},
}
# pin and label layers: generic metal -> the PDK's metal
_PINS = {"sky130A": ("li", "met1"), "gf180mcuD": ("met1",)}

# generator value -> the PDK table's rule key ("_licon_tap_enc": the one-direction
# value of licon.7, used on all sides; "met1_mcon_enc": the two-edge value)
_RULES = {
    "sky130A": {"tap_w": "tap_w", "licon": "licon", "licon_s": "licon_s", "licon_tap_enc": "licon_tap_enc1",
                "sdm_enc": "sdm_enc", "nwell_ntap_enc": "nwell_ntap_enc", "nwell_w": "nwell_w",
                "dnwell_w": "dnwell_w", "nwell_dnwell_out": "nwell_dnwell_out",
                "nwell_dnwell_in": "nwell_dnwell_in", "li_w": "li_w", "mcon": "mcon", "mcon_s": "mcon_s",
                "met1_mcon_enc": "met1_mcon_enc1", "met1_w": "met1_w"},
    "gf180mcuD": {"tap_w": "comp_w", "licon": "contact", "licon_s": "contact_s",
                  "licon_tap_enc": "comp_contact_enc", "sdm_enc": "sdm_enc", "nwell_ntap_enc": "nwell_comp_enc",
                  "nwell_w": "nwell_w", "met1_mcon_enc": "metal1_contact_enc", "met1_w": "metal1_w"},
}
_CONTACT_TO = {"sky130A": "li", "gf180mcuD": "met1"}   # what the guard-ring contact lands on


def _generic(names):
    return {v: k for k, v in names.items()}


def _from_table(pdk):
    t = pdk_rules.get(pdk)
    names = _NAMES[pdk]
    g = _generic(names)
    out = {"grid": t.grid}
    layers = {k: t.layer(v) for k, v in names.items()}
    for m in _PINS[pdk]:
        layers[m + "_label"] = t.label[names[m]]
        layers[m + "_pin"] = t.pin[names[m]]
    out["layers"] = layers
    out.update({k: t.um(v) for k, v in _RULES[pdk].items()})
    # VIA_STACK's metal stack, bottom to top: (metal, min width, min area um2, cut to the
    # next metal, cut size, cut spacing, enclosure of the cut by the metal below, by the
    # metal above)
    stack = []
    for metal, cut, enc_lo, enc_hi in t.stack:
        if cut is None:
            stack.append((g[metal], t.um(metal + "_w"), t.um(metal + "_area"), None, 0, 0, 0, 0))
        else:
            stack.append((g[metal], t.um(metal + "_w"), t.um(metal + "_area"), g[cut], t.um(cut),
                          t.um(cut + "_s"), t.um(enc_lo), t.um(enc_hi)))
    out["stack"] = stack
    # DC current per cut (mA) for electromigration sizing: empty, the open PDKs
    # publish no EM table; the current per cut must be given.
    out["em_ma_per_cut"] = dict(t.em_ma_per_cut)
    out["contact_to"] = _CONTACT_TO[pdk]
    if pdk == "sky130A":
        out["label_layer"] = {"li": "li", "met1": "met1"}
    return out


SKY130A = _from_table("sky130A")
GF180MCUD = _from_table("gf180mcuD")
PDKS = {"sky130A": SKY130A, "gf180mcuD": GF180MCUD}
LIBRARIES = {"sky130A": "sky130_gen", "gf180mcuD": "gf180mcu_gen"}
