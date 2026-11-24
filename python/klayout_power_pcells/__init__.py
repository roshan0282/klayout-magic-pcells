"""Power-device generators built on klayout-magic-pcells.

Milestone 1: ``hybrid_waffle.generate()``, a sky130A nfet_01v8 power FET in
the hybrid-waffle (HW) layout, whose unit cell is the device that Magic's own
generator draws (through the ``sky130_magic`` library).
"""

__version__ = "0.1.0"

from .hybrid_waffle import HWParams, HWResult, generate, write_gds  # noqa: F401
