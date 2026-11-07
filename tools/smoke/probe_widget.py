import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, "src")

from PySide6.QtWidgets import QApplication

app = QApplication([])
app.setStyleSheet(open("src/mihomo_lite/resources/styles/dark.qss", encoding="utf-8").read())

from PySide6.QtWidgets import QSplitter, QListWidget, QWidget, QVBoxLayout, QLabel
w = QWidget(); layout = QVBoxLayout(w)
sp = QSplitter(); sp.setChildrenCollapsible(False)
left = QListWidget(); left.addItems(["a", "b"])
right = QListWidget(); right.addItems(["x"])
sp.addWidget(left); sp.addWidget(right)
layout.addWidget(sp)
w.resize(800, 500); w.show(); app.processEvents()
for point in ((400, 250), (399, 250), (401, 250), (482, 250)):
    child = w.childAt(*point)
    print(point, type(child).__name__ if child else None, getattr(child, "objectName", lambda: "")())
print("splitter handle width:", sp.handleWidth())
print("left list scrollbar visible:", left.verticalScrollBar().isVisible())
