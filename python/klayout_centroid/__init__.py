"""Common-centroid matched arrays.

``pattern`` and ``metrics`` are pure Python (no KLayout): device unit
counts -> a common-centroid letter grid, and a report on how good it is.
``placer`` and ``pcell`` turn a grid into placed unit cells from the
``*_magic`` libraries (klayout-magic-pcells); ``register()`` adds the
``centroid`` library with the ``CC_ARRAY`` PCell.
"""

__version__ = "0.1.0"

from .pattern import (DUMMY, STYLES, Pattern, PatternError, build, check_centroid,  # noqa: F401
                      parse_devices, parse_grid)
from .metrics import evaluate, report_text, summary_line  # noqa: F401


def register():
    """Register the ``centroid`` KLayout library (idempotent); returns it,
    or None with one logged error."""
    from .pcell import register as _register
    return _register()
