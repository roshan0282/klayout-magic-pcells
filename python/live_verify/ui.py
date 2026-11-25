"""KLayout GUI: Tools > Live verify.

* "DRC visible area" (Ctrl+Alt+D): tier 0 at once, then the PDK deck in a
  background QProcess; the results go to the marker database "Live DRC"
  (shown in the Marker Browser) and as red markers on the canvas.
* "Live DRC" (Ctrl+Alt+L, checkable): once a second the visible area is
  compared with the last look; when an edit has settled (no change for
  one more tick), the changed area (at least 5 um, plus the halo) is
  checked. Views larger than MAX_VIEW_UM on a side are skipped, so live
  mode never flattens a whole chip.
* "Clear live DRC markers".
"""

import os

import pya

from . import dirty, engine, results

MENU = "tools_menu.live_verify"
RDB_NAME = "Live DRC"
TICK_MS = 1000
MAX_VIEW_UM = 300.0
MIN_AREA_UM = 5.0


class LiveDRC:
    def __init__(self):
        self.app = pya.Application.instance()
        self.mw = self.app.main_window()
        self.proc = None
        self.job = None
        self.pending = None           # (view, cellview, window) waiting for the running deck
        self.markers = []
        self.live = False
        self.prev = None
        self.prev_key = None
        self.dirty = None
        self.timer = pya.QTimer(self.mw)
        self.timer.interval = TICK_MS
        self.timer.timeout = self._tick
        self.last_result = None
        self.runs = 0
        self.known = {}               # (view id, cell index) -> {tier: markers} of earlier checks

    # -- menu ------------------------------------------------------------------
    def install(self):
        menu = self.mw.menu()
        if not menu.is_valid(MENU):
            menu.insert_menu("tools_menu.end", "live_verify", "Live verify")
        a = pya.Action()
        a.title = "DRC visible area"
        a.shortcut = "Ctrl+Alt+D"
        a.on_triggered = self.check_visible
        menu.insert_item(MENU + ".end", "drc_visible", a)
        self.a_live = pya.Action()
        self.a_live.title = "Live DRC"
        self.a_live.shortcut = "Ctrl+Alt+L"
        self.a_live.checkable = True
        self.a_live.on_triggered = self.toggle_live
        menu.insert_item(MENU + ".end", "drc_live", self.a_live)
        c = pya.Action()
        c.title = "Clear live DRC markers"
        c.on_triggered = self.clear
        menu.insert_item(MENU + ".end", "drc_clear", c)
        self._actions = [a, self.a_live, c]

    # -- running -----------------------------------------------------------------
    def _view(self):
        v = self.mw.current_view()
        if v is None or v.active_cellview().cell is None:
            self.mw.message("Live verify: no layout open", 3000)
            return None, None
        return v, v.active_cellview()

    def check_visible(self):
        v, cv = self._view()
        if v is None:
            return
        self.run(v, cv, v.box(), show_browser=True)

    def run(self, view, cv, window, show_browser=False):
        if self.proc is not None:
            self.pending = (view, cv, window)
            return
        ly = cv.layout()
        from . import pdk as pdk_mod
        self.job = engine.prepare(ly, cv.cell, window, pdk_mod.current(cv.technology))
        self.job.update({"view": view, "cv": cv, "browser": show_browser})
        self._publish(engine.finish(self.job), final=self.job["cmd"] is None)
        if self.job["cmd"]:
            self.proc = pya.QProcess(self.mw)
            self.proc.workingDirectory = self.job["work"]
            self.proc.finished = self._finished
            self.proc.start(self.job["cmd"][0], self.job["cmd"][1:])

    def _finished(self, code, status):
        self.proc = None
        self._publish(engine.finish(self.job), final=True)
        if self.pending:
            v, cv, w = self.pending
            self.pending = None
            self.run(v, cv, w)

    def _merged(self, view, cv, res):
        """Earlier markers outside this check's window, plus this check's."""
        key = (id(view), cv.index(), cv.cell.cell_index())
        win = self.job["window"]
        old = self.known.get(key, {})
        out = {}
        for tier in set(old) | set(res):
            keep = [(r, s) for r, s in old.get(tier, []) if not s.bbox().overlaps(win)]
            out[tier] = keep + list(res.get(tier, []))
        self.known[key] = out
        return out

    def _publish(self, res, final):
        view, cv = self.job["view"], self.job["cv"]
        name = cv.cell.name
        self.last_result = res
        res = self._merged(view, cv, res)
        rdb = pya.ReportDatabase(RDB_NAME)
        results.to_rdb(rdb, name, res, RDB_NAME)
        idx = None
        for i in range(view.num_rdbs()):
            if view.rdb(i).description == RDB_NAME:
                idx = i
        idx = view.replace_rdb(idx, rdb) if idx is not None else view.add_rdb(rdb)
        if final and self.job.get("browser"):
            view.show_rdb(idx, cv.index())
        self._draw(view, res)
        n = {t: len(m) for t, m in res.items()}
        if final:
            self.runs += 1
        self.mw.message("Live DRC%s: %s" % ("" if final else " (deck running)",
                                             ", ".join("T%d %d" % kv for kv in sorted(n.items())) or "clean"),
                        5000)

    def _draw(self, view, res):
        self.markers = []
        for tier, markers in res.items():
            for _, shape in markers:
                m = pya.Marker(view)
                try:
                    m.set(shape)
                except Exception:
                    m.set(shape.bbox())
                m.color = 0xff0000
                m.line_width = 2
                m.vertex_size = 0
                self.markers.append(m)

    def clear(self):
        self.markers = []
        self.known = {}
        self.mw.message("Live DRC markers cleared", 2000)

    # -- live mode ---------------------------------------------------------------
    def toggle_live(self):
        self.live = bool(self.a_live.is_checked())
        self.prev, self.prev_key, self.dirty = None, None, None
        if self.live:
            self.timer.start()
        else:
            self.timer.stop()
        self.mw.message("Live DRC %s" % ("on" if self.live else "off"), 3000)

    def _tick(self):
        v = self.mw.current_view()
        if v is None or v.active_cellview().cell is None:
            return
        cv = v.active_cellview()
        box = v.box()
        if box.width() > MAX_VIEW_UM or box.height() > MAX_VIEW_UM:
            return
        key = (cv.index(), cv.cell.cell_index(), str(box))
        snap = dirty.snapshot(cv.layout(), cv.cell, box)
        if self.prev is None or key != self.prev_key:
            self.prev, self.prev_key = snap, key
            return
        ch = dirty.changed(self.prev, snap, cv.layout().dbu)
        self.prev = snap
        if ch is not None:
            self.dirty = ch if self.dirty is None else self.dirty + ch
            return
        if self.dirty is not None:
            w = self.dirty
            c = w.center()
            hw, hh = max(w.width(), MIN_AREA_UM) / 2, max(w.height(), MIN_AREA_UM) / 2
            self.dirty = None
            self.run(v, cv, pya.DBox(c.x - hw, c.y - hh, c.x + hw, c.y + hh))


_instance = None


def install():
    global _instance
    if _instance is None and pya.Application.instance().main_window() is not None:
        _instance = LiveDRC()
        _instance.install()
    return _instance
