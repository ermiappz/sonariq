"""SonarIQ dock panel for FreeCAD 1.x (design page 7: PanelHead, P1 Idle, P3 Results, P4 Evidence).

Plain Qt widgets styled by panel.qss (objectName SonarIQPanel). The panel talks to the local SonarIQ engine over
HTTP (default http://127.0.0.1:8765, start it with `make api`). Every verdict and number shown comes from the
engine; this file formats, it never computes a status.

Run standalone (no FreeCAD) for a quick look:  python sonariq_panel.py [--shot out.png] [--rev B] [--finding F-07]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:  # FreeCAD ships a PySide shim (PySide2 or PySide6 underneath)
    from PySide import QtCore, QtGui
    from PySide import QtWidgets  # type: ignore
except ImportError:  # standalone
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ENGINE = os.environ.get("SONARIQ_ENGINE", "http://127.0.0.1:8765")
TOKENS = json.loads((HERE / "tokens.json").read_text())
DARK = TOKENS["dark"]
WORD = TOKENS["status_words"]
GLYPH = TOKENS["status_glyphs"]
ORDER = TOKENS["status_order"]  # fail warn unk pass dor
STATUS_COLOR = {"fail": DARK["st-fail-fill"], "warn": DARK["st-warn-fill"], "unk": DARK["st-unk"],
                "pass": DARK["st-pass-fill"], "acc": DARK["st-acc-fill"]}
GROUPS = [("fls", "Fire & life safety", "FS"), ("acc", "Accessibility", "AC"), ("dnv", "Class · DNV", "CL")]
DISC_SHORT = {"fire_life_safety": "FS", "accessibility": "AC", "structure": "CL", "hvac": "HV"}


# ----------------------------------------------------------------------------------------------- engine client
class Engine:
    def __init__(self, base: str = ENGINE):
        self.base = base.rstrip("/")

    def _req(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def health(self):
        return self._req("GET", "/health", timeout=3)

    def model(self):
        return self._req("GET", "/model")

    def analyse(self, scope="deck:5", packs=None, revision=None, path=None, selection=None):
        return self._req("POST", "/analyse", {"scope": scope, "packs": packs, "revision": revision, "path": path,
                                              "selection": selection})

    def finding(self, fid):
        return self._req("GET", f"/findings/{fid}")

    def fixes(self, fid):
        return self._req("GET", f"/findings/{fid}/fixes", timeout=60)

    def accept(self, fid, reason):
        return self._req("POST", f"/findings/{fid}/accept", {"reason": reason})

    def bcf(self):
        return self._req("POST", "/export/bcf")

    def history(self):
        return self._req("GET", "/history")

    def recheck(self, revision=None):
        return self._req("POST", "/recheck" + (f"?revision={revision}" if revision else ""))


def panel_qss() -> str:
    """design/panel.qss as is, plus one override: text inside cards sits on the card colour, pills keep their tint."""
    d = DARK
    extra = f"""
#SonarIQPanel QFrame[role="card"] QLabel, #SonarIQPanel QFrame[role="card-dashed"] QLabel {{ background: transparent; }}
#SonarIQPanel QFrame QLabel[status="fail"] {{ background: {d['st-fail-tint']}; }}
#SonarIQPanel QFrame QLabel[status="warn"] {{ background: {d['st-warn-tint']}; }}
#SonarIQPanel QFrame QLabel[status="pass"] {{ background: {d['st-pass-tint']}; }}
#SonarIQPanel QFrame QLabel[status="acc"] {{ background: {d['st-acc-tint']}; }}
#SonarIQPanel QFrame QLabel[chip="loc"] {{ background: {d['bg-2']}; }}
"""
    return (HERE / "panel.qss").read_text() + extra


# ----------------------------------------------------------------------------------------------- small widgets
def label(text="", role=None, mono=False, wrap=False, **props):
    w = QtWidgets.QLabel(text)
    if role:
        w.setProperty("role", role)
    if mono:
        w.setProperty("mono", "true")
    for k, v in props.items():
        w.setProperty(k, v)
    w.setWordWrap(wrap)
    if wrap:
        w.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        w.setMinimumWidth(40)
    w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse) if not wrap else None
    return w


def pill(status: str) -> QtWidgets.QLabel:
    """Status pill: glyph + word, never colour alone."""
    w = QtWidgets.QLabel(f"{GLYPH[status]} {WORD[status]}")
    w.setProperty("status", status)
    w.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
    return w


def chip(text, kind="loc"):
    w = QtWidgets.QLabel(text)
    w.setProperty("chip", kind)
    w.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
    return w


def hline():
    f = QtWidgets.QFrame()
    f.setProperty("role", "hr")
    f.setFixedHeight(1)
    return f


def hbox(*ws, spacing=6, stretch_end=True):
    h = QtWidgets.QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(spacing)
    for w in ws:
        if isinstance(w, QtWidgets.QLayout):
            h.addLayout(w)
        elif w is None:
            h.addStretch(1)
        else:
            h.addWidget(w)
    if stretch_end:
        h.addStretch(1)
    return h


def fmt_val(d: dict | None, unit_mode="native") -> str:
    if not d or d.get("value") is None:
        return "?"
    v, u = d["value"], d.get("unit", "")
    if unit_mode == "in" and u == "mm":
        return f"{v / 25.4:.1f} in"
    if unit_mode == "mm" and u == "in" and d.get("alt"):
        return f"{d['alt']['value']:,} mm"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)) and u in ("mm",):
        sign = "−" if v < 0 else ""
        return f"{sign}{abs(v):,.0f} mm"
    if isinstance(v, float):
        return f"{v:g} {u}".strip()
    return f"{v} {u}".strip() if u not in ("class", "bool", "") else str(v)


def rule_badge(c: dict) -> str:
    src = c["source"]
    if src.startswith("SOLAS"):
        src = "SOLAS"
    return f"{src}  {c['clause']}"


def loc_label(f: dict) -> str:
    return (f.get("location") or {}).get("label") or ""


# ----------------------------------------------------------------------------------------------- 3D bridge
class FreeCADBridge:
    """Select and colour IFC objects by GlobalId in the active FreeCAD document. No-op outside FreeCAD."""

    def __init__(self):
        try:
            import FreeCAD  # noqa: F401
            import FreeCADGui  # noqa: F401
            self.ok = True
        except ImportError:
            self.ok = False
        self._orig: dict[str, tuple] = {}

    def _objects(self):
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        return list(doc.Objects) if doc else []

    @staticmethod
    def guid_of(o):
        for attr in ("GlobalId", "IfcGuid"):
            v = getattr(o, attr, None)
            if v:
                return v
        data = getattr(o, "IfcData", None)
        if isinstance(data, dict):
            return data.get("GlobalId") or data.get("IfcUID")
        return None

    def find(self, guid: str | None, name: str | None):
        if not self.ok:
            return []
        hits = [o for o in self._objects() if guid and self.guid_of(o) == guid]
        if not hits and name:
            hits = [o for o in self._objects() if o.Label == name or o.Label.startswith(name + " ")]
        return hits

    def model_path(self) -> str | None:
        if not self.ok:
            return None
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        for o in self._objects():
            p = getattr(o, "IfcFilePath", None)
            if p:
                return p
        return getattr(doc, "FileName", None) if doc and str(getattr(doc, "FileName", "")).endswith(".ifc") else None

    def show(self, f: dict, zoom: bool = True):
        if not self.ok:
            return 0
        import FreeCADGui as Gui
        self.reset()
        el = f.get("element") or {}
        objs = self.find(el.get("guid"), el.get("name"))
        Gui.Selection.clearSelection()
        color = QtGui.QColor(STATUS_COLOR.get(f["status"], DARK["accent"]))
        rgb = (color.redF(), color.greenF(), color.blueF())
        for o in objs:
            vo = getattr(o, "ViewObject", None)
            if vo is not None and hasattr(vo, "ShapeColor"):
                self._orig[o.Name] = (o, vo.ShapeColor, getattr(vo, "LineColor", None))
                vo.ShapeColor = rgb
                if hasattr(vo, "LineColor"):
                    vo.LineColor = rgb
            Gui.Selection.addSelection(o)
        if objs and zoom:
            Gui.SendMsgToActiveView("ViewSelection")
        return len(objs)

    def reset(self):
        for o, sc, lc in self._orig.values():
            try:
                o.ViewObject.ShapeColor = sc
                if lc is not None:
                    o.ViewObject.LineColor = lc
            except Exception:  # noqa: BLE001
                pass
        self._orig.clear()

    def selection_guids(self) -> list[str]:
        if not self.ok:
            return []
        import FreeCADGui as Gui
        return [g for g in (self.guid_of(o) for o in Gui.Selection.getSelection()) if g]


# ----------------------------------------------------------------------------------------------- the panel
class SonarIQPanel(QtWidgets.QWidget):
    def __init__(self, engine: Engine | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SonarIQPanel")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(panel_qss())
        self.engine = engine or Engine()
        self.bridge = FreeCADBridge()
        self.run: dict | None = None
        self.prev_run: dict | None = None
        self.filter: str | None = None
        self.group_by = "discipline"
        self.unit_mode = "native"
        self.current: dict | None = None
        self.revision = os.environ.get("SONARIQ_REV", "A")
        self._build()
        QtCore.QTimer.singleShot(50, self._probe)

    # ---------------- layout
    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        head = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(12, 10, 12, 8)
        word = QtWidgets.QLabel("SonarIQ")
        word.setStyleSheet("font-weight: 700; font-size: 15px;")
        self.proj = label("Demo ship · Rev A", role="faint", mono=True)
        self.live = QtWidgets.QCheckBox("Live")
        self.live.setToolTip("Live re-checks what each change touches. Arrives in build round 2.")
        self.live.setEnabled(False)
        hl.addWidget(word)
        hl.addWidget(self.proj)
        hl.addStretch(1)
        hl.addWidget(self.live)
        root.addWidget(head)
        root.addWidget(hline())

        # context bar
        ctx = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(ctx)
        g.setContentsMargins(12, 8, 12, 8)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        g.addWidget(label("Profile", role="faint"), 0, 0)
        self.profile = chip("Passenger ship · > 36 passengers", "rule")
        g.addWidget(self.profile, 0, 1, 1, 3)
        g.addWidget(label("Scope", role="faint"), 1, 0)
        self.scope_btns = {}
        seg = QtWidgets.QHBoxLayout()
        seg.setSpacing(0)
        for key, text in (("selection", "Selection"), ("deck:5", "Deck 5"), ("whole", "Whole model")):
            b = QtWidgets.QPushButton(text)
            b.setCheckable(True)
            b.setProperty("kind", "ghost")
            b.clicked.connect(lambda _=False, k=key: self._set_scope(k))
            seg.addWidget(b)
            self.scope_btns[key] = b
        self.scope = "deck:5"
        self.scope_btns["deck:5"].setChecked(True)
        self._style_scope()
        seg.addStretch(1)
        g.addLayout(seg, 1, 1, 1, 3)
        g.addWidget(label("Packs", role="faint"), 2, 0, QtCore.Qt.AlignTop)
        packs = QtWidgets.QVBoxLayout()
        packs.setSpacing(4)
        self.pack_boxes = {}
        r1 = QtWidgets.QHBoxLayout()
        for key, text, _ in GROUPS:
            cb = QtWidgets.QCheckBox(text.replace("&", "&&"))
            cb.setChecked(True)
            self.pack_boxes[key] = cb
            if key == "dnv":
                packs.addLayout(r1)
                packs.addLayout(hbox(cb, chip("To verify", "engine")))
            else:
                r1.addWidget(cb)
        r1.addStretch(1)
        g.addLayout(packs, 2, 1, 1, 3)
        root.addWidget(ctx)

        # analyse row
        arow = QtWidgets.QWidget()
        al = QtWidgets.QHBoxLayout(arow)
        al.setContentsMargins(12, 4, 12, 8)
        self.analyse_btn = QtWidgets.QPushButton("Analyse")
        self.analyse_btn.setProperty("kind", "primary")
        self.analyse_btn.setShortcut(QtGui.QKeySequence("Ctrl+Shift+A"))
        self.analyse_btn.clicked.connect(self.analyse)
        self.meta = label("", role="faint", mono=True)
        self.sim_btn = QtWidgets.QPushButton("Simulate")
        self.sim_btn.setToolTip("Evacuation simulation of Deck 5 (night case) · design insight, not a full-ship analysis")
        self.sim_btn.clicked.connect(self.simulate)
        self.sim_btn.setVisible(False)
        al.addWidget(self.analyse_btn)
        al.addWidget(self.sim_btn)
        al.addWidget(self.meta, 1)
        root.addWidget(arow)

        # summary strip
        strip = QtWidgets.QWidget()
        sl = QtWidgets.QHBoxLayout(strip)
        sl.setContentsMargins(12, 0, 12, 8)
        sl.setSpacing(4)
        self.cells = {}
        for st in ORDER:
            b = QtWidgets.QPushButton("—\n" + WORD[st])
            b.setCheckable(True)
            b.setMinimumHeight(44)
            b.setToolTip(f"Show {WORD[st]} only")
            b.clicked.connect(lambda _=False, s=st: self._toggle_filter(s))
            sl.addWidget(b, 1)
            self.cells[st] = b
        root.addWidget(strip)

        # tabs
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.findings_page = QtWidgets.QStackedWidget()
        self.list_scroll = QtWidgets.QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.list_host = QtWidgets.QWidget()
        self.list_layout = QtWidgets.QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(12, 8, 12, 12)
        self.list_layout.setSpacing(6)
        self.list_scroll.setWidget(self.list_host)
        self.ev_scroll = QtWidgets.QScrollArea()
        self.ev_scroll.setWidgetResizable(True)
        self.ev_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.ev_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.list_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.findings_page.addWidget(self.list_scroll)
        self.findings_page.addWidget(self.ev_scroll)
        self.tabs.addTab(self.findings_page, "Findings")
        from chat_view import ChatView
        self.chat = ChatView(self)
        self.tabs.addTab(self.chat, "Chat")
        self.hist = QtWidgets.QPlainTextEdit()
        self.hist.setReadOnly(True)
        self.tabs.addTab(self.hist, "History")
        self.tabs.currentChanged.connect(lambda i: self._load_history() if i == 2 else None)
        root.addWidget(self.tabs, 1)

        # footer
        root.addWidget(hline())
        foot = QtWidgets.QWidget()
        fl = QtWidgets.QHBoxLayout(foot)
        fl.setContentsMargins(12, 6, 12, 6)
        self.foot_l = label("IFC4 · —", role="faint", mono=True)
        self.foot_r = label("Rule engine …", role="faint")
        fl.addWidget(self.foot_l, 1)
        fl.addWidget(self.foot_r)
        root.addWidget(foot)
        self._idle()

    # ---------------- state helpers
    def _style_scope(self):
        for k, b in self.scope_btns.items():
            b.setProperty("kind", "primary" if k == self.scope else "ghost")
            b.style().unpolish(b)
            b.style().polish(b)

    def _set_scope(self, k):
        self.scope = k
        for kk, b in self.scope_btns.items():
            b.setChecked(kk == k)
        self._style_scope()

    def _clear_list(self):
        while self.list_layout.count():
            it = self.list_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())

    def _probe(self):
        try:
            h = self.engine.health()
            m = self.engine.model()
            self.revision = m.get("revision", self.revision)
            self.proj.setText(f"{m.get('name', 'Demo ship')} · Rev {self.revision}")
            ship = m.get("ship", {})
            if ship.get("vessel_type") == "research":
                self.profile.setText(f"Research vessel · {ship.get('persons_on_board')} on board")
            self.foot_l.setText(f"IFC4 · {Path(m.get('path') or '').stem}")
            self.foot_r.setText("Rule engine ready")
            self.analyse_btn.setEnabled(True)
            self.sim_btn.setVisible(bool(h.get("simulate")))
        except Exception as e:  # noqa: BLE001
            self.foot_r.setText("Engine not reachable")
            self.foot_l.setText(f"Start it: make api ({ENGINE})")
            self.analyse_btn.setEnabled(False)
            self._err = str(e)

    def _idle(self):
        self._clear_list()
        self.list_layout.addWidget(label("The checks in 3 packs will run on Deck 5." if not self.run else "",
                                         wrap=True))
        self.list_layout.addWidget(label("The rule engine decides every verdict. It needs no AI and no network.",
                                         role="muted", wrap=True))
        for key, text, _ in GROUPS:
            st = "To verify" if key == "dnv" else "Verified"
            self.list_layout.addLayout(hbox(label(text), None, chip(st, "engine"), stretch_end=False))
        self.list_layout.addWidget(label("Class rules marked To verify still run. Their verdicts carry the To verify "
                                         "tag until the pack is signed off.", role="faint", wrap=True))
        self.list_layout.addSpacing(16)
        t = label("No findings yet", wrap=True)
        t.setAlignment(QtCore.Qt.AlignCenter)
        self.list_layout.addWidget(t)
        s = label("Press Analyse. Findings highlight the objects in the 3D view first, then list here.",
                  role="muted", wrap=True)
        s.setAlignment(QtCore.Qt.AlignCenter)
        self.list_layout.addWidget(s)
        self.list_layout.addStretch(1)

    def _packs(self):
        return [k for k, cb in self.pack_boxes.items() if cb.isChecked()]

    # ---------------- analyse -> P3
    def analyse(self):
        self.analyse_btn.setEnabled(False)
        self.meta.setText("Analysing…")
        QtWidgets.QApplication.processEvents()
        try:
            sel = self.bridge.selection_guids() if self.scope == "selection" else None
            path = self.bridge.model_path()
            self.prev_run = self.run
            self.run = self.engine.analyse(self.scope, self._packs(), revision=None, path=path, selection=sel)
        except Exception as e:  # noqa: BLE001
            self.meta.setText(f"Engine error: {e}")
            self.analyse_btn.setEnabled(True)
            return
        self.analyse_btn.setEnabled(True)
        r = self.run
        import datetime as dt
        self.meta.setText(f"{r['total_checks']} checks · {r['duration_s']:.2f} s · Rev {r['revision']} · "
                          f"{dt.datetime.now():%H:%M}")
        self.proj.setText(f"Demo ship · Rev {r['revision']}")
        for st, b in self.cells.items():
            b.setText(f"{GLYPH[st]} {r['counts'][st]}\n{WORD[st]}")
        n_open = len(r["findings"])
        self.tabs.setTabText(0, f"Findings {n_open}")
        c = r["counts"]
        self.foot_r.setText(f"{c['fail']} fail · {c['warn']} warning · {c['unk']} cannot verify")
        self.render_list()
        self.findings_page.setCurrentIndex(0)

    def simulate(self):
        """Simulate action: a night-case scenario preview in Chat; the engineer confirms before anything runs."""
        self.tabs.setCurrentWidget(self.chat)
        self.chat.send("Simulate night")

    def refresh_after_edit(self):
        """After a confirmed chat edit: re-read the engine's current run (no reload, so the edit is kept)."""
        try:
            self.prev_run = self.run
            self.run = self.engine.analyse(self.scope, self._packs(), revision=None, path=None)
        except Exception as e:  # noqa: BLE001
            self.meta.setText(f"Engine error: {e}")
            return
        r = self.run
        for st, b in self.cells.items():
            b.setText(f"{GLYPH[st]} {r['counts'][st]}\n{WORD[st]}")
        self.tabs.setTabText(0, f"Findings {len(r['findings'])}")
        self.render_list()

    def _toggle_filter(self, st):
        self.filter = None if self.filter == st else st
        for k, b in self.cells.items():
            b.setChecked(k == self.filter)
        if self.run:
            self.render_list()

    def render_list(self):
        self._clear_list()
        r = self.run
        rows = [c for c in r["checks"] if (self.filter is None and c["status"] in ("fail", "warn", "unk"))
                or c["status"] == self.filter]
        title = "Showing open findings" if self.filter is None else f"Showing {WORD[self.filter]}"
        g1 = QtWidgets.QPushButton("Discipline")
        g2 = QtWidgets.QPushButton("Location")
        for b, k in ((g1, "discipline"), (g2, "location")):
            b.setProperty("kind", "primary" if self.group_by == k else "ghost")
            b.clicked.connect(lambda _=False, kk=k: (setattr(self, "group_by", kk), self.render_list()))
        self.list_layout.addLayout(hbox(label(f"{title}  {len(rows)}", role="label"), None, label("Group", role="faint"),
                                        g1, g2, stretch_end=False))
        if self.group_by == "discipline":
            for key, text, short in GROUPS + [("hvac", "HVAC", "HV")]:
                if key not in self._packs():
                    continue
                grp = [c for c in rows if c["group"] == key]
                self._group_header(short, text, len(grp), to_verify=(key == "dnv"))
                if not grp:
                    self.list_layout.addWidget(label("No open findings in this pack.", role="faint"))
                for c in sorted(grp, key=lambda c: (ORDER.index(c["status"]), c["id"] or c["check_key"])):
                    self.list_layout.addWidget(self._row(c))
        else:
            for c in sorted(rows, key=lambda c: ((c["location"] or {}).get("frame") or "", c["id"] or "")):
                self.list_layout.addWidget(self._row(c))
        if self.filter is None:
            cnt = r["counts"]
            more = QtWidgets.QPushButton(f"{GLYPH['pass']} Pass {cnt['pass']}  ·  {GLYPH['dor']} Dormant {cnt['dor']}"
                                         "  — show")
            more.setProperty("kind", "ghost")
            more.clicked.connect(lambda: self._toggle_filter("pass"))
            self.list_layout.addWidget(more)
        self.list_layout.addStretch(1)

    def _group_header(self, short, text, n, to_verify=False):
        bits = [chip(short, "rule"), label(text)]
        if to_verify:
            bits.append(chip("To verify", "engine"))
        self.list_layout.addSpacing(6)
        self.list_layout.addLayout(hbox(*bits, None, label(str(n), role="faint"), stretch_end=False))

    def _row(self, c: dict) -> QtWidgets.QWidget:
        fr = QtWidgets.QFrame()
        fr.setProperty("role", "card-dashed" if c["status"] == "unk" else "card")
        fr.setCursor(QtCore.Qt.PointingHandCursor)
        v = QtWidgets.QVBoxLayout(fr)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        el = (c.get("element") or {}).get("name", "")
        title = label(f"{c['id'] or ''}  {c['title']}".strip(), wrap=True)
        title.setStyleSheet("font-weight: 600;")
        v.addLayout(hbox(pill(c["status"]), title, stretch_end=False))
        chips = [chip(loc_label(c))]
        if el and el not in loc_label(c):
            chips.insert(0, chip(el))
        v.addLayout(hbox(*chips))
        rb = [chip(rule_badge(c), "rule")]
        if c.get("to_verify"):
            rb.append(chip("To verify", "engine"))
        v.addLayout(hbox(*rb))
        v.addWidget(label(c["summary"] or "", role="muted", wrap=True))
        fr.mousePressEvent = lambda ev, cc=c: self.open_evidence(cc)
        return fr

    # ---------------- P4 evidence
    def open_evidence(self, c: dict):
        try:
            f = self.engine.finding(c["id"] or c["check_key"])
        except Exception:  # noqa: BLE001
            f = c
        self.current = f
        n3d = self.bridge.show(f)
        self.ev_scroll.setWidget(self._evidence(f, n3d))
        self.findings_page.setCurrentIndex(1)

    def _open_ids(self):
        return [c["id"] for c in self.run["findings"]] if self.run else []

    def _step(self, d):
        ids = self._open_ids()
        if self.current and self.current.get("id") in ids:
            i = (ids.index(self.current["id"]) + d) % len(ids)
            self.open_evidence(next(c for c in self.run["findings"] if c["id"] == ids[i]))

    def _evidence(self, f: dict, n3d: int) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(12, 8, 12, 12)
        v.setSpacing(8)
        back = QtWidgets.QPushButton("← Findings")
        back.setProperty("kind", "ghost")
        back.clicked.connect(lambda: (self.bridge.reset(), self.findings_page.setCurrentIndex(0)))
        ids = self._open_ids()
        pos = f"{f['id']} · {ids.index(f['id']) + 1} of {len(ids)} open" if f.get("id") in ids else (f.get("id") or "")
        up, dn = QtWidgets.QPushButton("↑"), QtWidgets.QPushButton("↓")
        for b, d in ((up, -1), (dn, 1)):
            b.setProperty("kind", "ghost")
            b.setFixedWidth(28)
            b.clicked.connect(lambda _=False, dd=d: self._step(dd))
        v.addLayout(hbox(back, None, label(pos, role="faint", mono=True), up, dn, stretch_end=False))

        card = QtWidgets.QFrame()
        card.setProperty("role", "card-dashed" if f["status"] == "unk" else "card")
        cv = QtWidgets.QVBoxLayout(card)
        cv.setContentsMargins(12, 10, 12, 12)
        cv.setSpacing(8)
        cv.addLayout(hbox(pill(f["status"]), label(f.get("id") or "", mono=True), None, chip("Rule engine", "engine"),
                          stretch_end=False))
        t = label(f["title"], wrap=True)
        t.setStyleSheet("font-size: 15px; font-weight: 600;")
        cv.addWidget(t)
        el = (f.get("element") or {})
        locs = [chip(loc_label(f))]
        if el.get("name") and el["name"] not in loc_label(f):
            locs.insert(0, chip(el["name"]))
        if f.get("location", {}).get("deck") and "Deck" not in loc_label(f):
            locs.append(chip(f"Deck {f['location']['deck']}"))
        cv.addLayout(hbox(*locs))
        cv.addLayout(hbox(chip(DISC_SHORT.get(f["discipline"], "··"), "rule"), label(f["discipline_label"])))
        cv.addWidget(hline())
        rb = [chip(rule_badge(f), "rule")]
        if f.get("to_verify"):
            rb.append(chip("To verify", "engine"))
        cv.addLayout(hbox(*rb))
        cv.addWidget(label(f["clause_text"], role="muted", wrap=True))

        if f["status"] == "unk":
            box = QtWidgets.QFrame()
            box.setProperty("role", "card-dashed")
            bl = QtWidgets.QVBoxLayout(box)
            bl.addWidget(label("CANNOT VERIFY", role="label"))
            bl.addWidget(label("Missing: " + ", ".join(f.get("missing") or []), wrap=True))
            bl.addWidget(label(f"{f['rule']} needs it. SonarIQ does not guess: add the property in FreeCAD, or confirm "
                               "it with a source and send it to the lead.", role="muted", wrap=True))
            cv.addWidget(box)

        # required / measured / margin + unit toggle
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        for i, (lab, d) in enumerate((("REQUIRED", f.get("required")), ("MEASURED", f.get("measured")),
                                      ("MARGIN", f.get("margin")))):
            grid.addWidget(label(lab, role="label"), 0, i)
            val = label(fmt_val(d, self.unit_mode) if d else "—", mono=True)
            val.setStyleSheet("font-size: 15px; font-weight: 600;")
            grid.addWidget(val, 1, i)
        cv.addLayout(grid)
        units = {(f.get("required") or {}).get("unit"), (f.get("measured") or {}).get("unit")}
        if units & {"mm", "in"}:
            tog = QtWidgets.QPushButton("Units: mm" if self.unit_mode != "in" else "Units: in")
            tog.setProperty("kind", "ghost")
            tog.clicked.connect(self._toggle_units)
            cv.addLayout(hbox(tog))

        if f.get("formula"):
            fo = f["formula"]
            cv.addWidget(label("FORMULA · INPUTS FROM THE MODEL", role="label"))
            fb = QtWidgets.QFrame()
            fb.setProperty("role", "card")
            fl = QtWidgets.QVBoxLayout(fb)
            fl.addWidget(label(fo["text"], mono=True, wrap=True))
            for inp in fo["inputs"]:
                src = "counted from the model" if inp.get("source") == "model" else "persons_by_deck"
                wt = "" if inp["weight"] == 1 else f"{inp['weight']:g} × "
                fl.addWidget(label(f"{inp['name']} = {wt}{inp['value']}  · Deck {inp['deck']} · {src}", mono=True,
                                   wrap=True))
            fl.addWidget(label("= " + fo["worked"], mono=True, wrap=True))
            cv.addWidget(fb)
            prev = self._previous_required(f)
            if prev:
                cv.addWidget(label(prev, role="muted", wrap=True))
        cv.addWidget(label("MEASUREMENT METHOD", role="label"))
        cv.addWidget(label(f.get("method") or "", role="muted", wrap=True))
        try:   # Source text (public sources + our reading, with citation); retrieval never sets a verdict
            src = self.engine._req("GET", f"/findings/{f['id']}/sources", timeout=8)
            hits = (src.get("reading") or []) + (src.get("public") or [])
            if hits:
                cv.addWidget(label("SOURCE TEXT", role="label"))
                if src.get("note"):
                    cv.addWidget(label(src["note"], role="faint", wrap=True))
                for h in hits[:2]:
                    cv.addWidget(label(h["citation"], mono=True, wrap=True))
                    cv.addWidget(label(h["text"][:240].replace("\n", " ") + "…", role="muted", wrap=True))
        except Exception:  # noqa: BLE001
            pass
        if n3d:
            cv.addWidget(label(f"Highlighted in 3D: {n3d} object(s).", role="faint"))
        v.addWidget(card)

        acts = QtWidgets.QGridLayout()
        for i, (text, fn) in enumerate( (("Fix options", self._fixes), ("Accept with reason", self._accept),
                         ("Send to review", self._send), ("Zoom to", lambda: self.bridge.show(self.current)))):
            b = QtWidgets.QPushButton(text)
            if text == "Fix options" and f["status"] not in ("fail", "warn"):
                b.setEnabled(False)
            b.clicked.connect(fn)
            acts.addWidget(b, i // 2, i % 2)
        v.addLayout(acts)
        self.fix_box = QtWidgets.QVBoxLayout()
        v.addLayout(self.fix_box)
        v.addStretch(1)
        return w

    def _previous_required(self, f):
        if not self.prev_run:
            return None
        for c in self.prev_run["checks"]:
            if c["check_key"] == f["check_key"] and c.get("required") and c["revision"] != f["revision"]:
                return (f"Rev {c['revision']} needed {fmt_val(c['required'])} ({c['status_word']}).")
        return None

    def _toggle_units(self):
        self.unit_mode = "in" if self.unit_mode != "in" else "mm"
        if self.current:
            self.ev_scroll.setWidget(self._evidence(self.current, 0))

    def _fixes(self):
        f = self.current
        try:
            fixes = self.engine.fixes(f["id"])
        except Exception as e:  # noqa: BLE001
            self.fix_box.addWidget(label(f"Engine error: {e}", role="faint"))
            return
        self.fix_box.addWidget(label("FIX OPTIONS · EACH RE-CHECKED BY THE RULE ENGINE", role="label"))
        for i, x in enumerate(fixes, 1):
            fr = QtWidgets.QFrame()
            fr.setProperty("role", "card-dashed" if x.get("rejected") else "card")
            fl = QtWidgets.QVBoxLayout(fr)
            head = f"{i}  {x['label']}" if not x.get("rejected") else f"Rejected idea · {x['label']}"
            fl.addLayout(hbox(pill(x["verdict"] if x["verdict"] in GLYPH else "unk"), label(head, wrap=True),
                              stretch_end=False))
            fl.addWidget(label(x["summary"], role="muted", mono=True, wrap=True))
            if x.get("needs"):
                fl.addWidget(chip(f"needs {x['needs']}", "engine"))
            self.fix_box.addWidget(fr)

    def _accept(self):
        f = self.current
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Accept with reason")
        dlg.setObjectName("SonarIQPanel")
        dlg.setStyleSheet(panel_qss())
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(label(f"{f.get('id')} · {f['title']}", wrap=True))
        lay.addWidget(label(f"{f['source']} {f['clause']} · required {fmt_val(f.get('required'))}, measured "
                            f"{fmt_val(f.get('measured'))}", role="muted", wrap=True))
        lay.addWidget(label("Reason (required)", role="label"))
        txt = QtWidgets.QPlainTextEdit()
        lay.addWidget(txt)
        lay.addWidget(label("Goes to: Fire & life safety lead. The engine verdict stays Fail; the status becomes "
                            "Accepted with reason only after approval.", role="faint", wrap=True))
        err = label("", role="faint")
        lay.addWidget(err)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        lay.addWidget(bb)

        def ok():
            if not txt.toPlainText().strip():
                err.setText("Write a reason: the lead signs against it.")
                return
            self.engine.accept(f["id"], txt.toPlainText())
            dlg.accept()
        bb.accepted.connect(ok)
        bb.rejected.connect(dlg.reject)
        dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()

    def _send(self):
        try:
            r = self.engine.bcf()
            QtWidgets.QMessageBox.information(self, "Send to review",
                                              f"BCF written: {r['path']}\n{r['topics']} topics · {r['decisions']} "
                                              f"decisions · {r['open']} open findings")
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Send to review", f"BCF write failed, nothing sent: {e}")

    def _load_history(self):
        try:
            h = self.engine.history()
            lines = []
            for e in h["history"]:
                if e["event"] == "analyse":
                    c = e["counts"]
                    lines.append(f"{e['time']}  Rev {e['revision']} · Analyse · {e['checks']} checks · "
                                 f"{c['fail']}·{c['warn']}·{c['unk']}·{c['pass']}·{c['dor']}")
                else:
                    lines.append(f"{e['time']}  {e['event']} {json.dumps({k: v for k, v in e.items() if k not in ('time', 'event')})[:120]}")
            self.hist.setPlainText("\n".join(lines))
        except Exception as e:  # noqa: BLE001
            self.hist.setPlainText(f"Engine not reachable: {e}")


# ----------------------------------------------------------------------------------------------- entry points
def show_in_freecad():
    import FreeCADGui as Gui
    mw = Gui.getMainWindow()
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if d.objectName() == "SonarIQDock":
            d.show()
            d.raise_()
            return d
    dock = QtWidgets.QDockWidget("SonarIQ", mw)
    dock.setObjectName("SonarIQDock")
    panel = SonarIQPanel()
    dock.setWidget(panel)
    dock.setMinimumWidth(380)
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    return dock


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot")
    ap.add_argument("--finding")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    p = SonarIQPanel()
    p.resize(380, 860)
    p.show()
    if a.analyse or a.finding:
        QtCore.QTimer.singleShot(200, p.analyse)
    if a.finding:
        QtCore.QTimer.singleShot(600, lambda: p.open_evidence({"id": a.finding, "check_key": a.finding}))
    if a.shot:
        QtCore.QTimer.singleShot(1500, lambda: (p.grab().save(a.shot), app.quit()))
    app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    main()
