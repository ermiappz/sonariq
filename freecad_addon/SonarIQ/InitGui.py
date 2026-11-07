# SonarIQ FreeCAD add-on: adds "SonarIQ ▶ Analyse" to the toolbar/menu and docks the SonarIQ panel on the right.
import FreeCADGui as Gui


class SonarIQShowPanel:
    def GetResources(self):
        return {"MenuText": "SonarIQ panel", "ToolTip": "Show the SonarIQ compliance panel", "Accel": "Ctrl+Shift+S"}

    def Activated(self):
        import sonariq_panel
        sonariq_panel.show_in_freecad()

    def IsActive(self):
        return True


class SonarIQAnalyse:
    def GetResources(self):
        return {"MenuText": "▶ Analyse", "ToolTip": "Run SonarIQ on the open IFC model (Ctrl+Shift+A in the panel)"}

    def Activated(self):
        import sonariq_panel
        from PySide import QtWidgets
        dock = sonariq_panel.show_in_freecad()
        dock.widget().analyse()

    def IsActive(self):
        return True


Gui.addCommand("SonarIQ_ShowPanel", SonarIQShowPanel())
Gui.addCommand("SonarIQ_Analyse", SonarIQAnalyse())


def _sonariq_startup():
    try:
        import sonariq_panel
        sonariq_panel.show_in_freecad()
    except Exception as e:  # noqa: BLE001
        import FreeCAD
        FreeCAD.Console.PrintWarning(f"SonarIQ panel not shown: {e}\n")


try:
    from PySide import QtCore
    QtCore.QTimer.singleShot(2500, _sonariq_startup)
except Exception:  # noqa: BLE001
    pass
