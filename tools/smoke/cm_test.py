import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
HOME = tempfile.mkdtemp(prefix="mihomo-cm-")
os.environ["MIHOMO_LITE_HOME"] = HOME
sys.path.insert(0, "src")

from PySide6.QtCore import QObject, Signal, QEventLoop
from PySide6.QtWidgets import QApplication

from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.mihomo.core_manager import CoreInfo
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.system.proxy import ProxyState, SystemProxy

app = QApplication([])
from pathlib import Path
paths = AppPaths(root=Path(HOME)); paths.ensure()

class FakeAPI:
    def __init__(self, *a, **k): pass
    def version(self): return {"version": "v-test"}
    def close(self): pass

class FakeCore:
    def ensure(self): return CoreInfo(path=paths.core / "mihomo.exe", version="v-test", source="test")

class FakeProcess(QObject):
    started = Signal(int); stopped = Signal(int, bool); output = Signal(str); failed = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent); self.running = False; self.pid = 0
    def start(self, *a, **k):
        self.running = True; self.pid = 4242
        self.started.emit(self.pid)
        return True
    def stop(self, **k):
        self.running = False; self.stopped.emit(0, False)
    def kill_now(self, *a, **k):
        self.running = False

class FakeBackend:
    def __init__(self): self.state = ProxyState(flags=1); self.writes = []
    def read(self): return self.state
    def write(self, s):
        self.writes.append(s); self.state = s

settings = SettingsStore(paths); settings.load()
profiles = ProfileManager(paths)
src = paths.root / "p.yaml"
src.write_text("proxies:\n  - {name: a, type: socks5, server: 127.0.0.1, port: 1}\nrules:\n  - MATCH,DIRECT\n")
profiles.import_file(src, name="P")

backend = FakeBackend()
conn = ConnectionManager(paths, settings, profiles, process=FakeProcess(), proxy=SystemProxy(paths.proxy_journal, backend=backend), core=FakeCore(), api_factory=FakeAPI)
conn.state_changed.connect(lambda s: print("state:", s.value))
conn.error_changed.connect(lambda m: print("error:", m))
conn.connect()

end = time.time() + 5
while time.time() < end and conn.state is not ConnectionState.CONNECTED:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.02)
print("final state:", conn.state.value)
