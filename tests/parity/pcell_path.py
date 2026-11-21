"""Path B of the parity sweep: the PCell, through ``klayout -b``.

    KMP_SWEEP=sweep.json KMP_OUT=<dir> \
      klayout -b -rm pymacros/klayout_magic_pcells.lym -r tests/parity/pcell_path.py

For each point: a layout at dbu 0.001, ``create_cell(device, "sky130_magic",
params)`` with the request converted to the declared types, the variant
placed in a top cell ``T<id>``, and ``<id>.gds`` and ``<id>.oas`` written.
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

LIB = kmp.LIBRARY_NAME


def main():
    sweep_path = os.environ["KMP_SWEEP"]
    out = os.environ["KMP_OUT"]
    os.makedirs(out, exist_ok=True)
    with open(sweep_path, encoding="utf-8") as f:
        sweep = json.load(f)
    st = kmp.state
    index = {"registered": st.library is not None, "error": st.last_error,
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
            params = spec.parse_request(pt["request"])
            ly = db.Layout()
            ly.dbu = 0.001
            pc = ly.create_cell(dev, LIB, params)
            if pc is None:
                raise RuntimeError("create_cell returned None")
            top = ly.create_cell("T" + pid)
            top.insert(db.CellInstArray(pc.cell_index(), db.Trans()))
            ly.write(os.path.join(out, pid + ".gds"))
            ly.write(os.path.join(out, pid + ".oas"))
            req = spec.build_request(spec.defaults_values() | params)
            res = st.generator.peek(spec, req)
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
