"""The text the PCell must send Magic for a value: the README's contract
("Parameters"), written again here without importing the plugin, so that a
bug in klayout_magic_pcells.manifest.format() fails the sweep's request and
geometry checks instead of reaching both paths.

  float  -> the value rounded to 12 significant digits (half-even on the
            exact binary value, as C's %.12g does), in Python's float
            notation: shortest digits, at least one digit after the point;
            if that equals the manifest default at 12 digits, the default's
            own text ("0.420")
  int    -> decimal digits
  bool01 -> "1" or "0"
  signed -> the text as typed
"""

from decimal import Context, Decimal, ROUND_HALF_EVEN

_C12 = Context(prec=12, rounding=ROUND_HALF_EVEN)


def _d12(x):
    return _C12.plus(Decimal(float(x))).normalize(_C12)


def float_text(x, default=None):
    d = _d12(x)
    if default is not None:
        try:
            if d == _d12(float(default)):
                return default
        except ValueError:
            pass
    if d.is_zero():
        return "-0.0" if d.is_signed() else "0.0"
    if not -4 <= d.adjusted() < 16:
        raise ValueError("%r is outside the range the sweep uses (1e-4 .. 1e16)" % (x,))
    s = format(d, "f")
    return s if "." in s else s + ".0"


def typed(ptype, text):
    """The text a user types -> the value given to Layout.create_cell."""
    if ptype == "float":
        return float(text)
    if ptype == "int":
        return int(text)
    if ptype == "bool01":
        return bool(int(text))
    return str(text)


def text(ptype, value, default=None):
    if ptype == "float":
        return float_text(value, default)
    if ptype == "int":
        return "%d" % value
    if ptype == "bool01":
        return "1" if value else "0"
    return str(value)
