"""Configuration: environment variables, then config.ini, then defaults.

``config.ini`` lives at ``$XDG_CONFIG_HOME/klayout-magic-pcells/config.ini``
(else ``~/.config/klayout-magic-pcells/config.ini``). Its keys sit in a
``[kmp]`` section, in lower case and without the ``KMP_`` prefix, for
example ``magic = /opt/magic/bin/magic`` or ``pdk_root = /foss/pdks``.

The plugin reads ``KMP_PDK`` and ignores ``PDK``: the iic-osic-tools image
sets ``PDK=ihp-sg13g2`` by default.
"""

import configparser
import os
import shutil

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
SHIPPED_MANIFEST = os.path.join(PACKAGE_DIR, "data", "manifest-sky130A.json")
TCL_DIR = os.path.join(PACKAGE_DIR, "tcl")
SUPPORTED_PDKS = ("sky130A",)

# (environment variable, ini key)
_KEYS = [
    ("KMP_MAGIC", "magic"),
    ("PDK_ROOT", "pdk_root"),
    ("KMP_PDK", "pdk"),
    ("KMP_MAGICRC", "magicrc"),
    ("KMP_CACHE_DIR", "cache_dir"),
    ("KMP_CACHE", "cache"),
    ("KMP_BACKEND", "backend"),
    ("KMP_TIMEOUT", "timeout"),
    ("KMP_LAZY", "lazy"),
    ("KMP_MANIFEST", "manifest"),
    ("KMP_LOG", "log"),
]


class ConfigError(Exception):
    pass


def _truthy(text, name):
    t = str(text).strip().lower()
    if t in ("1", "true", "yes", "on"):
        return True
    if t in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError("%s must be 0 or 1, not %r" % (name, text))


def _home(env):
    return env.get("HOME") or os.path.expanduser("~")


def config_file_path(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or os.path.join(_home(env), ".config")
    return os.path.join(base, "klayout-magic-pcells", "config.ini")


def default_cache_dir(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CACHE_HOME") or os.path.join(_home(env), ".cache")
    return os.path.join(base, "klayout-magic-pcells")


class Config:
    """Resolved settings. ``sources[name]`` says where each value came from."""

    def __init__(self):
        self.magic = None
        self.pdk_root = None
        self.pdk = None
        self.magicrc = None
        self.cache_dir = None
        self.cache_enabled = True
        self.backend = "server"
        self.timeout = 30.0
        self.lazy = False
        self.manifest = SHIPPED_MANIFEST
        self.log = None
        self.config_file = None
        self.sources = {}

    @classmethod
    def load(cls, env=None, config_path=None):
        env = dict(os.environ) if env is None else dict(env)
        cfg = cls()
        path = config_path or config_file_path(env)
        ini = {}
        if os.path.isfile(path):
            cp = configparser.ConfigParser()
            try:
                cp.read(path, encoding="utf-8")
            except configparser.Error as e:
                raise ConfigError("cannot read %s: %s" % (path, e))
            if cp.has_section("kmp"):
                ini = {k.lower(): v for k, v in cp.items("kmp")}
            cfg.config_file = path

        def get(var, key):
            if env.get(var, "") != "":
                return env[var], "env %s" % var
            if key in ini and ini[key] != "":
                return ini[key], "%s [kmp] %s" % (path, key)
            return None, None

        raw = {}
        for var, key in _KEYS:
            raw[key] = get(var, key)

        def setv(name, value, source):
            setattr(cfg, name, value)
            cfg.sources[name] = source

        v, s = raw["magic"]
        if v is None:
            v = shutil.which("magic", path=env.get("PATH")) or "/foss/tools/bin/magic"
            s = "default (PATH, then /foss/tools/bin/magic)"
        setv("magic", os.path.expanduser(v), s)

        v, s = raw["pdk_root"]
        setv("pdk_root", os.path.expanduser(v) if v else "/foss/pdks", s or "default")

        v, s = raw["pdk"]
        setv("pdk", v or "sky130A", s or "default")
        if cfg.pdk not in SUPPORTED_PDKS:
            raise ConfigError("KMP_PDK=%s is not supported; this version supports %s"
                              % (cfg.pdk, ", ".join(SUPPORTED_PDKS)))

        v, s = raw["magicrc"]
        if v is None:
            v = os.path.join(cfg.pdk_root, cfg.pdk, "libs.tech", "magic", cfg.pdk + ".magicrc")
            s = "default ($PDK_ROOT/$KMP_PDK/libs.tech/magic/$KMP_PDK.magicrc)"
        setv("magicrc", os.path.expanduser(v), s)

        v, s = raw["cache_dir"]
        setv("cache_dir", os.path.expanduser(v) if v else default_cache_dir(env),
             s or "default ($XDG_CACHE_HOME or ~/.cache)/klayout-magic-pcells")

        v, s = raw["cache"]
        setv("cache_enabled", _truthy(v, "KMP_CACHE") if v is not None else True, s or "default")

        v, s = raw["backend"]
        v = (v or "server").strip().lower()
        if v not in ("server", "oneshot"):
            raise ConfigError("KMP_BACKEND must be 'server' or 'oneshot', not %r" % v)
        setv("backend", v, s or "default")

        v, s = raw["timeout"]
        try:
            t = float(v) if v is not None else 30.0
        except ValueError:
            raise ConfigError("KMP_TIMEOUT must be a number of seconds, not %r" % v)
        if t <= 0:
            raise ConfigError("KMP_TIMEOUT must be positive")
        setv("timeout", t, s or "default")

        v, s = raw["lazy"]
        if v is None:
            setv("lazy", cfg.backend == "oneshot", "default (1 with oneshot, 0 with server)")
        else:
            setv("lazy", _truthy(v, "KMP_LAZY"), s)

        v, s = raw["manifest"]
        setv("manifest", os.path.expanduser(v) if v else SHIPPED_MANIFEST, s or "default (shipped)")

        v, s = raw["log"]
        setv("log", os.path.expanduser(v) if v else None, s or "default (off)")
        return cfg

    @property
    def pdk_path(self):
        return os.path.join(self.pdk_root, self.pdk)

    def problems(self):
        """Missing pieces, as messages naming the variable to set."""
        out = []
        if not (os.path.isfile(self.magic) and os.access(self.magic, os.X_OK)):
            out.append("Magic executable not found at %s (set KMP_MAGIC, or put magic on PATH)"
                       % self.magic)
        if not os.path.isfile(self.magicrc):
            out.append("Magic rcfile not found at %s (set PDK_ROOT, or KMP_MAGICRC)" % self.magicrc)
        if not os.path.isfile(self.manifest):
            out.append("manifest not found at %s (check KMP_MANIFEST)" % self.manifest)
        return out

    def describe(self):
        rows = []
        for name in ("magic", "pdk_root", "pdk", "magicrc", "cache_dir", "cache_enabled",
                     "backend", "timeout", "lazy", "manifest", "log"):
            rows.append((name, getattr(self, name), self.sources.get(name, "")))
        return rows
