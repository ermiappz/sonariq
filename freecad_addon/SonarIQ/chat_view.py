"""P5 Chat for the SonarIQ panel: words -> preview card -> engineer confirms -> engine computes.

Cards come from the engine's /chat router (code parser first, AI as fallback). The panel only draws them.
Simulate: scenario preview -> Confirm and run -> live run count -> result card -> Open replay (portal W10).
"""
from __future__ import annotations

import os

try:
    from PySide import QtCore, QtGui, QtWidgets  # type: ignore
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore

PORTAL = os.environ.get("SONARIQ_PORTAL", "http://localhost:5173/")
SUGGEST = ["Summarise open fails", "Why does F-07 fail?", "What blocks sign-off?", "Apply fix 2"]


def mmss(s):
    if s is None:
        return "—"
    m = int(s // 60)
    return f"{m:02d}:{int(round(s - 60 * m)):02d}"


class PlanWidget(QtWidgets.QWidget):
    """Mini Deck 5 plan for the fire what-if preview: walkable area, walls, first smoke hops (hatched), origin."""
    def __init__(self, plan: dict):
        super().__init__()
        self.plan = plan
        self.setMinimumHeight(110)

    def paintEvent(self, _):
        g = self.plan["geometry"]
        x0, y0, x1, y1 = g["bounds"]
        w, h = self.width() - 8, self.height() - 8
        k = min(w / (x1 - x0), h / (y1 - y0))
        ox, oy = 4 + (w - (x1 - x0) * k) / 2, 4 + (h - (y1 - y0) * k) / 2
        P = lambda x, y: QtCore.QPointF(ox + (x - x0) * k, oy + (y1 - y) * k)  # noqa: E731
        qp = QtGui.QPainter(self)
        qp.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = self.palette()
        ink = pal.color(QtGui.QPalette.WindowText)

        def path(r):
            pp = QtGui.QPainterPath()
            rings = r if isinstance(r, list) else [r]
            for rr in rings:
                pts = [P(*p) for p in rr["outer"]]
                pp.addPolygon(QtGui.QPolygonF(pts))
                for hole in rr["holes"]:
                    pp.addPolygon(QtGui.QPolygonF([P(*p) for p in hole]))
            pp.setFillRule(QtCore.Qt.OddEvenFill)
            return pp
        base = QtGui.QColor(ink)
        base.setAlpha(28)
        qp.fillPath(path(g["walkable"]), base)
        hatch = QtGui.QBrush(ink, QtCore.Qt.BDiagPattern)
        for ev in self.plan.get("smoke", []):
            for sp in ev["spaces"]:
                if sp in self.plan["spaces"]:
                    qp.fillPath(path(self.plan["spaces"][sp]), hatch)
        pen = QtGui.QPen(ink)
        pen.setWidthF(0.6)
        qp.setPen(pen)
        for wl in g["walls"]:
            xs = [p[0] for p in wl["poly"]["outer"]]
            ys = [p[1] for p in wl["poly"]["outer"]]
            if max(xs) - min(xs) >= max(ys) - min(ys):
                qp.drawLine(P(min(xs), (min(ys) + max(ys)) / 2), P(max(xs), (min(ys) + max(ys)) / 2))
            else:
                qp.drawLine(P((min(xs) + max(xs)) / 2, min(ys)), P((min(xs) + max(xs)) / 2, max(ys)))
        o = self.plan.get("origin")
        if o:
            pen.setWidthF(1.6)
            qp.setPen(pen)
            qp.drawEllipse(P(*o["xy"]), 5, 5)
        qp.end()


def _label(text, role=None, mono=False, wrap=True, bold=False):
    w = QtWidgets.QLabel(text)
    if role:
        w.setProperty("role", role)
    if mono:
        w.setProperty("mono", "true")
    w.setWordWrap(wrap)
    if wrap:
        w.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        w.setMinimumWidth(40)
    if bold:
        w.setStyleSheet("font-weight: 600;")
    w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    return w


def _card(dashed=False):
    f = QtWidgets.QFrame()
    f.setProperty("role", "card-dashed" if dashed else "card")
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(4)
    return f, lay


class ChatView(QtWidgets.QWidget):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.engine = panel.engine
        self.polls: dict[str, QtCore.QTimer] = {}
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        host = QtWidgets.QWidget()
        self.lay = QtWidgets.QVBoxLayout(host)
        self.lay.setContentsMargins(12, 10, 12, 10)
        self.lay.setSpacing(8)
        self.lay.addWidget(_label("Assistant Engineer · ask why a check fails, or describe one of the four allowed edits. "
                                  "Nothing changes until you confirm. Evacuation simulation lives in the portal.", role="muted"))
        self.lay.addStretch(1)
        self.scroll.setWidget(host)
        root.addWidget(self.scroll, 1)
        chips = QtWidgets.QHBoxLayout()
        chips.setContentsMargins(12, 4, 12, 0)
        chips.setSpacing(4)
        cw = QtWidgets.QWidget()
        flow = QtWidgets.QGridLayout(cw)
        flow.setContentsMargins(12, 4, 12, 0)
        flow.setSpacing(4)
        for i, s in enumerate(SUGGEST):
            b = QtWidgets.QPushButton(s)
            b.setProperty("kind", "ghost")
            b.clicked.connect(lambda _=False, t=s: self.send(t))
            flow.addWidget(b, i // 2, i % 2)
        root.addWidget(cw)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(12, 6, 12, 10)
        self.inp = QtWidgets.QLineEdit()
        self.inp.setPlaceholderText("Ask about this run, or describe a change")
        self.inp.returnPressed.connect(lambda: self.send(self.inp.text()))
        go = QtWidgets.QPushButton("Send")
        go.setProperty("kind", "primary")
        go.clicked.connect(lambda: self.send(self.inp.text()))
        row.addWidget(self.inp, 1)
        row.addWidget(go)
        root.addLayout(row)

    # ------------------------------------------------------------------ plumbing
    def _add(self, w):
        self.lay.insertWidget(self.lay.count() - 1, w)
        QtCore.QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _you(self, text):
        f, l = _card(dashed=True)
        l.addWidget(_label(text))
        self._add(f)

    def send(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        self.inp.clear()
        self._you(text)
        fid = (self.panel.current or {}).get("id") if getattr(self.panel, "current", None) else None
        wait = _label("…", role="faint")
        self._add(wait)
        QtWidgets.QApplication.processEvents()
        try:
            r = self.engine._req("POST", "/chat", {"text": text, "finding": fid}, timeout=40)
        except Exception as e:  # noqa: BLE001
            r = {"cards": [{"type": "error", "text": f"Engine not reachable ({e}). Start it with make api."}]}
        wait.deleteLater()
        for c in r.get("cards", []):
            self.render(c)

    def confirm(self, action: dict, card: QtWidgets.QWidget):
        for b in card.findChildren(QtWidgets.QPushButton):
            b.setEnabled(False)
        try:
            r = self.engine._req("POST", "/chat/confirm", {"action": action}, timeout=60)
        except Exception as e:  # noqa: BLE001
            r = {"cards": [{"type": "error", "text": f"Refused: {e}"}]}
        for c in r.get("cards", []):
            self.render(c)
        if action.get("kind") == "edit" and hasattr(self.panel, "analyse"):
            QtCore.QTimer.singleShot(50, self.panel.refresh_after_edit if hasattr(self.panel, "refresh_after_edit")
                                     else (lambda: None))

    # ------------------------------------------------------------------ cards
    def render(self, c: dict):
        t = c.get("type")
        f, l = _card()
        if t == "edit_preview":
            l.addWidget(_label("Edit preview · nothing has changed yet", role="faint"))
            if c.get("fix"):
                fx = c["fix"]
                l.addWidget(_label(f"Fix {fx['n']} for {fx['finding']}: {fx['label']} · checked by the rule engine: "
                                   f"{fx.get('verdict')}", role="muted"))
            l.addWidget(_label(c["text"], bold=True))
            l.addWidget(_label(f"Read by {c.get('source')}", role="faint"))
            self._buttons(l, f, "Confirm", c["confirm"])
        elif t in ("scenario_preview", "simulation_result", "sim_result") and getattr(self.panel, "bridge", None) \
                and getattr(self.panel.bridge, "ok", False):
            # the FreeCAD panel does not run simulations: point to the portal (Simulate screen)
            import sonariq_panel as _sp
            l.addWidget(_label("Simulation lives in the portal", bold=True))
            l.addWidget(_label(f"Open {_sp.PORTAL}/#simulate to set up and run evacuation scenarios.", role="muted"))
            b = QtWidgets.QPushButton("Open Simulate in the portal")
            b.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(f"{_sp.PORTAL}/#simulate")))
            l.addWidget(b)
        elif t == "scenario_preview":
            fire = bool(c["scenario"].get("fire_origin"))
            hd = QtWidgets.QHBoxLayout()
            hd.addWidget(_label("FIRE WHAT-IF · PREVIEW" if fire else "SIMULATION PREVIEW", role="faint", wrap=False))
            hd.addStretch(1)
            hd.addWidget(_label("Illustrative smoke spread" if fire else
                                ("AI draft · you decide" if str(c.get("source", "")).startswith("ai") else "Read from your words · you decide"),
                                role="faint", wrap=False))
            l.addLayout(hd)
            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(10)
            rows = [("Scenario", c["text"]), ("People", f"{c['people']} on Deck 5" if c.get("people") is not None else None),
                    ("Inflow 3B", c.get("inflow_3B")), ("Runs", str(c["runs"])), ("Model", c["model"])]
            rows += [("", g) for g in c.get("gaps", [])]
            for i, (k, v) in enumerate([r for r in rows if r[1]]):
                grid.addWidget(_label(k, role="faint", wrap=False), i, 0, QtCore.Qt.AlignTop)
                grid.addWidget(_label(v), i, 1)
            l.addLayout(grid)
            if c.get("plan"):
                l.addWidget(PlanWidget(c["plan"]))
                l.addWidget(_label("Hatched: smoke in the first hops · not a fire model", role="faint"))
            self._buttons(l, f, "Confirm", c["confirm"], note="Nothing runs until you confirm.")
        elif t == "ping":
            l.addWidget(_label(f"Applied: {c['text']}", bold=True))
            l.addWidget(_label(f"Re-checked {c['rerun']} checks in {c.get('duration_s')} s", role="muted", mono=True))
            for ch in c.get("changed", []):
                l.addWidget(_label(f"{ch['id']} · {ch.get('title') or ''} → {ch.get('status') or 'cleared'}"))
            k = c.get("counts", {})
            l.addWidget(_label(" · ".join(str(k.get(s, 0)) for s in ("fail", "warn", "unk", "pass", "dor")), mono=True))
        elif t == "sim_progress":
            hd = QtWidgets.QHBoxLayout()
            hd.addWidget(_label("Simulating", bold=True, wrap=False))
            hd.addStretch(1)
            hd.addWidget(_label(f"{c.get('scenario_label')} · {c.get('revision')}", role="faint", wrap=False))
            l.addLayout(hd)
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, int(c.get("runs_target") or 500))
            bar.setValue(int(c.get("runs_done") or 0))
            bar.setFormat("%v of %m runs")
            l.addWidget(bar)
            st = _label(c.get("state", ""), role="faint", mono=True)
            l.addWidget(st)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(_label("Rule checks are not affected.", role="faint"), 1)
            cancel = QtWidgets.QPushButton("Cancel")
            cancel.setProperty("kind", "ghost")
            cancel.clicked.connect(lambda _=False, j=c["id"]: self._cancel(j, cancel))
            row.addWidget(cancel)
            l.addLayout(row)
            self._poll(c["id"], bar, st, c.get("state") == "done")
        elif t == "sim_result":
            hd = QtWidgets.QHBoxLayout()
            hd.addWidget(_label(c["title"], bold=True))
            hd.addWidget(_label(f"Simulation · {c['runs']} runs", role="faint", wrap=False))
            l.addLayout(hd)
            grid = QtWidgets.QGridLayout()
            lr = c.get("longest_route") or {}
            rows = [("p95 time", f"{c.get('tA_p95_mmss')} mm:ss"),
                    ("Peak density", f"{c.get('peak_density_p95')} p/m² (p95)"),
                    ("Longest route", f"{lr.get('length_m')} m from {lr.get('space')}"),
                    ("Longest queue", f"{c['worst_landing']} · {c['worst_queue_p95']} people (p95)" if c.get("worst_landing") else None),
                    ("Clears last", f"Stair {c['last_stair']} at {mmss(c.get('last_stair_p95_s'))}" if c.get("last_stair") else None)]
            for i, (k, v) in enumerate([r for r in rows if r[1]]):
                grid.addWidget(_label(k, role="faint", wrap=False), i, 0)
                grid.addWidget(_label(v, mono=True), i, 1)
            l.addLayout(grid)
            l.addWidget(_label(c.get("badge", ""), role="faint"))
            l.addWidget(_label(c.get("analyst", "")))
            l.addWidget(_label(c.get("label", ""), role="faint"))
            row = QtWidgets.QHBoxLayout()
            b = QtWidgets.QPushButton("Open replay")
            b.setProperty("kind", "primary")
            b.clicked.connect(lambda _=False, u=c["replay_url"]: QtGui.QDesktopServices.openUrl(QtCore.QUrl(PORTAL + u)))
            rr = QtWidgets.QPushButton("Re-run")
            rr.clicked.connect(lambda _=False, sc=c.get("scenario"): self.confirm(
                {"kind": "simulate", "scenario": sc, "revision": None, "runs": c["runs"]}, QtWidgets.QWidget()))
            row.addWidget(b)
            row.addWidget(rr)
            row.addStretch(1)
            l.addLayout(row)
        elif t == "explain":
            l.addWidget(_label(c.get("badge", ""), role="faint"))
            l.addWidget(_label(c["text"]))
        elif t == "sources":
            l.addWidget(_label("Source text", role="faint"))
            for s in c.get("sources", [])[:3]:
                l.addWidget(_label(f"{s.get('citation')}: “{s.get('text', '')[:240]}…”", role="muted"))
        elif t == "fixes":
            l.addWidget(_label(c.get("text", ""), bold=True))
            for i, fx in enumerate(c.get("fixes", []), 1):
                l.addWidget(_label(f"{i}. {fx['label']} → {fx.get('verdict')}{' (rejected)' if fx.get('rejected') else ''}"))
        else:
            l.addWidget(_label(c.get("text", "?"), role="muted"))
        self._add(f)

    def _cancel(self, jid, btn):
        btn.setEnabled(False)
        try:
            self.engine._req("POST", f"/simulate/{jid}/cancel", {}, timeout=5)
        except Exception:  # noqa: BLE001
            pass

    def _buttons(self, l, card, ok_text, action, note=None):
        row = QtWidgets.QHBoxLayout()
        ok = QtWidgets.QPushButton(ok_text)
        ok.setProperty("kind", "primary")
        ok.clicked.connect(lambda: self.confirm(action, card))
        no = QtWidgets.QPushButton("Cancel")
        no.setProperty("kind", "ghost")
        no.clicked.connect(lambda: [b.setEnabled(False) for b in card.findChildren(QtWidgets.QPushButton)])
        row.addWidget(ok)
        row.addWidget(no)
        if note:
            row.addWidget(_label(note, role="faint"), 1)
        else:
            row.addStretch(1)
        l.addLayout(row)

    def _poll(self, jid, bar, st, done):
        def tick():
            try:
                s = self.engine._req("GET", f"/simulate/{jid}", timeout=5)
            except Exception:  # noqa: BLE001
                return
            bar.setMaximum(int(s.get("runs_target") or bar.maximum()))
            bar.setValue(int(s.get("runs_done") or 0))
            live = s.get("live")
            st.setText(f"{s['state']}" + (f" · so far p95 {live['tA_p95_s']} s (not final)" if live else ""))
            if s["state"] in ("done", "error", "cancelled"):
                timer.stop()
                if s["state"] == "done":
                    try:
                        self.render(self.engine._req("GET", f"/simulate/{jid}/card", timeout=30))
                    except Exception as e:  # noqa: BLE001
                        self.render({"type": "error", "text": str(e)})
                else:
                    self.render({"type": "error", "text": s.get("error") or "Simulation failed"})
                    bar.setFormat(f"{s['state']} · %v of %m runs")
        timer = QtCore.QTimer(self)
        timer.timeout.connect(tick)
        timer.start(1000)
        self.polls[jid] = timer
        QtCore.QTimer.singleShot(10, tick)
