import json, os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
os.environ.setdefault("MIHOMO_LITE_TRANSLUCENT", "1")
HOME = Path(tempfile.mkdtemp(prefix="mihomo-zh-"))
os.environ["MIHOMO_LITE_HOME"] = str(HOME)
(HOME).mkdir(parents=True, exist_ok=True)
Path(HOME / "settings.json").write_text(json.dumps({"language": "zh"}), encoding="utf-8")
sys.path.insert(0, "src")

from PySide6.QtWidgets import QApplication
from mihomo_lite.app import MihomoLiteApp

app = MihomoLiteApp(["MihomoLite.exe"])
w = app.window
w.resize(1000, 680)
w.show()
QApplication.processEvents()
out = Path("tools/smoke")
for index, name in ((0, "zh_dashboard"), (3, "zh_settings"), (2, "zh_profiles"), (1, "zh_proxies")):
    w.show_page(index)
    QApplication.processEvents()
    w.grab().save(str(out / f"{name}.png"))
print("zh pages rendered")
