"""sky130A: layers, design rules and devices for this package's generators, in um.

Every value was checked on 2026-11-24/25 against the PDK as installed
(open_pdks 1689ac3): ``kl`` against libs.tech/klayout/drc/sky130A_mr.drc,
``mg``/``cif`` against libs.tech/magic/sky130A.tech, ``tcl`` against Magic's
device generator sky130A.tcl. Rules with a probe kind are re-checked by
tests/rules (the deck must pass at the value and fail one grid step under).

This merges the tables that klayout_power_pcells, klayout_gen,
klayout_centroid and live_verify carried before version 0.9.
"""

from ._rule import R

NAME = "sky130A"
GRID = 0.005

LAYERS = {
    "nwell": (64, 20), "dnwell": (64, 18), "diff": (65, 20), "tap": (65, 44), "poly": (66, 20),
    "licon": (66, 44), "npc": (95, 20), "nsdm": (93, 44), "psdm": (94, 20), "hvi": (75, 20),
    "lvtn": (125, 44), "hvtp": (78, 44), "edid": (81, 57), "hvntm": (125, 20), "rpm": (86, 20),
    "urpm": (79, 20), "capm": (89, 44), "cap2m": (97, 44), "areaid_analog": (81, 79),
    "li": (67, 20), "mcon": (67, 44), "met1": (68, 20), "via": (68, 44), "met2": (69, 20),
    "via2": (69, 44), "met3": (70, 20), "via3": (70, 44), "met4": (71, 20), "via4": (71, 44),
    "met5": (72, 20),
}
PIN = {"li": (67, 16), "met1": (68, 16), "met2": (69, 16), "met3": (70, 16), "met4": (71, 16), "met5": (72, 16)}
LABEL = {"li": (67, 5), "met1": (68, 5), "met2": (69, 5), "met3": (70, 5), "met4": (71, 5), "met5": (72, 5)}

# Metal stack bottom to top: (metal, cut to the next metal or None, rule key of
# the cut's enclosure by this metal, by the next metal). The enclosures are the
# larger "two adjacent/opposite edges" values, which the generators use on all sides.
STACK = [("li", "mcon", "li_mcon_enc", "met1_mcon_enc1"), ("met1", "via", "via_enc1", "via_enc1"),
         ("met2", "via2", "via2_enc_lo", "via2_enc_hi"), ("met3", "via3", "via3_enc_lo", "via3_enc_hi"),
         ("met4", "via4", "via4_enc_lo", "via4_enc_hi"), ("met5", None, None, None)]

RULES = {
    # ---- diffusion and tap
    "diff_w": R(0.15, "difftap.1", kind="width", on="diff"),
    "tap_w": R(0.15, "difftap.1", kind="width", on="tap"),
    "diff_s": R(0.27, "difftap.3", kind="space", on="diff"),
    "tap_s": R(0.27, "difftap.3", kind="space", on="tap"),
    "diff_tap_s_mv": R(0.37, "diff/tap.15b", "mg", note="thick-oxide n-diffusion to p-tap"),
    "diff_s_mv": R(0.30, "diff/tap.15a", "mg", note="MV diffusion spacing"),
    "ndiff_nwell_s_mv": R(0.43, "diff/tap.24", "mg", note="MV n-diffusion to n-well"),
    # ---- poly
    "poly_w": R(0.15, "poly.1a", kind="width", on="poly"),
    "poly_s": R(0.21, "poly.2", kind="space", on="poly"),
    "poly_diff_s": R(0.075, "poly.4", "mg"),
    "diff_past_gate": R(0.25, "poly.7", "mg"),
    "poly_past_diff": R(0.13, "poly.8", "mg"),
    # ---- licon
    "licon": R(0.17, "licon.1", kind="exact", on="licon"),
    "licon_s": R(0.17, "licon.2", kind="space", on="licon", probe_ids=("MR_licon.SP.1",)),
    "licon_diff_enc": R(0.04, "licon.5a", "mg"),
    "licon_diff_enc1": R(0.06, "licon.5c", "mg", note="one direction"),
    "licon_tap_enc1": R(0.12, "licon.7", "mg", note="one direction; klayout_gen uses it on all sides"),
    "licon_poly_enc": R(0.05, "licon.8", "mg"),
    "licon_poly_enc1": R(0.08, "licon.8a", "mg", note="one direction"),
    "licon_gate_s": R(0.055, "licon.11", "mg"),
    "pcon_diff_s": R(0.19, "licon.14", "mg"),
    "pcon_pdiff_s": R(0.235, "licon.9+psdm.5a", "mg", note="poly contact to p-diffusion"),
    "npc_enc": R(0.10, "", "cif", note="npc around a poly contact: cifoutput 'grow 100'"),
    "npc_w": R(0.27, "npc.1", kind="width", on="npc"),
    "npc_s": R(0.27, "npc.2", kind="space", on="npc"),
    # ---- li
    "li_w": R(0.17, "li.1", kind="width", on="li"),
    "li_s": R(0.17, "li.3", kind="space", on="li"),
    "li_enc1": R(0.08, "li.5", note="li around licon, one direction"),
    "li_area": R(0.0561, "li.6", kind="area", on="li"),
    "li_mcon_enc": R(0.0, "", "use", note="li under mcon: no enclosure rule (ct.? needs none)"),
    # ---- mcon and met1
    "mcon": R(0.17, "ct.1", kind="exact", on="mcon"),
    "mcon_s": R(0.19, "ct.2", kind="space", on="mcon"),
    "met1_mcon_enc": R(0.03, "m1.4", kind="enc", on=("met1", "mcon"), probe_ids=("791_m1.4",)),
    "met1_mcon_enc1": R(0.06, "m1.5", note="two adjacent edges"),
    "met1_w": R(0.14, "m1.1", kind="width", on="met1"),
    "met1_s": R(0.14, "m1.2", kind="space", on="met1"),
    "met1_s_wide": R(0.28, "m1.3ab", kind="space", on="met1", wide=3.5, note="metal wider than 3 um"),
    "met1_area": R(0.083, "m1.6", kind="area", on="met1"),
    # ---- via and met2
    "via": R(0.15, "via.1a", kind="exact", on="via"),
    "via_s": R(0.17, "via.2", kind="space", on="via"),
    "via_enc": R(0.055, "via.4a", kind="enc", on=("met1", "via"), note="also m2.4"),
    "via_enc1": R(0.085, "via.5a", note="two adjacent edges; also m2.5"),
    "met2_w": R(0.14, "m2.1", kind="width", on="met2"),
    "met2_s": R(0.14, "m2.2", kind="space", on="met2"),
    "met2_s_wide": R(0.28, "m2.3ab", kind="space", on="met2", wide=3.5),
    "met2_area": R(0.0676, "m2.6", kind="area", on="met2"),
    # ---- via2 and met3
    "via2": R(0.20, "via2.1a", kind="exact", on="via2"),
    "via2_s": R(0.20, "via2.2", kind="space", on="via2"),
    "via2_enc_lo": R(0.085, "via2.5", note="via2.4 is 0.04; via2.5's 0.085 used on all sides"),
    "via2_enc_hi": R(0.085, "via2.5", note="m3.4 0.065, via2.5 0.085"),
    "met3_w": R(0.30, "m3.1", kind="width", on="met3"),
    "met3_s": R(0.30, "m3.2", kind="space", on="met3"),
    "met3_s_wide": R(0.40, "m3.3cd", kind="space", on="met3", wide=3.5),
    "met3_area": R(0.24, "m3.6", kind="area", on="met3"),
    # ---- via3 and met4
    "via3": R(0.20, "via3.1", kind="exact", on="via3"),
    "via3_s": R(0.20, "via3.2", kind="space", on="via3"),
    "via3_enc_lo": R(0.09, "via3.5", note="via3.4 0.06, via3.5 0.09"),
    "via3_enc_hi": R(0.065, "m4.3", kind="enc", on=("met4", "via3")),
    "met4_w": R(0.30, "m4.1", kind="width", on="met4"),
    "met4_s": R(0.30, "m4.2", kind="space", on="met4"),
    "met4_s_wide": R(0.40, "m4.5ab", kind="space", on="met4", wide=3.5),
    "met4_area": R(0.24, "m4.4a", kind="area", on="met4"),
    # ---- via4 and met5
    "via4": R(0.80, "via4.1", kind="exact", on="via4"),
    "via4_s": R(0.80, "via4.2", kind="space", on="via4"),
    "via4_enc_lo": R(0.19, "via4.4", kind="enc", on=("met4", "via4")),
    "via4_enc_hi": R(0.31, "m5.3", kind="enc", on=("met5", "via4")),
    "met5_w": R(1.60, "m5.1", kind="width", on="met5"),
    "met5_s": R(1.60, "m5.2", kind="space", on="met5"),
    "met5_area": R(4.0, "m5.4", kind="area", on="met5"),
    # ---- implants and wells
    "sdm_enc": R(0.125, "nsd.5a", "cif", note="nsdm/psdm around diff: baseNSDM/basePSDM grow 125"),
    "nsdm_s": R(0.38, "nsd.2", kind="space", on="nsdm", probe_ids=("nsdm.1",),
                 note="the deck numbers nsdm spacing nsdm.1"),
    "psdm_s": R(0.38, "psd.2", kind="space", on="psdm", probe_ids=("psdm.1",),
                 note="the deck numbers psdm spacing psdm.1"),
    "nwell_pdiff_enc": R(0.18, "diff/tap.8", "mg"),
    "nwell_pdiff_enc_mv": R(0.33, "diff/tap.17", "mg"),
    "nwell_ntap_enc": R(0.18, "diff/tap.10", "mg"),
    "nwell_ntap_enc_mv": R(0.33, "diff/tap.19", "mg"),
    "nwell_w": R(0.84, "nwell.1", kind="width", on="nwell"),
    "nwell_s": R(1.27, "nwell.2a", kind="space", on="nwell"),
    "nwell_s_hv": R(2.0, "nwell.8", "mg", note="HV n-well spacing, notches included"),
    "dnwell_w": R(3.0, "dnwell.1", kind="width", on="dnwell"),
    "dnwell_s": R(6.3, "dnwell.2", kind="space", on="dnwell"),
    "nwell_dnwell_out": R(0.4, "nwell.5a", "mg", note="n-well past the deep n-well's edge, outside"),
    "nwell_dnwell_in": R(1.03, "nwell.6", note="... and inside; holes in the n-well this far in"),
    "hvi_w": R(0.6, "hvi.1", kind="width", on="hvi"),
    "hvi_s": R(0.7, "hvi.2a", kind="space", on="hvi"),
    "hvntm_w": R(0.7, "hvntm.1", kind="width", on="hvntm"),
    "hvntm_s": R(0.7, "hvntm.2", kind="space", on="hvntm"),
    "hvntm_enc": R(0.185, "", "cif", note="HVNTM around MV n diffusion and gates, and its gap to a p-tap: grow 185"),
    "lvtn_s": R(0.38, "lvtn.2", kind="space", on="lvtn"),
    "hvtp_s": R(0.38, "hvtp.2", kind="space", on="hvtp"),
    "rpm_s": R(0.84, "rpm.2", kind="space", on="rpm"),
    "urpm_s": R(0.84, "urpm.2", kind="space", on="urpm"),
    "capm_s": R(0.84, "capm.2a", kind="space", on="capm"),
    "cap2m_s": R(0.84, "cap2m.2a", kind="space", on="cap2m"),
    "capm_bottom_s": R(1.2, "capm.2b", note="met3 bottom plates of MIM caps"),
    "cap2m_bottom_s": R(1.2, "cap2m.2b", note="met4 bottom plates"),
    "lu_max": R(15.0, "LU.2", "mg", note="diffusion within 15 um of a tap (LU.2/LU.3)"),
    # ---- extended-drain (LDMOS) devices, as Magic draws (sky130A.tcl draw_ldnmos_drain /
    #      draw_ldpmos_drain) and checks them (sky130A.tech "Extended drain rules")
    "ld_underlap": R(0.13, "", "tcl", note="diffusion stops this short of the poly's drain side"),
    "ld_drift_n": R(1.585, "ldbreak", "mg", note="drain tap to source diffusion, n"),
    "ld_drift_p": R(1.19, "ldbreak", "mg", note="... p"),
    "ld_n_well_past_diff": R(0.225, "", "tcl", note="n-LDMOS drift n-well under the gate past the diffusion: 0.54 - 0.315"),
    "ld_n_well_enc_tap": R(0.66, "", "tcl", note="... and around the drain tap: grow 0.66"),
    "ld_p_hole_past_diff": R(0.26, "", "tcl", note="p-LDMOS n-well hole under the gate: 0.38 - 0.12"),
    "ld_p_hole_enc_tap": R(0.86, "", "mg", note="... around the drain tap: extpwell grow 860"),
    "ld_wmin": R(5.0, "denmos.2", "mg", note="also depmos.2 and Magic's wmin"),
    "ld_drain_to_source_n": R(2.51, "denmos.6+denmos.3", "mg"),
    "ld_drain_to_source_p": R(2.11, "depmos.6+depmos.3", "mg"),
}

# kind, thick oxide (hvi), minimum L in nm (Magic's _check of the same device),
# threshold-implant layers over the active area, "ld" for extended-drain devices
DEVICES = {
    "nfet_01v8": {"kind": "n", "hv": False, "lmin": 150, "vt": []},
    "nfet_01v8_lvt": {"kind": "n", "hv": False, "lmin": 150, "vt": ["lvtn"]},
    "pfet_01v8": {"kind": "p", "hv": False, "lmin": 150, "vt": []},
    "pfet_01v8_lvt": {"kind": "p", "hv": False, "lmin": 350, "vt": ["lvtn"]},
    "pfet_01v8_hvt": {"kind": "p", "hv": False, "lmin": 150, "vt": ["hvtp"]},
    "nfet_g5v0d10v5": {"kind": "n", "hv": True, "lmin": 500, "vt": []},
    "pfet_g5v0d10v5": {"kind": "p", "hv": True, "lmin": 500, "vt": []},
    # denmos.1 1.055 um, on the 10 nm grid the waffle uses for L
    "nfet_g5v0d16v0": {"kind": "n", "hv": True, "lmin": 1060, "vt": [], "ld": True},
    "pfet_g5v0d16v0": {"kind": "p", "hv": True, "lmin": 1050, "vt": [], "ld": True},   # depmos.1
}
MODEL_PREFIX = "sky130_fd_pr__"

# Edge angles (OFFGRID-ANGLES): x.2 keeps poly, diff, tap and the cuts at
# 0/90 degrees; x.3a allows 45 on li, the metals, wells and implants.
ALLOWS_45_FET = False
ALLOWS_45_METAL = True

# The PDK's DRC deck: (path under the PDK, top-cell variable, {variable: value}).
DRC_DECK = ("libs.tech/klayout/drc/sky130A_mr.drc", "top_cell",
            {"feol": "true", "beol": "true", "offgrid": "true", "floating_met": "false", "seal": "false"})
# EM limits (mA per cut): the open PDK publishes none (x.4 names the guideline only).
EM_MA_PER_CUT = {}
