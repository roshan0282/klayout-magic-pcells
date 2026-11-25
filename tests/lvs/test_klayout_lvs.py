"""The PDKs' own KLayout LVS decks on layouts built from this package's
PCells (roadmap Phase 0.4): verify.klayout_lvs on the PCell inverter of the
case suite (sky130A, gf180mcuD) and on the routed CC_ARRAY diff pair,
separate-source pair and pfet mirror (sky130A), each with a negative control.

    python3 -m unittest discover -s tests/lvs -t .

See docs/klayout-lvs.md for the deck settings these tests pin down.
"""

import importlib
import os
import shutil
import sys
import tempfile
import unittest

from tests.power._util import HAVE_KLAYOUT, PY  # noqa: F401  (sets KMP_PDKS and a temp cache)

if PY not in sys.path:
    sys.path.insert(0, PY)

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")


def _have(pdk, *deck):
    return HAVE_KLAYOUT and shutil.which("magic") is not None and os.path.isfile(
        os.path.join(PDK_ROOT, pdk, "libs.tech", "klayout", *deck))


HAVE_SKY = _have("sky130A", "lvs", "sky130.lvs")
HAVE_GF = _have("gf180mcuD", "tech", "lvs", "gf180mcu.lvs")
CASE_MODULE = {"sky130A": "tests.cases.pdk_sky130a", "gf180mcuD": "tests.cases.pdk_gf180mcud"}


class _Work(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix="kl_lvs_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def path(self, *parts):
        p = os.path.join(self.work, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def dir(self, *parts):
        p = os.path.join(self.work, *parts)
        os.makedirs(p, exist_ok=True)
        return p

    def write(self, name, text):
        p = self.path(name)
        with open(p, "w") as f:
            f.write(text)
        return p


class _Inverter(_Work):
    PDK = None

    def build(self):
        import klayout.db as db
        import klayout_magic_pcells as kmp
        self.assertIsNotNone(kmp.register(self.PDK))
        mod = importlib.import_module(CASE_MODULE[self.PDK])
        ly = db.Layout()
        ly.dbu = 0.001
        mod.pcell_inverter(db, ly)
        gds = self.path(self.PDK, "inv_pcell.gds")
        ly.write(gds)
        return gds, mod

    def lvs(self, gds, text, name):
        from klayout_power_pcells import verify
        sch = self.write(os.path.join(self.PDK, name + ".spice"), text)
        return verify.klayout_lvs(gds, "inv_pcell", sch, self.dir(self.PDK, name), pdk=self.PDK)


@unittest.skipUnless(HAVE_SKY, "needs klayout, Magic and sky130A")
class TestSky130Inverter(_Inverter):
    PDK = "sky130A"

    def test_inverter(self):
        gds, mod = self.build()
        # The case suite's schematic, as xschem writes it: X elements, W and L in um without units.
        sch = mod.SCHEMATIC.format(top="inv_pcell", **mod.PCELL_SCH_W)
        ok, info = self.lvs(gds, sch, "good")
        self.assertTrue(ok, info["circuits"])
        bad = mod.SCHEMATIC.format(top="inv_pcell", wn=mod.PCELL_SCH_W["wn"], wp=2 * mod.PCELL_SCH_W["wp"])
        self.assertFalse(self.lvs(gds, bad, "wide_p")[0])


@unittest.skipUnless(HAVE_GF, "needs klayout, Magic and gf180mcuD")
class TestGf180Inverter(_Inverter):
    PDK = "gf180mcuD"

    def test_inverter(self):
        gds, mod = self.build()
        sch = mod.SCHEMATIC.format(top="inv_pcell", **mod.PCELL_SCH_W)
        # xschem's gf180mcu lvs_format writes M elements; the deck has no X-to-device conversion.
        m = "\n".join(line[1:] if line.startswith("XM") else line for line in sch.splitlines()) + "\n"
        ok, info = self.lvs(gds, m, "good")
        self.assertTrue(ok, info["circuits"])
        self.assertFalse(self.lvs(gds, sch, "x_elements")[0])


@unittest.skipUnless(HAVE_SKY, "needs klayout, Magic and sky130A")
class TestSky130RoutedArrays(_Work):
    # The cases of tests/centroid/test_router.py, which netgen matches too.
    CASES = {
        "cc_dp": {"devices": "A:4,B:4", "rows": 2, "cols": 4, "unit_params": "w=1.3 l=0.5 nf=2 guard=0",
                  "route": "tracks"},
        "cc_sep": {"devices": "A:4,B:4", "rows": 2, "cols": 4, "unit_params": "w=2.1 l=0.5 nf=2 guard=0",
                   "route": "tracks", "source": "separate", "dummy_tie": "DUM"},
        "cc_mirror_pf": {"unit": "sky130_magic/sky130_fd_pr__pfet_01v8", "devices": "A:2,B:6",
                         "style": "symmetric", "unit_params": "w=1.3 l=1 nf=2 guard=0", "route": "tracks"},
    }

    def test_routed_arrays(self):
        import klayout.db as db
        import klayout_magic_pcells as kmp
        import klayout_centroid as kc
        from klayout_centroid import pcell, router
        from klayout_power_pcells import verify
        kmp.register("sky130A")
        kc.register()
        for name, params in self.CASES.items():
            with self.subTest(name):
                v = {p.name: p.default for p in pcell.CCArrayPCell().get_parameters()}
                v.update(params)
                ly = db.Layout()
                ly.dbu = 0.001
                top = ly.create_cell(name)
                info = pcell.draw(ly, top, v)
                gds = self.path(name, name + ".gds")
                ly.write(gds)
                up = dict(t.split("=") for t in v["unit_params"].split())
                ref = router.reference_spice(name, info["route"], pcell.split_unit(v["unit"])[1],
                                             float(up["w"]), float(up["l"]), int(up["nf"]))
                # Tapless units: the bulks are Magic's substrate net VSUBS, which is not a pin.
                ok, res = verify.klayout_lvs(gds, name, self.write(os.path.join(name, "ref.spice"), ref),
                                             self.dir(name, "good"), substrate="VSUBS")
                self.assertTrue(ok, res["circuits"])
                if name == "cc_dp":
                    # Swap the gates of one A unit: A and B no longer match.
                    lines = ref.splitlines()
                    i = next(k for k, s in enumerate(lines) if " A_D A_G S " in s)
                    lines[i] = lines[i].replace(" A_D A_G S ", " A_D B_G S ")
                    bad = self.write(os.path.join(name, "bad.spice"), "\n".join(lines) + "\n")
                    self.assertFalse(verify.klayout_lvs(gds, name, bad, self.dir(name, "bad"),
                                                        substrate="VSUBS")[0])


if __name__ == "__main__":
    unittest.main()
