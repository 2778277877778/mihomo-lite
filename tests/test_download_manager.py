"""DownloadManager maps settings/session state into engine options."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from mihomo_lite.core.download_manager import DownloadManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.download.types import DownloadResult


class FakeConnection(QObject):
    state_changed = Signal(object)
    session_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.session = None


class FakeEngine:
    instances: list[FakeEngine] = []

    def __init__(self):
        self.options = None
        self.cancel = None
        FakeEngine.instances.append(self)

    def run(self, options, on_snapshot=None, cancel=None):
        self.options = options
        self.cancel = cancel
        if on_snapshot is not None and cancel is not None and not cancel.is_set():
            pass
        return DownloadResult(
            target=options.target,
            total=0,
            downloaded=0,
            ok=True,
        )


def _settings_store(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    return store


def _manager(paths, qapp, monkeypatch):
    FakeEngine.instances.clear()
    monkeypatch.setattr("mihomo_lite.core.download_manager.DownloadEngine", FakeEngine)
    settings = _settings_store(paths, qapp)
    connection = FakeConnection()
    manager = DownloadManager(settings, connection)
    return manager, settings, connection


def test_start_requires_a_connection(paths, qapp, monkeypatch, tmp_path):
    manager, _settings, _connection = _manager(paths, qapp, monkeypatch)
    warnings = []
    manager.warning.connect(warnings.append)
    assert manager.start("https://example.com/a.bin", tmp_path / "a.bin") is False
    assert warnings


def test_both_switches_off_uses_plain_single_node(paths, qapp, monkeypatch, tmp_path):
    manager, settings, connection = _manager(paths, qapp, monkeypatch)
    connection.is_connected = True
    connection.session = _session(23456, ())
    assert manager.start("https://example.com/a.bin", tmp_path / "a.bin") is True
    manager._thread.join(2)
    options = FakeEngine.instances[0].options
    assert options.multithreaded is False
    assert options.multi_node is False
    assert options.node_routes == ()
    assert options.proxy_port == 23456


def test_multithread_uses_the_configured_thread_count(paths, qapp, monkeypatch, tmp_path):
    manager, settings, connection = _manager(paths, qapp, monkeypatch)
    settings.update(download_multithreaded=True, download_threads=12)
    connection.is_connected = True
    connection.session = _session(23456, ())
    assert manager.start("https://example.com/a.bin", tmp_path / "a.bin") is True
    manager._thread.join(2)
    options = FakeEngine.instances[0].options
    assert options.multithreaded is True
    assert options.thread_count == 12
    assert options.multi_node is False


def test_multi_node_maps_listener_ports_to_routes(paths, qapp, monkeypatch, tmp_path):
    manager, settings, connection = _manager(paths, qapp, monkeypatch)
    settings.update(
        download_multithreaded=True,
        download_multi_node=True,
        download_threads=4,
        download_nodes=["p::a", "p::b"],
    )
    connection.is_connected = True
    connection.session = _session(
        23456,
        (
            _listener("ml-download-1", "a", 30001),
            _listener("ml-download-2", "b", 30002),
        ),
    )
    assert manager.start("https://example.com/a.bin", tmp_path / "a.bin") is True
    manager._thread.join(2)
    options = FakeEngine.instances[0].options
    assert options.multi_node is True
    assert [(route.name, route.port) for route in options.node_routes] == [
        ("a", 30001),
        ("b", 30002),
    ]


def test_multi_node_without_listeners_falls_back_with_warning(
    paths, qapp, monkeypatch, tmp_path
):
    manager, settings, connection = _manager(paths, qapp, monkeypatch)
    settings.update(download_multithreaded=True, download_multi_node=True)
    connection.is_connected = True
    connection.session = _session(23456, ())
    warnings = []
    manager.warning.connect(warnings.append)
    assert manager.start("https://example.com/a.bin", tmp_path / "a.bin") is True
    manager._thread.join(2)
    assert FakeEngine.instances[0].options.multi_node is False
    assert any("listeners" in warning for warning in warnings)


def test_cancel_sets_the_engine_event(paths, qapp, monkeypatch, tmp_path):
    manager, _settings, connection = _manager(paths, qapp, monkeypatch)
    connection.is_connected = True
    connection.session = _session(23456, ())
    assert manager.start("https://example.com/a.bin", tmp_path / "a.bin") is True
    manager._thread.join(2)
    # The fake run already returned; cancel is still safe.
    manager.cancel()
    assert isinstance(manager._cancel, threading.Event)
    assert manager.active is False


def _session(mixed_port: int, listeners: tuple):
    from types import SimpleNamespace

    return SimpleNamespace(
        mixed_port=mixed_port,
        api_port=mixed_port + 1,
        download_listeners=listeners,
        core_version="v-test",
    )


def _listener(name: str, node: str, port: int):
    from types import SimpleNamespace

    return SimpleNamespace(name=name, node=node, port=port)
