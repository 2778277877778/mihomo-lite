import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, "src")

from PySide6.QtWidgets import QApplication, QSplitter, QListWidget, QWidget, QVBoxLayout

app = QApplication([])

def render(extra_qss: str, filename: str) -> tuple:
    w = QWidget(); layout = QVBoxLayout(w)
    sp = QSplitter(); sp.setChildrenCollapsible(False)
    left = QListWidget(); left.addItems(["a", "b"])
    right = QListWidget(); right.addItems(["x"])
    sp.addWidget(left); sp.addWidget(right)
    layout.addWidget(sp)
    w.resize(800, 500); w.show(); app.processEvents()
    if extra_qss:
        sp.setStyleSheet(extra_qss)
        app.processEvents()
    img = w.grab().toImage()
    w.close()
    return img.pixelColor(400, 250).name(), img.pixelColor(400, 100).name()

print("no qss:", render("", "a.png"))
print("transparent:", render("QSplitter::handle { background: transparent; }", "b.png"))
print("solid:", render("QSplitter::handle { background-color: #14161a; border: none; }", "c.png"))
