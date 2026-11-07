import sys
sys.path.insert(0, "freecad_addon/SonarIQ")
from PySide6 import QtWidgets, QtCore
import sonariq_panel as sp

app = QtWidgets.QApplication(sys.argv)
p = sp.SonarIQPanel()
p.resize(380, 900)
p.show()
steps = sys.argv[2:] or ["Simulate night", "Why does F-07 fail?"]


def run():
    p.analyse()
    p.tabs.setCurrentWidget(p.chat)
    for i, t in enumerate(steps):
        QtCore.QTimer.singleShot(300 + i * 2500, lambda t=t: p.chat.send(t))


QtCore.QTimer.singleShot(500, run)
QtCore.QTimer.singleShot(1500 + len(steps) * 2500 + 2000, lambda: (p.grab().save(sys.argv[1]), app.quit()))
app.exec()
