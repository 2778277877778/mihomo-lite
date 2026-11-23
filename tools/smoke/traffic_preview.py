import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ.setdefault("MIHOMO_LITE_TRANSLUCENT", "1")
HOME = tempfile.mkdtemp(prefix="mihomo-tr-")
os.environ["MIHOMO_LITE_HOME"] = HOME
sys.path.insert(0, "src")

import random
from PySide6.QtWidgets import QApplication
from mihomo_lite.app import MihomoLiteApp
from mihomo_lite.core.traffic_monitor import TrafficSample

app = MihomoLiteApp(["MihomoLite.exe"])
w = app.window
w.resize(1000, 680)
w.show()
QApplication.processEvents()
w.show_page(1)
QApplication.processEvents()
for i in range(90):
    up = random.randint(2000, 90000)
    down = random.randint(100000, 2500000)
    app.traffic.sample.emit(TrafficSample(up=up, down=down, up_total=i*up//3, down_total=i*down//3))
    QApplication.processEvents()
w.grab().save("tools/smoke/traffic_page.png")
w.grab().save("docs/images/traffic.png")
print("traffic page rendered")
