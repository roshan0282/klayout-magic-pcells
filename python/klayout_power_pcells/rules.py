"""Design rules and layers per PDK for the hybrid-waffle FET.

All lengths in nm (the drawing uses a 1 nm database unit). No rule value
appears in the drawing code: it reads this table. Each value was checked on
2026-11-24 against the PDK as installed (open_pdks 1689ac3, sky130A):

  [kl]  libs.tech/klayout/drc/sky130A_mr.drc  (rule text quoted with its value)
  [mg]  libs.tech/magic/sky130A.tech          (DRC section, or the gdsii
                                               cifoutput style for layers Magic
                                               generates: npc, nsdm, psdm)

gf180mcu goes here later, as another entry of PDKS.
"""

SKY130 = {
    "name": "sky130A",
    "grid": 5,
    "layers": {
        "nwell": (64, 20), "diff": (65, 20), "tap": (65, 44), "poly": (66, 20), "licon": (66, 44),
        "npc": (95, 20), "nsdm": (93, 44), "psdm": (94, 20), "hvi": (75, 20), "lvtn": (125, 44),
        "hvtp": (78, 44), "edid": (81, 57), "hvntm": (125, 20), "dnwell": (64, 18),
        "li": (67, 20), "mcon": (67, 44), "met1": (68, 20), "via": (68, 44), "met2": (69, 20),
        "via2": (69, 44), "met3": (70, 20), "via3": (70, 44), "met4": (71, 20), "via4": (71, 44),
        "met5": (72, 20),
    },
    # pin (datatype 16) and label (datatype 5) layers of the metals
    "pin": {"li": (67, 16), "met1": (68, 16), "met2": (69, 16), "met3": (70, 16), "met4": (71, 16),
            "met5": (72, 16)},
    "label": {"li": (67, 5), "met1": (68, 5), "met2": (69, 5), "met3": (70, 5), "met4": (71, 5),
              "met5": (72, 5)},
    "rules": {
        # diffusion and tap
        "diff_w": 150,          # difftap.1   [kl] 0.15
        "diff_s": 270,          # difftap.3   [kl] 0.27
        "diff_tap_s_mv": 370,   # diff/tap.15b [mg] 370 (thick-oxide n-diffusion to p-tap)
        # poly
        "poly_w": 150,          # poly.1a     [kl] 0.15
        "poly_s": 210,          # poly.2      [kl] 0.21
        "poly_diff_s": 75,      # poly.4      [mg] 75
        "diff_past_gate": 250,  # poly.7      [mg] 250
        "poly_past_diff": 130,  # poly.8      [mg] 130
        # licon
        "licon": 170,           # licon.1     [mg] 170
        "licon_s": 170,         # licon.2     [mg] 170
        "licon_diff_enc": 40,   # licon.5a    [mg] 40
        "licon_diff_enc1": 60,  # licon.5c    [mg] 60 (one direction)
        "licon_tap_enc1": 120,  # licon.7     [mg] 120 (one direction)
        "licon_poly_enc": 50,   # licon.8     [mg] 50
        "licon_poly_enc1": 80,  # licon.8a    [mg] 80 (one direction)
        "licon_gate_s": 55,     # licon.11    [mg] 55
        "pcon_diff_s": 190,     # licon.14    [mg] 190
        "pcon_pdiff_s": 235,    # licon.9 + psdm.5a [mg] 235 (poly contact to p-diffusion)
        "npc_enc": 100,         # npc around a poly contact [mg] cifoutput "grow 100"
        "npc_w": 270,           # npc.1       [kl] 0.27
        "npc_s": 270,           # npc.2       [kl] 0.27
        # li
        "li_w": 170,            # li.1        [kl] 0.17
        "li_s": 170,            # li.3        [kl] 0.17
        "li_enc1": 80,          # li.5        [kl] 0.08 (one direction)
        "li_area": 56100,       # li.6        [kl] 0.0561 um2 (nm2 / 1000)
        # mcon and met1
        "mcon": 170,            # ct.1        [kl] 0.17
        "mcon_s": 190,          # ct.2        [kl] 0.19
        "met1_mcon_enc": 30,    # m1.4        [mg] 30
        "met1_mcon_enc1": 60,   # m1.5        [kl] 0.06 (two adjacent edges)
        "met1_w": 140,          # m1.1        [kl] 0.14
        "met1_s": 140,          # m1.2        [kl] 0.14
        "met1_s_wide": 280,     # m1.3ab      [kl] 0.28 (metal wider than 3 um)
        "met1_area": 83000,     # m1.6        [kl] 0.083 um2
        # via and met2
        "via": 150,             # via.1a      [kl] 0.15
        "via_s": 170,           # via.2       [kl] 0.17
        "via_enc": 55,          # via.4a, m2.4 [kl] 0.055
        "via_enc1": 85,         # via.5a, m2.5 [kl] 0.085 (two adjacent edges)
        "met2_w": 140,          # m2.1        [kl] 0.14
        "met2_s": 140,          # m2.2        [kl] 0.14
        "met2_s_wide": 280,     # m2.3ab      [kl] 0.28
        "met2_area": 67600,     # m2.6        [kl] 0.0676 um2
        # via2 and met3
        "via2": 200,            # via2.1a     [kl] 0.2
        "via2_s": 200,          # via2.2      [kl] 0.2
        "via2_enc_lo": 85,      # via2.4 0.04 [kl]; 0.085 used on all sides (via2.5's 0.085, whose text names m3)
        "via2_enc_hi": 85,      # m3.4 0.065, via2.5 0.085 [kl]
        "met3_w": 300,          # m3.1        [kl] 0.3
        "met3_s": 300,          # m3.2        [kl] 0.3
        "met3_s_wide": 400,     # m3.3cd      [kl] 0.4 (metal wider than 3 um)
        "met3_area": 240000,    # m3.6        [kl] 0.24 um2
        # via3 and met4
        "via3": 200,            # via3.1_a    [kl] 0.2
        "via3_s": 200,          # via3.2      [kl] 0.2
        "via3_enc_lo": 90,      # via3.4 0.06, via3.5 0.09 [kl]
        "via3_enc_hi": 65,      # m4.3        [kl] 0.065
        "met4_w": 300,          # m4.1        [kl] 0.3
        "met4_s": 300,          # m4.2        [kl] 0.3
        "met4_s_wide": 400,     # m4.5ab      [kl] 0.4
        "met4_area": 240000,    # m4.4a       [kl] 0.24 um2
        # via4 and met5
        "via4": 800,            # via4.1_a    [kl] 0.8
        "via4_s": 800,          # via4.2      [kl] 0.8
        "via4_enc_lo": 190,     # via4.4      [kl] 0.19
        "via4_enc_hi": 310,     # m5.3        [kl] 0.31
        "met5_w": 1600,         # m5.1        [kl] 1.6
        "met5_s": 1600,         # m5.2        [kl] 1.6
        "met5_area": 4000000,   # m5.4        [kl] 4.0 um2
        # implants and wells
        "sdm_enc": 125,         # nsdm/psdm around diff: [mg] baseNSDM/basePSDM (diff grown 125), nsd/psd.5a 125
        "nwell_pdiff_enc": 180,     # diff/tap.8  [mg] 180
        "nwell_pdiff_enc_mv": 330,  # diff/tap.17 [mg] 330
        "nwell_ntap_enc": 180,      # diff/tap.10 [mg] 180
        "nwell_ntap_enc_mv": 330,   # diff/tap.19 [mg] 330
        "nwell_w": 840,         # nwell.1     [kl] 0.84
        "hvi_w": 600,           # hvi.1       [kl] 0.6
        "hvi_s": 700,           # hvi.2a      [kl] 0.7
        "lu_max": 15000,        # LU.2/LU.3   [mg] diffusion within 15 um of a tap
        # thick-oxide spacings the extended-drain devices need
        "diff_s_mv": 300,           # diff/tap.15a [mg] 300 (MV diffusion spacing)
        "ndiff_nwell_s_mv": 430,    # diff/tap.24  [mg] 430 (MV n-diffusion to n-well)
        "nwell_s_hv": 2000,
        "hvntm_enc": 185,           # HVNTM (MV n tip implant) around MV n diffusion and gates; and its
                                    # gap to a p-tap [mg] HVNTM "grow 185", hvntm_block "grow 185"
        "hvntm_w": 700,
        "dnwell_w": 3000,           # dnwell.1 [kl] 3.0
        "nwell_dnwell_out": 400,    # n-well over the deep n-well's edge, outside [mg] 0.4 (nwell.5a)
        "nwell_dnwell_in": 1030,    # ... and inside; holes in the n-well this far in (nwell.6) [kl] 1.03             # hvntm.1/.2 [kl] 0.7         # nwell.8      [mg] 2000 (HV n-well spacing, notches included)
        # extended-drain (LDMOS) devices, as Magic's generator draws them
        # (sky130A.tcl draw_ldnmos_drain / draw_ldpmos_drain) and checks them
        # (sky130A.tech, "Extended drain rules")
        "ld_underlap": 130,         # the diffusion stops this short of the poly's drain side [tcl] 0.13
        "ld_drift_n": 1585,         # drain tap to source diffusion [mg] ldbreak 1585 (n)
        "ld_drift_p": 1190,         #                                [mg] ldbreak 1190 (p)
        "ld_n_well_past_diff": 225,  # n-LDMOS drift n-well reaches under the gate past the diffusion edge [tcl] 0.54 - 0.315
        "ld_n_well_enc_tap": 660,   # ... and encloses the drain tap by [tcl] grow 0.66
        "ld_p_hole_past_diff": 260,  # p-LDMOS hole in the n-well: under the gate past the diffusion edge [tcl] 0.38 - 0.12
        "ld_p_hole_enc_tap": 860,   # ... and around the drain tap [mg] extpwell grow 860
        "ld_wmin": 5000,            # denmos.2 / depmos.2 [mg] 5000 (and Magic's wmin)
        "ld_drain_to_source_n": 2510,  # denmos.6 + denmos.3 [mg] 2510 (drain tap to source diffusion, across the gate)
        "ld_drain_to_source_p": 2110,  # depmos.6 + depmos.3 [mg] 2110
    },
    # kind, thick oxide (hvi), minimum L (Magic's _check of the same device),
    # the threshold-implant layers drawn over the active area, and "ld" for
    # the extended-drain devices (drain in a drift region: the D squares)
    "devices": {
        "nfet_01v8": {"kind": "n", "hv": False, "lmin": 150, "vt": []},
        "nfet_01v8_lvt": {"kind": "n", "hv": False, "lmin": 150, "vt": ["lvtn"]},
        "pfet_01v8": {"kind": "p", "hv": False, "lmin": 150, "vt": []},
        "pfet_01v8_lvt": {"kind": "p", "hv": False, "lmin": 350, "vt": ["lvtn"]},
        "pfet_01v8_hvt": {"kind": "p", "hv": False, "lmin": 150, "vt": ["hvtp"]},
        "nfet_g5v0d10v5": {"kind": "n", "hv": True, "lmin": 500, "vt": []},
        "pfet_g5v0d10v5": {"kind": "p", "hv": True, "lmin": 500, "vt": []},
        # denmos.1 1.055 um, on the 10 nm grid this generator uses for L
        "nfet_g5v0d16v0": {"kind": "n", "hv": True, "lmin": 1060, "vt": [], "ld": True},
        "pfet_g5v0d16v0": {"kind": "p", "hv": True, "lmin": 1050, "vt": [], "ld": True},   # depmos.1
    },
    # edge angles ([kl] OFFGRID-ANGLES): x.2 keeps poly, diff, tap and the
    # cuts at 0/90 degrees; x.3a allows 45 on li, the metals, wells and
    # implants. A 45 degree FET (a rotated waffle) needs 45 degree poly
    # and diffusion, which sky130A doesn't allow; gf180mcu (PL.7) and IHP
    # SG13G2 (Gat.g) do, so their entries will set it.
    "allows_45_fet": False,
    "allows_45_metal": True,
    "model_prefix": "sky130_fd_pr__",
}

PDKS = {"sky130A": SKY130}
