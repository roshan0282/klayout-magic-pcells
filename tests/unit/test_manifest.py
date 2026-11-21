import unittest

from tests.unit._util import needs_klayout
from klayout_magic_pcells.config import SHIPPED_MANIFEST
from klayout_magic_pcells.manifest import InvalidValue, Manifest, ParamSpec, format_float

MAN = Manifest.load(SHIPPED_MANIFEST)


def P(**kw):
    d = {"name": "w", "type": "float", "default": "0.420", "editable": True, "label": "Width (um)"}
    d.update(kw)
    return ParamSpec(d, kw.pop("family", "mos"))


class Formatting(unittest.TestCase):
    def test_float_default_string_is_kept(self):
        p = P()
        self.assertEqual(p.format(0.42), "0.420")
        self.assertEqual(p.format(0.42000000000000004), "0.420")

    def test_float_text(self):
        p = P()
        self.assertEqual(p.format(1.5), "1.5")
        self.assertEqual(p.format(31.0), "31.0")       # never "31": Tcl divides integers
        self.assertEqual(p.format(0.4234), "0.4234")
        self.assertEqual(p.format(1e-05), "1e-05")
        # KLayout reads "0.35" back from a file as 0.35000000000000003
        self.assertEqual(p.format(0.35000000000000003), "0.35")
        self.assertEqual(format_float(2898.6000000000004), "2898.6")

    def test_int_bool_signed(self):
        self.assertEqual(P(name="nf", type="int", default="1").format(3), "3")
        b = P(name="guard", type="bool01", default="1")
        self.assertEqual(b.format(True), "1")
        self.assertEqual(b.format(False), "0")
        self.assertIs(b.parse("0"), False)
        s = P(name="viasrc", type="signed", default="100", label="Source via coverage [+/-](%)")
        # Verbatim, whitespace included: Magic takes the anchor from the first
        # character, so " +50" (no anchor) and "+50" draw differently.
        self.assertEqual(s.format(" +50 "), " +50 ")
        self.assertEqual(s.parse("\t+30"), "\t+30")
        self.assertEqual(s.canonical(" -50"), " -50")
        self.assertEqual(s.format("-50"), "-50")
        self.assertEqual(s.unit, "%")
        self.assertIn("anchor", s.description)

    def test_signed_values_that_may_reach_magic(self):
        s = P(name="viagb", type="signed", default="0", label="Bottom via coverage [+/-](%)")
        for ok in ("+50", "-50", "50", "0", "100", "50.5", " +50", "\t-30", "+50 ", "1e2", ".5", "50."):
            s.check(ok)
        for bad in ("", "+", "-", "abc", "50abc", "50 50", "0x32", "nan", "inf", "{", "{50}",
                    "[exec touch /tmp/x]", "$x", "5$x", "\\x", "1[set a 1]", "\u0663\u0660"):
            with self.assertRaises(InvalidValue, msg=repr(bad)) as cm:
                s.check(bad)
            self.assertEqual(cm.exception.param, "viagb")
            self.assertIn("not sent to Magic", str(cm.exception))

    def test_build_request_refuses_a_command_in_a_coverage_value(self):
        d = MAN["sky130_fd_pr__nfet_01v8"]
        vals = dict(d.defaults_values(), viagb="[exec touch /tmp/x]")
        with self.assertRaises(InvalidValue):
            d.build_request(vals)
        # names and labels still work, and never reach Magic
        self.assertEqual(d.build_request(vals, check=False)["viagb"], "[exec touch /tmp/x]")

    def test_int_rejects_fraction(self):
        with self.assertRaises(ValueError):
            P(name="nf", type="int", default="1").parse("2.5")

    def test_units_and_descriptions(self):
        self.assertEqual(P().unit, "µm")
        self.assertEqual(P().description, "Finger width")
        self.assertEqual(P(family="res").description, "Width")
        self.assertEqual(P(name="area", label="Area (um^2)", family="diode").unit, "µm²")
        self.assertEqual(P(name="val", label="Value (ohms)", family="res").unit, "Ω")


class ShippedManifest(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(MAN.devices), 60)
        self.assertEqual(len(MAN.editable_names()), 49)
        fams = {}
        for d in MAN.devices:
            fams[d.family] = fams.get(d.family, 0) + 1
        self.assertEqual(fams, {"res": 22, "mos": 12, "fixed": 12, "diode": 8, "varactor": 3,
                                "mim_cap": 2, "photodiode": 1})
        self.assertEqual(len(MAN.data["excluded"]), 20)

    def test_exclusions_say_which_helpers_magic_offers_in_its_menu(self):
        menu = {"mcon", "via1", "via2", "via3", "via4", "subconn", "mvsubconn", "subconn_guard",
                "mvsubconn_guard", "nwell", "mvnwell", "deep_nwell", "mvdeep_nwell"}
        ex = {e["name"]: e for e in MAN.data["excluded"]}
        self.assertEqual({n for n, e in ex.items() if e["menu"]}, menu)
        for n, e in ex.items():
            if n in menu:
                self.assertTrue(e["menu"].startswith("Devices 1 / "), n)
                self.assertIn("paints into the current box", e["reason"])
            else:
                self.assertIn("menus don't offer it", e["reason"])

    def test_grid_of_the_default_output(self):
        grids = {d.name: d.raw["defaults_run"]["grid_nm"] for d in MAN.devices}
        fine = sorted(n for n, g in grids.items() if g % 5)
        self.assertEqual(fine, ["sky130_fd_pr__pnp_05v5_W0p68L0p68", "sky130_fd_pr__rf_test_coil1",
                                "sky130_fd_pr__rf_test_coil2", "sky130_fd_pr__rf_test_coil3"])

    def test_types(self):
        for d in MAN.devices:
            for p in d.params:
                self.assertIn(p.type, ("float", "int", "bool01", "signed"), (d.name, p.name))
                p.default_value()  # parses
            self.assertEqual(d.form, "wrapper" if d.nocell else "cell")

    def test_every_signed_default_passes_the_check(self):
        n = 0
        for d in MAN.devices:
            for p in d.params:
                if p.type == "signed":
                    p.check(p.default)
                    n += 1
        self.assertGreater(n, 50)

    def test_request_of_defaults_is_magic_defaults(self):
        for d in MAN.devices:
            req = d.build_request(d.defaults_values())
            magic = dict(d.defaults)
            for k, v in req.items():
                self.assertEqual(v, magic[k], (d.name, k))

    def test_parse_request_round_trip(self):
        d = MAN["sky130_fd_pr__nfet_01v8"]
        vals = d.parse_request({"w": "1.5", "nf": "3", "guard": "0", "viasrc": "+50"})
        self.assertEqual(vals, {"w": 1.5, "nf": 3, "guard": False, "viasrc": "+50"})
        req = d.build_request(dict(d.defaults_values(), **vals))
        self.assertEqual((req["w"], req["nf"], req["guard"], req["viasrc"]), ("1.5", "3", "0", "+50"))

    def test_defaults_digest_recomputes(self):
        from klayout_magic_pcells.backend import defaults_digest
        self.assertEqual(defaults_digest(MAN.defaults_by_device()), MAN.defaults_digest)

    @needs_klayout
    def test_no_name_collides_with_the_helper(self):
        from klayout_magic_pcells.pcell import check_names
        for d in MAN.devices:
            check_names(d)

    @needs_klayout
    def test_collision_is_refused(self):
        from klayout_magic_pcells.manifest import DeviceSpec
        from klayout_magic_pcells.pcell import PCellNameError, check_names
        spec = DeviceSpec({"name": "x", "family": "mos", "nocell": False, "defaults": [["layout", "1"]],
                           "params": [{"name": "layout", "type": "float", "default": "1",
                                       "editable": True}]})
        with self.assertRaises(PCellNameError):
            check_names(spec)


if __name__ == "__main__":
    unittest.main()
