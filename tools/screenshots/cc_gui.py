# KLayout macro that opens the CC_ARRAY form (library "centroid") under Xvfb,
# picks another unit in the Unit cell dropdown and records what the form
# shows. Run by tools/screenshots/cc_shots.sh as
#
#   klayout -e -rm tools/screenshots/cc_gui.py
#
# Writes $KMP_SHOT_WORK/raw/cc-*.png and $KMP_SHOT_WORK/notes-cc.json.
# Uses qtdrive.py, as power_gui.py does, and ends KLayout with os._exit.

import json
import os
import sys

import pya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qtdrive import Canvas, Steps, app, dock, find, find1, global_rect, grab, key, mw, toplevel  # noqa: E402

WORK = os.environ.get("KMP_SHOT_WORK", "/work")
RAW = os.path.join(WORK, "raw")
LOG = os.path.join(WORK, "cc-gui.log")
NOTES = os.path.join(WORK, "notes-cc.json")
notes = {}

a = app()
a.set_config("background-color", "#ffffff")
a.set_config("tip-window-hidden", "only-top-level-shown-by-default=3")
a.commit_config()


def shot(name, rect=None):
    os.makedirs(RAW, exist_ok=True)
    grab(os.path.join(RAW, name + ".png"), rect)


def _dump():
    with open(NOTES, "w") as f:
        json.dump(notes, f, indent=1, default=str)


def finish():
    _dump()
    with open(os.path.join(WORK, "done-cc"), "w") as f:
        f.write("ok\n")
    os._exit(0)


def fail():
    _dump()
    try:
        shot("FAILED-cc")
    finally:
        os._exit(1)


def window():
    m = mw()
    m.move(0, 0)
    m.resize(1440, 900)
    for name in ("navigator_dock_widget", "bookmarks_dock_widget", "lt_dock_widget"):
        dock(name).hide()


def tips():
    for _ in range(3):
        t = toplevel(name="TipDialog")
        if t is None:
            return
        b = [x for x in find(t, cls="QPushButton", visible=True)
             if x.objectName in ("yes_button", "ok_button", "close_button")]
        b[0].click()


def new_layout():
    cv = mw().create_layout("sky130A", 1)
    cv.cell = cv.layout().create_cell("TOP")
    m = mw()
    m.resizeDocks([dock("hp_dock_widget")], [620], pya.Qt.Horizontal)
    m.resizeDocks([dock("hp_dock_widget"), dock("libs_dock_widget"), dock("eo_dock_widget")],
                  [90, 110, 700], pya.Qt.Vertical)


def cc_tool():
    mw().menu().action("edit_menu.mode_menu.instance").trigger()
    a.set_config("edit-inst-lib-name", "centroid")
    a.set_config("edit-inst-cell-name", "CC_ARRAY")
    a.commit_config()


def cc_form():
    eo = dock("eo_dock_widget")
    tabs = [t for t in find(eo, cls="QTabWidget") if t.isVisible()][0]
    for i in range(tabs.count):
        if tabs.tabText(i) == "PCell":
            tabs.setCurrentIndex(i)
    Canvas().move(0.0, 0.0)


def page():
    return find1(dock("eo_dock_widget"), name="EditorOptionsInstPCellParam")


def unit_combo():
    return [c for c in find(page(), cls="QComboBox", name="unit") if c.isVisible()][0]


def text_of(name):
    w = [c for c in find(page(), cls="QLineEdit", name=name) if c.isVisible()]
    return w[0].text if w else None


def form_rect():
    r = global_rect(page())
    return (r[0], r[1] - 34, min(r[2], 720), r[3] + 34)


def note_form(tag):
    cb = unit_combo()
    notes[tag] = {"unit": cb.currentText, "unit_params": text_of("unit_params"), "grid": text_of("grid"),
                  "info": text_of("info"), "unit_choices": cb.count}


def grab_default():
    note_form("default")
    shot("cc-form", form_rect())


def open_dropdown():
    unit_combo().showPopup()


def grab_dropdown():
    rects = [form_rect()]
    for w in pya.QApplication.topLevelWidgets():
        if w.isVisible() and w.objectName != "main_window":
            rects.append(global_rect(w))
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    shot("cc-unit-dropdown", (x0, y0, x1 - x0, y1 - y0))


def pick_mim():
    cb = unit_combo()
    cb.hidePopup()
    for i in range(cb.count):
        if str(cb.itemText(i)).startswith("MIM cap: cap_mim_m3_1"):
            # as a user would: the form reacts to activation, not to setCurrentIndex
            cb.setCurrentIndex(i - 1)
            cb.setFocus()
            key(cb, pya.Qt.Key_Down)
            return
    raise RuntimeError("no MIM cap in the dropdown")


def grab_mim():
    note_form("after_mim")
    shot("cc-form-mim", form_rect())


STEPS = [(1500, window), (500, tips), (500, new_layout), (800, cc_tool), (1500, cc_form), (3000, grab_default),
         (300, open_dropdown), (1200, grab_dropdown), (500, pick_mim), (3000, grab_mim), (500, finish)]

steps = Steps(STEPS, LOG, fail)
steps.start(2000)
