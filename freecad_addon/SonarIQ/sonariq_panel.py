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
import urllib.parse
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


def _settings() -> dict:
    """Engine URL and login. FreeCAD started from Finder does not see shell variables, so the Mac setup script
    writes ~/.sonariq.json ({"engine": "https://...", "user": "...", "password": "..."}); env vars override."""
    cfg: dict = {}
    for f in (HERE / "config.json", Path.home() / ".sonariq.json"):
        try:
            cfg.update(json.loads(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - missing or unreadable file = defaults
            pass
    for k, env in (("engine", "SONARIQ_ENGINE"), ("user", "SONARIQ_USER"), ("password", "SONARIQ_PASSWORD")):
        if os.environ.get(env):
            cfg[k] = os.environ[env]
    return cfg


SETTINGS = _settings()
ENGINE = SETTINGS.get("engine") or "http://127.0.0.1:8765"
TOKENS = json.loads((HERE / "tokens.json").read_text(encoding="utf-8"))
DARK = TOKENS["dark"]
WORD = TOKENS["status_words"]
GLYPH = TOKENS["status_glyphs"]
ORDER = TOKENS["status_order"]  # fail warn unk pass dor
STATUS_COLOR = {"fail": DARK["st-fail-fill"], "warn": DARK["st-warn-fill"], "unk": DARK["st-unk"],
                "pass": DARK["st-pass-fill"], "acc": DARK["st-acc-fill"]}
GROUPS = [("fls", "Fire & life safety", "FS"), ("acc", "Accessibility", "AC"), ("dnv", "Class · DNV", "CL")]
DISC_SHORT = {"fire_life_safety": "FS", "accessibility": "AC", "structure": "CL", "hvac": "HV"}

# Panel v2 (design page 11): vessel profiles, discipline chips and the packs they drive
PROFILES = ["Passenger ship · > 36 passengers", "Passenger ship · ≤ 36 passengers", "Cargo ship", "Research vessel"]
# (code, name, colour, engine pack or None, rule sets: (label, ok|verify|coming))
DISCS = [
    ("FIRE", "Fire & Safety", "#e392c8", "fls", [("SOLAS II-2", "ok"), ("FSS Code", "ok"), ("LSA Code", "coming")]),
    ("HULL", "Hull & Structure", "#62b8ec", "dnv", [("DNV Pt.3", "verify"), ("Load Line", "coming")]),
    ("INT", "Accommodation & Interiors", "#b39ddb", "acc", [("Accessibility (PVAG/ADA)", "ok"),
                                                            ("SOLAS II-2 materials", "coming")]),
    ("HVAC", "HVAC", "#4fd1d9", "hvac", [("SOLAS II-2/9.7 fire dampers", "ok")]),
    ("GA", "General arrangement", "#c9ccd2", None, []),
    ("PIPE", "Piping", "#7fd18b", None, []),
    ("ELEC", "Electrical", "#f2d04b", None, []),
    ("MACH", "Machinery", "#d9a066", None, []),
]
DEFAULT_DISCS = {"FIRE", "HULL", "INT"}          # = the engine's default packs fls, dnv, acc (demo contract counts)
GROUP_TAG = {"fls": "FIRE", "dnv": "HULL", "acc": "INT", "hvac": "HVAC"}
DISC_COLOR = {d[0]: d[2] for d in DISCS}
COMPONENTS = ["Door", "Stair", "Corridor", "Wall", "Space", "Other"]


def component(c: dict) -> str:
    el = c.get("element") or {}
    cls, name = el.get("ifc_class") or "", el.get("name") or ""
    if cls == "IfcDoor":
        return "Door"
    if cls.startswith("IfcStair"):
        return "Stair"
    if cls == "IfcSpace":
        return "Corridor" if name.startswith("COR") else "Space"
    if cls.startswith("IfcWall"):
        return "Wall"
    return "Other"


def _portal_url() -> str:
    if SETTINGS.get("portal"):
        return SETTINGS["portal"].rstrip("/")
    host = urllib.parse.urlparse(ENGINE).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1"):
        return "http://localhost:5173"
    return ENGINE.rstrip("/").removesuffix("/api")


PORTAL = _portal_url()


# ----------------------------------------------------------------------------------------------- engine client
class Engine:
    def __init__(self, base: str = ENGINE):
        self.base = base.rstrip("/")
        self.headers = {}
        if SETTINGS.get("user") and SETTINGS.get("password"):
            import base64
            tok = base64.b64encode(f"{SETTINGS['user']}:{SETTINGS['password']}".encode()).decode()
            self.headers["Authorization"] = "Basic " + tok
        host = urllib.parse.urlparse(self.base).hostname or ""
        self.remote = host not in ("127.0.0.1", "localhost", "::1")
        self._uploaded: dict = {}   # (path, mtime, size) -> upload answer

    def _raw(self, method: str, path: str, data: bytes | None, ctype: str, timeout: float):
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": ctype, **self.headers})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def _req(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        return json.loads(self._raw(method, path, data, "application/json", timeout).decode())

    def upload(self, path: str) -> dict:
        """Remote engine: send the IFC bytes once per file version. Demo files come back as their revision."""
        st = os.stat(path)
        key = (path, st.st_mtime, st.st_size)
        if key not in self._uploaded:
            with open(path, "rb") as f:
                data = f.read()
            q = urllib.parse.quote(os.path.basename(path))
            self._uploaded[key] = json.loads(self._raw("POST", f"/upload?name={q}", data,
                                                       "application/octet-stream", 300).decode())
        return self._uploaded[key]

    def download(self, path: str) -> bytes:
        return self._raw("GET", path, None, "application/json", 60)

    def health(self):
        return self._req("GET", "/health", timeout=3)

    def model(self):
        return self._req("GET", "/model")

    def analyse(self, scope="deck:5", packs=None, revision=None, path=None, selection=None):
        if path and self.remote:
            u = self.upload(path)
            revision, path = u.get("revision"), u.get("path")
        return self._req("POST", "/analyse", {"scope": scope, "packs": packs, "revision": revision, "path": path,
                                              "selection": selection}, timeout=120)

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
    return (HERE / "panel.qss").read_text(encoding="utf-8") + extra


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
        self._ghost: dict[str, tuple] = {}
        self._hidden: dict = {}
        self._focus: set = set()

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
        if not hits and guid:
            o = self._load_element(guid)
            hits = [o] if o is not None else []
        return hits

    def _load_element(self, guid: str):
        """Model opened lightweight (NativeIFC "Only root object" / "Project structure"): create just this
        element's object from the IFC so the finding can be selected and coloured. Returns None if not possible."""
        try:
            import FreeCAD
            from nativeifc import ifc_tools
            doc = FreeCAD.ActiveDocument
            path = getattr(doc, "IfcFilePath", None) if doc else None
            if not path:
                return None
            if getattr(self, "_ifc_path", None) != path:
                self._ifc_path, self._ifc_file = path, ifc_tools.get_ifcfile(doc)
            ent = self._ifc_file.by_guid(guid)
            obj = ifc_tools.create_object(ent, doc, self._ifc_file, shapemode=0)
            doc.recompute()
            return obj
        except Exception:  # noqa: BLE001 - not NativeIFC, element not in file, or older FreeCAD
            return None

    def model_path(self) -> str | None:
        if not self.ok:
            return None
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return None
        p = getattr(doc, "IfcFilePath", None)      # NativeIFC single-document mode keeps it on the document
        if p:
            return p
        for o in self._objects():
            p = getattr(o, "IfcFilePath", None)    # NativeIFC project object (multi-document mode)
            if p:
                return p
        return doc.FileName if str(getattr(doc, "FileName", "")).lower().endswith(".ifc") else None

    def has_document(self) -> bool:
        if not self.ok:
            return False
        import FreeCAD
        return FreeCAD.ActiveDocument is not None

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


    # ---- v2: focus (colour + select + zoom + ghost the rest), isolate, show all, select inverse
    def _shapes(self):
        out = []
        for o in self._objects():
            vo = getattr(o, "ViewObject", None)
            if vo is not None and hasattr(vo, "Transparency") and hasattr(o, "Shape"):
                out.append(o)
        return out

    def _unghost(self):
        for o, t in self._ghost.values():
            try:
                o.ViewObject.Transparency = t
            except Exception:  # noqa: BLE001 - object deleted or document closed
                pass
        self._ghost.clear()

    def _unhide(self):
        for o in self._hidden.values():
            try:
                o.ViewObject.Visibility = True
            except Exception:  # noqa: BLE001
                pass
        self._hidden.clear()

    def focus(self, f: dict, zoom: bool = True, ghost: bool = True) -> int:
        """Select and colour the finding's element by status, zoom to it, ghost everything else (15 % opacity)."""
        n = self.show(f, zoom=False)
        if not self.ok or not n:
            return n
        import FreeCADGui as Gui
        keep = {o.Name for o in Gui.Selection.getSelection()}
        self._focus = keep
        if ghost:
            for o in self._shapes():
                if o.Name not in keep and o.Name not in self._ghost:
                    self._ghost[o.Name] = (o, o.ViewObject.Transparency)
                    o.ViewObject.Transparency = 85
        if zoom:
            Gui.SendMsgToActiveView("ViewSelection")
        return n

    def zoom(self):
        if self.ok:
            import FreeCADGui as Gui
            Gui.SendMsgToActiveView("ViewSelection")

    def isolate(self, f: dict) -> int:
        """Show only the finding's element(s)."""
        n = self.focus(f, zoom=False, ghost=False)
        if not self.ok or not n:
            return n
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        focus = [doc.getObject(nm) for nm in self._focus if doc.getObject(nm)]
        keep = set(self._focus)
        for o in focus:   # the element's own parts (e.g. a stair's flights) stay
            keep |= {c.Name for c in getattr(o, "OutListRecursive", [])}
        for o in self._shapes():
            if o.Name not in keep and o.ViewObject.Visibility:
                self._hidden[o.Name] = o
                o.ViewObject.Visibility = False
        # hiding a container also hides its children: switch the element and its parts back on afterwards
        for nm in keep:
            o = doc.getObject(nm)
            if o is not None and getattr(o, "ViewObject", None) is not None and not o.ViewObject.Visibility:
                o.ViewObject.Visibility = True
        self.zoom()
        return n

    def show_all(self):
        """Everything visible and opaque again; the finding stays coloured and selected."""
        self._unhide()
        self._unghost()
        if self.ok:
            import FreeCADGui as Gui
            Gui.SendMsgToActiveView("ViewFit")

    def select_inverse(self) -> int:
        if not self.ok:
            return 0
        import FreeCADGui as Gui
        cur = {o.Name for o in Gui.Selection.getSelection()}
        Gui.Selection.clearSelection()
        n = 0
        for o in self._shapes():
            if o.Name not in cur and o.ViewObject.Visibility:
                Gui.Selection.addSelection(o)
                n += 1
        return n

    def reset_all(self):
        """Back to the model as opened: colours, transparency, visibility, selection."""
        self._unhide()
        self._unghost()
        self.reset()
        self._focus = set()
        if self.ok:
            try:
                import FreeCADGui as Gui
                Gui.Selection.clearSelection()
            except Exception:  # noqa: BLE001
                pass

    def doc_key(self):
        if not self.ok:
            return None
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        return (doc.Name, self.model_path()) if doc else None

    def frame_model(self):
        """On model open: hide the Model/Combo view, isometric view, fit all."""
        if not self.ok:
            return
        import FreeCADGui as Gui
        set_tree_visible(False)
        try:
            v = Gui.activeDocument().activeView()
            v.viewIsometric()
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:  # noqa: BLE001 - no 3D view yet
            pass


TREE_DOCKS = ("Combo View", "Model", "Tree view", "Property view", "Tasks", "BIM Views Manager")


def set_tree_visible(on: bool | None = None) -> bool:
    """Show/hide FreeCAD's Model (Combo) view. on=None toggles. Returns the new state."""
    try:
        import FreeCADGui as Gui
    except ImportError:
        return False
    docks = [d for d in Gui.getMainWindow().findChildren(QtWidgets.QDockWidget) if d.objectName() in TREE_DOCKS]
    if not docks:
        return False
    if on is None:
        on = not any(d.isVisible() for d in docks)
    for d in docks:
        d.setVisible(on)
    return on


# ----------------------------------------------------------------------------------------------- the panel
class SonarIQPanel(QtWidgets.QWidget):
    """Panel v2 (design page 11): header with the open model + Analyse/Export, profile, scope, discipline chips;
    results as compact cards; a card click colours, selects and zooms the element and ghosts the rest."""

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
        self.f_disc = self.f_deck = self.f_comp = None
        self.group_by = "discipline"
        self.unit_mode = "native"
        self.current: dict | None = None
        self.revision = os.environ.get("SONARIQ_REV", "A")
        self.engine_ok = False
        self.ship: dict = {}
        self.detected_profile: str | None = None
        self._busy = False
        self._result = None
        self._doc_key = None
        self._framed: set = set()
        self._cards: dict = {}
        self._build()
        self._spin = QtCore.QTimer(self)
        self._spin.timeout.connect(self._tick)
        self._watch = QtCore.QTimer(self)
        self._watch.timeout.connect(self._check_doc)
        self._watch.start(700)
        QtCore.QTimer.singleShot(50, self._probe)
        QtCore.QTimer.singleShot(60, self._check_doc)

    # ================================================================ layout
    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header: SonarIQ · model chip · Analyse · Export
        head = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(12, 10, 12, 8)
        hl.setSpacing(8)
        word = QtWidgets.QLabel("SonarIQ")
        word.setStyleSheet("font-weight: 700; font-size: 15px;")
        self.proj = label("No model open", role="faint", mono=True)
        self.proj.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self.analyse_btn = QtWidgets.QPushButton("Analyse")
        self.analyse_btn.setProperty("kind", "primary")
        self.analyse_btn.setShortcut(QtGui.QKeySequence("Ctrl+Shift+A"))
        self.analyse_btn.clicked.connect(self.analyse)
        self.export_btn = QtWidgets.QPushButton("Export")
        self.export_btn.setToolTip("Open this run in the portal Inbox")
        self.export_btn.clicked.connect(self.export)
        self.export_btn.setVisible(False)
        hl.addWidget(word)
        hl.addWidget(self.proj, 1)
        hl.addWidget(self.analyse_btn)
        hl.addWidget(self.export_btn)
        self.ai_btn = QtWidgets.QPushButton("✦ Assistant")
        self.ai_btn.setStyleSheet("QPushButton { color: #e392c8; border: 1px solid #e392c8; border-radius: 4px; "
                                  "padding: 0 8px; min-height: 26px; font-weight: 600; background: transparent; }")
        self.ai_btn.setToolTip("Assistant Engineer · ask why a check fails or describe a change")
        self.ai_btn.clicked.connect(self.show_assistant)
        hl.addWidget(self.ai_btn)
        root.addWidget(head)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar{border:0;background:#24262b;} QProgressBar::chunk{background:#e392c8;}")
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        root.addWidget(hline())

        # ---- setup: profile · scope · disciplines (collapses to one line after results)
        self.setup = QtWidgets.QWidget()
        sv = QtWidgets.QVBoxLayout(self.setup)
        sv.setContentsMargins(12, 10, 12, 10)
        sv.setSpacing(6)
        sv.addWidget(label("PROFILE", role="label"))
        self.profile_box = QtWidgets.QComboBox()
        self.profile_box.addItems(PROFILES)
        self.profile_box.currentIndexChanged.connect(self._profile_changed)
        sv.addWidget(self.profile_box)
        self.profile_cap = label("Detected after the model is read", role="faint", wrap=True)
        sv.addWidget(self.profile_cap)
        self.profile_warn = QtWidgets.QFrame()
        self.profile_warn.setStyleSheet("QFrame{background: rgba(230,159,0,.10); border: 1px solid #e69f00; "
                                        "border-radius: 4px;} QLabel{background: transparent; border: 0;}")
        wl = QtWidgets.QVBoxLayout(self.profile_warn)
        wl.setContentsMargins(10, 8, 10, 8)
        wt = QtWidgets.QLabel("⚠ Warning")
        wt.setStyleSheet("color: #e69f00; font-weight: 600;")
        wl.addWidget(wt)
        self.profile_warn_txt = label("", wrap=True)
        wl.addWidget(self.profile_warn_txt)
        keep, rev = QtWidgets.QPushButton("Keep"), QtWidgets.QPushButton("Revert")
        rev.setProperty("kind", "primary")
        keep.clicked.connect(lambda: self.profile_warn.setVisible(False))
        rev.clicked.connect(self._profile_revert)
        wl.addLayout(hbox(keep, rev))
        self.profile_warn.setVisible(False)
        sv.addWidget(self.profile_warn)

        sv.addSpacing(4)
        tree = QtWidgets.QPushButton("Show tree")
        tree.setProperty("kind", "ghost")
        tree.setCursor(QtCore.Qt.PointingHandCursor)
        tree.clicked.connect(lambda: tree.setText("Hide tree" if set_tree_visible() else "Show tree"))
        self.tree_btn = tree
        sv.addLayout(hbox(label("SCOPE", role="label"), None, tree, stretch_end=False))
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
        sv.addLayout(seg)

        sv.addSpacing(4)
        sv.addWidget(label("DISCIPLINES", role="label"))
        chips = QtWidgets.QGridLayout()
        chips.setSpacing(4)
        self.disc_btns = {}
        allb = QtWidgets.QPushButton("All")
        allb.setCheckable(True)
        allb.clicked.connect(self._disc_all)
        allb.setStyleSheet(self._chip_qss("#b7bbc3"))
        self.disc_all = allb
        chips.addWidget(allb, 0, 0)
        for i, (code, name, color, pack, _) in enumerate(DISCS, 1):
            b = QtWidgets.QPushButton(code)
            b.setCheckable(True)
            b.setChecked(code in DEFAULT_DISCS)
            b.setToolTip(name + ("" if pack else " · rule sets coming"))
            b.setStyleSheet(self._chip_qss(color))
            b.clicked.connect(self._disc_changed)
            chips.addWidget(b, i // 5, i % 5)
            self.disc_btns[code] = b
        sv.addLayout(chips)
        self.rulesets = QtWidgets.QFrame()
        self.rulesets.setProperty("role", "card")
        self.rs_lay = QtWidgets.QVBoxLayout(self.rulesets)
        self.rs_lay.setContentsMargins(10, 8, 10, 8)
        self.rs_lay.setSpacing(3)
        sv.addWidget(self.rulesets)
        root.addWidget(self.setup)
        self._render_rulesets()

        # ---- collapsed summary (after results)
        self.summary = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self.summary)
        sl.setContentsMargins(12, 8, 12, 4)
        sl.setSpacing(2)
        self.sum_l = label("")
        edit = QtWidgets.QPushButton("Edit")
        edit.setProperty("kind", "ghost")
        edit.clicked.connect(lambda: (self.setup.setVisible(not self.setup.isVisible())))
        sum_row = QtWidgets.QHBoxLayout()
        sum_row.addWidget(self.sum_l, 1)
        sum_row.addWidget(edit)
        sl.addLayout(sum_row)
        self.meta = label("", role="faint", mono=True, wrap=True)
        sl.addWidget(self.meta)
        self.summary.setVisible(False)
        root.addWidget(self.summary)

        # ---- results: status chips · filter row
        self.results = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(self.results)
        rl.setContentsMargins(12, 6, 12, 6)
        rl.setSpacing(6)
        strip = QtWidgets.QHBoxLayout()
        strip.setSpacing(6)
        self.cells = {}
        for st in ORDER:
            b = QtWidgets.QPushButton(f"{GLYPH[st]} — {WORD[st]}")
            b.setCheckable(True)
            b.setToolTip(f"Show {WORD[st]} only")
            b.setStyleSheet(self._status_qss(st))
            b.clicked.connect(lambda _=False, s=st: self._toggle_filter(s))
            strip.addWidget(b)
            self.cells[st] = b
        rl.addLayout(strip)
        self.fbox = {}
        frow = QtWidgets.QHBoxLayout()
        frow.setSpacing(4)
        for key, text in (("disc", "Discipline"), ("deck", "Deck"), ("comp", "Component")):
            cb = QtWidgets.QComboBox()
            cb.addItem(text, None)
            cb.currentIndexChanged.connect(lambda _=0, k=key: self._filter_changed(k))
            frow.addWidget(cb, 1)
            self.fbox[key] = cb
        clr = QtWidgets.QPushButton("Clear all")
        clr.setProperty("kind", "ghost")
        clr.clicked.connect(self._clear_filters)
        frow.addWidget(clr)
        rl.addLayout(frow)
        self.results.setVisible(False)
        root.addWidget(self.results)

        # ---- tabs: Findings · History
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setElideMode(QtCore.Qt.ElideNone)
        self.tabs.tabBar().setStyleSheet("QTabBar::tab { min-width: 96px; }")
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
        self.hist = QtWidgets.QPlainTextEdit()
        self.hist.setReadOnly(True)
        self.tabs.addTab(self.hist, "History")
        from chat_view import ChatView
        self.chat = ChatView(self)
        self.chat_tab = True     # FreeCAD moves the chat into its own (floatable) dock, see show_in_freecad
        self.tabs.addTab(self.chat, "Assistant")
        self.tabs.currentChanged.connect(lambda i: self._load_history() if self.tabs.widget(i) is self.hist else None)
        root.addWidget(self.tabs, 1)

        # ---- footer
        root.addWidget(hline())
        foot = QtWidgets.QWidget()
        fl = QtWidgets.QHBoxLayout(foot)
        fl.setContentsMargins(12, 6, 12, 6)
        self.foot_l = label("—", role="faint", mono=True)
        self.foot_r = label("Rule engine …", role="faint")
        fl.addWidget(self.foot_l, 1)
        fl.addWidget(self.foot_r)
        root.addWidget(foot)
        self._idle()
        self._update_analyse_state()

    # ================================================================ styles
    @staticmethod
    def _chip_qss(color):
        return (f"QPushButton {{ background: transparent; color: #959aa4; border: 1px solid #34373e; border-radius: 4px;"
                f" padding: 0 8px; min-height: 24px; font-family: 'IBM Plex Mono'; font-size: 11px; font-weight: 600; }}"
                f" QPushButton:checked {{ color: {color}; border-color: {color}; background: #24262b; }}")

    @staticmethod
    def _status_qss(st):
        col = {"fail": DARK["st-fail"], "warn": DARK["st-warn"], "unk": DARK["st-unk"], "pass": DARK["st-pass"],
               "dor": DARK["st-dor"]}[st]
        return (f"QPushButton {{ background: transparent; color: {col}; border: 1px solid #34373e; border-radius: 4px;"
                f" padding: 0 5px; min-height: 26px; font-size: 12px; }}"
                f" QPushButton:checked {{ border-color: {col}; background: #24262b; }}")

    # ================================================================ header / document state
    def _update_analyse_state(self):
        if self._busy:
            return
        has = bool(self._doc_key and self._doc_key[1]) or not self.bridge.ok
        if not self.engine_ok:
            self.analyse_btn.setEnabled(False)
            self.analyse_btn.setToolTip("Engine not reachable")
        elif not has:
            self.analyse_btn.setEnabled(False)
            self.analyse_btn.setToolTip("Open an IFC model to analyse")
        else:
            self.analyse_btn.setEnabled(True)
            self.analyse_btn.setToolTip("Run the rule engine on the open model (Ctrl+Shift+A)")

    def _check_doc(self):
        """Poll the active document: a new or closed document resets the panel."""
        try:
            key = self.bridge.doc_key()
        except Exception:  # noqa: BLE001 - document being closed
            key = None
        if key == self._doc_key:
            return
        self._doc_key = key
        self._reset_for_document()
        if key and key[1] and key not in self._framed:
            self._framed.add(key)
            QtCore.QTimer.singleShot(400, self.bridge.frame_model)
            self.tree_btn.setText("Show tree")

    def _reset_for_document(self):
        try:
            self.bridge.reset_all()
        except Exception:  # noqa: BLE001
            pass
        self.bridge._orig.clear()
        self.bridge._ghost.clear()
        self.bridge._hidden.clear()
        self.run = None
        self.current = None
        self.filter = None
        self._result = None
        self.export_btn.setVisible(False)
        self.summary.setVisible(False)
        self.results.setVisible(False)
        self.setup.setVisible(True)
        self.meta.setText("")
        self.tabs.setTabText(0, "Findings")
        self.findings_page.setCurrentIndex(0)
        for st, b in self.cells.items():
            b.setText(f"{GLYPH[st]} — {WORD[st]}")
            b.setChecked(False)
        if self.bridge.ok:
            name = Path(self._doc_key[1]).stem if self._doc_key and self._doc_key[1] else None
            self.proj.setText(name or ("Document has no IFC file" if self._doc_key else "No model open"))
            self.foot_l.setText(name or "—")
        self.detected_profile = None
        self.profile_cap.setText("Detected after the model is read")
        self.profile_warn.setVisible(False)
        self._idle()
        self._update_analyse_state()

    def _probe(self):
        try:
            h = self.engine.health()
            self.engine_ok = True
            self.foot_r.setText("Rule engine ready")
            if not self.bridge.ok:   # standalone: show the engine's current model
                m = self.engine.model()
                self.revision = m.get("revision", self.revision)
                self.proj.setText(f"{Path(m.get('path') or 'model').stem} · Rev {self.revision}")
                self._set_profile_from(m.get("ship") or {})
            self._sim = bool(h.get("simulate"))
        except Exception as e:  # noqa: BLE001
            self.engine_ok = False
            self.foot_r.setText("Engine not reachable")
            self.foot_l.setText(f"Start it: make api ({ENGINE})" if not self.engine.remote
                                else f"Check ~/.sonariq.json ({ENGINE})")
            self._err = str(e)
        self._update_analyse_state()

    # ================================================================ profile
    def _set_profile_from(self, ship: dict):
        self.ship = ship or {}
        vt = self.ship.get("vessel_type")
        pax = self.ship.get("passengers")
        pob = self.ship.get("persons_on_board")
        prof = None
        if vt == "passenger":
            prof = PROFILES[0] if (pax or 0) > 36 else PROFILES[1]
        elif vt == "research":
            prof = PROFILES[3]
        elif vt == "cargo":
            prof = PROFILES[2]
        self.detected_profile = prof
        if prof:
            self.profile_box.blockSignals(True)
            self.profile_box.setCurrentText(prof)
            self.profile_box.blockSignals(False)
            bits = [f"{pax:,} passengers" if pax else None, f"{pob:,} on board" if pob else None]
            self.profile_cap.setText("Detected from model · " + " · ".join(b for b in bits if b) + " (SonarIQ_Ship)")
        else:
            self.profile_cap.setText("Not in the model · pick the vessel class")
        self.profile_warn.setVisible(False)

    def _profile_changed(self, _=0):
        cur = self.profile_box.currentText()
        if self.detected_profile and cur != self.detected_profile:
            n = self.ship.get("persons_on_board") or self.ship.get("passengers")
            self.profile_warn_txt.setText(
                f"The model says {self.detected_profile}" + (f" ({n:,} persons)" if n else "") +
                f". {cur} rules skip or change passenger-ship checks. This build still runs the rules on the "
                "profile the model carries.")
            self.profile_warn.setVisible(True)
        else:
            self.profile_warn.setVisible(False)

    def _profile_revert(self):
        if self.detected_profile:
            self.profile_box.setCurrentText(self.detected_profile)
        self.profile_warn.setVisible(False)

    # ================================================================ disciplines
    def _disc_all(self):
        on = self.disc_all.isChecked()
        for b in self.disc_btns.values():
            b.setChecked(on)
        self._render_rulesets()

    def _disc_changed(self):
        self.disc_all.setChecked(all(b.isChecked() for b in self.disc_btns.values()))
        self._render_rulesets()

    def _selected_discs(self):
        return [code for code, b in self.disc_btns.items() if b.isChecked()]

    def _render_rulesets(self):
        self._clear_layout(self.rs_lay)
        self.rs_lay.addWidget(label("Rule sets selected automatically", role="faint"))
        sel = self._selected_discs()
        if not sel:
            self.rs_lay.addWidget(label("Pick at least one discipline.", role="muted"))
        for code, name, color, pack, sets in DISCS:
            if code not in sel:
                continue
            tag = QtWidgets.QLabel(code)
            tag.setStyleSheet(f"color: {color}; font-family: 'IBM Plex Mono'; font-size: 11px; font-weight: 700; "
                              "background: transparent;")
            tag.setFixedWidth(40)
            parts = []
            for s, st in (sets or [("No rule sets yet", "coming")]):
                if st == "ok":
                    parts.append(f"<span style='color:#e9eaed'>{s} ✓</span>")
                elif st == "verify":
                    parts.append(f"<span style='color:#e69f00'>{s} · To verify</span>")
                else:
                    parts.append(f"<span style='color:#6b7079'>{s} · Coming</span>")
            t = QtWidgets.QLabel("&nbsp;&nbsp;".join(parts))
            t.setTextFormat(QtCore.Qt.RichText)
            t.setWordWrap(True)
            t.setStyleSheet("background: transparent;")
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(tag, 0, QtCore.Qt.AlignTop)
            row.addWidget(t, 1)
            self.rs_lay.addLayout(row)

    def _packs(self):
        sel = self._selected_discs()
        return [pack for code, _, _, pack, _ in DISCS if pack and code in sel]

    # ================================================================ state helpers
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
        self._cards = {}
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

    def _idle(self):
        self._clear_list()
        if self.bridge.ok and not (self._doc_key and self._doc_key[1]):
            t = label("Open an IFC file (File → Open) to start", role="muted", wrap=True)
            t.setAlignment(QtCore.Qt.AlignCenter)
            self.list_layout.addStretch(1)
            self.list_layout.addWidget(t)
            self.list_layout.addStretch(2)
            return
        self.list_layout.addWidget(label("Ready · press Analyse", wrap=True))
        self.list_layout.addWidget(label("The rule engine decides every verdict. Findings show on the model first.",
                                         role="muted", wrap=True))
        self.list_layout.addStretch(1)

    # ================================================================ analyse (runs off the UI thread)
    def analyse(self):
        if self._busy:
            return
        sel = self.bridge.selection_guids() if self.scope == "selection" else None
        path = self.bridge.model_path()
        if self.bridge.ok and path is None:
            # never analyse the engine's current model in place of the document on screen
            self.meta.setText("Open an IFC model to analyse (File → Open, NativeIFC).")
            self.foot_r.setText("No IFC document")
            return
        packs = self._packs()
        if not packs:
            self.foot_r.setText("Pick a discipline with rule sets")
            return
        self._busy = True
        self._result = None
        self._started_for = self._doc_key
        self.analyse_btn.setEnabled(False)
        self.analyse_btn.setText("◐ Analysing…")
        self.progress.setVisible(True)
        self.foot_r.setText("Analysing…")
        self.bridge.reset_all()
        scope = self.scope

        def work():
            try:
                self._result = ("ok", self.engine.analyse(scope, packs, revision=None, path=path, selection=sel))
            except Exception as e:  # noqa: BLE001
                self._result = ("err", e)
        import threading
        threading.Thread(target=work, daemon=True).start()
        self._spin_i = 0
        self._spin.start(120)

    def _tick(self):
        self._spin_i += 1
        self.analyse_btn.setText("◐◓◑◒"[self._spin_i % 4] + " Analysing…")
        if self._result is None:
            return
        self._spin.stop()
        kind, val = self._result
        self._result = None
        self._busy = False
        self.analyse_btn.setText("Analyse")
        self.progress.setVisible(False)
        self._update_analyse_state()
        if self._started_for != self._doc_key:
            return   # the document changed while the engine was busy: drop the stale result
        if kind == "err":
            self.foot_r.setText("Engine error")
            self.meta.setText(f"Engine error: {val}")
            self.summary.setVisible(True)
            return
        self.prev_run = self.run
        self._apply_run(val)

    def wait_idle(self, timeout: float = 180):
        """For scripted checks: process events until the running Analyse has finished."""
        import time
        t0 = time.time()
        while self._busy and time.time() - t0 < timeout:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.05)
        return not self._busy

    def _apply_run(self, r: dict):
        import datetime as dt
        self.run = r
        self.revision = r.get("revision") or self.revision
        if r.get("scope_note"):   # the engine fell back to the whole model (e.g. an RCRV deck has no Deck 5)
            self._set_scope("whole")
            self.meta.setToolTip(r["scope_note"])
        else:
            self.meta.setToolTip("")
        try:
            self._set_profile_from(self.engine.model().get("ship") or {})
        except Exception:  # noqa: BLE001
            pass
        name = Path(self._doc_key[1]).stem if self._doc_key and self._doc_key[1] else Path(
            str(r.get("path") or "model")).stem
        self.proj.setText(f"{name} · Rev {r['revision']}")
        scope_t = {"deck:5": "Deck 5", "whole": "Whole model", "selection": "Selection"}.get(self.scope, self.scope)
        discs = " ".join(c for c in self._selected_discs() if dict((d[0], d[3]) for d in DISCS).get(c))
        self.sum_l.setText(f"{self.profile_box.currentText().split(' ·')[0]} · {scope_t} · {discs}")
        self.meta.setText(f"Rev {r['revision']} · {r['total_checks']} checks · {r['duration_s']:.2f} s · "
                          f"{dt.datetime.now():%H:%M}" + (" · whole model" if r.get("scope_note") else ""))
        self.setup.setVisible(False)
        self.summary.setVisible(True)
        self.results.setVisible(True)
        self.export_btn.setVisible(bool((r.get("run_meta") or {}).get("id")))
        for st, b in self.cells.items():
            b.setText(f"{GLYPH[st]} {r['counts'][st]} {WORD[st]}")
        self._fill_filters()
        self.tabs.setTabText(0, f"Findings {len(r['findings'])}")
        c = r["counts"]
        self.foot_r.setText(f"{c['fail']} fail · {c['warn']} warning · {c['unk']} cannot verify")
        self.render_list()
        self.findings_page.setCurrentIndex(0)

    def refresh_after_edit(self):
        """After a confirmed chat edit: re-read the engine's current run (no reload, so the edit is kept)."""
        try:
            self.prev_run = self.run
            r = self.engine.analyse(self.scope, self._packs(), revision=None, path=None)
        except Exception as e:  # noqa: BLE001
            self.meta.setText(f"Engine error: {e}")
            return
        self._apply_run(r)

    def export(self):
        rid = ((self.run or {}).get("run_meta") or {}).get("id")
        if not rid:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(f"{PORTAL}/#inbox/{rid}"))

    def show_assistant(self):
        if self.chat_tab:
            self.tabs.setCurrentWidget(self.chat)
            return
        dock = self.chat.parentWidget()
        while dock is not None and not isinstance(dock, QtWidgets.QDockWidget):
            dock = dock.parentWidget()
        if dock is not None:
            dock.show()
            dock.raise_()
            self.chat.inp.setFocus()

    # ================================================================ filters + list
    def _fill_filters(self):
        checks = self.run["checks"]
        opts = {
            "disc": sorted({GROUP_TAG.get(c["group"], c["group"]) for c in checks}),
            "deck": sorted({str((c.get("location") or {}).get("deck")) for c in checks
                            if (c.get("location") or {}).get("deck")}),
            "comp": [k for k in COMPONENTS if any(component(c) == k for c in checks)],
        }
        for key, cb in self.fbox.items():
            cb.blockSignals(True)
            head = cb.itemText(0)
            cb.clear()
            cb.addItem(head, None)
            for o in opts[key]:
                cb.addItem(f"Deck {o}" if key == "deck" else o, o)
            cb.blockSignals(False)
        self.f_disc = self.f_deck = self.f_comp = None

    def _filter_changed(self, key):
        val = self.fbox[key].currentData()
        setattr(self, "f_" + key, val)
        if self.run:
            self.render_list()

    def _clear_filters(self):
        for cb in self.fbox.values():
            cb.blockSignals(True)
            cb.setCurrentIndex(0)
            cb.blockSignals(False)
        self.f_disc = self.f_deck = self.f_comp = None
        self.filter = None
        for b in self.cells.values():
            b.setChecked(False)
        if self.run:
            self.render_list()

    def _toggle_filter(self, st):
        self.filter = None if self.filter == st else st
        for k, b in self.cells.items():
            b.setChecked(k == self.filter)
        if self.run:
            self.render_list()

    def _rows(self):
        r = self.run
        rows = [c for c in r["checks"] if (self.filter is None and c["status"] in ("fail", "warn", "unk"))
                or c["status"] == self.filter]
        if self.f_disc:
            rows = [c for c in rows if GROUP_TAG.get(c["group"], c["group"]) == self.f_disc]
        if self.f_deck:
            rows = [c for c in rows if str((c.get("location") or {}).get("deck")) == self.f_deck]
        if self.f_comp:
            rows = [c for c in rows if component(c) == self.f_comp]
        return rows

    def render_list(self):
        self._clear_list()
        rows = self._rows()
        title = "Open findings" if self.filter is None else WORD[self.filter]
        g1, g2 = QtWidgets.QPushButton("Discipline"), QtWidgets.QPushButton("Location")
        for b, k in ((g1, "discipline"), (g2, "location")):
            b.setProperty("kind", "primary" if self.group_by == k else "ghost")
            b.clicked.connect(lambda _=False, kk=k: (setattr(self, "group_by", kk), self.render_list()))
        self.list_layout.addLayout(hbox(label(f"{title}  {len(rows)}", role="label"), None, g1, g2,
                                        stretch_end=False, spacing=0))
        key = lambda c: (ORDER.index(c["status"]), c["id"] or c["check_key"])  # noqa: E731
        if self.group_by == "discipline":
            for code, name, color, pack, _ in DISCS:
                grp = [c for c in rows if GROUP_TAG.get(c["group"]) == code]
                if not grp:
                    continue
                self._group_header(code, name, color, len(grp))
                for c in sorted(grp, key=key):
                    self.list_layout.addWidget(self._card(c))
        else:
            by = {}
            for c in rows:
                by.setdefault(loc_label(c) or "No location", []).append(c)
            for loc in sorted(by, key=lambda s: ((by[s][0].get("location") or {}).get("frame") or "", s)):
                self._group_header("", loc, DARK["fg-3"], len(by[loc]))
                for c in sorted(by[loc], key=key):
                    self.list_layout.addWidget(self._card(c))
        if not rows:
            self.list_layout.addWidget(label("Nothing matches these filters.", role="faint"))
        if self.filter is None:
            cnt = self.run["counts"]
            more = QtWidgets.QPushButton(f"{GLYPH['pass']} Pass {cnt['pass']}  ·  {GLYPH['dor']} Dormant {cnt['dor']}"
                                         "  — show")
            more.setProperty("kind", "ghost")
            more.clicked.connect(lambda: self._toggle_filter("pass"))
            self.list_layout.addWidget(more)
        self.list_layout.addStretch(1)

    def _group_header(self, code, text, color, n):
        self.list_layout.addSpacing(4)
        t = QtWidgets.QLabel(f"<span style='color:{color};font-family:IBM Plex Mono;font-weight:700'>{code}</span>"
                             f"&nbsp; <span style='color:#b7bbc3'>{text}</span>")
        t.setTextFormat(QtCore.Qt.RichText)
        self.list_layout.addLayout(hbox(t, None, label(str(n), role="faint"), stretch_end=False))

    def _card(self, c: dict) -> QtWidgets.QWidget:
        """Compact finding card (~84 px): discipline stripe + tag, status, ID + title, location + rule, req vs meas."""
        code = GROUP_TAG.get(c["group"], "··")
        color = DISC_COLOR.get(code, DARK["fg-3"])
        fr = QtWidgets.QFrame()
        fr.setObjectName("card")
        dashed = c["status"] == "unk"
        fr._qss = (f"QFrame#card {{ background: #24262b; border: 1px {'dashed' if dashed else 'solid'} #34373e; "
                   f"border-left: 3px solid {color}; border-radius: 4px; }}"
                   " QFrame#card QLabel { background: transparent; }")
        fr._qss_sel = fr._qss.replace("border: 1px", "border: 1px").replace("#34373e;", f"{DARK['accent']};", 1)
        fr.setStyleSheet(fr._qss)
        fr.setCursor(QtCore.Qt.PointingHandCursor)
        v = QtWidgets.QVBoxLayout(fr)
        v.setContentsMargins(10, 6, 8, 6)
        v.setSpacing(2)
        tag = QtWidgets.QLabel(code)
        tag.setStyleSheet(f"color: {color}; font-family: 'IBM Plex Mono'; font-size: 11px; font-weight: 700;")
        top = [tag, pill(c["status"]), label(c["id"] or "", role="faint", mono=True)]
        if c.get("to_verify"):
            tv = QtWidgets.QLabel("To verify")
            tv.setStyleSheet("color: #e69f00; font-size: 10px; font-weight: 600;")
            top.append(tv)
        v.addLayout(hbox(*top))
        t = label(c["title"], wrap=True)
        t.setStyleSheet("font-weight: 600;")
        v.addWidget(t)
        el = (c.get("element") or {}).get("name", "")
        loc = loc_label(c)
        where = " · ".join(x for x in (el if el and el not in loc else "", loc, rule_badge(c)) if x)
        w = label(where, role="faint", mono=True, wrap=True)
        w.setStyleSheet("font-size: 11px;")
        v.addWidget(w)
        rq, ms = c.get("required"), c.get("measured")
        if c["status"] == "unk":
            line = "missing " + ", ".join(c.get("missing") or ["data"]) + " · add it or confirm"
        elif rq and ms and rq.get("value") is not None and ms.get("value") is not None:
            line = f"required {fmt_val(rq, self.unit_mode)} · measured {fmt_val(ms, self.unit_mode)}"
        else:
            line = c.get("summary") or ""
        m = label(line, mono=True, wrap=True)
        m.setStyleSheet("font-size: 11px;")
        v.addWidget(m)
        acts = QtWidgets.QWidget()
        al = QtWidgets.QHBoxLayout(acts)
        al.setContentsMargins(0, 4, 0, 0)
        al.setSpacing(4)
        for text, fn in (("Zoom to", lambda cc=c: self.bridge.focus(cc, ghost=False)),
                         ("Isolate", lambda cc=c: self.isolate(cc)),
                         ("Show all", lambda: self.show_all()),
                         ("Select inverse", lambda: self.bridge.select_inverse()),
                         ("Details →", lambda cc=c: self.open_evidence(cc))):
            b = QtWidgets.QPushButton(text)
            b.setStyleSheet("QPushButton { padding: 0 6px; min-height: 22px; font-size: 11px; }")
            b.clicked.connect(lambda _=False, f=fn: f())
            al.addWidget(b)
        al.addStretch(1)
        acts.setVisible(False)
        v.addWidget(acts)
        fr._acts = acts
        fr.mousePressEvent = lambda ev, cc=c: self.select_finding(cc)
        self._cards[c["check_key"]] = fr
        return fr

    # ================================================================ card click -> 3D
    def select_finding(self, c: dict):
        """Select + colour the element by status, zoom to it, ghost the rest; show the card actions."""
        self.current = c
        for k, fr in self._cards.items():
            on = k == c["check_key"]
            fr._acts.setVisible(on)
            fr.setStyleSheet(fr._qss_sel if on else fr._qss)
        n = self.bridge.focus(c)
        el = (c.get("element") or {}).get("name") or c.get("id")
        self.foot_l.setText(f"Selected: {el}" + ("" if n or not self.bridge.ok else " · not in this document"))
        return n

    def isolate(self, c: dict):
        n = self.bridge.isolate(c)
        self.foot_l.setText(f"Isolated: {c.get('id') or ''} · {n} object(s)")
        return n

    def show_all(self):
        self.bridge.show_all()
        self.foot_l.setText("All objects shown")

    # ================================================================ evidence (Details)
    def open_evidence(self, c: dict):
        try:
            f = self.engine.finding(c["id"] or c["check_key"])
        except Exception:  # noqa: BLE001
            f = c
        self.current = f
        n3d = self.bridge.focus(f)
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
        back.clicked.connect(lambda: self.findings_page.setCurrentIndex(0))
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
            where = r["path"]
            if self.engine.remote and r.get("download"):
                # the engine is on another machine: save the BCF next to the open IFC (or in the home folder)
                src = self.bridge.model_path()
                folder = Path(src).parent if src else Path.home()
                out = folder / Path(r["path"]).name
                out.write_bytes(self.engine.download(r["download"]))
                where = str(out)
            QtWidgets.QMessageBox.information(self, "Send to review",
                                              f"BCF written: {where}\n{r['topics']} topics · {r['decisions']} "
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
    dock.setMinimumWidth(400)
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    try:
        _assistant_dock(mw, panel)
    except Exception as e:  # noqa: BLE001 - the chat stays a tab in the panel
        import FreeCAD
        FreeCAD.Console.PrintWarning(f"SonarIQ: Assistant Engineer stays in the panel ({e})\n")
    return dock


def _assistant_dock(mw, panel):
    """Assistant Engineer in its own dock: floats over the 3D view, can be docked anywhere."""
    i = panel.tabs.indexOf(panel.chat)
    if i >= 0:
        panel.tabs.removeTab(i)
    host = QtWidgets.QWidget()
    host.setObjectName("SonarIQPanel")
    host.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    host.setStyleSheet(panel_qss())
    lay = QtWidgets.QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(panel.chat)
    d = QtWidgets.QDockWidget("✦ Assistant Engineer", mw)
    d.setObjectName("SonarIQAssistant")
    d.setWidget(host)
    d.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable |
                  QtWidgets.QDockWidget.DockWidgetClosable)
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
    d.setFloating(True)
    g = mw.geometry()
    d.resize(380, 460)
    d.move(g.x() + g.width() - 400 - 420, g.y() + g.height() - 520)
    d.hide()   # opened from the ✦ button in the panel header
    panel.chat_tab = False
    return d


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot")
    ap.add_argument("--finding")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    p = SonarIQPanel()
    p.resize(400, 900)
    p.show()
    if a.analyse or a.finding:
        QtCore.QTimer.singleShot(300, p.analyse)
    if a.finding:
        QtCore.QTimer.singleShot(2500, lambda: p.select_finding(next(
            c for c in p.run["findings"] if c["id"] == a.finding)))
    if a.shot:
        QtCore.QTimer.singleShot(3500, lambda: (p.grab().save(a.shot), app.quit()))
    app.exec() if hasattr(app, "exec") else app.exec_()


if __name__ == "__main__":
    main()
