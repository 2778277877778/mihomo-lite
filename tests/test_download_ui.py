"""Offscreen tests for the Downloads page and the download settings card.

Everything here uses lightweight fakes: no network, no real profile files and
no full app bootstrap. Qt runs on the offscreen platform configured in
conftest.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Qt, Signal

from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import AppSettings, ConnectionState
from mihomo_lite.ui import main_window as main_window_module
from mihomo_lite.ui import settings_page as settings_page_module
from mihomo_lite.ui.download_page import DownloadPage
from mihomo_lite.ui.settings_page import SettingsPage

PROFILE_A = "First"
PROFILE_B = "Second"


class FakeSettingsStore(QObject):
    changed = Signal(object)

    def __init__(self, **values) -> None:
        super().__init__()
        self.current = AppSettings(**values)
        self.updates: list[dict] = []

    def update(self, **changes: object) -> AppSettings:
        self.updates.append(dict(changes))
        data = self.current.model_dump()
        data.update(changes)
        self.current = AppSettings.model_validate(data)
        self.changed.emit(self.current)
        return self.current


class FakeConnection(QObject):
    state_changed = Signal(object)
    session_changed = Signal(object)

    def __init__(self, *, connected: bool = False, session: object = None) -> None:
        super().__init__()
        self.connected = connected
        self._session = session
        self.reload_calls = 0
        self.reload_result = True

    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def session(self) -> object:
        return self._session

    @property
    def state(self) -> ConnectionState:
        return ConnectionState.CONNECTED if self.connected else ConnectionState.STOPPED

    def reload_download_config(self) -> bool:
        self.reload_calls += 1
        return self.reload_result


class FakeDownloadManager(QObject):
    started = Signal()
    progress = Signal(object)
    node_state = Signal(object)
    warning = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.active = False
        self._snapshot = None
        self.start_calls: list[tuple[str, object]] = []
        self.cancel_calls = 0
        self.start_result = True

    @property
    def snapshot(self) -> object:
        return self._snapshot

    def start(self, url: str, target: object) -> bool:
        self.start_calls.append((url, target))
        return self.start_result

    def cancel(self) -> None:
        self.cancel_calls += 1


class FakeCatalog:
    def __init__(self, nodes: list[object]) -> None:
        self._nodes = list(nodes)

    def nodes(self) -> list[object]:
        return list(self._nodes)


def catalog_node(
    key: str,
    name: str,
    profile_name: str,
    *,
    conflict: bool = False,
    conflict_with: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        name=name,
        profile_id=key.split("::", 1)[0],
        profile_name=profile_name,
        proxy={"name": name},
        conflict=conflict,
        conflict_with=conflict_with,
    )


def listener(node: str, port: int, name: str = "ml-download-1") -> SimpleNamespace:
    return SimpleNamespace(name=name, node=node, port=port)


def download_services(
    *,
    settings: FakeSettingsStore,
    connection: FakeConnection | None = None,
    download: FakeDownloadManager | None = None,
    nodes: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        settings=settings,
        connection=connection or FakeConnection(),
        download=download or FakeDownloadManager(),
        catalog=FakeCatalog(nodes or []),
        paths=None,
        core=None,
        runner=None,
    )


def make_page(qtbot, services) -> DownloadPage:
    page = DownloadPage(services)
    qtbot.addWidget(page)
    return page


def two_node_catalog() -> list[object]:
    return [
        catalog_node("p1::node-a", "node-a", PROFILE_A),
        catalog_node("p1::node-b", "node-b", PROFILE_A),
        catalog_node("p2::node-c", "node-c", PROFILE_B),
    ]


# -- navigation ------------------------------------------------------------
def test_downloads_page_sits_right_after_traffic_in_the_sidebar():
    nav = main_window_module._NAV
    assert nav[nav.index("Traffic") + 1] == "Downloads"
    assert len(nav) == 7


# -- DownloadPage -----------------------------------------------------------
def test_download_features_off_hide_node_ui(qtbot):
    settings = FakeSettingsStore()
    page = make_page(qtbot, download_services(settings=settings))

    assert page._nodes_card.isHidden()
    assert page._node_status_card.isHidden()
    assert not page._threads.isEnabled()
    assert page._threads_hint.text() == "Enable multi-threaded download in Settings."


def test_features_off_never_scan_the_catalog(qtbot):
    class ExplodingCatalog:
        def nodes(self):
            raise AssertionError("the catalog must not be scanned while both switches are off")

    settings = FakeSettingsStore()
    services = download_services(settings=settings)
    services.catalog = ExplodingCatalog()
    page = make_page(qtbot, services)
    assert page._tree.topLevelItemCount() == 0


def test_multithreaded_setting_enables_thread_choice(qtbot):
    settings = FakeSettingsStore(download_multithreaded=True)
    page = make_page(qtbot, download_services(settings=settings))

    assert page._threads.isEnabled()
    assert page._threads_hint.text() == ""
    # Multi-node is still off, so its cards stay hidden.
    assert page._nodes_card.isHidden()
    assert page._node_status_card.isHidden()


def test_multi_node_setting_shows_tree_and_node_table(qtbot):
    settings = FakeSettingsStore(
        download_multithreaded=True,
        download_multi_node=True,
    )
    connection = FakeConnection(
        connected=True,
        session=SimpleNamespace(download_listeners=(listener("node-a", 53111),)),
    )
    page = make_page(
        qtbot,
        download_services(
            settings=settings,
            connection=connection,
            nodes=two_node_catalog(),
        ),
    )

    assert not page._nodes_card.isHidden()
    assert not page._node_status_card.isHidden()
    assert page._tree.topLevelItemCount() == 2
    assert page._tree.topLevelItem(0).text(0) == PROFILE_A
    assert page._tree.topLevelItem(0).childCount() == 2
    assert page._tree.topLevelItem(1).text(0) == PROFILE_B

    assert page._table.rowCount() == 1
    assert page._table.item(0, 0).text() == "node-a"
    assert page._table.item(0, 1).text() == "53111"
    # Nothing is selected in settings yet, so the hint asks for a reconnect.
    assert not page._reconnect_hint.isHidden()


def test_checking_a_node_writes_the_selection_back(qtbot):
    settings = FakeSettingsStore(
        download_multithreaded=True,
        download_multi_node=True,
    )
    page = make_page(
        qtbot,
        download_services(settings=settings, nodes=two_node_catalog()),
    )

    first_profile = page._tree.topLevelItem(0)
    first_profile.child(0).setCheckState(0, Qt.CheckState.Checked)
    assert settings.updates[-1]["download_nodes"] == ["p1::node-a"]

    # Selecting everything (top-level order: First, then Second) appends the rest.
    page._select_all_nodes()
    assert settings.updates[-1]["download_nodes"] == [
        "p1::node-a",
        "p1::node-b",
        "p2::node-c",
    ]

    page._select_no_nodes()
    assert settings.updates[-1]["download_nodes"] == []


def test_clicking_a_node_checkbox_selects_it(qtbot):
    settings = FakeSettingsStore(download_multithreaded=True, download_multi_node=True)
    page = make_page(qtbot, download_services(settings=settings, nodes=two_node_catalog()))
    page.show()
    qtbot.wait(20)

    child = page._tree.topLevelItem(0).child(0)
    assert child.checkState(0) == Qt.CheckState.Unchecked
    rect = page._tree.visualItemRect(child)
    page._tree.scrollToItem(child)
    qtbot.mouseClick(
        page._tree.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    assert child.checkState(0) == Qt.CheckState.Checked
    assert settings.updates[-1]["download_nodes"] == [child.data(0, Qt.ItemDataRole.UserRole)]


def test_conflicting_node_is_disabled_with_a_tooltip(qtbot):
    settings = FakeSettingsStore(
        download_multithreaded=True,
        download_multi_node=True,
    )
    nodes = [
        catalog_node("p1::dup", "dup", PROFILE_A),
        catalog_node(
            "p2::dup",
            "dup",
            PROFILE_B,
            conflict=True,
            conflict_with=(PROFILE_A, PROFILE_B),
        ),
    ]
    page = make_page(qtbot, download_services(settings=settings, nodes=nodes))

    conflicted = page._tree.topLevelItem(1).child(0)
    assert conflicted.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert not conflicted.flags() & Qt.ItemFlag.ItemIsEnabled
    assert conflicted.toolTip(0)


def test_node_state_updates_speed_and_status(qtbot):
    settings = FakeSettingsStore(
        download_multithreaded=True,
        download_multi_node=True,
    )
    connection = FakeConnection(
        connected=True,
        session=SimpleNamespace(download_listeners=(listener("node-a", 53111),)),
    )
    page = make_page(
        qtbot,
        download_services(
            settings=settings,
            connection=connection,
            nodes=two_node_catalog(),
        ),
    )

    page._services.download.node_state.emit(
        (
            SimpleNamespace(
                name="node-a",
                state="ok",
                downloaded=4096,
                speed=2048.0,
                message="",
            ),
        )
    )
    assert page._table.item(0, 2).text() == "2.0 KB/s"
    assert page._table.item(0, 3).text() == tr("ok")


def test_progress_updates_bar_and_status_line(qtbot):
    settings = FakeSettingsStore()
    page = make_page(qtbot, download_services(settings=settings))

    page._services.download.progress.emit(
        SimpleNamespace(
            total=1000,
            downloaded=500,
            speed=100.0,
            eta_seconds=5.0,
            threads=4,
            done=False,
            error="",
            nodes=(),
        )
    )
    assert page._progress.value() == 50
    text = page._status.text()
    assert "500 B / 1000 B" in text
    assert "100 B/s" in text
    assert "ETA 5s" in text


def test_finished_signal_updates_the_page(qtbot, tmp_path):
    settings = FakeSettingsStore()
    page = make_page(qtbot, download_services(settings=settings))
    target = tmp_path / "file.zip"

    page._services.download.finished.emit(
        SimpleNamespace(target=target, total=1000, downloaded=1000, ok=True, error="")
    )
    qtbot.wait(10)
    assert page._progress.value() == 100
    assert "Download complete:" in page._message.text()
    assert page._start_button.isEnabled()
    assert not page._cancel_button.isEnabled()

    page._services.download.finished.emit(
        SimpleNamespace(
            target=target, total=1000, downloaded=400, ok=False, error="cancelled"
        )
    )
    qtbot.wait(10)
    assert page._message.text() == tr("Download cancelled.")


def test_start_while_disconnected_never_calls_the_manager(qtbot, tmp_path):
    settings = FakeSettingsStore()
    download = FakeDownloadManager()
    page = make_page(
        qtbot,
        download_services(settings=settings, download=download),
    )

    page._url.setText("https://example.com/file.zip")
    page._target.setText(str(tmp_path / "file.zip"))
    page._start_button.click()

    assert download.start_calls == []
    assert page._message.text() == (
        "Connect first; downloads go through the local Mihomo proxy."
    )


def test_start_validates_url_and_target(qtbot, tmp_path):
    settings = FakeSettingsStore()
    download = FakeDownloadManager()
    page = make_page(
        qtbot,
        download_services(
            settings=settings,
            connection=FakeConnection(connected=True, session=SimpleNamespace()),
            download=download,
        ),
    )

    page._target.setText(str(tmp_path / "file.zip"))
    page._url.setText("ftp://example.com/file.zip")
    page._start_button.click()
    assert download.start_calls == []
    assert page._message.text() == "Enter an http:// or https:// URL."

    page._url.setText("https://example.com/file.zip")
    page._target.setText("")
    page._start_button.click()
    assert download.start_calls == []
    assert page._message.text() == "Choose where the file should be saved."


def test_start_reaches_the_manager_when_connected(qtbot, tmp_path):
    settings = FakeSettingsStore()
    download = FakeDownloadManager()
    page = make_page(
        qtbot,
        download_services(
            settings=settings,
            connection=FakeConnection(connected=True, session=SimpleNamespace()),
            download=download,
        ),
    )

    target = tmp_path / "file.zip"
    page._url.setText("https://example.com/file.zip")
    page._target.setText(str(target))
    page._start_button.click()

    assert len(download.start_calls) == 1
    url, path = download.start_calls[0]
    assert url == "https://example.com/file.zip"
    assert str(path) == str(target)


# -- SettingsPage -----------------------------------------------------------
def settings_services(
    tmp_path,
    *,
    connected: bool = False,
    **values: object,
) -> SimpleNamespace:
    class FakeCore:
        def downloaded_path(self):
            return tmp_path / "missing-mihomo.exe"

        def ensure(self):
            raise RuntimeError("no core in tests")

    return SimpleNamespace(
        settings=FakeSettingsStore(**values),
        connection=FakeConnection(connected=connected),
        core=FakeCore(),
        paths=SimpleNamespace(root=tmp_path),
        runner=None,
    )


@pytest.fixture
def no_startup_writes(monkeypatch):
    monkeypatch.setattr(
        settings_page_module,
        "startup",
        SimpleNamespace(is_enabled=lambda: False, set_enabled=lambda enabled: True),
    )


def test_multi_node_requires_multithreaded_toggle(qtbot, tmp_path, no_startup_writes):
    services = settings_services(tmp_path)
    page = SettingsPage(services)
    qtbot.addWidget(page)

    assert not page._download_multi_node.isEnabled()
    assert not page._download_multi_node.isChecked()
    assert not page._download_threads.isEnabled()

    page._download_multithreaded.setChecked(True)
    assert page._download_multi_node.isEnabled()
    assert page._download_threads.isEnabled()
    assert not page._download_dependency_hint.isVisible()

    # Turning the parent switch off again clears and disables multi-node.
    page._download_multi_node.setChecked(True)
    page._download_multithreaded.setChecked(False)
    assert not page._download_multi_node.isChecked()
    assert not page._download_multi_node.isEnabled()


def test_settings_has_a_button_that_opens_the_downloads_page(
    qtbot, tmp_path, no_startup_writes
):
    services = settings_services(tmp_path)
    page = SettingsPage(services)
    qtbot.addWidget(page)

    emitted: list[bool] = []
    page.open_downloads_requested.connect(lambda: emitted.append(True))
    assert page._open_downloads_button.text() == "Open Downloads page"
    page._open_downloads_button.click()
    assert emitted == [True]


def test_core_verification_shows_a_clear_success_prompt(
    qtbot, tmp_path, no_startup_writes, monkeypatch
):
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        settings_page_module.QMessageBox,
        "information",
        lambda *args: calls.append(args),
    )

    class ImmediateRunner:
        def submit(self, fn, *, on_success=None, on_error=None, **kwargs):
            on_success(SimpleNamespace(version="v1.19.33", path=tmp_path / "mihomo.exe"))

    services = settings_services(tmp_path)
    services.runner = ImmediateRunner()
    page = SettingsPage(services)
    qtbot.addWidget(page)

    page._verify_core()

    assert calls
    assert "Core verified" in str(calls[0][1])
    assert page._core_hint.property("state") == "success"
    assert "v1.19.33" in page._core_hint.text()
    assert "Core verified successfully." in page._status.text()


def test_save_writes_all_four_download_fields(qtbot, tmp_path, no_startup_writes):
    services = settings_services(
        tmp_path,
        download_multithreaded=True,
        download_multi_node=True,
        download_threads=6,
        download_nodes=["p1::node-a"],
    )
    page = SettingsPage(services)
    qtbot.addWidget(page)

    assert len(page._services.settings.current.download_nodes) == 1
    assert "1" in page._download_selected.text()

    page._download_threads.setCurrentIndex(page._download_threads.findData(8))
    page._save()

    written = services.settings.updates[-1]
    assert written["download_multithreaded"] is True
    assert written["download_multi_node"] is True
    assert written["download_threads"] == 8
    assert written["download_nodes"] == ["p1::node-a"]
    # Not connected: tell the user to reconnect, and never touch the manager.
    assert services.connection.reload_calls == 0
    assert "Reconnect to apply the download settings." in page._status.text()


def test_save_applies_download_settings_when_connected(
    qtbot, tmp_path, no_startup_writes
):
    services = settings_services(tmp_path, connected=True)
    page = SettingsPage(services)
    qtbot.addWidget(page)

    page._download_multithreaded.setChecked(True)
    page._save()

    assert services.connection.reload_calls == 1
    assert "Download settings applied." in page._status.text()
