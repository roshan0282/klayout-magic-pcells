# KLayout macro that drives the GUI with the sky130_power library and takes
# the screenshots of docs/guide-power.md. Run by tools/screenshots/power_shots.sh
# under Xvfb as
#
#   klayout -e -rm tools/screenshots/power_gui.py
#
# with KMP_SHOT_SESSION one of:
#
#   main     the Package Manager entry, the library list, the HW_FET form,
#            an error icon (strap too narrow) and a warning icon (L below
#            Magic's minimum) with their tool tips, placing the FET, editing
#            it in the Properties dialog (pfet, taps in the source tiles),
#            the log; saves $KMP_SHOT_WORK/power-demo.gds
#   reopen   opens that file with the libraries registered
#   defunct  opens it with Magic missing, so sky130_power doesn't register
#
# What each step saw (field values, icon tool tips, cell titles) goes to
# $KMP_SHOT_WORK/notes-<session>.json; raw PNGs to $KMP_SHOT_WORK/raw/.
# Uses qtdrive.py, as gui.py does, and ends KLayout with os._exit.

import json
import os
import sys

import pya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qtdrive import (Canvas, Steps, app, dock, find, find1, global_rect, grab,  # noqa: E402
                     hover, key, mw, toplevel, type_text, union)

SESSION = os.environ.get("KMP_SHOT_SESSION", "main")
WORK = os.environ.get("KMP_SHOT_WORK", "/work")
RAW = os.path.join(WORK, "raw")
GDS = os.path.join(WORK, "power-demo.gds")
LOG = os.path.join(WORK, "power-gui-%s.log" % SESSION)
NOTES = os.path.join(WORK, "notes-%s.json" % SESSION)
notes = {}
_keep = []

a = app()
a.set_config("background-color", "#ffffff")
a.set_config("full-hierarchy-new-cell", "true")
a.set_config("tip-window-hidden", "only-top-level-shown-by-default=3")
a.commit_config()


def shot(name, rect=None):
    os.makedirs(RAW, exist_ok=True)
    grab(os.path.join(RAW, name + ".png"), rect)


def finish():
    with open(NOTES, "w") as f:
        json.dump(notes, f, indent=1, default=str)
    with open(os.path.join(WORK, "done-%s" % SESSION), "w") as f:
        f.write("ok\n")
    os._exit(0)


def fail():
    with open(NOTES, "w") as f:
        json.dump(notes, f, indent=1, default=str)
    try:
        shot("FAILED-%s" % SESSION)
    finally:
        os._exit(1)


def later(fn):
    t = pya.QTimer(mw())
    t.singleShot = True
    t.interval = 50
    t.timeout = fn
    _keep.append(t)
    t.start()


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


def docks_wide(cells=110, libs=200, left=600):
    m = mw()
    m.resizeDocks([dock("hp_dock_widget")], [left], pya.Qt.Horizontal)
    m.resizeDocks([dock("lp_dock_widget")], [170], pya.Qt.Horizontal)
    m.resizeDocks([dock("hp_dock_widget"), dock("libs_dock_widget"), dock("eo_dock_widget")],
                  [cells, libs, 900 - cells - libs], pya.Qt.Vertical)


def view():
    return mw().current_view()


def pointer_away():
    r = global_rect(dock("lp_dock_widget"))
    hover(r[0] + r[2] // 2, r[1] + r[3] - 60)


def canvas_rect():
    c = Canvas().widget
    r = global_rect(c)
    m = mw()
    return (r[0], r[1] - 30, m.width - r[0], m.height - r[1] + 30)


def mode(name):
    mw().menu().action("edit_menu.mode_menu." + name).trigger()


def tool_tab(title):
    eo = dock("eo_dock_widget")
    tabs = [t for t in find(eo, cls="QTabWidget") if t.isVisible()][0]
    for i in range(tabs.count):
        if tabs.tabText(i) == title:
            tabs.setCurrentIndex(i)
            return
    raise RuntimeError("no tab %s" % title)


def pcell_page():
    return find1(dock("eo_dock_widget"), name="EditorOptionsInstPCellParam")


def field(root, name):
    return [c for c in find(root, cls="QLineEdit", name=name) if c.isVisible()][0]


def combo(root, name):
    return [c for c in find(root, cls="QComboBox", name=name) if c.isVisible()][0]


def icon_of(root, w):
    y = w.mapToGlobal(pya.QPoint(0, 0)).y
    best = None
    for c in find(root, cls="QLabel", visible=True):
        if c.width > 30:
            continue
        if abs(c.mapToGlobal(pya.QPoint(0, 0)).y - y) <= 4 and c.toolTip:
            best = c
    return best


def icons(root):
    out = {}
    for c in find(root, cls="QLabel", visible=True):
        if c.width <= 30 and c.toolTip:
            out[c.mapToGlobal(pya.QPoint(0, 0)).y] = c.toolTip
    return [out[k] for k in sorted(out)]


def hover_widget(w):
    mw().activateWindow()
    g = w.mapToGlobal(pya.QPoint(w.width // 2, w.height // 2))
    hover(g.x, g.y)


def top_instances():
    return list(view().active_cellview().cell.each_inst())


def select_instance(inst):
    cv = view().active_cellview()
    ip = pya.ObjectInstPath()
    ip.top = cv.cell.cell_index()
    ip.cv_index = cv.index()
    ip.append_path(pya.InstElement(inst))
    view().object_selection = [ip]


def choose(cb, value):
    for i in range(cb.count):
        if cb.itemText(i) == value or str(cb.itemData(i)) == value:
            cb.setCurrentIndex(i)
            return
    raise RuntimeError("no choice %r in %s" % (value, [cb.itemText(i) for i in range(cb.count)]))


# -- session main ------------------------------------------------------------

def salt_open():
    later(lambda: mw().menu().action("tools_menu.packages").trigger())


def salt_select():
    sm = toplevel(name="SaltManagerDialog")
    if sm is None:
        notes["salt"] = "Package Manager did not open; top-level windows: %s" % [
            w.objectName for w in pya.QApplication.topLevelWidgets() if w.isVisible()]
        return
    sm.resize(1000, 560)
    find1(sm, name="mode_tab").setCurrentIndex(2)
    lv = find1(sm, name="salt_view", visible=True)
    mod = lv.model
    root = pya.QModelIndex()
    names = []
    for r in range(mod.rowCount(root)):
        idx = mod.index(r, 0, root)
        names.append(str(mod.data(idx, 0)))
        if "klayout-power-pcells" in names[-1]:
            lv.setCurrentIndex(idx)
            lv.scrollTo(idx)
            notes["salt"] = names[-1]
            return
    raise RuntimeError("klayout-power-pcells is not in the Package Manager's list: %s" % names)


def salt_grab():
    if toplevel(name="SaltManagerDialog") is None:
        return
    shot("power-salt-package", global_rect(toplevel(name="SaltManagerDialog")))


def salt_close():
    sm = toplevel(name="SaltManagerDialog")
    if sm is None:
        return
    [b for b in find(sm, cls="QPushButton", visible=True) if "Close" in b.text][0].click()


def new_layout():
    cv = mw().create_layout("sky130A", 1)
    cv.cell = cv.layout().create_cell("TOP")
    docks_wide()


def libs_popup():
    cb = find1(dock("libs_dock_widget"), name="library_selection")
    notes["libraries"] = [cb.itemText(i) for i in range(cb.count)]
    cb.showPopup()


def libs_grab():
    rects = [global_rect(dock("libs_dock_widget"))]
    for w in pya.QApplication.topLevelWidgets():
        if w.isVisible() and w.objectName != "main_window":
            rects.append(global_rect(w))
    r = union(*rects)
    shot("power-libraries", (r[0], r[1], r[2] + 8, r[3] + 4))


def libs_choose():
    cb = find1(dock("libs_dock_widget"), name="library_selection")
    cb.hidePopup()
    i = [n for n in range(cb.count) if cb.itemText(n).startswith("sky130_power")][0]
    cb.setCurrentIndex(i - 1)
    cb.setFocus()
    key(cb, pya.Qt.Key_Down)
    notes["library_chosen"] = cb.currentText


def hw_tool():
    mode("instance")
    a.set_config("edit-inst-lib-name", "sky130_power")
    a.set_config("edit-inst-cell-name", "HW_FET")
    a.commit_config()
    docks_wide(cells=90, libs=110)


def hw_form():
    tool_tab("PCell")
    view().zoom_box(pya.DBox(-12, -12, 40, 30))
    Canvas().move(0.0, 0.0)


def hw_form_grab():
    pp = pcell_page()
    notes["form_fields"] = sorted(set(w.objectName for w in find(pp, cls="QLineEdit", visible=True)
                                      if w.objectName) |
                                  set(w.objectName for w in find(pp, cls="QComboBox", visible=True)
                                      if w.objectName))
    notes["form_icons_before"] = icons(pp)
    notes["form_info"] = field(pp, "info").text if find(pp, cls="QLineEdit", name="info") else None
    shot("power-form")


def hw_type_strap():
    type_text(field(pcell_page(), "strap_w"), "1.0")


def hw_hover_strap():
    pp = pcell_page()
    notes["after_strap"] = {"icons": icons(pp)}
    hover_widget(icon_of(pp, field(pp, "strap_w")))


def hw_strap_grab():
    pp = pcell_page()
    r = global_rect(pp)
    shot("power-strap-error", (r[0], r[1] - 34, min(r[2], 640), r[3] + 34))


def hw_type_strap_ok():
    type_text(field(pcell_page(), "strap_w"), "3.0")


def hw_type_l():
    type_text(field(pcell_page(), "l"), "0.1")


def hw_hover_l():
    pp = pcell_page()
    notes["after_l"] = {"l": field(pp, "l").text, "icons": icons(pp),
                        "info": field(pp, "info").text}
    hover_widget(icon_of(pp, field(pp, "l")))


def hw_l_grab():
    pp = pcell_page()
    r = global_rect(pp)
    shot("power-l-corrected", (r[0], r[1] - 34, min(r[2], 640), r[3] + 34))


def hw_place():
    c = Canvas()
    c.move(0.0, 0.0)
    c.click(0.0, 0.0)


def hw_placed():
    mode("select")
    view().max_hier()
    view().zoom_fit()
    pointer_away()
    insts = top_instances()
    notes["placed"] = {"title": insts[0].cell.display_title(), "live": insts[0].cell.is_pcell_variant(),
                       "params": {k: v for k, v in insts[0].pcell_parameters_by_name().items()}}


def hw_placed_grab():
    shot("power-placed", canvas_rect())


def hw_select():
    select_instance(top_instances()[0])
    later(lambda: mw().menu().action("edit_menu.show_properties").trigger())


def props_tab():
    pd = toplevel(name="properties_dialog")
    pd.resize(760, 640)
    for t in find(pd, cls="QTabWidget", visible=True):
        for i in range(t.count):
            if t.tabText(i) == "PCell parameters":
                t.setCurrentIndex(i)


def _pd_state(tag):
    pd = toplevel(name="properties_dialog")
    notes.setdefault("props_steps", []).append({
        "after": tag, "device": combo(pd, "device").currentText, "bulk": combo(pd, "bulk").currentText,
        "nx": field(pd, "nx").text, "ny": field(pd, "ny").text})


# One edit per step: each edit runs the form's callback, which rebuilds the
# fields, so the next one is looked up again after a pause.
def props_device():
    choose(combo(toplevel(name="properties_dialog"), "device"), "pfet_01v8")


def props_bulk():
    _pd_state("device")
    choose(combo(toplevel(name="properties_dialog"), "bulk"), "Tap in every source tile, tied to S")


def props_nx():
    _pd_state("bulk")
    type_text(field(toplevel(name="properties_dialog"), "nx"), "5", finish="Tab")


def props_ny():
    _pd_state("nx")
    type_text(field(toplevel(name="properties_dialog"), "ny"), "5", finish="Tab")


def props_grab():
    pd = toplevel(name="properties_dialog")
    notes["props"] = {"icons": icons(pd), "info": field(pd, "info").text}
    shot("power-properties", global_rect(pd))


def props_ok():
    pd = toplevel(name="properties_dialog")
    [b for b in find(pd, cls="QPushButton", visible=True) if b.text in ("OK", "Ok")][0].click()


def props_after():
    view().zoom_fit()
    pointer_away()
    insts = top_instances()
    notes["edited"] = {"title": insts[0].cell.display_title(),
                       "params": {k: v for k, v in insts[0].pcell_parameters_by_name().items()}}


def props_after_grab():
    shot("power-edited", canvas_rect())


def save():
    ly = view().active_cellview().layout()
    ly.write(GDS)
    notes["saved"] = GDS


# -- sessions reopen and defunct --------------------------------------------------

def open_file():
    mw().load_layout(GDS, 0)
    docks_wide()


def expand_cells():
    view().max_hier()
    view().zoom_fit()
    insts = top_instances()
    notes["reopened"] = [{"title": i.cell.display_title(), "live": i.cell.is_pcell_variant(),
                          "proxy": i.cell.is_proxy(), "bbox": str(i.cell.dbbox())} for i in insts]
    pointer_away()


def reopen_grab():
    name = {"reopen": "power-reopen-with-library", "defunct": "power-reopen-without-library"}[SESSION]
    shot(name, (0, 78, global_rect(Canvas().widget)[0] + Canvas().widget.width, 640))


MAIN = [
    # The Package Manager isn't shown: opening it fetches KLayout's online
    # package index, and a failed fetch opens a modal error that blocks the
    # session. The Salt install is checked by the klayout -zz autorun test.
    (1500, window), (500, tips), (500, new_layout), (800, libs_popup), (800, libs_grab), (500, libs_choose),
    (800, hw_tool), (1500, hw_form), (2500, hw_form_grab),
    (300, hw_type_strap), (2500, hw_hover_strap), (1500, hw_strap_grab),
    (300, hw_type_strap_ok), (1500, hw_type_l), (2500, hw_hover_l), (1500, hw_l_grab),
    (500, hw_place), (3000, hw_placed), (1500, hw_placed_grab),
    (500, hw_select), (2500, props_tab), (800, props_device), (2500, props_bulk), (2500, props_nx), (2500, props_ny), (4000, props_grab),
    (500, props_ok), (4000, props_after), (1500, props_after_grab), (500, save), (500, finish),
]
REOPEN = [(1500, window), (500, tips), (500, open_file), (1500, tips), (3000, expand_cells),
          (1500, reopen_grab), (500, finish)]
DEFUNCT = REOPEN

steps = Steps({"main": MAIN, "reopen": REOPEN, "defunct": DEFUNCT}[SESSION], LOG, fail)
steps.start(2000)
