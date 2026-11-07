import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ.setdefault("MIHOMO_LITE_HOME", tempfile.mkdtemp())
sys.path.insert(0, "src")

from PySide6.QtWidgets import QApplication
from mihomo_lite.app import MihomoLiteApp

app = MihomoLiteApp(["MihomoLite.exe"])
w = app.window
w.resize(1000, 680)
w.show()
QApplication.processEvents()
dash = w._dashboard
dash.updateGeometry()
QApplication.processEvents()

lay = dash.layout()
print("page h:", dash.height(), "layout hint:", lay.minimumSize().height(), lay.sizeHint().height())
for i in range(lay.count()):
    item = lay.itemAt(i)
    widget = item.widget()
    geo = item.geometry()
    name = widget.objectName() if widget else type(item).__name__
    print(i, name, "geo=", geo.y(), geo.height(), "min=", item.minimumSize().height(), "hint=", item.sizeHint().height())
