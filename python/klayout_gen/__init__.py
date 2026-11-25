"""Supporting generators for analog/power layout (roadmap Phase 3), drawn
from raw layers: the ``sky130_gen`` library.

* GUARD_RING: a tap ring that follows any Manhattan shape (box, polygon
  or path), p-tap or n-tap (with its n-well, optionally a deep n-well),
  contacted to li and optionally met1.

``register()`` adds the library; the geometry functions only need
klayout.db.
"""

__version__ = "0.1.0"


def register():
    """Register the ``sky130_gen`` library (idempotent); returns it or None."""
    from .pcell import register as _register
    return _register()
