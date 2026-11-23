# KLayout macro that takes the screenshots of guide.md. Run by
# tools/screenshots/take.sh inside the pinned image, as
#
#   klayout -e -rm tools/screenshots/gui.py
#
# under Xvfb, with KMP_SHOT_SESSION set to one of:
#
#   main     the Package Manager, the library list, placing and editing
#            devices, a via and an n-well, the log, a stamp; saves the
#            layout to $KMP_SHOT_WORK/guide-demo.gds
#   reopen   opens that file again with the libraries registered
#   defunct  opens it with KMP_PDKS=gf180mcuD, so sky130_magic is missing
#
# Raw PNGs go to $KMP_SHOT_WORK/raw/. The macro drives the GUI through
# qtdrive.py (Qt events and screen grabs from the macro) and ends KLayout
# with os._exit, because a normal exit after the sessions crashed in
# KLayout's cleanup ("double free or corruption") and left the process
# hanging.

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
GDS = os.path.join(WORK, "guide-demo.gds")
LOG = os.path.join(WORK, "gui-%s.log" % SESSION)
NOTES = os.path.join(WORK, "notes-%s.json" % SESSION)
notes = {}

# A light canvas (the image's klayoutrc sets black), every hierarchy level
# drawn in new views, and the start-up tip about that answered.
a = app()
a.set_config("background-color", "#ffffff")
a.set_config("full-hierarchy-new-cell", "true")
a.set_config("tip-window-hidden", "only-top-level-shown-by-default=3")
a.commit_config()


def shot(name, rect=None):
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
    with open(os.path.join(WORK, "failed-%s" % SESSION), "w") as f:
        f.write("failed\n")
    try:
        shot("FAILED-%s" % SESSION)
    finally:
        os._exit(1)


def later(fn):
    """Run fn from a fresh timer, so that a modal dialog it opens runs in
    its own event loop while the steps go on."""
    t = pya.QTimer(mw())
    t.singleShot = True
    t.interval = 50
    t.timeout = fn
    _keep.append(t)
    t.start()


_keep = []


# -- common steps -------------------------------------------------------------

def window():
    m = mw()
    m.move(0, 0)
    m.resize(1440, 900)
    for name in ("navigator_dock_widget", "bookmarks_dock_widget", "lt_dock_widget"):
        dock(name).hide()


def tips():
    """Answer any start-up tip with its default button (Yes: show the full
    hierarchy), as Return would."""
    for _ in range(3):
        t = toplevel(name="TipDialog")
        if t is None:
            return
        b = [x for x in find(t, cls="QPushButton", visible=True) if x.objectName in ("yes_button", "ok_button", "close_button")]
        b[0].click()


def docks_wide(cells=110, libs=230, left=560):
    m = mw()
    m.resizeDocks([dock("hp_dock_widget")], [left], pya.Qt.Horizontal)
    m.resizeDocks([dock("lp_dock_widget")], [190], pya.Qt.Horizontal)
    m.resizeDocks([dock("hp_dock_widget"), dock("libs_dock_widget"), dock("eo_dock_widget")],
                  [cells, libs, 900 - cells - libs], pya.Qt.Vertical)


def view():
    return mw().current_view()


def pointer_away():
    """Park the pointer on the Layers panel: over the canvas it draws a
    crosshair (the image's klayoutrc turns the crosshair cursor on)."""
    r = global_rect(dock("lp_dock_widget"))
    hover(r[0] + r[2] // 2, r[1] + r[3] - 60)


def canvas_rect():
    """The canvas with the Layers panel and the status bar."""
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


def icon_of(root, field_widget):
    """The icon label in the row of a form field (its tooltip says what
    Magic did)."""
    y = field_widget.mapToGlobal(pya.QPoint(0, 0)).y
    best = None
    for c in find(root, cls="QLabel", visible=True):
        if c.width > 30:
            continue
        cy = c.mapToGlobal(pya.QPoint(0, 0)).y
        if abs(cy - y) <= 4 and c.toolTip:
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


def set_instance_cell(cell):
    a.set_config("edit-inst-lib-name", "sky130_magic")
    a.set_config("edit-inst-cell-name", cell)
    a.commit_config()


def top_instances():
    cv = view().active_cellview()
    return list(cv.cell.each_inst())


def select_instance(inst):
    cv = view().active_cellview()
    ip = pya.ObjectInstPath()
    ip.top = cv.cell.cell_index()
    ip.cv_index = cv.index()
    ip.append_path(pya.InstElement(inst))
    view().object_selection = [ip]


def properties():
    later(lambda: mw().menu().action("edit_menu.show_properties").trigger())


def params_of(inst):
    return {k: v for k, v in inst.pcell_parameters_by_name().items()}


# -- session main -------------------------------------------------------------

def salt_open():
    later(lambda: mw().menu().action("tools_menu.packages").trigger())


def salt_select():
    sm = toplevel(name="SaltManagerDialog")
    sm.resize(1000, 560)
    find1(sm, name="mode_tab").setCurrentIndex(2)
    lv = find1(sm, name="salt_view", visible=True)
    mod = lv.model
    root = pya.QModelIndex()
    for r in range(mod.rowCount(root)):
        idx = mod.index(r, 0, root)
        if "klayout-magic-pcells" in str(mod.data(idx, 0)):
            lv.setCurrentIndex(idx)
            lv.scrollTo(idx)
            return
    raise RuntimeError("klayout-magic-pcells is not in the Package Manager's list")


def salt_grab():
    shot("salt-package", global_rect(toplevel(name="SaltManagerDialog")))


def salt_close():
    sm = toplevel(name="SaltManagerDialog")
    [b for b in find(sm, cls="QPushButton", visible=True) if "Close" in b.text][0].click()


def new_layout():
    cv = mw().create_layout("sky130A", 1)
    cv.cell = cv.layout().create_cell("TOP")
    docks_wide()


def libs_popup():
    combo = find1(dock("libs_dock_widget"), name="library_selection")
    notes["libraries"] = [combo.itemText(i) for i in range(combo.count)]
    combo.showPopup()


def libs_grab():
    """The Libraries panel with its library list open; the list is a
    top-level popup window."""
    rects = [global_rect(dock("libs_dock_widget"))]
    for w in pya.QApplication.topLevelWidgets():
        if w.isVisible() and w.objectName != "main_window":
            rects.append(global_rect(w))
    r = union(*rects)
    shot("libraries", (r[0], r[1], r[2] + 8, r[3] + 4))


def libs_choose():
    combo = find1(dock("libs_dock_widget"), name="library_selection")
    combo.hidePopup()
    i = [n for n in range(combo.count) if combo.itemText(n).startswith("sky130_magic")][0]
    combo.setCurrentIndex(i - 1)
    combo.setFocus()
    key(combo, pya.Qt.Key_Down)


def nfet_tool():
    mode("instance")
    set_instance_cell("sky130_fd_pr__nfet_01v8")
    docks_wide(cells=90, libs=150)


def nfet_form():
    tool_tab("PCell")
    view().zoom_box(pya.DBox(-3.5, -3, 3.5, 3))
    c = Canvas()
    c.move(0.0, 0.0)


def nfet_form_grab():
    shot("place-nfet")
    notes["nfet_form_before"] = icons(pcell_page())


def nfet_type_l():
    type_text(field(pcell_page(), "l"), "0.1")


def nfet_hover():
    pp = pcell_page()
    notes["nfet_after_l"] = {"l": field(pp, "l").text, "icons": icons(pp)}
    hover_widget(icon_of(pp, field(pp, "l")))


def nfet_hover_grab():
    pp = pcell_page()
    r = global_rect(pp)
    shot("nfet-l-corrected", (r[0], r[1] - 34, min(r[2], 600), 190))


def nfet_place():
    c = Canvas()
    c.move(0.0, 0.0)
    c.click(0.0, 0.0)


def nfet_placed():
    mode("select")
    view().max_hier()
    view().zoom_box(pya.DBox(-2.2, -1.6, 2.2, 1.6))
    pointer_away()
    insts = top_instances()
    notes["nfet_placed"] = {"cell": insts[0].cell.name, "title": insts[0].cell.display_title(),
                            "params": params_of(insts[0])}


def nfet_placed_grab():
    shot("nfet-placed", canvas_rect())


def via_tool():
    mode("instance")
    set_instance_cell("via1")
    tool_tab("PCell")
    view().zoom_box(pya.DBox(-3, -2.5, 6, 2.5))


def via_type_small():
    type_text(field(pcell_page(), "w"), "0.2")


def via_hover():
    pp = pcell_page()
    notes["via_small"] = {"w": field(pp, "w").text, "icons": icons(pp)}
    hover_widget(icon_of(pp, field(pp, "w")))


def via_small_grab():
    pp = pcell_page()
    r = global_rect(pp)
    shot("via1-too-small", (r[0], r[1] - 34, min(r[2], 600), 150))


def via_type_ok():
    type_text(field(pcell_page(), "w"), "1.0")


def via_type_h():
    type_text(field(pcell_page(), "h"), "0.5")


def via_place():
    c = Canvas()
    c.move(3.0, 0.0)
    c.click(3.0, 0.0)


def nwell_tool():
    set_instance_cell("nwell")
    tool_tab("PCell")


def nwell_type_w():
    type_text(field(pcell_page(), "w"), "3.0")


def nwell_type_h():
    type_text(field(pcell_page(), "h"), "2.0")


def nwell_place():
    c = Canvas()
    c.move(5.0, -1.0)
    c.click(5.0, -1.0)


def overview():
    mode("select")
    view().max_hier()
    view().zoom_box(pya.DBox(-1.4, -2.0, 8.6, 2.0))
    pointer_away()
    notes["overview"] = [(i.cell.display_title(), str(i.dtrans), params_of(i)) for i in top_instances()]


def overview_grab():
    """The canvas band that holds the three instances."""
    c = Canvas()
    box = view().active_cellview().cell.dbbox()
    x0, y0 = c.point(box.left, box.top)
    x1, y1 = c.point(box.right, box.bottom)
    o = c.widget.mapToGlobal(pya.QPoint(0, 0))
    m = 40
    shot("layout-overview", (o.x + max(int(x0) - m, 0), o.y + int(y0) - m,
                             min(int(x1 - x0) + 2 * m, c.widget.width), int(y1 - y0) + 2 * m))


def nfet_select():
    nfet = [i for i in top_instances() if i.cell.name.startswith("sky130_fd_pr__nfet_01v8")][0]
    select_instance(nfet)
    view().zoom_box(pya.DBox(-2.4, -2.6, 9.6, 2.6))
    properties()


def props_tab():
    pd = toplevel(name="properties_dialog")
    for t in find(pd, cls="QTabWidget", visible=True):
        for i in range(t.count):
            if t.tabText(i) == "PCell parameters":
                t.setCurrentIndex(i)
    notes["props_before"] = {n: field(pd, n).text for n in ("w", "l", "nf")}
    # Tab moves the focus only in the active window; activation takes effect
    # in the next event loop pass, so the typing is the next step.
    pd.activateWindow()


def props_type_w1():
    # Tab leaves the field, as a click into another one does. Return would
    # also press the dialog's Ok button.
    pd = toplevel(name="properties_dialog")
    type_text(field(pd, "w"), "1.0", finish="Tab")


def props_type_w2():
    pd = toplevel(name="properties_dialog")
    notes["props_after_w1"] = {"w": field(pd, "w").text, "icons": icons(pd),
                               "instance": top_instances()[0].cell.display_title()}
    type_text(field(pd, "w"), "0.3", finish="Tab")


def props_grab():
    pd = toplevel(name="properties_dialog")
    notes["props_after_w2"] = {"w": field(pd, "w").text, "icons": icons(pd),
                               "instance": top_instances()[0].cell.display_title()}
    r = global_rect(pd)
    shot("properties-edit", (r[0], r[1], r[2], 240))


def props_ok():
    pd = toplevel(name="properties_dialog")
    [b for b in find(pd, cls="QPushButton", visible=True) if b.text == "Ok"][0].click()


def props_after():
    nfet = [i for i in top_instances() if i.cell.name.startswith("sky130_fd_pr__nfet_01v8")][0]
    p = params_of(nfet)
    notes["nfet_after_properties"] = {"title": nfet.cell.display_title(), "params": p}


def log_open():
    mw().menu().action("file_menu.view_log").trigger()


def log_grab():
    lv = toplevel(name="LogViewerDialog")
    lv.resize(1100, 260)
    lv.move(170, 300)


def log_grab2():
    lv = toplevel(name="LogViewerDialog")
    notes["log_title"] = lv.windowTitle
    shot("log-viewer", global_rect(lv))


def log_close():
    toplevel(name="LogViewerDialog").hide()


def res_tool():
    """Record (no screenshot) what the PCell tab shows for a resistor's
    defaults, whose Value Magic's dialog shows in SPICE notation."""
    mode("instance")
    set_instance_cell("sky130_fd_pr__res_high_po_0p69")
    tool_tab("PCell")


def res_notes():
    pp = pcell_page()
    notes["res_high_po_0p69_defaults"] = {"val": field(pp, "val").text, "w": field(pp, "w").text,
                                          "icons": icons(pp)}


def cap_tool():
    set_instance_cell("sky130_fd_pr__cap_mim_m3_1")
    tool_tab("PCell")


def cap_type_l():
    pp = pcell_page()
    notes["cap_mim_m3_1_defaults"] = {n: field(pp, n).text for n in ("w", "l", "val")}
    type_text(field(pp, "l"), "5")


def cap_type_w():
    pp = pcell_page()
    notes["cap_mim_m3_1_after_l"] = {"fields": {n: field(pp, n).text for n in ("w", "l", "val")},
                                     "icons": icons(pp)}
    type_text(field(pp, "w"), "3")


def cap_notes():
    pp = pcell_page()
    notes["cap_mim_m3_1_after_w"] = {"fields": {n: field(pp, n).text for n in ("w", "l", "val")},
                                     "icons": icons(pp)}
    mode("select")


def stamp_select():
    nfet = [i for i in top_instances() if i.cell.name.startswith("sky130_fd_pr__nfet_01v8")][0]
    ly = view().active_cellview().layout()
    li = ly.find_layer(235, 4)
    box = list(nfet.cell.shapes(li).each())[0]
    notes["stamp"] = box.property(100)
    notes["kmp_created"] = nfet.pcell_parameter("kmp_created")
    cv = view().active_cellview()
    ip = pya.ObjectInstPath()
    ip.top = cv.cell.cell_index()
    ip.cv_index = cv.index()
    ip.append_path(pya.InstElement(nfet))
    ip.layer = li
    ip.shape = box
    view().object_selection = [ip]
    properties()


def stamp_userprops():
    pd = toplevel(name="properties_dialog")
    later(lambda: find1(pd, name="prop_pb").click())


def stamp_resize():
    up = toplevel(name="user_properties_form")
    up.resize(760, 300)


def stamp_grab():
    pd = toplevel(name="properties_dialog")
    up = toplevel(name="user_properties_form")
    shot("stamp", union(global_rect(pd), global_rect(up)))


def stamp_close_user():
    up = toplevel(name="user_properties_form")
    [b for b in find(up, cls="QPushButton", visible=True) if "Cancel" in b.text][0].click()


def stamp_close_props():
    pd = toplevel(name="properties_dialog")
    [b for b in find(pd, cls="QPushButton", visible=True) if b.text == "Cancel"][0].click()


def save():
    view().select_cell_path([view().active_cellview().cell.cell_index()], 0)
    ly = view().active_cellview().layout()
    ly.write(GDS)
    notes["saved"] = GDS


MAIN = [
    (1500, window), (500, tips),
    (500, salt_open), (4000, salt_select), (1500, salt_grab), (300, salt_close),
    (800, new_layout), (800, tips), (800, libs_popup), (800, libs_grab), (500, libs_choose),
    (800, nfet_tool), (1500, nfet_form), (1500, nfet_form_grab),
    (300, nfet_type_l), (2500, nfet_hover), (2500, nfet_hover_grab),
    (300, nfet_place), (1500, nfet_placed), (1500, nfet_placed_grab),
    (500, via_tool), (1500, via_type_small), (2500, via_hover), (2500, via_small_grab),
    (300, via_type_ok), (1500, via_type_h), (1500, via_place),
    (1000, nwell_tool), (1500, nwell_type_w), (1500, nwell_type_h), (1500, nwell_place),
    (1500, overview), (1500, overview_grab),
    (500, nfet_select), (2000, props_tab), (800, props_type_w1), (2500, props_type_w2),
    (2500, props_grab), (300, props_ok), (1500, props_after),
    (500, log_open), (800, log_grab), (800, log_grab2), (300, log_close),
    (500, res_tool), (2500, res_notes), (300, cap_tool), (2500, cap_type_l), (2500, cap_type_w),
    (2500, cap_notes),
    (500, stamp_select), (1500, stamp_userprops), (1000, stamp_resize), (1000, stamp_grab),
    (300, stamp_close_user), (800, stamp_close_props),
    (500, save), (500, finish),
]


# -- sessions reopen and defunct ----------------------------------------------

def open_file():
    mw().load_layout(GDS, "sky130A", 0)
    view().max_hier()
    docks_wide(cells=200, libs=120)
    view().zoom_box(pya.DBox(-1.4, -2.0, 8.6, 2.0))
    pointer_away()


def expand_cells():
    hp = dock("hp_dock_widget")
    for t in find(hp, cls="QTreeView", visible=True):
        t.expandAll()
    cells = []
    ly = view().active_cellview().layout()
    for c in ly.each_cell():
        cells.append({"name": c.name, "title": c.display_title(), "proxy": c.is_proxy(),
                      "library_cell": c.is_library_cell()})
    notes["cells"] = cells
    notes["libraries"] = pya.Library.library_names()
    notes["instances"] = [(i.cell.display_title(), params_of(i) if i.is_pcell() else None)
                          for i in top_instances()]


def reopen_grab():
    """The Cells panel and the canvas."""
    name = {"reopen": "reopen-with-library", "defunct": "reopen-without-library"}[SESSION]
    shot(name, (0, 78, global_rect(Canvas().widget)[0] + Canvas().widget.width, 600))


def reopen_props():
    nfet = [i for i in top_instances() if i.cell.name.startswith("sky130_fd_pr__nfet_01v8")][0]
    select_instance(nfet)
    properties()


def reopen_props_grab():
    pd = toplevel(name="properties_dialog")
    for t in find(pd, cls="QTabWidget", visible=True):
        for i in range(t.count):
            if t.tabText(i) == "PCell parameters":
                t.setCurrentIndex(i)


def reopen_props_grab2():
    pd = toplevel(name="properties_dialog")
    notes["reopen_props"] = {n: field(pd, n).text for n in ("w", "l", "nf")}
    notes["reopen_icons"] = icons(pd)
    shot("reopen-properties", global_rect(pd))


def reopen_props_close():
    pd = toplevel(name="properties_dialog")
    [b for b in find(pd, cls="QPushButton", visible=True) if b.text == "Cancel"][0].click()


def log_text():
    log_open()


def log_text2():
    lv = toplevel(name="LogViewerDialog")
    lv.resize(1100, 260)
    lv.move(170, 300)


def log_text3():
    shot("log-%s" % SESSION, global_rect(toplevel(name="LogViewerDialog")))
    toplevel(name="LogViewerDialog").hide()


REOPEN = [
    (1500, window), (500, tips), (500, open_file), (1500, tips), (500, expand_cells),
    (1500, reopen_grab), (300, reopen_props), (2000, reopen_props_grab),
    (1500, reopen_props_grab2), (300, reopen_props_close),
    (800, log_text), (800, log_text2), (800, log_text3), (500, finish),
]

DEFUNCT = [
    (1500, window), (500, tips), (500, open_file), (1500, tips), (500, expand_cells),
    (1500, reopen_grab), (800, log_text), (800, log_text2), (800, log_text3), (500, finish),
]

steps = Steps({"main": MAIN, "reopen": REOPEN, "defunct": DEFUNCT}[SESSION], LOG, fail)
steps.start(2000)
