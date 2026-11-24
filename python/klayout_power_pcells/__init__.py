"""Power-device generators built on klayout-magic-pcells.

``hybrid_waffle.generate()`` / ``write_gds()`` draw a sky130A hybrid-waffle
(HW) power MOSFET whose unit cells are the devices Magic's own generators
draw (through the ``sky130_magic`` library). ``register()`` registers the
``sky130_power`` KLayout library with the HW_FET PCell.
"""

__version__ = "0.2.0"

from .hybrid_waffle import DEVICES, HWParams, HWResult, generate, write_gds  # noqa: F401


def register():
    """Register the sky130_power PCell library; returns it."""
    from .pcell import register as _register
    return _register()
