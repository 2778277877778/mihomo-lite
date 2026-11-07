"""Headless render smoke test: build the real app, grab every page."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("MIHOMO_LITE_TRANSLUCENT", "1")
os.environ.setdefault("MIHOMO_LITE_HOME", tempfile.mkdtemp(prefix="mihomo-lite-ui-"))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from mihomo_lite.app import MihomoLiteApp  # noqa: E402

OUT = Path(__file__).resolve().parent
app = MihomoLiteApp(["mihomo-lite.exe"])
window = app.window
window.resize(1000, 680)
window.show()
QApplication.processEvents()

for index, name in enumerate(("dashboard", "proxies", "profiles", "settings", "logs")):
    window.show_page(index)
    QApplication.processEvents()
    window.grab().save(str(OUT / f"ui_{name}.png"))

window.show_page(1)
app.window.apply_theme("light")
window.show_page(0)
QApplication.processEvents()
window.grab().save(str(OUT / "ui_light.png"))
print("pages rendered")
