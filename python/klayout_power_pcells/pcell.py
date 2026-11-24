"""The ``sky130_power`` KLayout library: the HW FET as a PCell.

The PCell draws through ``hybrid_waffle.generate()`` into a scratch layout
and copies the flat result into its cell, so a placed HW_FET has exactly the
geometry ``write_gds()`` writes for the same parameters. Parameters the
generator refuses (or a Magic that fails) draw an error marker on 255/0
with the reason as text, as klayout-magic-pcells does; produce never raises.
"""

import logging

import klayout.db as db

from . import hybrid_waffle as hw

LIBRARY_NAME = "sky130_power"
PCELL_NAME = "HW_FET"
ERROR_LAYER = (255, 0)
MEMO_SIZE = 16          # generated variants kept per process

log = logging.getLogger("klayout_power_pcells")


class HWFetPCell(db.PCellDeclarationHelper):
    """Hybrid-waffle power MOSFET (sky130A), drawn from Magic's devices."""

    def __init__(self):
        super().__init__()
        d = hw.HWParams()
        self.param("device", self.TypeString, "Device", default=d.device,
                   choices=[(n.replace("sky130_fd_pr__", ""), n) for n in sorted(hw.DEVICES)])
        self.param("bulk", self.TypeString, "Body", default=d.bulk,
                   choices=[("Tap ring around the array (pin B)", "ring"),
                            ("Tap in every source tile, tied to S", "source")])
        self.param("l", self.TypeDouble, "Gate length L", default=d.l, unit="um")
        self.param("w", self.TypeDouble, "Finger width W", default=d.w, unit="um")
        self.param("nf", self.TypeInt, "Fingers per cell", default=d.nf)
        self.param("nx", self.TypeInt, "Tiles per row (N)", default=d.nx)
        self.param("ny", self.TypeInt, "Tiles per column (M)", default=d.ny)
        self.param("strap_w", self.TypeDouble, "Diagonal strap width", default=d.strap_w, unit="um")
        self.param("pitch", self.TypeDouble, "Tile pitch (0 = minimum)", default=0.0, unit="um")
        self._memo = {}

    def display_text_impl(self):
        return "HW_FET(%s %dx%d nf=%d W=%g L=%g %s)" % (
            self.device.replace("sky130_fd_pr__", ""), self.nx, self.ny, self.nf, self.w, self.l,
            self.bulk)

    def _params(self):
        return hw.HWParams(l=self.l, w=self.w, nf=self.nf, nx=self.nx, ny=self.ny,
                           strap_w=self.strap_w, pitch=self.pitch if self.pitch > 0 else None,
                           device=self.device, bulk=self.bulk)

    def produce_impl(self):
        p = self._params()
        key = tuple(sorted(p.as_dict().items()))
        try:
            src = self._memo.get(key)
            if src is None:
                ly = db.Layout()
                ly.dbu = hw.DBU
                res = hw.generate(ly, p, name="HW_FET")
                src = (ly, res.cell.cell_index())
                if len(self._memo) >= MEMO_SIZE:      # keep the newest variants only
                    self._memo.pop(next(iter(self._memo)))
                self._memo[key] = src
            ly, ci = src
            if abs(self.layout.dbu - ly.dbu) > 1e-12:
                raise RuntimeError("library layout dbu %g, expected %g" % (self.layout.dbu, ly.dbu))
            cell = ly.cell(ci)
            for li in ly.layer_indexes():
                if not cell.shapes(li).is_empty():
                    self.cell.shapes(self.layout.layer(ly.get_info(li))).insert(cell.shapes(li))
        except Exception as e:
            log.warning("%s %s: %s", LIBRARY_NAME, PCELL_NAME, e)
            self.cell.clear_shapes()
            li = self.layout.layer(*ERROR_LAYER)
            self.cell.shapes(li).insert(db.DBox(-0.5, -0.5, 0.5, 0.5))
            self.cell.shapes(li).insert(db.DText("HW_ERROR: %s" % " ".join(str(e).split())[:400], db.DTrans()))


class PowerLibrary(db.Library):
    def __init__(self):
        super().__init__()
        self.description = "Power MOSFET layouts for sky130A built from Magic's devices"
        self.layout().dbu = hw.DBU
        self.layout().register_pcell(PCELL_NAME, HWFetPCell())
        self.register(LIBRARY_NAME)


def register():
    """Register the ``sky130_power`` library (idempotent) and return it.

    The library needs no Magic to register; the first HW_FET drawn registers
    klayout-magic-pcells' ``sky130_magic`` if it isn't yet."""
    lib = db.Library.library_by_name(LIBRARY_NAME)
    if lib is None:
        lib = PowerLibrary()
    return lib
