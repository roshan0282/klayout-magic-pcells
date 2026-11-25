"""The ``sky130_gen`` KLayout library.

GUARD_RING: a guard ring following a box, polygon or path (the ``shape``
parameter; the PCell can also be made from a drawn shape: select it and
use Edit > Selection > Convert To PCell). Values that can't be drawn
show an error icon on the parameter to blame and a GEN_ERROR text on 255/0.
"""

import logging

import klayout.db as db

from . import guard_ring

log = logging.getLogger("klayout_gen")
LIBRARY_NAME = "sky130_gen"
ERROR_LAYER = (255, 0)


def _error_marker(layout, cell, name, e):
    try:
        from klayout_magic_pcells import _kl
        _kl.error("%s %s: not drawn: %s" % (LIBRARY_NAME, name, e))
    except Exception:
        log.error("%s %s: not drawn: %s", LIBRARY_NAME, name, e)
    cell.clear_shapes()
    li = layout.layer(*ERROR_LAYER)
    cell.shapes(li).insert(db.DBox(-0.5, -0.5, 0.5, 0.5))
    cell.shapes(li).insert(db.DText("GEN_ERROR %s: %s" % (name, " ".join(str(e).split())[:400]), db.DTrans()))


class GuardRingPCell(db.PCellDeclarationHelper):
    """Guard ring following any Manhattan outline (sky130A)."""

    EDITABLE = ("shape", "kind", "width", "clearance", "met1", "deep_nwell", "label")

    def __init__(self):
        super().__init__()
        self.param("shape", self.TypeShape, "Outline to enclose", default=db.DBox(0, 0, 10, 5))
        self.param("kind", self.TypeString, "Tap", default="ptap",
                   choices=[("p-tap (substrate / p-well, around nfets)", "ptap"),
                            ("n-tap in n-well (around pfets, or an n-well barrier)", "ntap")])
        self.param("width", self.TypeDouble, "Ring width (0 = narrowest with a contact)", default=0.0, unit="um")
        self.param("clearance", self.TypeDouble, "Clearance from the outline", default=0.3, unit="um")
        self.param("met1", self.TypeBoolean, "met1 over the ring (with mcon)", default=True)
        self.param("deep_nwell", self.TypeBoolean, "Deep n-well inside (n-tap only: isolated p-well)",
                   default=False)
        self.param("label", self.TypeString, "Pin name", default="B")

    def display_text_impl(self):
        return "GUARD_RING(%s %s)" % (self.kind, "dnw" if self.deep_nwell else "")

    def _kw(self, v):
        return dict(kind=v["kind"], width=v["width"], clearance=v["clearance"], met1=v["met1"],
                    deep_nwell=v["deep_nwell"])

    def callback_impl(self, name):
        states = getattr(self, "_param_states", None)
        if states is None:
            return
        for n in self.EDITABLE:
            st = states.parameter(n)
            st.icon = db.PCellParameterState.NoIcon
            st.tooltip = ""
        v = {n: states.parameter(n).value for n in self.EDITABLE}
        try:
            guard_ring.ring(v["shape"], 0.001, **self._kw(v))
        except guard_ring.RingError as e:
            st = states.parameter(e.param if e.param in self.EDITABLE else "shape")
            st.icon = db.PCellParameterState.ErrorIcon
            st.tooltip = str(e)
        except Exception:
            pass

    def can_create_from_shape_impl(self):
        return self.shape.is_box() or self.shape.is_polygon() or self.shape.is_path()

    def parameters_from_shape_impl(self):
        s = self.shape
        if s.is_box():
            self.shape = s.dbox
        elif s.is_path():
            self.shape = s.dpath
        else:
            self.shape = s.dpolygon

    def transformation_from_shape_impl(self):
        return db.Trans()

    def produce_impl(self):
        try:
            v = {n: getattr(self, n) for n in self.EDITABLE}
            guard_ring.draw(self.layout, self.cell, v["shape"], label=v["label"], **self._kw(v))
        except Exception as e:
            _error_marker(self.layout, self.cell, "GUARD_RING", e)


class GenLibrary(db.Library):
    def __init__(self):
        super().__init__()
        self.description = "sky130A supporting generators: guard ring"
        self.layout().dbu = 0.001
        self.layout().register_pcell("GUARD_RING", GuardRingPCell())
        self.register(LIBRARY_NAME)


_library = None


def register():
    global _library
    if _library is not None and db.Library.library_by_name(LIBRARY_NAME) is not None:
        return _library
    try:
        _library = GenLibrary()
    except Exception as e:
        log.error("klayout_gen: %s not registered: %s", LIBRARY_NAME, e)
        return None
    return _library
