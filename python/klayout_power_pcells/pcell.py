"""The ``sky130_power`` KLayout library: the hybrid-waffle FET as a PCell.

* produce draws through ``backend.HWGenerator`` (memo, disk cache, then
  waffle.py), copies the flat GDS into the cell and stamps it. It never
  raises: values the generator refuses draw a 1 x 1 um box and an
  ``HW_ERROR HW_FET: <reason>`` text on 255/0.
* The form: an error icon on the parameter the generator blames (its
  reason as the tool tip), a warning icon on nx and ny when the diffusion
  lies more than 15 um from the guard ring (Magic's LU.2/LU.3), and a
  read-only Result line with the gate count, total W and area.
* ``hw_created`` (hidden) is the created-with stamp; an instance reopened
  under another generator or rule table logs a warning once.
* With ``KMP_LAZY=1`` the form shows an Update button instead of drawing on
  every edit.
"""

import hashlib
import json

import klayout.db as db

from . import backend
from .rules import PDKS
from .waffle import WaffleError, WaffleParams

LIBRARY_NAME = "sky130_power"
PCELL_NAME = backend.CELL
PDK = "sky130A"
ERROR_LAYER = (255, 0)
CREATED_PARAM = "hw_created"
INFO_PARAM = "info"
EDITABLE = ("device", "nx", "ny", "P", "L", "N", "gate_strap", "runners", "runner_style", "bus", "bus_w",
            "guard_ring")
RUNNER_CHOICES = ("met3,met4", "met3", "met3,met4,met5")


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


def params_of_values(v):
    """WaffleParams of the PCell's values (0 means 'the minimum' for L, N, bus_w)."""
    return WaffleParams(device=v["device"], nx=v["nx"], ny=v["ny"], P=v["P"],
                        L=v["L"] if v["L"] > 0 else None, N=v["N"] if v["N"] > 0 else None,
                        gate_strap=v["gate_strap"], runners=tuple(str(v["runners"]).split(",")),
                        runner_style=v["runner_style"], bus=v["bus"],
                        bus_w=v["bus_w"] if v["bus_w"] > 0 else None, guard_ring=bool(v["guard_ring"]),
                        pdk=PDK)


def info_text(res):
    i = res.info
    lu = i.get("lu_max_um")
    return ("%d gates, W %.2f um, L %.3f, N %.3f um, %.1f um2 (W/area %.3f)%s"
            % (i["n_gates"], i["W_total_um"], i["L_um"], i["N_um"], i["bbox_area_um2"], i["W_per_bbox_area"],
               "" if lu is None or i.get("lu_ok") else "; diffusion %.1f um from a tap (Magic LU wants 15)" % lu))


class HWFetPCell(db.PCellDeclarationHelper):
    """Hybrid-waffle power MOSFET (sky130A), drawn from raw layers."""

    def __init__(self):
        super().__init__()
        d = WaffleParams()
        devs = sorted(PDKS[PDK]["devices"])
        self.param("device", self.TypeString, "Device", default=d.device, choices=[(n, n) for n in devs])
        self.param("nx", self.TypeInt, "Squares in x (nx)", default=d.nx)
        self.param("ny", self.TypeInt, "Squares in y (ny)", default=d.ny)
        self.param("P", self.TypeDouble, "Square pitch P", default=d.P, unit="um")
        self.param("L", self.TypeDouble, "Gate length L (0 = device minimum)", default=0.0, unit="um")
        self.param("N", self.TypeDouble, "Notch side N (0 = minimum)", default=0.0, unit="um")
        self.param("gate_strap", self.TypeString, "Gate strap", default=d.gate_strap,
                   choices=[("met1 mesh, contacts in every notch", "met1_mesh"),
                            ("frame only (high gate resistance)", "frame_only")])
        self.param("runners", self.TypeString, "Diagonal S/D runners", default=",".join(d.runners),
                   choices=[(c, c) for c in RUNNER_CHOICES])
        self.param("runner_style", self.TypeString, "Runner style", default=d.runner_style,
                   choices=[("45 degree", "diag45")])
        self.param("bus", self.TypeString, "S/D buses", default=d.bus,
                   choices=[("L buses: S top/right, D bottom/left", "L_buses"), ("none: a pin per stripe", "none")])
        self.param("bus_w", self.TypeDouble, "Bus width (0 = auto)", default=0.0, unit="um")
        self.param("guard_ring", self.TypeBoolean, "Guard ring (pin B)", default=d.guard_ring)
        self.param(INFO_PARAM, self.TypeString, "Result", default="", readonly=True)
        self.param(CREATED_PARAM, self.TypeString, "Created with", hidden=True, readonly=True,
                   default=backend.state.created_stamp or backend.make_stamp())
        self._warned = set()

    def _values(self, states=None):
        if states is not None:
            return {n: states.parameter(n).value for n in EDITABLE}
        return {n: getattr(self, n) for n in EDITABLE}

    def display_text_impl(self):
        return "HW_FET(%s %dx%d P=%g %s)" % (self.device, self.nx, self.ny, self.P, self.gate_strap)

    def cell_name_impl(self):
        req = backend.request_of(params_of_values(self._values()))
        req[CREATED_PARAM] = getattr(self, CREATED_PARAM)
        text = json.dumps(req, sort_keys=True, separators=(",", ":"))
        return "HW_FET__%s" % hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    def wants_lazy_evaluation(self):
        cfg = backend.state.cfg
        return bool(cfg is not None and cfg.lazy)

    def coerce_parameters_impl(self):
        if backend.state.generator is None or self.wants_lazy_evaluation():
            return
        try:
            res = backend.state.generator.get(params_of_values(self._values()))
            setattr(self, INFO_PARAM, info_text(res))
        except Exception as e:
            setattr(self, INFO_PARAM, "not drawn: %s" % " ".join(str(e).split()))

    def produce_impl(self):
        try:
            if backend.state.generator is None:
                raise RuntimeError("the sky130_power backend is not running")
            from klayout_magic_pcells.importer import insert_gds_flat
            gen = backend.state.generator
            p = params_of_values(self._values())
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
        # GUI form only: icons say why a value can't be drawn, or warn.
        states = getattr(self, "_param_states", None)
        if states is None:
            return
        for n in EDITABLE:
            st = states.parameter(n)
            st.icon = db.PCellParameterState.NoIcon
            st.tooltip = ""
        if self.wants_lazy_evaluation() or backend.state.generator is None:
            return
        try:
            res = backend.state.generator.get(params_of_values(self._values(states)))
            i = res.info
            if i.get("lu_max_um") is not None and not i.get("lu_ok"):
                for n in ("nx", "ny"):
                    st = states.parameter(n)
                    st.icon = db.PCellParameterState.WarningIcon
                    st.tooltip = ("diffusion lies %.1f um from the guard ring; Magic's LU.2/LU.3 want "
                                  "15 um (KLayout's sky130 deck doesn't check it)" % i["lu_max_um"])
        except WaffleError as e:
            st = states.parameter(e.param if e.param in EDITABLE else "device")
            st.icon = db.PCellParameterState.ErrorIcon
            st.tooltip = str(e)
        except Exception as e:
            st = states.parameter("device")
            st.icon = db.PCellParameterState.ErrorIcon
            st.tooltip = "drawing failed: %s" % e


class PowerLibrary(db.Library):
    def __init__(self):
        super().__init__()
        self.description = "Hybrid-waffle power MOSFET for sky130A"
        self.layout().dbu = 0.001
        self.layout().register_pcell(PCELL_NAME, HWFetPCell())
        self.register(LIBRARY_NAME)


def register(cfg=None):
    """Register the ``sky130_power`` library and return it (idempotent).
    Needs only KLayout; returns None, with one logged error, if the cache
    or configuration can't be set up."""
    st = backend.state
    if db.Library.library_by_name(LIBRARY_NAME) is not None and st.library is not None \
            and st.generator is not None:
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
