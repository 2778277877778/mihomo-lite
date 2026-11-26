"""Proxy groups as a chip row, nodes as a clickable list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core import net_tools
from mihomo_lite.core.services import Services
from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.models.proxy import ProxyGroup, ProxyNode
from mihomo_lite.ui.widgets.smooth_scroll import enable_smooth_scroll


class ProxyPage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._groups: list[ProxyGroup] = []
        self._nodes: dict[str, ProxyNode] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._current_group: str = ""
        self._history: dict[str, str] = dict(services.settings.current.last_proxy_nodes)
        self._build()

        services.proxy.groups_updated.connect(self._on_groups)
        services.proxy.node_stats.connect(self._on_stats)
        services.proxy.failed.connect(self._on_error)
        services.proxy.batch_delay_started.connect(self._on_batch_started)
        services.proxy.batch_delay_progress.connect(self._on_batch_progress)
        services.proxy.batch_delay_finished.connect(self._on_batch_finished)
        services.connection.state_changed.connect(self._on_state)
        self._on_state(services.connection.state)

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Proxies")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Pick a group, then click a node to switch.")
        subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        self._ip_button = QPushButton("Check IP")
        self._ip_button.clicked.connect(self._check_ip)
        self._speed_button = QPushButton("Speed test")
        self._speed_button.clicked.connect(self._speed_test)
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(lambda: self._services.proxy.refresh())
        self._delay_button = QPushButton("Test all nodes")
        self._delay_button.setToolTip(tr("Quick latency test for every loaded node."))
        self._delay_button.clicked.connect(self._test_all_delays)
        for button in (self._ip_button, self._speed_button, self._refresh_button, self._delay_button):
            header.addWidget(button)
        root.addLayout(header)

        # Group chips: one row, horizontally scrollable.
        self._group_scroll = QScrollArea()
        self._group_scroll.setWidgetResizable(True)
        self._group_scroll.setFixedHeight(52)
        self._group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._group_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._chip_host = QWidget()
        self._chip_layout = QHBoxLayout(self._chip_host)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(8)
        self._chip_layout.addStretch(1)
        self._group_scroll.setWidget(self._chip_host)
        enable_smooth_scroll(self._group_scroll)
        root.addWidget(self._group_scroll)

        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self._chip_group.idClicked.connect(self._select_chip)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(tr("Filter nodes…"))
        self._filter.textChanged.connect(self._filter_nodes)
        row.addWidget(self._filter, 1)
        self._sort_check = QCheckBox(tr("Sort by latency"))
        self._sort_check.toggled.connect(self._render_nodes)
        row.addWidget(self._sort_check)
        self._previous_button = QPushButton(tr("Previous node"))
        self._previous_button.clicked.connect(self._use_previous_node)
        self._previous_button.setEnabled(False)
        row.addWidget(self._previous_button)
        self._group_hint = QLabel("")
        self._group_hint.setObjectName("Hint")
        row.addWidget(self._group_hint)
        root.addLayout(row)

        self._node_list = QListWidget()
        self._node_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        enable_smooth_scroll(self._node_list)
        self._node_list.itemClicked.connect(self._apply_item)
        root.addWidget(self._node_list, 1)

        self._status = QLabel("")
        self._status.setObjectName("Hint")
        root.addWidget(self._status)

    # -- data --------------------------------------------------------------
    def _on_groups(self, groups: object, nodes: object) -> None:
        self._groups = list(groups) if isinstance(groups, list) else []
        self._nodes = dict(nodes) if isinstance(nodes, dict) else {}
        self._rebuild_chips()
        self._status.setText(f"{len(self._groups)} groups, {len(self._nodes)} nodes loaded.")
        self._render_nodes()

    def _on_stats(self, stats: object) -> None:
        if isinstance(stats, dict):
            self._stats = dict(stats)
            self._render_nodes()

    def _rebuild_chips(self) -> None:
        for button in self._chip_group.buttons():
            self._chip_group.removeButton(button)
            button.deleteLater()
        while self._chip_layout.count() > 1:
            item = self._chip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, group in enumerate(self._groups):
            name = group.name
            button = QPushButton(name)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setObjectName("Chip")
            self._chip_group.addButton(button, index)
            self._chip_layout.insertWidget(self._chip_layout.count() - 1, button)

        preferred = self._preferred_group()
        if preferred is not None:
            self._select_group(preferred.name)

    def _preferred_group(self) -> ProxyGroup | None:
        for group in self._groups:
            if group.name != "GLOBAL" and group.is_selector:
                return group
        for group in self._groups:
            if group.name != "GLOBAL":
                return group
        return self._groups[0] if self._groups else None

    def _select_chip(self, index: int) -> None:
        if 0 <= index < len(self._groups):
            self._select_group(self._groups[index].name)
            self._render_nodes()

    def _select_group(self, name: str) -> None:
        self._current_group = name
        for index, group in enumerate(self._groups):
            if group.name == name:
                button = self._chip_group.button(index)
                if button is not None and not button.isChecked():
                    button.setChecked(True)
        group = self._group()
        if group is not None:
            self._group_hint.setText(f"{group.type} · active: {group.now or '-'}")
        self._update_previous_button()

    def _group(self) -> ProxyGroup | None:
        for group in self._groups:
            if group.name == self._current_group:
                return group
        return None

    def _node_title(self, name: str, delay: int | None) -> str:
        stats = self._stats.get(name, {})
        value = delay if delay is not None else stats.get("delay")
        if value is None:
            return name
        if value <= 0:
            return f"{name}    timeout"
        jitter = stats.get("jitter", 0)
        suffix = f"  ±{jitter} ms" if jitter else ""
        return f"{name}    {value} ms{suffix}"

    def _render_nodes(self) -> None:
        group = self._group()
        self._node_list.clear()
        if group is None:
            self._update_previous_button()
            return
        members = list(group.members)
        if self._sort_check.isChecked():
            members.sort(key=self._latency_sort_key)
        for member in members:
            delay = group.delay_of(member)
            label = self._node_title(member, delay)
            if member == group.now:
                label = f"●  {label}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, member)
            if member == group.now:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            colour = self._delay_colour(delay)
            if colour is not None:
                item.setForeground(QBrush(QColor(colour)))
            self._node_list.addItem(item)
        self._filter_nodes(self._filter.text())
        self._update_previous_button()

    def _latency_sort_key(self, name: str) -> tuple[bool, int, str]:
        delay = self._stats.get(name, {}).get("delay")
        if delay is None:
            group = self._group()
            delay = group.delay_of(name) if group is not None else None
        return (delay is None or delay <= 0, delay or 10**9, name.lower())

    def _update_previous_button(self) -> None:
        group = self._group()
        target = self._history.get(group.name) if group is not None else None
        can_use = bool(
            group is not None
            and target
            and target in group.members
            and target != group.now
        )
        self._previous_button.setEnabled(can_use)
        self._previous_button.setToolTip(
            tr("Switch back to {node}").format(node=target)
            if can_use and target
            else tr("No previous node for this group.")
        )

    @staticmethod
    def _delay_colour(delay: int | None) -> str | None:
        if delay is None:
            return None
        if delay <= 0:
            return "#ff8080"
        if delay <= 120:
            return "#5fe3a1"
        if delay <= 300:
            return "#f5c26b"
        return "#ff9b7a"

    def _filter_nodes(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self._node_list.count()):
            item = self._node_list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    # -- actions -----------------------------------------------------------
    def _apply_item(self, item: QListWidgetItem) -> None:
        group = self._group()
        node = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if group is None or not node or not group.is_selector:
            return
        if node == group.now:
            return
        previous = group.now
        if previous:
            self._remember_previous(group.name, previous)
        # Optimistic update so the selection highlights immediately; the next
        # refresh reconciles with the core.
        group.now = node
        self._render_nodes()
        self._services.proxy.select(group.name, node)
        self._status.setText(f"Switching {group.name} to {node}…")

    def _remember_previous(self, group_name: str, node: str) -> None:
        if self._history.get(group_name) == node:
            return
        self._history[group_name] = node
        self._services.settings.update(last_proxy_nodes=dict(self._history))

    def _use_previous_node(self) -> None:
        group = self._group()
        target = self._history.get(group.name) if group is not None else None
        if group is None or not target or target not in group.members:
            self._status.setText(tr("No previous node for this group."))
            self._update_previous_button()
            return
        if target == group.now:
            self._update_previous_button()
            return
        current = group.now
        if current:
            self._remember_previous(group.name, current)
        group.now = target
        self._render_nodes()
        self._services.proxy.select(group.name, target)
        self._status.setText(f"Switching {group.name} back to {target}…")

    def _test_all_delays(self) -> None:
        if not self._services.connection.is_connected:
            self._status.setText(tr("Connect first."))
            return
        if self._services.proxy.batch_running:
            return
        total = len(self._services.proxy.nodes)
        self._status.setText(tr("Testing all nodes: {done}/{total}…").format(done=0, total=total))
        if not self._services.proxy.test_all_delays():
            self._status.setText(tr("No nodes to test."))

    def _on_batch_started(self, total: int) -> None:
        self._delay_button.setEnabled(False)
        self._status.setText(
            tr("Testing all nodes: {done}/{total}…").format(done=0, total=total)
        )

    def _on_batch_progress(self, done: int, total: int) -> None:
        self._status.setText(
            tr("Testing all nodes: {done}/{total}…").format(done=done, total=total)
        )

    def _on_batch_finished(self, results: object) -> None:
        self._delay_button.setEnabled(self._services.connection.is_connected)
        count = len(results) if isinstance(results, dict) else 0
        self._status.setText(tr("Tested {count} nodes.").format(count=count))
        if count:
            self._sort_check.setChecked(True)
            self._render_nodes()

    def _proxy_server(self) -> str | None:
        session = self._services.connection.session
        return session.proxy_server if session is not None else None

    def _check_ip(self) -> None:
        if not self._services.connection.is_connected:
            self._status.setText(tr("Connect first."))
            return
        self._status.setText(tr("Checking the public IP…"))
        self._services.runner.submit(
            net_tools.fetch_public_ip,
            args=(self._proxy_server(),),
            on_success=lambda result: self._status.setText(
                f"Public IP: {result.address}  ({result.source})"
            ),
            on_error=self._status.setText,
        )

    def _speed_test(self) -> None:
        group = self._group()
        item = self._node_list.currentItem()
        api = self._services.connection.api
        if group is None or item is None or api is None:
            self._status.setText(tr("Connect first and pick a node."))
            return
        if not group.is_selector:
            self._status.setText(tr("Speed test needs a Selector group."))
            return
        node = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not node:
            return
        server = self._proxy_server()
        previous = group.now
        self._status.setText(f"Testing {node}…")

        def restore() -> None:
            if previous:
                self._services.runner.submit(api.select_proxy, args=(group.name, previous))

        def failed(message: str) -> None:
            restore()
            self._status.setText(message)

        def measured(mbps: float) -> None:
            restore()
            self._status.setText(f"{node}: {mbps:.1f} Mbit/s")

        def switched(_result: object) -> None:
            self._services.runner.submit(
                net_tools.measure_download,
                args=(server,),
                on_success=measured,
                on_error=failed,
            )

        self._services.runner.submit(
            api.select_proxy, args=(group.name, node), on_success=switched, on_error=failed
        )

    def _on_error(self, message: str) -> None:
        self._status.setText(message)

    def _on_state(self, state: ConnectionState) -> None:
        connected = state is ConnectionState.CONNECTED
        for button in (self._refresh_button, self._ip_button, self._speed_button):
            button.setEnabled(connected)
        self._delay_button.setEnabled(connected and not self._services.proxy.batch_running)
        self._update_previous_button()
        self._filter.setEnabled(connected)
        if not connected:
            self._groups = []
            self._nodes = {}
            self._rebuild_chips()
            self._node_list.clear()
            profile = self._services.profiles.active_profile()
            if profile is not None:
                self._group_hint.setText(
                    f"Profile '{profile.name}' is ready. Press Connect to load nodes."
                )
            else:
                self._group_hint.setText(tr("Import a profile first, then connect."))
        elif not self._groups:
            self._services.proxy.refresh()
