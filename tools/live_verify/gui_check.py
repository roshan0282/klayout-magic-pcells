# Drive Tools > Live verify in KLayout's GUI under Xvfb (tools/live_verify/gui_check.sh):
# draw a met1 gap, run "DRC visible area", then turn live mode on, add a
# second gap and wait for the live check. Writes $LV_WORK/notes.json and
# screenshots; ends KLayout with os._exit.

import json
import os
import sys

import pya

sys.path.insert(0, os.environ["QTDRIVE_DIR"])
from qtdrive import Again, Steps, grab, mw  # noqa: E402

WORK = os.environ["LV_WORK"]
notes = {}


def done(ok=True):
    with open(os.path.join(WORK, "notes.json"), "w") as f:
        json.dump(notes, f, indent=1, default=str)
    os._exit(0 if ok else 1)


def ui():
    from live_verify import ui as u
    return u._instance


def setup():
    m = mw()
    m.move(0, 0)
    m.resize(1400, 880)
    cv = m.create_layout("sky130A", 1)
    ly = cv.layout()
    top = ly.create_cell("TOP")
    cv.cell = top
    li = ly.layer(68, 20)
    top.shapes(li).insert(pya.DBox(0, 0, 1, 1))
    top.shapes(li).insert(pya.DBox(1.1, 0, 2, 1))      # 0.10 um gap: m1.2
    top.shapes(li).insert(pya.DBox(0, 3, 4, 4))
    v = m.current_view()
    v.add_missing_layers()
    v.zoom_box(pya.DBox(-3, -3, 9, 7))
    notes["menu"] = mw().menu().is_valid("tools_menu.live_verify.drc_visible")


def run_visible():
    mw().menu().action("tools_menu.live_verify.drc_visible").trigger()


def wait_done():
    u = ui()
    if u.proc is not None or u.runs < 1:
        raise Again()
    notes["visible"] = {t: sorted(set(r for r, _ in m)) for t, m in u.last_result.items()}
    notes["markers_visible"] = len(u.markers)
    v = mw().current_view()
    notes["rdbs"] = [v.rdb(i).description for i in range(v.num_rdbs())]
    grab(os.path.join(WORK, "visible.png"))


def live_on():
    mw().menu().action("tools_menu.live_verify.drc_live").trigger()     # checkable: toggles on
    notes["live"] = ui().live


def edit():
    v = mw().current_view()
    cv = v.active_cellview()
    li = cv.layout().layer(68, 20)
    notes["runs_before_edit"] = ui().runs
    cv.cell.shapes(li).insert(pya.DBox(5, 0, 6, 1))
    cv.cell.shapes(li).insert(pya.DBox(6.08, 0, 7, 1))   # 0.08 um gap


def wait_live():
    u = ui()
    if u.runs <= notes["runs_before_edit"] or u.proc is not None:
        raise Again()
    notes["live_result"] = {t: [(r, str(s.bbox())) for r, s in m] for t, m in u.last_result.items()}
    notes["markers_after_live"] = len(u.markers)      # the first gap's markers stay
    grab(os.path.join(WORK, "live.png"))


def fail():
    grab(os.path.join(WORK, "FAILED.png"))
    done(False)


steps = Steps([(1500, setup), (800, run_visible), (500, wait_done), (500, live_on), (2500, edit),
               (500, wait_live), (300, lambda: done(True))], os.path.join(WORK, "gui.log"), fail)
steps.start(2500)
