"""The ``centroid`` KLayout library: ``CC_ARRAY``, a common-centroid array
of unit cells from a ``*_magic`` library (klayout-magic-pcells).

The pattern comes from pattern.py (common centroid checked exactly before
anything is drawn), the placement from placer.py. The form shows the
letter grid and a one-line report; values that can't be drawn put an
error icon on the parameter to blame and draw a 1 x 1 um box with a
``CC_ERROR`` text on 255/0, like HW_FET.
"""

import functools
import logging

import klayout.db as db

from . import rules as rules_mod
from .metrics import evaluate, summary_line
from .pattern import STYLES, PatternError, build, parse_devices
from .placer import place

log = logging.getLogger("klayout_centroid")

LIBRARY_NAME = "centroid"
PCELL_NAME = "CC_ARRAY"
ERROR_LAYER = (255, 0)
DUMMY_CHOICES = (("full ring of dummy units", "ring"), ("dummy columns left and right", "edge"),
                 ("none (only the grid's own . cells)", "none"))
EDITABLE = ("unit", "unit_params", "devices", "style", "rows", "cols", "override", "dummies",
            "gap_x", "gap_y", "seed", "labels", "route", "source", "dummy_tie")
ROUTE_CHOICES = (("no routing (place only)", "none"),
                 ("met2 row tracks + met3 trunks (MOS units)", "tracks"))
SOURCE_CHOICES = (("common source (pin S)", "common"), ("a source per device (pins <dev>_S)", "separate"))
TIE_CHOICES = (("dummies off, tied to the source", "S"), ("dummies off, on their own pin DUM", "DUM"))


FAMILY_ORDER = ("mos", "mim_cap", "varactor", "res", "diode", "fixed", "photodiode")
FAMILY_LABEL = {"mos": "MOS", "mim_cap": "MIM cap", "varactor": "varactor", "res": "resistor", "diode": "diode",
                "fixed": "fixed cell", "photodiode": "photodiode"}
# the parameters offered in the unit-parameter field when a unit is picked
SIZE_PARAMS = ("w", "l", "nf", "nx", "ny", "guard")
DEFAULT_UNIT = "sky130_magic/sky130_fd_pr__nfet_01v8"
DEFAULT_UNIT_PARAMS = "w=1 l=0.5 nf=2 guard=1"
LAST_UNIT = "last_unit"

# value -> (label, suggested unit parameters); filled by unit_catalog()
_catalog = {}


def _manifest(pdk):
    import json
    import os
    try:
        import klayout_magic_pcells
        path = os.path.join(os.path.dirname(klayout_magic_pcells.__file__), "data", "manifest-%s.json" % pdk)
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def unit_catalog(libs=None):
    """[(label, value)] for the unit dropdown: the devices (not the
    box-paint generators) of the ``*_magic`` libraries that are registered,
    or of every PDK with a manifest if none is. value = "<library>/<pcell>"."""
    if libs is None:
        libs = [lib for lib in rules_mod.LIBRARY_PDK if db.Library.library_by_name(lib) is not None]
        if not libs:
            libs = list(rules_mod.LIBRARY_PDK)
    rows = []
    for lib in libs:
        man = _manifest(rules_mod.LIBRARY_PDK[lib])
        if not man:
            continue
        for d in man.get("devices", []):
            name, fam = d["name"], d.get("family", "")
            short = name.split("__", 1)[1] if "__" in name else name
            label = "%s: %s" % (FAMILY_LABEL.get(fam, fam or "device"), short)
            if len(libs) > 1:
                label = "%s %s" % (rules_mod.LIBRARY_PDK[lib], label)
            defaults = dict((k, v) for k, v in (d.get("defaults") or []))
            if fam == "mos" and "w" in defaults and "l" in defaults:
                # Magic's minimum-size defaults break m1.6 (met1 area) on their own
                # and match poorly: offer a matching-sized unit instead
                defaults["w"] = max(float(defaults["w"]), 1.0)
                defaults["l"] = max(float(defaults["l"]), 0.5)
                if "nf" in defaults:
                    defaults["nf"] = max(int(float(defaults["nf"])), 2)
            sugg = " ".join("%s=%s" % (k, _num(defaults[k])) for k in SIZE_PARAMS if k in defaults)
            value = "%s/%s" % (lib, name)
            fo = FAMILY_ORDER.index(fam) if fam in FAMILY_ORDER else len(FAMILY_ORDER)
            rows.append(((libs.index(lib), fo, short), label, value, sugg))
    rows.sort()
    _catalog.clear()
    for _, label, value, sugg in rows:
        _catalog[value] = (label, sugg)
    if DEFAULT_UNIT in _catalog:
        _catalog[DEFAULT_UNIT] = (_catalog[DEFAULT_UNIT][0], DEFAULT_UNIT_PARAMS)
    return [(label, value) for _, label, value, _ in rows]


def _num(v):
    try:
        f = float(v)
        return ("%g" % f) if f != int(f) or "." in str(v) else str(int(f))
    except (TypeError, ValueError):
        return str(v)


def suggested_params(value):
    """The unit-parameter text offered when ``value`` is picked."""
    if not _catalog:
        unit_catalog()
    return _catalog.get(value, ("", ""))[1]


def _fits(value, text):
    """True if every name in ``text`` is a parameter of the unit ``value``
    (True too when the unit's library isn't registered: nothing to check)."""
    lib_name, name = split_unit(value)
    lib = db.Library.library_by_name(lib_name)
    decl = lib.layout().pcell_declaration(name) if lib is not None else None
    if decl is None:
        return True
    try:
        parse_unit_params(text, decl)
        return True
    except PatternError:
        return False


def params_for_new_unit(unit, last, text):
    """The unit-parameter text after the unit changed from ``last`` to
    ``unit``: the new unit's suggestion when ``text`` is still the old
    unit's suggestion (or empty, or doesn't fit the new unit); else
    ``text`` as typed."""
    sugg = suggested_params(unit)
    if not sugg:
        return text
    old = suggested_params(last)
    if not text.strip() or " ".join(text.split()) == " ".join(old.split()) or not _fits(unit, text):
        return sugg
    return text


def split_unit(value):
    """(library, pcell) of a dropdown value. A bare PCell name is looked up
    in the registered *_magic libraries."""
    value = (value or "").strip()
    if "/" in value:
        lib, name = value.split("/", 1)
        return lib, name
    for lib in rules_mod.LIBRARY_PDK:
        L = db.Library.library_by_name(lib)
        if L is not None and L.layout().pcell_declaration(value) is not None:
            return lib, value
    return "sky130_magic", value


def _msg(level, text):
    try:
        from klayout_magic_pcells import _kl
        getattr(_kl, level)(text)
    except Exception:
        getattr(log, "warning" if level == "warn" else level)(text)


def parse_unit_params(text, decl):
    """{name: value} from "w=1 l=0.5 nf=2", typed after the unit PCell's
    declaration ``decl``."""
    types = {p.name: p.type for p in decl.get_parameters()} if decl else {}
    out = {}
    for tok in (text or "").replace(",", " ").split():
        if "=" not in tok:
            raise PatternError("unit parameter %r is not name=value" % tok, "unit_params")
        k, v = tok.split("=", 1)
        k = k.strip()
        if decl and k not in types:
            raise PatternError("the unit cell has no parameter %r" % k, "unit_params")
        t = types.get(k)
        try:
            if t == db.PCellParameterDeclaration.TypeInt:
                out[k] = int(float(v))
            elif t == db.PCellParameterDeclaration.TypeDouble:
                out[k] = float(v)
            elif t == db.PCellParameterDeclaration.TypeBoolean:
                out[k] = v.lower() in ("1", "true", "yes", "on")
            else:
                out[k] = v
        except ValueError:
            raise PatternError("unit parameter %s=%s: not a number" % (k, v), "unit_params")
    return out


@functools.lru_cache(maxsize=256)
def _pattern(devices, rows, cols, style, override, seed, aspect):
    return build(devices, rows, cols, style, aspect=aspect, seed=seed, override=override or None)


def pattern_of(v, aspect=1.0):
    devs = tuple(parse_devices(v["devices"]))
    if v["rows"] < 0 or v["cols"] < 0:
        raise PatternError("rows and cols: 0 (auto) or more", "rows")
    return _pattern(devs, int(v["rows"]), int(v["cols"]), v["style"], (v["override"] or "").strip(),
                    int(v["seed"]), round(aspect, 3))


class CCArrayPCell(db.PCellDeclarationHelper):
    """Common-centroid array of unit cells, with dummies."""

    def __init__(self):
        super().__init__()
        choices = unit_catalog()
        if DEFAULT_UNIT not in [v for _, v in choices]:
            choices = [("nfet_01v8 (sky130_magic)", DEFAULT_UNIT)] + choices
        self.param("unit", self.TypeString, "Unit cell", default=DEFAULT_UNIT, choices=choices)
        self.param("unit_params", self.TypeString, "Unit parameters (name=value ...; filled in when a unit is picked)",
                   default=DEFAULT_UNIT_PARAMS)
        self.param("devices", self.TypeString, "Devices (A:4,B:4 or a ratio 1:2:4:8)", default="A:4,B:4")
        self.param("style", self.TypeString, "Pattern style", default="optimized",
                   choices=[(s, s) for s in STYLES])
        self.param("rows", self.TypeInt, "Rows (0 = auto)", default=0)
        self.param("cols", self.TypeInt, "Columns (0 = auto)", default=0)
        self.param("override", self.TypeString, "Pattern override (ABBA/BAAB; . = dummy)", default="")
        self.param("dummies", self.TypeString, "Dummies", default="ring",
                   choices=[c for c in DUMMY_CHOICES])
        self.param("gap_x", self.TypeDouble, "Gap x between units (0 = DRC minimum)", default=0.0, unit="um")
        self.param("gap_y", self.TypeDouble, "Gap y between units (0 = DRC minimum)", default=0.0, unit="um")
        self.param("seed", self.TypeInt, "Seed (optimized style)", default=1)
        self.param("route", self.TypeString, "Routing", default="none", choices=list(ROUTE_CHOICES))
        self.param("source", self.TypeString, "Sources (routing)", default="common", choices=list(SOURCE_CHOICES))
        self.param("dummy_tie", self.TypeString, "Dummies (routing)", default="S", choices=list(TIE_CHOICES))
        self.param("labels", self.TypeBoolean, "Label each unit with its device (text only, on a layer "
                   "no extraction reads)", default=True)
        self.param(LAST_UNIT, self.TypeString, "Unit the parameters were filled in for", default=DEFAULT_UNIT,
                   hidden=True)
        self.param("grid", self.TypeString, "Pattern", default="", readonly=True)
        self.param("info", self.TypeString, "Report", default="", readonly=True)

    def _values(self, states=None):
        if states is not None:
            return {n: states.parameter(n).value for n in EDITABLE}
        return {n: getattr(self, n) for n in EDITABLE}

    def display_text_impl(self):
        return "CC_ARRAY(%s %s %s)" % (self.devices, self.style, split_unit(self.unit)[1])

    def coerce_parameters_impl(self):
        # A new unit picked in the form: offer its parameters. (KLayout's form
        # ignores values set in callback_impl, so this happens here.)
        unit, last = self.unit, getattr(self, LAST_UNIT)
        if unit != last:
            self.unit_params = params_for_new_unit(unit, last, self.unit_params)
            setattr(self, LAST_UNIT, unit)
        try:
            p = pattern_of(self._values())
            self.grid = " / ".join(p.grid)
            self.info = summary_line(evaluate(p))
        except PatternError as e:
            self.grid = ""
            self.info = "not drawn: %s" % e
        except Exception as e:
            self.grid = ""
            self.info = "not drawn: %s" % e

    def callback_impl(self, name):
        states = getattr(self, "_param_states", None)
        if states is None:
            return
        for n in EDITABLE:
            st = states.parameter(n)
            st.icon = db.PCellParameterState.NoIcon
            st.tooltip = ""
        try:
            pattern_of(self._values(states))
        except PatternError as e:
            st = states.parameter(e.param if e.param in EDITABLE else "devices")
            st.icon = db.PCellParameterState.ErrorIcon
            st.tooltip = str(e)

    def _unit_cell(self):
        return unit_cell(self.layout, self.unit, self.unit_params)

    def produce_impl(self):
        try:
            draw(self.layout, self.cell, self._values())
        except Exception as e:
            _msg("error", "%s %s: not drawn: %s" % (LIBRARY_NAME, PCELL_NAME, e))
            try:
                self.cell.clear_insts()
                self.cell.clear_shapes()
            except Exception:
                pass
            li = self.layout.layer(*ERROR_LAYER)
            self.cell.shapes(li).insert(db.DBox(-0.5, -0.5, 0.5, 0.5))
            self.cell.shapes(li).insert(db.DText("CC_ERROR %s: %s" % (PCELL_NAME, " ".join(str(e).split())[:400]),
                                                 db.DTrans()))


def unit_cell(layout, unit_value, unit_params):
    """(unit cell variant in ``layout``, library name)."""
    lib_name, name = split_unit(unit_value)
    lib = db.Library.library_by_name(lib_name)
    if lib is None:
        raise PatternError("library %s is not registered (is klayout-magic-pcells installed, "
                           "and its PDK in KMP_PDKS?)" % lib_name, "unit")
    decl = lib.layout().pcell_declaration(name)
    if decl is None:
        raise PatternError("library %s has no PCell %s" % (lib_name, name), "unit")
    params = parse_unit_params(unit_params, decl)
    cell = layout.create_cell(name, lib_name, params)
    if cell is None:
        raise PatternError("could not create %s %s" % (lib_name, name), "unit")
    return cell, lib_name


def draw(layout, cell, v):
    """Place (and route) a CC_ARRAY into ``cell`` from the parameter values
    ``v`` (the EDITABLE names). Returns {"pattern", "placement", "route",
    "unit", "unit_params"}; raises on values that can't be drawn."""
    unit, lib_name = unit_cell(layout, v["unit"], v["unit_params"])
    bb = unit.dbbox()
    aspect = (bb.width() / bb.height()) if bb.height() > 0 else 1.0
    p = pattern_of(v, aspect)
    rules = rules_mod.for_library(lib_name)
    info = place(layout, cell, unit, p.grid, v["gap_x"], v["gap_y"], v["dummies"], rules, labels=v["labels"])
    rinfo = None
    if v.get("route", "none") != "none":
        from .router import route
        rinfo = route(layout, cell, unit, info["units"], rules, v.get("source", "common"), v.get("dummy_tie", "S"))
    return {"pattern": p, "placement": info, "route": rinfo, "unit": unit, "lib": lib_name}


class CentroidLibrary(db.Library):
    def __init__(self):
        super().__init__()
        self.description = "Common-centroid matched arrays of klayout-magic-pcells unit cells"
        self.layout().dbu = 0.001
        self.layout().register_pcell(PCELL_NAME, CCArrayPCell())
        self.register(LIBRARY_NAME)


_library = None


def register():
    """Register the ``centroid`` library (idempotent). The unit-cell
    libraries are looked up when an array is drawn, so the order of
    registration doesn't matter."""
    global _library
    if _library is not None and db.Library.library_by_name(LIBRARY_NAME) is not None:
        return _library
    try:
        _library = CentroidLibrary()
    except Exception as e:
        _msg("error", "klayout_centroid: %s not registered: %s" % (LIBRARY_NAME, e))
        return None
    return _library
