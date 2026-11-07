import pytest
from PySide6.QtCore import QObject, Signal

from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.mihomo.core_manager import CoreInfo
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.system.proxy import PROXY_TYPE_DIRECT, ProxyState, SystemProxy
from mihomo_lite.utils.exceptions import ApiError

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


class FakeBackend:
    def __init__(self):
        self.state = ProxyState(flags=PROXY_TYPE_DIRECT)
        self.writes = []

    def read(self):
        return self.state

    def write(self, state):
        self.writes.append(state)
        self.state = state


class FakeProcess(QObject):
    started = Signal(int)
    stopped = Signal(int, bool)
    output = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.pid = 0
        self.started_calls = 0
        self.stop_calls = 0
        self.events = []

    def start(self, core, config, workdir, extra_env=None):
        self.started_calls += 1
        self.running = True
        self.pid = 4242
        self.events.append("process.start")
        self.started.emit(self.pid)
        return True

    def stop(self, **kwargs):
        self.stop_calls += 1
        self.events.append("process.stop")
        self.running = False
        self.stopped.emit(0, False)

    def kill_now(self, *args, **kwargs):
        self.running = False


class FakeAPI:
    def __init__(self, fail=False):
        self.fail = fail
        self.closed = False

    def version(self):
        if self.fail:
            raise ApiError("not ready")
        return {"version": "v-test"}

    def close(self):
        self.closed = True


class FakeCore:
    def ensure(self):
        return CoreInfo(path="mihomo.exe", version="v-test", source="test")


class FakeTraffic(QObject):
    sample = Signal(object)
    link_changed = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self.started = None
        self.stopped = 0

    def start(self, port, secret):
        self.started = (port, secret)

    def stop(self):
        self.stopped += 1


class RecordingProxy(SystemProxy):
    def __init__(self, journal, backend, events):
        super().__init__(journal, backend=backend, owner_pid=999, process_checker=lambda _p: False)
        self.events = events

    def restore(self):
        self.events.append("proxy.restore")
        return super().restore()


@pytest.fixture
def harness(paths, qapp):
    settings = SettingsStore(paths)
    settings.load()
    profiles = ProfileManager(paths)
    source = paths.root / "p.yaml"
    source.write_text(PROFILE, encoding="utf-8")
    profiles.import_file(source, name="P")

    backend = FakeBackend()
    process = FakeProcess()
    api = FakeAPI()
    traffic = FakeTraffic()
    events = process.events

    class ApiFactory:
        def __call__(self, *args, **kwargs):
            return api

    connection = ConnectionManager(
        paths,
        settings,
        profiles,
        process=process,
        proxy=RecordingProxy(paths.proxy_journal, backend, events),
        core=FakeCore(),
        api_factory=ApiFactory(),
        traffic=traffic,
    )
    return connection, process, api, traffic, backend, events, settings


def wait_connected(qtbot, connection, expected=ConnectionState.CONNECTED):
    qtbot.waitUntil(lambda: connection.state is expected, timeout=4000)


def test_connect_reaches_connected_state(harness, qtbot):
    connection, process, api, traffic, backend, _events, _settings = harness
    connection.connect()
    wait_connected(qtbot, connection)

    assert process.started_calls == 1
    assert connection.session is not None
    assert connection.session.core_version == "v-test"
    assert 1024 < connection.session.mixed_port <= 65535
    assert backend.state.enabled
    assert backend.state.server == f"127.0.0.1:{connection.session.mixed_port}"
    assert traffic.started is not None


def test_connect_without_profile_fails(paths, qapp):
    settings = SettingsStore(paths)
    settings.load()
    profiles = ProfileManager(paths)
    connection = ConnectionManager(
        paths, settings, profiles, process=FakeProcess(), core=FakeCore()
    )
    connection.connect()
    assert connection.state is ConnectionState.ERROR


def test_api_timeout_leaves_error_and_stops_core(harness, qtbot, monkeypatch):
    connection, process, _api, _traffic, backend, _events, _settings = harness

    def boom(*args, **kwargs):
        raise ApiError("the core API did not become ready in time")

    monkeypatch.setattr("mihomo_lite.core.connection_manager.wait_for_api", boom)
    connection.connect()
    qtbot.waitUntil(lambda: connection.state is ConnectionState.ERROR, timeout=4000)
    assert process.stop_calls == 1
    assert not backend.state.enabled
    assert connection.session is None


def test_disconnect_restores_proxy_before_stopping_core(harness, qtbot):
    connection, process, _api, _traffic, backend, events, _settings = harness
    connection.connect()
    wait_connected(qtbot, connection)

    connection.disconnect()
    qtbot.waitUntil(lambda: connection.state is ConnectionState.STOPPED, timeout=4000)

    assert "proxy.restore" in events
    assert "process.stop" in events
    assert events.index("proxy.restore") < events.index("process.stop")
    assert not backend.state.enabled
    assert connection.session is None


def test_core_crash_restores_the_system_proxy(harness, qtbot):
    connection, process, _api, _traffic, backend, _events, _settings = harness
    connection.connect()
    wait_connected(qtbot, connection)
    assert backend.state.enabled

    process.running = False
    process.stopped.emit(1, True)

    qtbot.waitUntil(lambda: connection.state is ConnectionState.ERROR, timeout=4000)
    assert not backend.state.enabled
    assert not paths_journal_exists(connection)


def paths_journal_exists(connection):
    return connection._paths.proxy_journal.exists()


def test_shutdown_is_idempotent(harness, qtbot):
    connection, _process, _api, _traffic, backend, _events, _settings = harness
    connection.connect()
    wait_connected(qtbot, connection)

    connection.shutdown()
    connection.shutdown()

    assert not backend.state.enabled
    assert connection.state is ConnectionState.STOPPED


def test_system_proxy_setting_off_skips_apply(harness, qtbot):
    connection, _process, _api, _traffic, backend, _events, settings = harness
    settings.update(system_proxy=False)
    connection.connect()
    wait_connected(qtbot, connection)
    assert not backend.state.enabled
