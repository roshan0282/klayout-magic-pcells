"""The ``sky130_power`` KLayout library: the HW FET as a PCell.

Behaviour, after klayout-magic-pcells' PCells:

* produce draws through ``backend.HWGenerator`` (memo, disk cache, then the
  generator), copies the flat GDS into the cell and stamps it (generated-by
  stamp, a GDS property on one shape). It never raises: refused values or a
  failed generation draw a 1 x 1 um box and an ``HW_ERROR HW_FET: <reason>``
  text on 255/0.
* coerce makes W, L and nf what Magic's dialog shows for the unit device
  (Magic's ``_check`` limits, e.g. ``Mos length must be >= 0.15 um``), as the
  device PCells of klayout-magic-pcells do, and fills the read-only fields
  that report the pitch, the number of fingers, the total W and the size.
* The form's icons: a warning on a value Magic's dialog changed, an error on
  the parameter that makes the generator refuse (with its reason), as tool
  tips.
* ``hw_created`` (hidden) is the created-with stamp. An instance reopened
  under another Magic, PDK or generator logs a warning once.
* With ``KMP_LAZY=1`` the form shows an Update button instead of drawing on
  every edit.
"""

import hashlib
import json

import klayout.db as db

from . import backend
from . import hybrid_waffle as hw

LIBRARY_NAME = "sky130_power"
PCELL_NAME = backend.CELL
ERROR_LAYER = (255, 0)
CREATED_PARAM = "hw_created"
INFO_PARAM = "info"
EDITABLE = ("device", "bulk", "l", "w", "nf", "nx", "ny", "strap_w", "pitch")


def _warn(msg):
    try:
        from klayout_magic_pcells._kl import warn
        warn(msg)
    except Exception:
        backend.log.warning(msg)


def _error(msg):
    try:
        from klayout_magic_pcells._kl import error
        error(msg)
    except Exception:
        backend.log.error(msg)


def draw_error(layout, cell, reason):
    li = layout.layer(*ERROR_LAYER)
    cell.shapes(li).insert(db.DBox(-0.5, -0.5, 0.5, 0.5))
    cell.shapes(li).insert(db.DText("HW_ERROR %s: %s" % (PCELL_NAME, " ".join(str(reason).split())[:400]),
                                    db.DTrans()))


def magic_corrections(values):
    """{name: (typed, shown)} for W, L and nf that Magic's dialog changes,
    and the dialog's message text."""
    import klayout_magic_pcells as kmp
    typed = {"w": values["w"], "l": values["l"], "nf": values["nf"], "guard": False}
    shown = kmp.dialog_values(values["device"], typed, pdk=backend.PDK)
    out = {}
    for k in ("w", "l", "nf"):
        sv = int(shown[k]) if k == "nf" else float(shown[k])
        if abs(float(sv) - float(values[k])) > 1e-9:
            out[k] = (values[k], sv)
    return out


def info_text(res):
    i = res.info
    return ("pitch %.3f um, %d fingers (%d cells x nf %d), total W %.2f um, strap %.3f um"
            % (i["pitch"], i["devices"], i["blocks"], i["nf"], i["total_w"], i["strap_w"]))


class HWFetPCell(db.PCellDeclarationHelper):
    """Hybrid-waffle power MOSFET (sky130A), drawn from Magic's devices."""

    def __init__(self):
        super().__init__()
        d = hw.HWParams()
        self.param("device", self.TypeString, "Device", default=d.device,
                   choices=[(n.replace("sky130_fd_pr__", ""), n) for n in sorted(hw.DEVICES)])
        self.param("bulk", self.TypeString, "Body", default=d.bulk,
                   choices=[("Tap ring around the array (pin B)", "ring"),
                            ("Tap in every source tile, tied to S", "source")])
        self.param("l", self.TypeDouble, "Gate length L", default=d.l, unit="um")
        self.param("w", self.TypeDouble, "Finger width W", default=d.w, unit="um")
        self.param("nf", self.TypeInt, "Fingers per cell", default=d.nf)
        self.param("nx", self.TypeInt, "Tiles per row (N)", default=d.nx)
        self.param("ny", self.TypeInt, "Tiles per column (M)", default=d.ny)
        self.param("strap_w", self.TypeDouble, "Diagonal strap width", default=d.strap_w, unit="um")
        self.param("pitch", self.TypeDouble, "Tile pitch (0 = minimum)", default=0.0, unit="um")
        self.param(INFO_PARAM, self.TypeString, "Result", default="", readonly=True)
        self.param(CREATED_PARAM, self.TypeString, "Created with", hidden=True, readonly=True,
                   default=backend.state.created_stamp)
        self._warned = set()

    # -- helpers ---------------------------------------------------------

    def _values(self, states=None):
        if states is not None:
            return {n: states.parameter(n).value for n in EDITABLE}
        return {n: getattr(self, n) for n in EDITABLE}

    @staticmethod
    def _params(v):
        return hw.HWParams(l=v["l"], w=v["w"], nf=v["nf"], nx=v["nx"], ny=v["ny"],
                           strap_w=v["strap_w"], pitch=v["pitch"] if v["pitch"] > 0 else None,
                           device=v["device"], bulk=v["bulk"])

    # -- KLayout hooks ---------------------------------------------------

    def display_text_impl(self):
        return "HW_FET(%s %dx%d nf=%d W=%g L=%g %s)" % (
            self.device.replace("sky130_fd_pr__", ""), self.nx, self.ny, self.nf, self.w, self.l,
            self.bulk)

    def cell_name_impl(self):
        req = backend.request_of(self._params(self._values()))
        req[CREATED_PARAM] = getattr(self, CREATED_PARAM)
        text = json.dumps(req, sort_keys=True, separators=(",", ":"))
        return "HW_FET__%s" % hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    def wants_lazy_evaluation(self):
        cfg = backend.state.cfg
        return bool(cfg is not None and cfg.lazy)

    def coerce_parameters_impl(self):
        if backend.state.generator is None:
            return
        try:
            corr = magic_corrections(self._values())
        except Exception as e:
            backend.log.debug("coerce: Magic's dialog failed: %s", e)
            return
        for k, (typed, shown) in corr.items():
            setattr(self, k, shown)
            key = ("corr", k, typed)
            if key not in self._warned:
                self._warned.add(key)
                _warn("%s %s: Magic's dialog shows %s=%s (entered %s)"
                      % (LIBRARY_NAME, PCELL_NAME, k, shown, typed))
        if self.wants_lazy_evaluation():
            return
        try:
            res = backend.state.generator.get(self._params(self._values()))
            setattr(self, INFO_PARAM, info_text(res))
        except Exception as e:
            setattr(self, INFO_PARAM, "not drawn: %s" % " ".join(str(e).split()))

    def produce_impl(self):
        try:
            if backend.state.generator is None:
                raise RuntimeError("the sky130_power backend is not running")
            from klayout_magic_pcells.importer import insert_gds_flat
            gen = backend.state.generator
            p = self._params(self._values())
            res = gen.get(p)
            try:
                insert_gds_flat(self.layout, self.cell, res.gds_path)
            except Exception as e:
                if res.source == "drawn":
                    raise
                _warn("%s %s: the cached GDS %s can't be read (%s); drawing it again"
                      % (LIBRARY_NAME, PCELL_NAME, res.gds_path, e))
                gen.evict(p)
                self.cell.clear_shapes()
                res = gen.get(p)
                insert_gds_flat(self.layout, self.cell, res.gds_path)
            created = backend.parse_stamp(getattr(self, CREATED_PARAM) or "")
            if created and not backend.same_versions(created, backend.state.stamp_dict):
                key = ("created", getattr(self, CREATED_PARAM))
                if key not in self._warned:
                    self._warned.add(key)
                    _warn("%s %s: instance created with %s, drawn again with %s"
                          % (LIBRARY_NAME, PCELL_NAME, backend.describe(created),
                             backend.describe(backend.state.stamp_dict)))
            backend.apply_stamp(self.layout, self.cell, res.stamp)
        except Exception as e:
            _error("%s %s: not drawn, error marker on %d/%d: %s"
                   % (LIBRARY_NAME, PCELL_NAME, ERROR_LAYER[0], ERROR_LAYER[1], e))
            try:
                self.cell.clear_shapes()
            except Exception:
                pass
            draw_error(self.layout, self.cell, e)

    def callback_impl(self, name):
        # GUI form only. KLayout calls this before coerce, which then writes
        # the corrected values into the form; the icons say why.
        states = getattr(self, "_param_states", None)
        if states is None:
            return
        for n in EDITABLE:
            st = states.parameter(n)
            st.icon = db.PCellParameterState.NoIcon
            st.tooltip = ""
        try:
            values = self._values(states)
            corr = magic_corrections(values)
            for k, (typed, shown) in corr.items():
                st = states.parameter(k)
                st.icon = db.PCellParameterState.WarningIcon
                st.tooltip = "Magic's dialog shows %s (entered %s)" % (shown, typed)
                values[k] = shown
            if self.wants_lazy_evaluation():
                return
            backend.state.generator.get(self._params(values))
        except hw.HWParamError as e:
            st = states.parameter(e.param if e.param in EDITABLE else "device")
            st.icon = db.PCellParameterState.ErrorIcon
            st.tooltip = str(e)
        except Exception as e:
            st = states.parameter("device")
            st.icon = db.PCellParameterState.ErrorIcon
            st.tooltip = "generation failed: %s" % e


class PowerLibrary(db.Library):
    def __init__(self):
        super().__init__()
        self.description = "Power MOSFET layouts for sky130A built from Magic's devices"
        self.layout().dbu = hw.DBU
        self.layout().register_pcell(PCELL_NAME, HWFetPCell())
        self.register(LIBRARY_NAME)


def register(cfg=None):
    """Register the ``sky130_power`` library and return it, or None.

    It needs klayout-magic-pcells' sky130A library (registered here if it
    isn't yet). When that can't register, one error is logged and nothing is
    registered: cells of open files stay ``<defunct>sky130_power.HW_FET`` with
    their stored geometry until a later register() succeeds. Idempotent."""
    st = backend.state
    lib = db.Library.library_by_name(LIBRARY_NAME)
    if lib is not None and st.library is not None and st.generator is not None:
        return st.library
    try:
        backend.start(cfg)
    except Exception as e:
        st.last_error = str(e)
        _error("klayout_power_pcells: %s not registered: %s" % (LIBRARY_NAME, e))
        return None
    st.library = PowerLibrary()
    st.last_error = None
    return st.library
