import os, random, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ.setdefault("MIHOMO_LITE_TRANSLUCENT", "1")
os.environ["MIHOMO_LITE_HOME"] = tempfile.mkdtemp(prefix="mihomo-lat-")
sys.path.insert(0, "src")

from PySide6.QtWidgets import QApplication
from mihomo_lite.app import MihomoLiteApp

app = MihomoLiteApp(["MihomoLite.exe"])
w = app.window
w.resize(1000, 680)
w.show()
QApplication.processEvents()
series = [40 + random.randint(-12, 30) for _ in range(45)]
w._dashboard._latency_chart.set_series(series, 18)
w._dashboard._latency_row.set_value("52 ms  ±18 ms")
QApplication.processEvents()
w.grab().save("tools/smoke/latency_dashboard.png")
print("latency preview rendered")
