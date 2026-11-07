"""Render the dashboard in a connected state using a fake system proxy backend.

A real Mihomo core is started and stopped; the user's Windows proxy is never touched.
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("MIHOMO_LITE_TRANSLUCENT", "1")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
HOME = Path(tempfile.mkdtemp(prefix="mihomo-shot-"))
os.environ["MIHOMO_LITE_HOME"] = str(HOME)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mihomo_lite.app import MihomoLiteApp  # noqa: E402
from mihomo_lite.models.app_state import ConnectionState  # noqa: E402
from mihomo_lite.system.proxy import ProxyState, SystemProxy  # noqa: E402

CORE = ROOT / "tools" / "core" / "extracted" / "mihomo-windows-amd64.exe"
PROFILE = """mixed-port: 7890
mode: rule
proxies:
  - {name: "Tokyo 01", type: socks5, server: 127.0.0.1, port: 1}
  - {name: "Singapore 02", type: socks5, server: 127.0.0.1, port: 2}
  - {name: "Frankfurt 03", type: socks5, server: 127.0.0.1, port: 3}
proxy-groups:
  - name: Proxy
    type: select
    proxies: ["Tokyo 01", "Singapore 02", "Frankfurt 03", DIRECT]
rules:
  - MATCH,Proxy
"""


class FakeBackend:
    def __init__(self):
        self.state = ProxyState(flags=1)

    def read(self):
        return self.state

    def write(self, state):
        self.state = state


def spin(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.02)


def main() -> int:
    (HOME / "core").mkdir(parents=True, exist_ok=True)
    shutil.copy2(CORE, HOME / "core" / "mihomo.exe")
    profile_file = HOME / "sample.yaml"
    profile_file.write_text(PROFILE, encoding="utf-8")

    app = MihomoLiteApp(["MihomoLite.exe"])
    app.connection._proxy = SystemProxy(app.paths.proxy_journal, backend=FakeBackend())
    app.profiles.import_file(profile_file, name="Demo subscription")
    app.window.resize(1000, 680)
    app.window.show()
    spin(0.3)

    app.connection.connect()
    end = time.monotonic() + 30
    while time.monotonic() < end and app.connection.state is not ConnectionState.CONNECTED:
        spin(0.1)
    spin(1.5)

    out = ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    app.window.show_page(0)
    spin(0.3)
    app.window.grab().save(str(out / "dashboard.png"))
    app.window.show_page(1)
    spin(1.0)
    app.window.grab().save(str(out / "proxies.png"))
    app.window.show_page(2)
    spin(0.3)
    app.window.grab().save(str(out / "profiles.png"))
    app.window.show_page(0)
    app.window.apply_theme("light")
    spin(0.3)
    app.window.grab().save(str(out / "dashboard-light.png"))

    app.connection.disconnect()
    end = time.monotonic() + 10
    while time.monotonic() < end and app.connection.state is not ConnectionState.STOPPED:
        spin(0.1)
    app.connection.shutdown()
    app.single.release()
    print("screenshots written to", out, "final state:", app.connection.state.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
