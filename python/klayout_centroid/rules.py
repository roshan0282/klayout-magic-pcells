"""Spacing rules the placer needs, per PDK: layer -> (space_um, mode).

mode "keep": shapes of neighbouring unit cells must stay at least
    ``space`` apart (conductors, diffusion, cuts: merging them would short
    devices). The auto pitch is chosen for these layers.
mode "merge": shapes of neighbours may touch, so gaps narrower than
    ``space`` are filled in (wells, implants, threshold and thick-oxide
    layers: same layer, same potential or no electrical meaning).

sky130A values from libs.tech/klayout/drc/sky130A_mr.drc (rule ids
quoted); the same numbers as klayout_power_pcells.rules where both have
them. Metals use their wide-metal spacing, which is conservative for unit
cells.
"""

SKY130A = {
    "grid": 0.005,
    # where the device-name labels go: areaid.analog. Magic ignores the
    # layer, the LVS deck doesn't read it, and the DRC deck only declares it
    # as polygons, so the texts can't become net names.
    "label_layer": (81, 79),
    "layers": {
        (65, 20): (0.27, "keep"),    # diff   difftap.3
        (65, 44): (0.27, "keep"),    # tap    difftap.3
        (66, 20): (0.21, "keep"),    # poly   poly.2
        (66, 44): (0.17, "keep"),    # licon  licon.2
        (67, 20): (0.17, "keep"),    # li1    li.3
        (67, 44): (0.19, "keep"),    # mcon   ct.2
        (68, 20): (0.28, "keep"),    # met1   m1.3ab (wide), m1.2 0.14
        (68, 44): (0.17, "keep"),    # via    via.2
        (69, 20): (0.28, "keep"),    # met2   m2.3ab (wide), m2.2 0.14
        (69, 44): (0.20, "keep"),    # via2   via2.2
        (70, 20): (0.40, "keep"),    # met3   m3.3cd (wide)
        (70, 44): (0.20, "keep"),    # via3   via3.2
        (71, 20): (0.40, "keep"),    # met4   m4.5ab (wide)
        (71, 44): (0.80, "keep"),    # via4   via4.2
        (72, 20): (1.60, "keep"),    # met5   m5.2
        (64, 20): (1.27, "merge"),   # nwell  nwell.2a
        (64, 18): (6.30, "merge"),   # dnwell dnwell.3
        (93, 44): (0.38, "merge"),   # nsdm   nsd.2
        (94, 20): (0.38, "merge"),   # psdm   psd.2
        (95, 20): (0.27, "merge"),   # npc    npc.2
        (125, 44): (0.38, "merge"),  # lvtn   lvtn.2
        (78, 44): (0.38, "merge"),   # hvtp   hvtp.2
        (75, 20): (0.70, "merge"),   # hvi    hvi.2a
        (125, 20): (0.70, "merge"),  # hvntm  hvntm.2
        (86, 20): (0.84, "merge"),   # rpm    rpm.2
        (79, 20): (0.84, "merge"),   # urpm   urpm.2
        (89, 44): (0.84, "keep"),    # capm   capm.2a
        (97, 44): (0.84, "keep"),    # cap2m  cap2m.2a
    },
    # a MIM cap's bottom plate needs more space than plain metal:
    # cap layer present in the unit -> (metal, its spacing then)
    "bottom_plates": {(89, 44): ((70, 20), 1.2),    # capm.2b  met3 bottom plates
                      (97, 44): ((71, 20), 1.2)},   # cap2m.2b met4 bottom plates
    # implants that must not overlap each other after filling
    "exclusive": [((93, 44), (94, 20))],
}

PDKS = {"sky130A": SKY130A}

# which PDK a unit-cell library belongs to
LIBRARY_PDK = {"sky130_magic": "sky130A", "gf180mcu_magic": "gf180mcuD", "sg13g2_magic": "ihp-sg13g2",
               "sg13cmos5l_magic": "ihp-sg13cmos5l"}


def for_library(lib):
    """The rule table for a unit-cell library, or None if there is none yet
    (then the gaps must be given)."""
    return PDKS.get(LIBRARY_PDK.get(lib, ""))
