"""The record every rule of the shared table is stored as."""

from dataclasses import dataclass, field

# Where a value was read from:
#   kl   the PDK's KLayout DRC deck
#   mg   Magic's tech file (DRC section)
#   cif  Magic's cifoutput (layers Magic generates: npc, nsdm, psdm, hvntm)
#   tcl  Magic's device generator (sky130A.tcl, gf180mcuD.tcl)
#   drm  the foundry's design rule manual
#   use  a choice of this package, not a rule (documented in ``note``)
SOURCES = ("kl", "mg", "cif", "tcl", "drm", "use")

# What a probe draws for a rule (pdk_rules.probe), with ``on`` naming the layers:
#   width  one rectangle of layer on[0], ``value`` wide
#   space  two rectangles of on[0], ``value`` apart (``wide``: their width)
#   enc    a square of on[1] (``size`` or the layer's width rule) inside on[0], enclosed by ``value``
#   area   a rectangle of on[0] of area ``value`` (um2)
#   exact  like width, for cuts whose size is fixed (also fails above the value)
#   None   no probe (a rule that needs a device around it, or a "use" value)
KINDS = ("width", "space", "enc", "area", "exact", None)


@dataclass(frozen=True)
class Rule:
    value: float                 # um (um2 for areas)
    rule: str                    # rule id as the deck or manual names it, "" for "use"
    src: str = "kl"
    kind: str = None
    on: tuple = ()
    wide: float = None           # space probes: width of the two shapes (wide-metal rules)
    size: float = None           # enc probes: size of the inner square
    note: str = ""
    probe_ids: tuple = field(default=())   # deck categories that report it, when they differ from ``rule``

    def __post_init__(self):
        assert self.src in SOURCES, self.src
        assert self.kind in KINDS, self.kind
        if isinstance(self.on, str):
            object.__setattr__(self, "on", (self.on,))

    @property
    def nm(self):
        """The value in nm (nm2 / 1000 for areas, as klayout_power_pcells stores them)."""
        return int(round(self.value * 1000)) if self.kind != "area" else int(round(self.value * 1e6))


def R(value, rule, src="kl", kind=None, on=(), **kw):
    return Rule(value, rule, src, kind, on, **kw)
