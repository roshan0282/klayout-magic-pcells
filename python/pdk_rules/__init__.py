"""One rule table per PDK for this package's generators and checks.

KLayout-free: plain data plus a few accessors. Every generator
(klayout_power_pcells, klayout_gen, klayout_centroid) and live_verify's
tier-0 check read their numbers from here; ``mapped.glayout`` exports a table
in gLayout's MappedPDK schema; ``probe`` checks the values against the PDK's
own DRC deck (tests/rules).

    import pdk_rules
    t = pdk_rules.get("sky130A")
    t.um("met1_s")              # 0.14
    t.rule("met1_s").rule       # "m1.2"
    t.layer("met1")             # (68, 20)
"""

from importlib import import_module

from ._rule import KINDS, SOURCES, R, Rule  # noqa: F401

__version__ = "1.0"
NAMES = ("sky130A", "gf180mcuD")


class Table:
    """A PDK's table: layers, rules (``Rule`` records) and device data."""

    def __init__(self, mod):
        self.mod = mod
        self.name = mod.NAME
        self.grid = mod.GRID
        self.layers = dict(mod.LAYERS)
        self.pin = dict(mod.PIN)
        self.label = dict(mod.LABEL)
        self.stack = list(mod.STACK)
        self.rules = dict(mod.RULES)
        self.devices = dict(mod.DEVICES)
        self.model_prefix = mod.MODEL_PREFIX
        self.allows_45_fet = mod.ALLOWS_45_FET
        self.allows_45_metal = mod.ALLOWS_45_METAL
        self.drc_deck = mod.DRC_DECK
        self.em_ma_per_cut = dict(mod.EM_MA_PER_CUT)

    def rule(self, key):
        return self.rules[key]

    def um(self, key):
        return self.rules[key].value

    def nm(self, key):
        return self.rules[key].nm

    def layer(self, name):
        return self.layers[name]

    def layer_name(self, ld):
        """The table's name of a (layer, datatype), or None."""
        return next((n for n, v in self.layers.items() if v == tuple(ld)), None)

    def width_space(self, layer):
        """(min width, min space) in um of a layer, from its ``<layer>_w`` /
        ``<layer>_s`` rules, or the cut size for a cut layer."""
        w = self.rules.get(layer + "_w") or self.rules.get(layer)
        s = self.rules.get(layer + "_s")
        return (w.value if w else None, s.value if s else None)

    def probed(self):
        """{key: Rule} of the rules a probe can check."""
        return {k: r for k, r in self.rules.items() if r.kind}

    def __repr__(self):
        return "<pdk_rules.Table %s: %d layers, %d rules>" % (self.name, len(self.layers), len(self.rules))


_CACHE = {}


def get(pdk):
    """The Table of a PDK; KeyError if there is none."""
    if pdk not in NAMES:
        raise KeyError("no rule table for PDK %r (have: %s)" % (pdk, ", ".join(NAMES)))
    if pdk not in _CACHE:
        _CACHE[pdk] = Table(import_module("." + pdk, __name__))
    return _CACHE[pdk]


def tables():
    return {n: get(n) for n in NAMES}
