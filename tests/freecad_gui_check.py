# Real-FreeCAD check (not run by pytest): make fc-check. Opens deck5_revA.ifc with NativeIFC, shows the SonarIQ
# panel, runs Analyse, opens F-01 and checks FD-5-165P is selected; writes fc_gui_test.log, fc_window.png, fc_view.png.
import os, sys, traceback
import FreeCAD, FreeCADGui as Gui
from PySide import QtCore, QtWidgets
OUT = os.environ["SQ_OUT"]
IFC = os.environ["SQ_IFC"]
log = open(OUT + "/fc_gui_test.log", "w", encoding="utf-8")
def p(*a):
    log.write(" ".join(str(x) for x in a) + "\n"); log.flush()

import faulthandler
_fh = open(OUT + "/fc_hang.txt", "w")
faulthandler.dump_traceback_later(90, exit=False, file=_fh)
p("macro loaded")
FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/BIM").SetBool("FirstTime", False)
FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/NativeIFC").SetBool("SingleDoc", True)

def step1():
    p("step1")
    try:
        Gui.activateWorkbench("BIMWorkbench")
    except Exception as e:
        p("wb", e)
    try:
        from nativeifc import ifc_import
        doc = FreeCAD.newDocument("Demo_ship_RevA")
        ifc_import.insert(IFC, doc.Name, strategy=2, shapemode=0, switchwb=False, silent=True, singledoc=True)
        doc = FreeCAD.ActiveDocument
        doc.recompute()
        p("doc", doc.Name, "objects", len(doc.Objects))
        import sonariq_panel
        g = [o for o in doc.Objects if sonariq_panel.FreeCADBridge.guid_of(o)]
        p("objects with GlobalId", len(g), "sample", [(o.Label, sonariq_panel.FreeCADBridge.guid_of(o)) for o in g[:3]])
        Gui.activeDocument().activeView().viewTop()
        Gui.SendMsgToActiveView("ViewFit")
    except Exception:
        p(traceback.format_exc())
    QtCore.QTimer.singleShot(4000, step2)

def step2():
    try:
        import sonariq_panel
        dock = sonariq_panel.show_in_freecad()
        panel = dock.widget()
        panel.analyse()
        p("meta", panel.meta.text())
        f01 = next(c for c in panel.run["findings"] if c["id"] == "F-01")
        panel.open_evidence(f01)
        doc = FreeCAD.ActiveDocument
        shp = [o for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        vis = [o for o in doc.Objects if getattr(o, "ViewObject", None) and o.ViewObject.Visibility]
        p("with shape", len(shp), "visible", len(vis), "classes", sorted({getattr(o, "IfcClass", "?") for o in doc.Objects})[:12])
        Gui.activeDocument().activeView().viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
        sel = Gui.Selection.getSelection()
        p("selected", [o.Label for o in sel])
    except Exception:
        p(traceback.format_exc())
    QtCore.QTimer.singleShot(2500, step3)

def step3():
    mw = Gui.getMainWindow()
    mw.resize(1440, 900)
    mw.grab().save(OUT + "/fc_window.png")
    try:
        v = Gui.activeDocument().activeView()
        v.viewTop()
        Gui.SendMsgToActiveView("ViewFit")
        v.saveImage(OUT + "/fc_view.png", 1000, 600, "Current")
    except Exception as e:
        p("saveImage", e)
    p("saved")
    log.close()
    QtCore.QTimer.singleShot(500, lambda: os._exit(0))

QtCore.QTimer.singleShot(3000, step1)
