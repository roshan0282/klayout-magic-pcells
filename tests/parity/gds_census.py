"""Raw GDSII record census, without KLayout.

KLayout's GDS reader drops element types it has no shape for (NODE, which
the vendor GDS of some sky130 fixed devices holds) without a warning, so a
comparison that reads both files through KLayout can't see them. This reads
the records itself and counts the elements of each type per layer/datatype,
over all structures of the file (not flattened: an arrayed vendor cell is
counted once).

    python3 gds_census.py FILE.gds [...]
"""

import struct
import sys
from collections import Counter

EL = {0x08: "BOUNDARY", 0x09: "PATH", 0x0A: "SREF", 0x0B: "AREF", 0x0C: "TEXT", 0x15: "NODE",
      0x2D: "BOX"}
LAYER, DATATYPE, TEXTTYPE, NODETYPE, BOXTYPE, ENDEL = 0x0D, 0x0E, 0x16, 0x2A, 0x2E, 0x11
# Element types a KLayout cell holds as shapes or instances.
KLAYOUT_TYPES = {"BOUNDARY", "PATH", "SREF", "AREF", "TEXT"}


def census(path):
    """{(element type, 'layer/datatype' or '-'): count} over the whole file."""
    with open(path, "rb") as f:
        data = f.read()
    i = 0
    cur = None
    elems = Counter()
    while i + 4 <= len(data):
        n, rt, _dt = struct.unpack(">HBB", data[i:i + 4])
        if n < 4:
            break
        body = data[i + 4:i + n]
        if rt in EL:
            cur = {"type": EL[rt], "layer": None, "dt": None}
        elif cur is not None:
            if rt == LAYER:
                cur["layer"] = struct.unpack(">h", body[:2])[0]
            elif rt in (DATATYPE, TEXTTYPE, NODETYPE, BOXTYPE):
                cur["dt"] = struct.unpack(">h", body[:2])[0]
            elif rt == ENDEL:
                ld = "-" if cur["layer"] is None else "%d/%d" % (cur["layer"], cur["dt"] or 0)
                elems[(cur["type"], ld)] += 1
                cur = None
        i += n
    return elems


def lost(path):
    """Elements of types KLayout can't hold, as {'TYPE layer/dt': count}."""
    return {"%s %s" % k: v for k, v in sorted(census(path).items()) if k[0] not in KLAYOUT_TYPES}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        c = census(p)
        types = Counter()
        for (k, _ld), n in c.items():
            types[k] += n
        print("%s %s lost=%s" % (p.split("/")[-1], dict(types), lost(p)))
