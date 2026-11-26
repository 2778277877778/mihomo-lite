"""Downloads: fetch a file through the local Mihomo proxy.

Multi-threaded and multi-node downloads are optional settings; the page only
exposes those controls when they are enabled, and it never builds segmented
download state itself - the DownloadManager owns all of that.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core.traffic_monitor import human_bytes, human_speed
from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.ui.widgets.controls import Combo
from mihomo_lite.ui.widgets.smooth_scroll import enable_smooth_scroll

if TYPE_CHECKING:
    from mihomo_lite.core.services import Services

log = logging.getLogger(__name__)

_TABLE_COLUMNS = ("Node", "Port", "Speed", "Status")


def _first_attr(obj: object, *names: str) -> Any:
    """Return the first attribute that exists and is not None (duck typing)."""
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class _CheckableTree(QTreeWidget):
    """A tree where clicking anywhere on a node row toggles its checkbox."""

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        item = self.itemAt(event.position().toPoint())
        if item is None or item.parent() is None:
            super().mouseReleaseEvent(event)
            return
        before = item.checkState(0)
        super().mouseReleaseEvent(event)
        enabled = bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        checkable = bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        if enabled and checkable and item.checkState(0) == before:
            item.setCheckState(
                0,
                Qt.CheckState.Unchecked
                if before == Qt.CheckState.Checked
                else Qt.CheckState.Checked,
            )


class DownloadPage(QWidget):
    open_settings_requested = Signal()

    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._syncing = False
        self._writing = False
        self._node_rows: dict[str, int] = {}
        self._build()
        self._wire()
        self._apply_settings()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        enable_smooth_scroll(scroll)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 18, 32, 18)
        root.setSpacing(14)

        title = QLabel("Downloads")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Download files through the local Mihomo proxy. "
            "Multi-threaded and multi-node downloads are optional."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._build_form_card())
        root.addWidget(self._build_nodes_card())
        root.addWidget(self._build_node_status_card())
        root.addStretch(1)

    def _section(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("MetricLabel")
        layout.addWidget(heading)
        if subtitle:
            hint = QLabel(subtitle)
            hint.setObjectName("Hint")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        return card, layout

    def _build_form_card(self) -> QWidget:
        card, layout = self._section("Download file")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._url = QLineEdit()
        self._url.setObjectName("DownloadUrl")
        self._url.setPlaceholderText("https://example.com/file.zip")
        grid.addWidget(QLabel("URL"), 0, 0)
        grid.addWidget(self._url, 0, 1, 1, 2)

        self._target = QLineEdit()
        self._target.setObjectName("DownloadTarget")
        self._target.setPlaceholderText("C:\\Users\\you\\Downloads\\file.zip")
        self._browse_button = QPushButton("Browse…")
        self._browse_button.clicked.connect(self._browse)
        grid.addWidget(QLabel("Save to"), 1, 0)
        grid.addWidget(self._target, 1, 1)
        grid.addWidget(self._browse_button, 1, 2)

        self._threads = Combo()
        self._threads.setObjectName("DownloadThreads")
        self._threads.addItem("Auto (4–16)", 0)
        for count in range(4, 17):
            self._threads.addItem(str(count), count)
        self._threads_hint = QLabel("")
        self._threads_hint.setObjectName("Hint")
        self._threads_hint.setWordWrap(True)
        grid.addWidget(QLabel("Threads"), 2, 0)
        grid.addWidget(self._threads, 2, 1)
        grid.addWidget(self._threads_hint, 2, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self._node_hint = QLabel("")
        self._node_hint.setObjectName("Hint")
        self._node_hint.setWordWrap(True)
        layout.addWidget(self._node_hint)
        self._open_settings_button = QPushButton("Open download settings")
        self._open_settings_button.clicked.connect(self.open_settings_requested.emit)
        layout.addWidget(self._open_settings_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._progress = QProgressBar()
        self._progress.setObjectName("DownloadProgress")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setObjectName("DownloadStatus")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._message = QLabel("")
        self._message.setObjectName("Hint")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        buttons = QHBoxLayout()
        self._start_button = QPushButton("Start download")
        self._start_button.setObjectName("Primary")
        self._start_button.clicked.connect(self._start)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self._start_button)
        buttons.addWidget(self._cancel_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return card

    def _build_nodes_card(self) -> QWidget:
        card, layout = self._section(
            "Multi-node downloads",
            "Selections can span profiles. Reconnect after changing them.",
        )
        self._nodes_card = card

        self._tree = _CheckableTree()
        self._tree.setObjectName("DownloadTree")
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tree.setMinimumHeight(150)
        self._tree.setMaximumHeight(240)
        layout.addWidget(self._tree)

        actions = QHBoxLayout()
        self._select_all_button = QPushButton("Select all")
        self._select_all_button.clicked.connect(self._select_all_nodes)
        self._select_none_button = QPushButton("Select none")
        self._select_none_button.clicked.connect(self._select_no_nodes)
        actions.addWidget(self._select_all_button)
        actions.addWidget(self._select_none_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return card

    def _build_node_status_card(self) -> QWidget:
        card, layout = self._section("Node status")
        self._node_status_card = card

        self._reconnect_hint = QLabel("Reconnect to apply the selected nodes.")
        self._reconnect_hint.setObjectName("Hint")
        self._reconnect_hint.setWordWrap(True)
        layout.addWidget(self._reconnect_hint)

        self._table = QTableWidget(0, len(_TABLE_COLUMNS))
        self._table.setObjectName("DownloadNodeTable")
        self._table.setHorizontalHeaderLabels([tr(name) for name in _TABLE_COLUMNS])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(130)
        layout.addWidget(self._table)
        return card

    def _wire(self) -> None:
        services = self._services
        services.settings.changed.connect(self._on_settings_changed)
        services.connection.state_changed.connect(self._on_state_changed)
        services.connection.session_changed.connect(self._on_session_changed)

        download = services.download
        download.started.connect(self._on_started)
        download.progress.connect(self._on_progress)
        download.node_state.connect(self._on_node_state)
        download.warning.connect(self._on_warning)
        download.finished.connect(self._on_finished)
        download.failed.connect(self._on_failed)

        self._threads.currentIndexChanged.connect(self._on_threads_changed)
        self._tree.itemChanged.connect(self._on_tree_item_changed)

    # -- settings / visibility --------------------------------------------
    def _apply_settings(self, *, rebuild: bool = True) -> None:
        settings = self._services.settings.current
        multithreaded = bool(settings.download_multithreaded)
        multi_node = bool(multithreaded and settings.download_multi_node)

        self._syncing = True
        try:
            index = self._threads.findData(int(settings.download_threads))
            self._threads.setCurrentIndex(max(0, index))
            self._threads.setEnabled(multithreaded)
            self._threads_hint.setText(
                "" if multithreaded else tr("Enable multi-threaded download in Settings.")
            )
            self._nodes_card.setVisible(multi_node)
            self._node_status_card.setVisible(multi_node)
            self._open_settings_button.setVisible(not multi_node)
            if multi_node:
                self._node_hint.setText(
                    tr("Multi-node is enabled. Select the nodes that may carry segments below.")
                )
                if rebuild:
                    self._populate_tree(settings.download_nodes)
            else:
                self._tree.clear()
                if multithreaded:
                    self._node_hint.setText(
                        tr(
                            "Multi-node is off. Open download settings to enable it, then "
                            "select nodes here."
                        )
                    )
                else:
                    self._node_hint.setText(
                        tr(
                            "Multi-threaded download is off; this page uses a normal "
                            "single-threaded download. Open download settings to enable "
                            "multi-thread and multi-node mode."
                        )
                    )
        finally:
            self._syncing = False

        self._reload_node_table()
        self._sync_active()

    def _on_settings_changed(self, _settings: object) -> None:
        self._apply_settings(rebuild=not self._writing)

    def _on_threads_changed(self, _index: int) -> None:
        if self._syncing:
            return
        value = self._threads.currentData()
        if value is None:
            return
        self._writing = True
        try:
            self._services.settings.update(download_threads=int(value))
        finally:
            self._writing = False

    # -- node selection ----------------------------------------------------
    def _populate_tree(self, selected: list[str]) -> None:
        self._tree.clear()
        catalog = getattr(self._services, "catalog", None)
        if catalog is None:
            return
        try:
            nodes = list(catalog.nodes())
        except Exception as exc:  # noqa: BLE001 - a broken profile must not break the page
            log.warning("could not list download nodes: %s", exc)
            return

        selected_keys = set(selected)
        groups: dict[str, list[Any]] = {}
        for node in nodes:
            groups.setdefault(str(node.profile_name), []).append(node)

        for profile_name, group in groups.items():
            top = QTreeWidgetItem([profile_name])
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for node in sorted(group, key=lambda item: str(item.name).lower()):
                child = QTreeWidgetItem([str(node.name)])
                child.setData(0, Qt.ItemDataRole.UserRole, node.key)
                if node.conflict:
                    # Disabled: the same name is defined differently in several profiles.
                    child.setFlags(Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    child.setToolTip(
                        0,
                        tr(
                            "Conflicting node: defined differently in several profiles; "
                            "rename one before selecting it."
                        )
                        + f" ({', '.join(node.conflict_with)})",
                    )
                else:
                    child.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    child.setCheckState(
                        0,
                        Qt.CheckState.Checked
                        if node.key in selected_keys
                        else Qt.CheckState.Unchecked,
                    )
                top.addChild(child)
            self._tree.addTopLevelItem(top)
            top.setExpanded(True)

    def _selected_node_keys(self) -> list[str]:
        keys: list[str] = []
        for index in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(index)
            for row in range(top.childCount()):
                child = top.child(row)
                if child.checkState(0) != Qt.CheckState.Checked:
                    continue
                key = child.data(0, Qt.ItemDataRole.UserRole)
                if key:
                    keys.append(str(key))
        return keys

    def _selected_node_names(self) -> list[str]:
        keys = set(self._selected_node_keys())
        if not keys:
            return []
        catalog = getattr(self._services, "catalog", None)
        if catalog is None:
            return []
        try:
            nodes = catalog.nodes()
        except Exception:  # noqa: BLE001 - hint only
            return []
        return [str(node.name) for node in nodes if node.key in keys]

    def _on_tree_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._syncing or item.parent() is None:
            return
        self._persist_nodes()

    def _persist_nodes(self) -> None:
        keys = self._selected_node_keys()
        current = list(getattr(self._services.settings.current, "download_nodes", []))
        if keys == current:
            return
        self._writing = True
        try:
            self._services.settings.update(download_nodes=keys)
        finally:
            self._writing = False
        self._update_reconnect_hint()

    def _select_all_nodes(self) -> None:
        self._set_all_nodes(Qt.CheckState.Checked)

    def _select_no_nodes(self) -> None:
        self._set_all_nodes(Qt.CheckState.Unchecked)

    def _set_all_nodes(self, state: Qt.CheckState) -> None:
        self._syncing = True
        try:
            for index in range(self._tree.topLevelItemCount()):
                top = self._tree.topLevelItem(index)
                for row in range(top.childCount()):
                    child = top.child(row)
                    if not child.flags() & Qt.ItemFlag.ItemIsEnabled:
                        continue
                    child.setCheckState(0, state)
        finally:
            self._syncing = False
        self._persist_nodes()

    # -- node status table -------------------------------------------------
    def _listeners(self) -> tuple[Any, ...]:
        session = self._services.connection.session
        if session is None:
            return ()
        return tuple(getattr(session, "download_listeners", ()) or ())

    def _reload_node_table(self) -> None:
        self._table.setRowCount(0)
        self._node_rows.clear()
        settings = self._services.settings.current
        if not (settings.download_multithreaded and settings.download_multi_node):
            self._update_reconnect_hint()
            return
        for row, listener in enumerate(self._listeners()):
            node = str(getattr(listener, "node", ""))
            port = str(getattr(listener, "port", ""))
            self._table.insertRow(row)
            for column, text in enumerate((node, port, "-", "-")):
                item = QTableWidgetItem(text)
                if column in (1, 2):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(row, column, item)
            self._node_rows[node] = row
        self._update_reconnect_hint()

    def _update_reconnect_hint(self) -> None:
        settings = self._services.settings.current
        multi_node = bool(settings.download_multithreaded and settings.download_multi_node)
        if not multi_node:
            self._reconnect_hint.setVisible(False)
            return
        listeners = {str(getattr(listener, "node", "")) for listener in self._listeners()}
        if not listeners:
            self._reconnect_hint.setVisible(True)
            return
        self._reconnect_hint.setVisible(set(self._selected_node_names()) != listeners)

    def _apply_node_states(self, states: object) -> None:
        try:
            entries = tuple(states)  # type: ignore[arg-type]
        except TypeError:
            return
        for state in entries:
            name = str(_first_attr(state, "node", "name") or "")
            row = self._node_rows.get(name)
            if row is None:
                continue
            speed = _first_attr(state, "speed", "current_speed", "bytes_per_second", "rate")
            if speed is not None:
                item = self._table.item(row, 2)
                if item is not None:
                    item.setText(human_speed(float(speed)))
            status = _first_attr(state, "status", "state", "phase")
            if status is not None:
                item = self._table.item(row, 3)
                if item is not None:
                    item.setText(self._status_text(status))
                    message = _first_attr(state, "message", "error")
                    if message:
                        item.setToolTip(str(message))

    @staticmethod
    def _status_text(status: object) -> str:
        text = str(getattr(status, "value", status))
        return tr(text) if text else "-"

    # -- download manager signals -----------------------------------------
    def _on_state_changed(self, state: object) -> None:
        if state is not ConnectionState.CONNECTED:
            self._reload_node_table()
        self._sync_active()

    def _on_session_changed(self, _session: object) -> None:
        self._reload_node_table()

    def _on_started(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._status.setText(tr("Starting download…"))
        self._sync_active()

    def _on_progress(self, snapshot: object) -> None:
        downloaded = _as_int(
            _first_attr(snapshot, "downloaded", "bytes_downloaded", "received")
        )
        total = _as_int(_first_attr(snapshot, "total", "total_bytes", "size"))
        speed = _as_int(_first_attr(snapshot, "speed", "bytes_per_second", "rate"))
        eta = _first_attr(snapshot, "eta", "eta_seconds", "remaining", "seconds_left")

        if total > 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(max(0, min(100, int(downloaded * 100 / total))))
        elif self._download_active():
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)

        if total > 0:
            text = f"{human_bytes(downloaded)} / {human_bytes(total)}"
        else:
            text = human_bytes(downloaded)
        text += f"  ·  {human_speed(speed)}"
        if eta is not None and _as_int(eta) > 0:
            text += f"  ·  {tr('ETA')} {self._format_eta(_as_int(eta))}"
        self._status.setText(text)

        nodes = getattr(snapshot, "nodes", None)
        if nodes:
            self._apply_node_states(nodes)

    def _on_node_state(self, states: object) -> None:
        self._apply_node_states(states)

    def _on_warning(self, message: str) -> None:
        self._message.setText(tr(message))

    def _on_finished(self, result: object) -> None:
        ok_value = _first_attr(result, "ok", "success")
        ok = True if ok_value is None else bool(ok_value)
        target = _first_attr(result, "target", "path")
        # Keep a fallback warning (for example "server does not support ranges")
        # visible after the completion line instead of overwriting it.
        warning = self._message.text().strip()
        self._progress.setRange(0, 100)
        if ok:
            self._progress.setValue(100)
            message = (
                tr("Download complete: {path}").format(path=target or "-")
                if target
                else tr("Download complete.")
            )
            if warning and warning != message:
                message = f"{message} {warning}"
            self._message.setText(message)
        else:
            self._progress.setValue(0)
            error = _first_attr(result, "error", "message")
            cancelled = str(error or "").lower() in ("cancelled", "canceled")
            if cancelled:
                self._message.setText(tr("Download cancelled."))
            elif error:
                self._message.setText(tr("Download failed: {error}").format(error=error))
            else:
                self._message.setText(tr("Download failed."))
        self._set_running_buttons(False)
        QTimer.singleShot(0, self._sync_active)

    def _on_failed(self, message: str) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._message.setText(tr("Download failed: {error}").format(error=tr(message)))
        self._set_running_buttons(False)
        QTimer.singleShot(0, self._sync_active)

    def _download_active(self) -> bool:
        try:
            return bool(self._services.download.active)
        except Exception:  # noqa: BLE001 - the fake/real manager must never break the UI
            return False

    def _set_running_buttons(self, active: bool) -> None:
        self._start_button.setEnabled(not active)
        self._cancel_button.setEnabled(active)

    def _sync_active(self) -> None:
        self._set_running_buttons(self._download_active())

    # -- actions -----------------------------------------------------------
    def _browse(self) -> None:
        current = self._target.text().strip()
        path, _filter = QFileDialog.getSaveFileName(
            self,
            tr("Save downloaded file"),
            current or str(Path.home() / "Downloads"),
            tr("All files (*)"),
        )
        if path:
            self._target.setText(path)

    def _start(self) -> None:
        url = self._url.text().strip()
        target = self._target.text().strip()
        if not url.lower().startswith(("http://", "https://")):
            self._message.setText(tr("Enter an http:// or https:// URL."))
            return
        if not target:
            self._message.setText(tr("Choose where the file should be saved."))
            return
        if not self._services.connection.is_connected:
            self._message.setText(
                tr("Connect first; downloads go through the local Mihomo proxy.")
            )
            return
        self._message.setText("")
        try:
            started = bool(self._services.download.start(url, Path(target)))
        except Exception as exc:  # noqa: BLE001 - report instead of crashing the window
            log.exception("could not start the download")
            self._message.setText(tr("Download failed: {error}").format(error=exc))
            return
        if started:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._status.setText(tr("Starting download…"))
        self._sync_active()

    def _cancel(self) -> None:
        self._services.download.cancel()
        self._message.setText(tr("Cancelling…"))

    # -- formatting --------------------------------------------------------
    @staticmethod
    def _format_eta(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes:02d}m"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"
