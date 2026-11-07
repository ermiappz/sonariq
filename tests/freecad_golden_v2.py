# Real-FreeCAD golden path for panel v2 (not run by pytest): make fc-golden.
# open revA -> Analyse -> close -> open revB -> Analyse -> click F-07 -> Isolate -> Show all -> open fix2 -> Analyse.
# Writes data/out/fc_golden.log (+ fc_golden_*.png). The engine must be running (SONARIQ_ENGINE).
import os, time, traceback
import FreeCAD, FreeCADGui as Gui
from PySide import QtCore, QtWidgets

OUT = os.environ["SQ_OUT"]
DATA = os.environ["SQ_DATA"]
log = open(OUT + "/fc_golden.log", "w", encoding="utf-8")
FAILS = []


def p(*a):
    log.write(" ".join(str(x) for x in a) + "\n"); log.flush()


def check(name, ok, *info):
    p(("PASS " if ok else "FAIL ") + name, *info)
    if not ok:
        FAILS.append(name)


def pump(s):
    t = time.time()
    while time.time() - t < s:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.03)


def open_ifc(fname):
    from nativeifc import ifc_import
    doc = FreeCAD.newDocument(os.path.splitext(fname)[0])
    ifc_import.insert(os.path.join(DATA, fname), doc.Name, strategy=2, shapemode=0, switchwb=False, silent=True,
                      singledoc=True)
    FreeCAD.setActiveDocument(doc.Name)
    Gui.ActiveDocument = Gui.getDocument(doc.Name)
    FreeCAD.ActiveDocument.recompute()
    pump(2.0)
    return FreeCAD.ActiveDocument


def visible(doc):
    return sum(1 for o in doc.Objects if getattr(o, "ViewObject", None) and hasattr(o, "Shape")
               and o.ViewObject.Visibility)


def shot(name):
    Gui.getMainWindow().grab().save(f"{OUT}/fc_golden_{name}.png")
    try:   # the GL view does not show in a widget grab under xvfb
        Gui.activeDocument().activeView().saveImage(f"{OUT}/fc_golden_{name}_view.png", 1000, 640, "Current")
    except Exception as e:
        p("saveImage", e)


def tree_visible():
    import sonariq_panel as sp
    mw = Gui.getMainWindow()
    return any(d.isVisible() for d in mw.findChildren(QtWidgets.QDockWidget) if d.objectName() in sp.TREE_DOCKS)


def analyse(panel, label):
    t = time.time()
    panel.analyse()
    busy_seen = panel._busy
    ok = panel.wait_idle(180)
    pump(0.3)
    r = panel.run or {}
    c = r.get("counts", {})
    check(f"Analyse {label}", ok and bool(r), "busy-state", busy_seen, "header", panel.proj.text(),
          "counts", c, "checks", r.get("total_checks"), f"{time.time() - t:.1f}s")
    return r


def main():
    FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/BIM").SetBool("FirstTime", False)
    FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/NativeIFC").SetBool("SingleDoc", True)
    try:
        Gui.activateWorkbench("BIMWorkbench")
    except Exception as e:
        p("wb", e)
    Gui.getMainWindow().resize(1440, 900)
    import sonariq_panel as sp
    panel = sp.show_in_freecad().widget()
    pump(1.5)
    check("No doc: Analyse disabled", not panel.analyse_btn.isEnabled(), "tooltip", panel.analyse_btn.toolTip())
    check("No Live / Simulate in panel", not hasattr(panel, "live") and not hasattr(panel, "sim_btn"))
    check("Assistant Engineer is its own dock", not panel.chat_tab)

    # 1. Rev A
    doc = open_ifc("deck5_revA.ifc")
    p("revA objects", len(doc.Objects))
    check("Rev A: header shows file", "deck5_revA" in panel.proj.text(), panel.proj.text())
    check("Rev A: Analyse enabled", panel.analyse_btn.isEnabled())
    check("Model open: tree hidden", not tree_visible())
    p("docks", [(d.objectName(), d.windowTitle(), d.isVisible()) for d in Gui.getMainWindow().findChildren(QtWidgets.QDockWidget)])
    rA = analyse(panel, "Rev A")
    check("Rev A counts 1·1·1·89·4", [rA["counts"][k] for k in ("fail", "warn", "unk", "pass", "dor")] == [1, 1, 1, 89, 4])
    check("Export visible", panel.export_btn.isVisible(), (rA.get("run_meta") or {}).get("id"))
    shot("1_revA")

    # 2. close -> reset
    FreeCAD.closeDocument(doc.Name)
    pump(1.5)
    check("Close: panel reset", panel.run is None and not panel.export_btn.isVisible() and
          not panel.analyse_btn.isEnabled(), panel.proj.text())

    # 3. Rev B -> F-07 -> Isolate -> Show all
    doc = open_ifc("deck5_revB.ifc")
    check("Rev B: header shows file", "deck5_revB" in panel.proj.text(), panel.proj.text())
    rB = analyse(panel, "Rev B")
    check("Rev B counts 4·1·1·86·4", [rB["counts"][k] for k in ("fail", "warn", "unk", "pass", "dor")] == [4, 1, 1, 86, 4])
    f07 = next((c for c in rB["findings"] if c["id"] == "F-07"), None)
    check("F-07 present", f07 is not None)
    all_vis = visible(doc)
    n = panel.select_finding(f07)
    pump(0.5)
    sel = [o.Label for o in Gui.Selection.getSelection()]
    ghosted = sum(1 for o in doc.Objects if getattr(o, "ViewObject", None) and hasattr(o.ViewObject, "Transparency")
                  and o.ViewObject.Transparency == 85)
    stair = panel.bridge.find(f07["element"]["guid"], f07["element"]["name"])[0]
    want = sp.QtGui.QColor(sp.STATUS_COLOR["fail"])
    sc = stair.ViewObject.ShapeColor
    check("Click F-07: element coloured by status, selection cleared", n > 0 and not sel and
          abs(sc[0] - want.redF()) < 0.02 and abs(sc[1] - want.greenF()) < 0.02, "objects", n, "colour", sc[:3],
          "line width", getattr(stair.ViewObject, "LineWidth", None))
    check("Click F-07: card active", panel._cards[f07["check_key"]]._acts.isVisible())
    check("F-07 overlay drawn", panel.bridge.has_overlay())
    check("Click F-07: rest ghosted", ghosted > 0, "ghosted", ghosted)
    shot("2_F07")
    panel.isolate(f07)
    pump(0.5)
    iso_vis = visible(doc)
    check("Isolate: only the element visible", 0 < iso_vis < all_vis, "visible", iso_vis, "of", all_vis)
    shot("3_isolate")
    panel.show_all()
    pump(0.5)
    check("Show all: everything visible again", visible(doc) == all_vis, "visible", visible(doc))
    m = panel.bridge.select_inverse()
    check("Select inverse", m > 0, "selected", m)

    # 3b. F-08 dead-end overlay appears, and disappears on Show all
    f08 = next(c for c in rB["findings"] if c["id"] == "F-08")
    sg = Gui.ActiveDocument.ActiveView.getSceneGraph()
    n0 = sg.getNumChildren()
    n8 = panel.select_finding(f08)
    pump(0.5)
    o8 = panel.bridge.find(f08["element"]["guid"], f08["element"]["name"])
    p("F-08 objects", n8, [(o.Name, o.Label, o.TypeId, getattr(o.ViewObject, "DisplayMode", None),
                            o.ViewObject.Visibility, getattr(o.ViewObject, "Transparency", None),
                            str(o.Shape.BoundBox) if hasattr(o, "Shape") else None) for o in o8])
    lgs = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QLabel, "SonarIQLegend") if w.isVisible()]
    lg = lgs[0] if len(lgs) == 1 else None
    check("F-08 overlay appears", panel.bridge.has_overlay() and sg.getNumChildren() == n0 + 1 and lg is not None,
          "spec", sp.FreeCADBridge.overlay_spec(f08), "legend", lg.text() if lg else None)
    shot("5_F08_overlay")
    panel.show_all()
    pump(0.5)
    lgs = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QLabel, "SonarIQLegend") if w.isVisible()]
    check("Show all removes the overlay", not panel.bridge.has_overlay() and sg.getNumChildren() == n0 and not lgs)

    # 4. fix2 (new document while Rev B stays open)
    doc2 = open_ifc("deck5_revB_fix2.ifc")
    check("fix2: panel switched + reset", "deck5_revB_fix2" in panel.proj.text() and panel.run is None, panel.proj.text())
    rF = analyse(panel, "Rev B fix2")
    check("fix2 counts 3·1·1·87·4", [rF["counts"][k] for k in ("fail", "warn", "unk", "pass", "dor")] == [3, 1, 1, 87, 4])
    shot("4_fix2")
    p("RESULT", "ALL PASS" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")


def run():
    try:
        main()
    except Exception:
        p(traceback.format_exc())
        p("RESULT", "ERROR")
    log.close()
    QtCore.QTimer.singleShot(300, lambda: os._exit(0))


QtCore.QTimer.singleShot(3000, run)
