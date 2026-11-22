"""Path B of the parity sweep: the PCell, through ``klayout -b``.

    KMP_SWEEP=sweep.json KMP_OUT=<dir> \
      klayout -b -rm pymacros/klayout_magic_pcells.lym -r tests/parity/pcell_path.py

The PDK is the one KMP_PDK names (run_sweep.py sets KMP_PDK and KMP_PDKS to
it). For each point: a layout at dbu 0.001, ``create_cell(device, <the
PDK's library>, params)`` with the point's typed values, the variant placed
in a top cell ``T<id>``, and ``<id>.gds`` and ``<id>.oas`` written.
``index.json`` records the variant's name, its stored parameters and what the
backend returned (checked dict, messages, Magic's cell name, cache source).
"""

import json
import os
import sys
import time
import traceback

import klayout.db as db
import klayout_magic_pcells as kmp
from klayout_magic_pcells.stamp import read_stamp

def main():
    sweep_path = os.environ["KMP_SWEEP"]
    out = os.environ["KMP_OUT"]
    os.makedirs(out, exist_ok=True)
    with open(sweep_path, encoding="utf-8") as f:
        sweep = json.load(f)
    st = kmp.state_for(os.environ.get("KMP_PDK") or "sky130A")
    LIB = st.library_name
    index = {"registered": st.library is not None, "error": st.last_error, "library": LIB,
             "versions": st.versions.as_dict() if st.versions else None,
             "created_stamp": st.created_stamp, "points": {}}
    if st.library is None:
        with open(os.path.join(out, "index.json"), "w") as f:
            json.dump(index, f, indent=1)
        print("PCELL_PATH: library not registered: %s" % st.last_error)
        return 2
    t0 = time.time()
    for pt in sweep["points"]:
        pid, dev = pt["id"], pt["device"]
        spec = st.manifest[dev]
        rec = {"device": dev}
        try:
            # The typed values come from the sweep, not from the plugin's parser.
            params = pt["value"]
            ly = db.Layout()
            ly.dbu = 0.001
            before = set(st.generator._memo)
            pc = ly.create_cell(dev, LIB, params)
            if pc is None:
                raise RuntimeError("create_cell returned None")
            top = ly.create_cell("T" + pid)
            top.insert(db.CellInstArray(pc.cell_index(), db.Trans()))
            ly.write(os.path.join(out, pid + ".gds"))
            ly.write(os.path.join(out, pid + ".oas"))
            # The request the PCell actually sent: the memo entry whose key
            # starts with the key in the variant's generated-by stamp.
            # An empty cell has no stamp: then the one entry this call added.
            stp = read_stamp(pc) or {}
            k16 = stp.get("key") or ""
            hits = [st.generator._memo[k] for k in st.generator._memo if k16 and k.startswith(k16)]
            if not k16:
                hits = [st.generator._memo[k] for k in set(st.generator._memo) - before]
            res = hits[0] if len(hits) == 1 else None
            req = res.sidecar.get("request") if res is not None else None
            rec.update({
                "variant": pc.name, "top": top.name,
                "title": pc.display_title(),
                "stored": {k: v for k, v in pc.pcell_parameters_by_name().items()},
                "request": req,
            })
            if res is not None:
                rec.update({"key": res.key, "source": res.source, "checked": res.checked,
                            "messages": res.messages, "magic_cell": res.magic_cell,
                            "stamp": res.stamp})
            else:
                rec["source"] = None
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            rec["traceback"] = traceback.format_exc()
        index["points"][pid] = rec
    index["seconds"] = round(time.time() - t0, 2)
    index["generator_stats"] = dict(st.generator.stats)
    index["server_stats"] = dict(st.server.stats)
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, default=str)
    print("PCELL_PATH: %d points in %.1f s, generator %s"
          % (len(index["points"]), index["seconds"], st.generator.stats))
    return 0


rc = main()
if rc:
    sys.exit(rc)
