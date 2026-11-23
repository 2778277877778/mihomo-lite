from PySide6.QtCore import QObject, Signal

from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.mihomo.core_manager import CoreInfo
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.system.proxy import PROXY_TYPE_DIRECT, ProxyState, SystemProxy

PROFILE = """
proxies:
  - name: a
    type: socks5
    server: 127.0.0.1
    port: 1
proxy-groups:
  - name: G
    type: select
    proxies: [a, DIRECT]
rules:
  - MATCH,G
"""


class FakeProcess(QObject):
    started = Signal(int)
    stopped = Signal(int, bool)
    output = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.killed = 0

    def start(self, *args, **kwargs):
        self.running = True
        self.started.emit(1)
        return True

    def stop(self, **kwargs):
        self.running = False
        self.stopped.emit(0, False)

    def kill_now(self, *args, **kwargs):
        self.killed += 1
        self.running = False


class FakeAPI:
    def version(self):
        return {"version": "v-test"}

    def close(self):
        pass


class FakeCore:
    def ensure(self):
        return CoreInfo(path="mihomo.exe", version="v-test", source="test")


class FakeTraffic(QObject):
    sample = Signal(object)
    link_changed = Signal(bool, str)

    def start(self, port, secret):
        pass

    def stop(self):
        pass


class FakeBackend:
    def __init__(self):
        self.state = ProxyState(flags=PROXY_TYPE_DIRECT)

    def read(self):
        return self.state

    def write(self, state):
        self.state = state


def test_force_stop_kills_core_and_reaches_stopped(paths, qapp):
    settings = SettingsStore(paths)
    settings.load()
    profiles = ProfileManager(paths)
    source = paths.root / "p.yaml"
    source.write_text(PROFILE, encoding="utf-8")
    profiles.import_file(source, name="P")
    process = FakeProcess()
    connection = ConnectionManager(
        paths,
        settings,
        profiles,
        process=process,
        proxy=SystemProxy(paths.proxy_journal, backend=FakeBackend()),
        core=FakeCore(),
        api_factory=lambda *a, **k: FakeAPI(),
        traffic=FakeTraffic(),
    )
    process.running = True
    connection.force_stop()
    assert process.killed == 1
    assert connection.state is ConnectionState.STOPPED
    assert connection.session is None
