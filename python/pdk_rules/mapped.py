"""Export a table in gLayout's MappedPDK schema (ReaLLMASIC/gLayout,
src/glayout/pdk/mappedpdk.py, read Nov 2026):

* ``glayers``: generic layer name -> (layer, datatype); names from
  ``MappedPDK.valid_glayers``.
* ``grules[a][b]``: a rule dict or None for every pair of valid glayers;
  ``grules[a][a]`` holds a layer's own rules, ``grules[a][b]`` the rules
  between two layers (enclosure of b by a). Values in um.

gLayout's sky130 mapping shifts the metal names by one: its ``met1`` is
li1, ``mcon`` is licon, ``via1`` is mcon, ``met2`` is met1, and so on, so
sky130's met5 has no generic name. ``glayout()`` follows that convention so
the dicts can be passed to ``MappedPDK(glayers=..., grules=...)`` as they
are. Unlike gLayout's own table, ``active_tap`` is the tap layer (65, 44).
"""

from . import get

VALID_GLAYERS = (
    "fin", "lvt", "slvt", "sramvt", "gcut", "sdt", "lig", "lisd", "dnwell", "pwell", "nwell", "p+s/d", "n+s/d",
    "active_diff", "active_tap", "poly", "mcon", "met1", "via1", "met2", "via2", "met3", "via3", "met4", "via4",
    "met5", "capmet", "lvs_bjt", "drc_bjt", "met5_pin", "met4_pin", "met3_pin", "met2_pin", "met1_pin",
    "poly_pin", "active_diff_pin", "met5_label", "met4_label", "met3_label", "met2_label", "met1_label",
    "poly_label", "active_diff_label",
)
# the rule keys gLayout's own tables use
RULE_KEYS = {"min_width", "min_separation", "min_enclosure", "max_separation", "width", "overhang", "extension",
             "via_enclosure"}

# generic name -> this table's layer name
GENERIC = {
    "sky130A": {"dnwell": "dnwell", "nwell": "nwell", "p+s/d": "psdm", "n+s/d": "nsdm", "active_diff": "diff",
                "active_tap": "tap", "poly": "poly", "mcon": "licon", "met1": "li", "via1": "mcon",
                "met2": "met1", "via2": "via", "met3": "met2", "via3": "via2", "met4": "met3", "via4": "via3",
                "met5": "met4"},
    "gf180mcuD": {"dnwell": "dnwell", "nwell": "nwell", "p+s/d": "pplus", "n+s/d": "nplus", "active_diff": "comp",
                  "active_tap": "comp", "poly": "poly2", "mcon": "contact", "met1": "metal1", "via1": "via1",
                  "met2": "metal2", "via2": "via2", "met3": "metal3", "via3": "via3", "met4": "metal4",
                  "via4": "via4", "met5": "metal5"},
}
# enclosures of the first contact (generic "mcon"): (generic outer layer, rule key)
CONTACT_ENC = {
    "sky130A": [("met1", "li_enc1"), ("poly", "licon_poly_enc"), ("active_diff", "licon_diff_enc1")],
    "gf180mcuD": [("met1", "metal1_contact_enc"), ("active_diff", "comp_contact_enc")],
}


def glayout(pdk):
    """{"glayers": ..., "grules": ...} of a PDK in gLayout's schema."""
    t = get(pdk)
    gen = GENERIC[pdk]
    glayers = {g: t.layer(n) for g, n in gen.items()}
    for g, n in gen.items():
        if g.startswith("met") or g == "poly":
            if n in t.pin:
                glayers[g + "_pin"] = t.pin[n]
            if n in t.label:
                glayers[g + "_label"] = t.label[n]
    glayers = {g: v for g, v in glayers.items() if g in VALID_GLAYERS}
    grules = {a: {b: None for b in VALID_GLAYERS} for a in VALID_GLAYERS}
    back = {n: g for g, n in gen.items()}

    def put(a, b, **rule):
        rule = {k: v for k, v in rule.items() if v is not None}
        if rule:
            grules[a][b] = dict(grules[a][b] or {}, **rule)

    for g, n in gen.items():
        w, s = t.width_space(n)
        cut = n in t.rules and t.rules[n].kind == "exact"
        put(g, g, min_width=w, min_separation=s, width=w if cut else None)
    for metal, cut, lo, hi in t.stack:
        if cut is None or metal not in back or cut not in back:
            continue
        above = t.stack[[m for m, *_ in t.stack].index(metal) + 1][0]
        put(back[metal], back[cut], min_enclosure=t.um(lo))
        if above in back:
            put(back[cut], back[above], min_enclosure=t.um(hi))
    for outer, key in CONTACT_ENC[pdk]:
        put(outer, "mcon", min_enclosure=t.um(key))
    return {"glayers": glayers, "grules": grules}
