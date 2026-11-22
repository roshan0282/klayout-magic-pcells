import os
import tempfile
import unittest

from tests.unit._util import REPO  # noqa: F401
from klayout_magic_pcells.config import Config, ConfigError, SHIPPED_MANIFEST


def write_ini(text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "config.ini")
    with open(p, "w") as f:
        f.write(text)
    return p


class ConfigPrecedence(unittest.TestCase):
    def test_defaults(self):
        c = Config.load(env={"PATH": "/nonexistent", "HOME": "/home/x"}, config_path="/nonexistent.ini")
        self.assertEqual(c.magic, "/foss/tools/bin/magic")
        self.assertEqual(c.pdk_root, "/foss/pdks")
        self.assertEqual(c.pdk, "sky130A")
        self.assertEqual(c.magicrc, "/foss/pdks/sky130A/libs.tech/magic/sky130A.magicrc")
        self.assertEqual(c.cache_dir, "/home/x/.cache/klayout-magic-pcells")
        self.assertTrue(c.cache_enabled)
        self.assertEqual(c.backend, "server")
        self.assertEqual(c.timeout, 30.0)
        self.assertFalse(c.lazy)
        self.assertEqual(c.manifest, SHIPPED_MANIFEST)
        self.assertIsNone(c.log)

    def test_env_beats_ini_beats_default(self):
        ini = write_ini("[kmp]\nmagic = /ini/magic\npdk_root = /ini/pdks\ntimeout = 7\n")
        c = Config.load(env={"KMP_MAGIC": "/env/magic", "HOME": "/h"}, config_path=ini)
        self.assertEqual(c.magic, "/env/magic")
        self.assertEqual(c.sources["magic"], "env KMP_MAGIC")
        self.assertEqual(c.pdk_root, "/ini/pdks")
        self.assertIn("[kmp] pdk_root", c.sources["pdk_root"])
        self.assertEqual(c.timeout, 7.0)
        self.assertEqual(c.magicrc, "/ini/pdks/sky130A/libs.tech/magic/sky130A.magicrc")

    def test_xdg_dirs(self):
        c = Config.load(env={"XDG_CACHE_HOME": "/xc", "HOME": "/h"}, config_path="/nope")
        self.assertEqual(c.cache_dir, "/xc/klayout-magic-pcells")
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "klayout-magic-pcells"))
        with open(os.path.join(d, "klayout-magic-pcells", "config.ini"), "w") as f:
            f.write("[kmp]\ncache = 0\n")
        c = Config.load(env={"XDG_CONFIG_HOME": d, "HOME": "/h"})
        self.assertFalse(c.cache_enabled)

    def test_pdk_variable_is_ignored(self):
        c = Config.load(env={"PDK": "ihp-sg13g2", "HOME": "/h"}, config_path="/nope")
        self.assertEqual(c.pdk, "sky130A")

    def test_unsupported_pdk(self):
        with self.assertRaises(ConfigError):
            Config.load(env={"KMP_PDK": "gf180mcuC", "HOME": "/h"}, config_path="/nope")

    def test_pdk_selection(self):
        d = tempfile.mkdtemp()
        for p in ("sky130A", "ihp-sg13g2"):
            os.makedirs(os.path.join(d, p, "libs.tech", "magic"))
            open(os.path.join(d, p, "libs.tech", "magic", p + ".magicrc"), "w").close()
        env = {"HOME": "/h", "PDK_ROOT": d}
        # auto: the supported PDKs installed under PDK_ROOT
        c = Config.load(env=env, config_path="/nope")
        self.assertEqual(c.pdks, ["sky130A", "ihp-sg13g2"])
        self.assertEqual(c.pdk, "sky130A")
        # KMP_PDK alone selects one PDK, as in version 0.2
        c = Config.load(env=dict(env, KMP_PDK="ihp-sg13g2"), config_path="/nope")
        self.assertEqual(c.pdks, ["ihp-sg13g2"])
        self.assertEqual(c.library_name, "sg13g2_magic")
        self.assertEqual(c.magicrc, os.path.join(d, "ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc"))
        self.assertTrue(c.manifest.endswith("manifest-ihp-sg13g2.json"))
        # an explicit list keeps a missing or unknown PDK, to fail for that PDK alone
        c = Config.load(env=dict(env, KMP_PDKS="gf180mcuD, sky130A gf180mcuC"), config_path="/nope")
        self.assertEqual(c.pdks, ["gf180mcuD", "sky130A"])
        self.assertIn("gf180mcuC", c.pdk_errors)
        g = c.for_pdk("gf180mcuD")
        self.assertTrue(g.problems())
        self.assertIn("KMP_MAGICRC_GF180MCUD", " ".join(g.problems()))
        self.assertEqual(c.pdk, "sky130A")

    def test_per_pdk_settings(self):
        ini = write_ini("[kmp]\npdks = sky130A, ihp-sg13g2\n[kmp:ihp-sg13g2]\nmagicrc = /ini/ihp.rc\n")
        c = Config.load(env={"HOME": "/h", "KMP_MANIFEST_SKY130A": "/env/m.json",
                             "KMP_MAGICRC": "/env/generic.rc"}, config_path=ini)
        self.assertEqual(c.pdks, ["sky130A", "ihp-sg13g2"])
        self.assertEqual(c.manifest, "/env/m.json")
        self.assertEqual(c.magicrc, "/env/generic.rc")       # unqualified: KMP_PDK's PDK only
        i = c.for_pdk("ihp-sg13g2")
        self.assertEqual(i.magicrc, "/ini/ihp.rc")
        self.assertIn("[kmp:ihp-sg13g2]", i.sources["magicrc"])
        self.assertTrue(i.manifest.endswith("manifest-ihp-sg13g2.json"))

    def test_bad_values(self):
        for env in ({"KMP_TIMEOUT": "soon"}, {"KMP_TIMEOUT": "-1"}, {"KMP_CACHE": "maybe"},
                    {"KMP_BACKEND": "remote"}):
            env["HOME"] = "/h"
            with self.assertRaises(ConfigError, msg=str(env)):
                Config.load(env=env, config_path="/nope")

    def test_lazy_follows_backend(self):
        c = Config.load(env={"KMP_BACKEND": "oneshot", "HOME": "/h"}, config_path="/nope")
        self.assertTrue(c.lazy)
        c = Config.load(env={"KMP_BACKEND": "oneshot", "KMP_LAZY": "0", "HOME": "/h"}, config_path="/nope")
        self.assertFalse(c.lazy)

    def test_problems_name_the_variable(self):
        c = Config.load(env={"KMP_MAGIC": "/no/magic", "PDK_ROOT": "/no/pdks", "HOME": "/h"},
                        config_path="/nope")
        text = " ".join(c.problems())
        self.assertIn("KMP_MAGIC", text)
        self.assertIn("PDK_ROOT", text)


if __name__ == "__main__":
    unittest.main()
