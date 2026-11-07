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
SUGGEST = ["Simulate night", "Why does F-07 fail?", "Apply fix 2", "Fire near stair 3A at night"]


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
        self.lay.addWidget(_label("Ask why a check fails, describe one of the four allowed edits, or ask for an "
                                  "evacuation simulation. Nothing changes until you confirm.", role="muted"))
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
        self.inp.setPlaceholderText("Ask, describe a change, or 'simulate night'")
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
        elif t == "scenario_preview":
            l.addWidget(_label("Scenario preview · confirm to run", role="faint"))
            l.addWidget(_label(c["text"], bold=True))
            l.addWidget(_label(f"Model {c['model']} · {c['runs']} runs · read by {c.get('source')}", role="muted"))
            if c["scenario"].get("fire_origin"):
                l.addWidget(_label("Illustrative smoke spread, not a fire model.", role="faint"))
            self._buttons(l, f, "Confirm and run", c["confirm"])
        elif t == "ping":
            l.addWidget(_label(f"Applied: {c['text']}", bold=True))
            l.addWidget(_label(f"Re-checked {c['rerun']} checks in {c.get('duration_s')} s", role="muted", mono=True))
            for ch in c.get("changed", []):
                l.addWidget(_label(f"{ch['id']} · {ch.get('title') or ''} → {ch.get('status') or 'cleared'}"))
            k = c.get("counts", {})
            l.addWidget(_label(" · ".join(str(k.get(s, 0)) for s in ("fail", "warn", "unk", "pass", "dor")), mono=True))
        elif t == "sim_progress":
            l.addWidget(_label(f"{c.get('scenario_label')} · {c.get('revision')}", bold=True))
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, int(c.get("runs_target") or 500))
            bar.setValue(int(c.get("runs_done") or 0))
            bar.setFormat("%v / %m runs")
            l.addWidget(bar)
            st = _label(c.get("state", ""), role="faint", mono=True)
            l.addWidget(st)
            l.addWidget(_label(c.get("label", ""), role="faint"))
            self._poll(c["id"], bar, st, c.get("state") == "done")
        elif t == "sim_result":
            l.addWidget(_label(c["title"], bold=True))
            l.addWidget(_label(f"Assembly time p95 {c['tA_p95_s']} s (p50 {c['tA_p50_s']} s) over {c['runs']} runs",
                               mono=True))
            if c.get("worst_landing"):
                l.addWidget(_label(f"Longest landing queue: {c['worst_landing']} · {c['worst_queue_p95']} people (p95)",
                                   mono=True))
            if c.get("last_stair"):
                l.addWidget(_label(f"Clears last: Stair {c['last_stair']} at {c['last_stair_p95_s']} s (p95)", mono=True))
            l.addWidget(_label(c.get("badge", ""), role="faint"))
            l.addWidget(_label(c.get("analyst", "")))
            l.addWidget(_label(c.get("label", ""), role="faint"))
            b = QtWidgets.QPushButton("Open replay")
            b.clicked.connect(lambda _=False, u=c["replay_url"]: QtGui.QDesktopServices.openUrl(QtCore.QUrl(PORTAL + u)))
            l.addWidget(b)
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

    def _buttons(self, l, card, ok_text, action):
        row = QtWidgets.QHBoxLayout()
        ok = QtWidgets.QPushButton(ok_text)
        ok.setProperty("kind", "primary")
        ok.clicked.connect(lambda: self.confirm(action, card))
        no = QtWidgets.QPushButton("Cancel")
        no.setProperty("kind", "ghost")
        no.clicked.connect(lambda: [b.setEnabled(False) for b in card.findChildren(QtWidgets.QPushButton)])
        row.addWidget(ok)
        row.addWidget(no)
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
            if s["state"] in ("done", "error"):
                timer.stop()
                if s["state"] == "done":
                    try:
                        self.render(self.engine._req("GET", f"/simulate/{jid}/card", timeout=30))
                    except Exception as e:  # noqa: BLE001
                        self.render({"type": "error", "text": str(e)})
                else:
                    self.render({"type": "error", "text": s.get("error") or "Simulation failed"})
        timer = QtCore.QTimer(self)
        timer.timeout.connect(tick)
        timer.start(1000)
        self.polls[jid] = timer
        QtCore.QTimer.singleShot(10, tick)
