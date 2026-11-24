"""Power-device generators built on klayout-magic-pcells.

``hybrid_waffle.generate()`` / ``write_gds()`` draw a sky130A hybrid-waffle
(HW) power MOSFET whose unit cells are the devices Magic's own generators
draw (through the ``sky130_magic`` library). ``register()`` registers the
``sky130_power`` KLayout library with the HW_FET PCell.
"""

__version__ = "0.3.0"

from .hybrid_waffle import DEVICES, HWParams, HWResult, generate, write_gds  # noqa: F401


def register(cfg=None):
    """Register the sky130_power PCell library; returns it, or None (with one
    logged error) when klayout-magic-pcells' sky130A library can't register."""
    from .pcell import register as _register
    return _register(cfg)


def form_values(values=None):
    """The HW_FET parameters the GUI form stores for ``values``: W, L and nf
    as Magic's dialog shows them for the unit device, and the read-only
    ``info`` text. Use it before ``create_cell`` to store what the GUI
    stores (outside the GUI, KLayout draws the corrected values but keeps
    the ones passed). Needs register()."""
    from . import backend
    from .pcell import EDITABLE, INFO_PARAM, HWFetPCell, info_text, magic_corrections
    if backend.state.generator is None:
        raise RuntimeError("klayout_power_pcells.register() has not succeeded")
    decl = HWFetPCell()
    out = {p.name: p.default for p in decl.get_parameters()}
    out.update(values or {})
    for k, (_typed, shown) in magic_corrections(out).items():
        out[k] = shown
    try:
        out[INFO_PARAM] = info_text(backend.state.generator.get(HWFetPCell._params(
            {n: out[n] for n in EDITABLE})))
    except Exception as e:
        out[INFO_PARAM] = "not drawn: %s" % " ".join(str(e).split())
    return out
