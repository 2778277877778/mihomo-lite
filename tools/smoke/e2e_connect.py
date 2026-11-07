"""End-to-end: real core, fake system proxy backend, temp data directory.

Run from the repository root:  .venv\Scripts\python tools\smoke\e2e_connect.py
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
HOME = Path(tempfile.mkdtemp(prefix="mihomo-e2e-"))
os.environ["MIHOMO_LITE_HOME"] = str(HOME)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mihomo_lite.core.connection_manager import ConnectionManager  # noqa: E402
from mihomo_lite.core.profile_manager import ProfileManager  # noqa: E402
from mihomo_lite.core.state_manager import SettingsStore  # noqa: E402
from mihomo_lite.models.app_state import ConnectionState  # noqa: E402
from mihomo_lite.system.paths import AppPaths  # noqa: E402
from mihomo_lite.system.proxy import ProxyState, SystemProxy  # noqa: E402

CORE_SOURCE = ROOT / "tools" / "core" / "extracted" / "mihomo-windows-amd64.exe"


class FakeBackend:
    def __init__(self):
        self.state = ProxyState(flags=1, server="", bypass="localhost;<local>", autoconfig_url="")
        self.writes = []

    def read(self):
        return self.state

    def write(self, state):
        self.writes.append(state)
        self.state = state


PROFILE = """
mixed-port: 7890
allow-lan: true
mode: rule
proxies:
  - name: smoke-node
    type: socks5
    server: 127.0.0.1
    port: 1
proxy-groups:
  - name: Smoke
    type: select
    proxies: [smoke-node, DIRECT]
rules:
  - MATCH,DIRECT
"""


def wait_for(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main() -> int:
    app = QApplication.instance() or QApplication([])
    paths = AppPaths(root=HOME)
    paths.ensure()
    shutil.copy2(CORE_SOURCE, paths.core / "mihomo.exe")

    from mihomo_lite.utils.logger import setup_logging
    import logging

    setup_logging(paths.logs, level=logging.DEBUG, console=True)

    settings = SettingsStore(paths)
    settings.load()
    settings.update(system_proxy=True)

    profiles = ProfileManager(paths)
    source = HOME / "smoke.yaml"
    source.write_text(PROFILE, encoding="utf-8")
    profile = profiles.import_file(source, name="Smoke profile")
    print(f"imported profile: {profile.name} ({profile.proxy_count} proxies)")

    backend = FakeBackend()
    proxy = SystemProxy(paths.proxy_journal, backend=backend)
    connection = ConnectionManager(paths, settings, profiles, proxy=proxy)

    events = []
    connection.state_changed.connect(lambda s: events.append(s.value))
    connection.error_changed.connect(lambda m: print("ERROR SIGNAL:", m))
    connection.core_log.connect(lambda line: print("CORE:", line[:120]))

    connection.connect()
    if not wait_for(lambda: connection.state is ConnectionState.CONNECTED):
        print("FAILED to connect; state =", connection.state)
        return 1

    session = connection.session
    print(f"connected: mixed={session.mixed_port} api={session.api_port} core={session.core_version}")
    print("proxy backend now:", backend.state.flags, backend.state.server)
    version = connection.api.version()
    print("api version:", version)
    proxies = connection.api.proxies()
    print("api proxies:", sorted(proxies.get("proxies", {}).keys()))

    connection.disconnect()
    if not wait_for(lambda: connection.state is ConnectionState.STOPPED):
        print("FAILED to stop; state =", connection.state)
        return 1

    print("restored proxy:", backend.state.flags, repr(backend.state.server))
    print("journal exists:", paths.proxy_journal.exists())
    print("state events:", events)
    connection.shutdown()
    ok = backend.state.flags == 1 and backend.state.server == ""
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
