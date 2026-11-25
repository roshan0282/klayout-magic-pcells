"""Hybrid-waffle (HW) power MOSFET for sky130A, as a KLayout PCell.

``waffle.build()`` / ``waffle.write_gds()`` draw the FET from raw layers:
square source/drain regions in a checkerboard, one straight gate on every
shared edge, notches at the poly crossings, a met1 gate mesh and S/D runners (45 degree,
staircase or planes; see docs/hybrid_waffle.md), for 1.8 V, 5 V and 16 V
extended-drain devices. ``register()`` registers the
``sky130_power`` KLayout library with the HW_FET PCell. Drawing needs only
KLayout; ``verify`` runs the PDK's KLayout deck, Magic DRC and netgen LVS.
"""

__version__ = "0.9.0"

from .waffle import WaffleError, WaffleParams, build, summary, write_gds  # noqa: F401


def register(cfg=None):
    """Register the sky130_power PCell library; returns it, or None (with one
    logged error) when it can't be set up."""
    from .pcell import register as _register
    return _register(cfg)


def form_values(values=None):
    """The HW_FET parameters the GUI form stores for ``values``: the given
    values over the defaults, plus the read-only ``info`` line. Needs
    register()."""
    from . import backend
    from .pcell import EDITABLE, INFO_PARAM, HWFetPCell, info_text, params_of_values
    if backend.state.generator is None:
        raise RuntimeError("klayout_power_pcells.register() has not succeeded")
    out = {p.name: p.default for p in HWFetPCell().get_parameters()}
    out.update(values or {})
    try:
        out[INFO_PARAM] = info_text(backend.state.generator.get(params_of_values({n: out[n] for n in EDITABLE})))
    except Exception as e:
        out[INFO_PARAM] = "not drawn: %s" % " ".join(str(e).split())
    return out
