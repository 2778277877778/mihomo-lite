"""Proxy groups and node selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core import net_tools
from mihomo_lite.core.services import Services
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.models.proxy import ProxyGroup, ProxyNode


class ProxyPage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._groups: list[ProxyGroup] = []
        self._nodes: dict[str, ProxyNode] = {}
        self._build()

        services.proxy.groups_updated.connect(self._on_groups)
        services.proxy.failed.connect(self._on_error)
        services.connection.state_changed.connect(self._on_state)
        self._on_state(services.connection.state)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Proxies")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Pick a group, then a node.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        header.addStretch(1)

        self._ip_button = QPushButton("Check IP")
        self._ip_button.clicked.connect(self._check_ip)
        self._speed_button = QPushButton("Speed test")
        self._speed_button.clicked.connect(self._speed_test)
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(lambda: self._services.proxy.refresh())
        self._delay_button = QPushButton("Test latency")
        self._delay_button.clicked.connect(self._test_delay)
        header.addWidget(self._ip_button)
        header.addWidget(self._speed_button)
        header.addWidget(self._refresh_button)
        header.addWidget(self._delay_button)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._group_list = QListWidget()
        self._group_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._group_list.setMinimumWidth(230)
        self._group_list.currentRowChanged.connect(self._on_group_selected)
        splitter.addWidget(self._group_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._group_hint = QLabel("Select a policy group.")
        self._group_hint.setObjectName("Hint")
        right_layout.addWidget(self._group_hint)

        self._node_filter = QLineEdit()
        self._node_filter.setPlaceholderText("Filter nodes…")
        self._node_filter.textChanged.connect(self._filter_nodes)
        right_layout.addWidget(self._node_filter)

        self._node_list = QListWidget()
        self._node_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._node_list.itemDoubleClicked.connect(self._activate_item)
        right_layout.addWidget(self._node_list, 1)

        actions = QHBoxLayout()
        self._use_button = QPushButton("Use selected node")
        self._use_button.setObjectName("Primary")
        self._use_button.clicked.connect(self._activate_current)
        actions.addStretch(1)
        actions.addWidget(self._use_button)
        right_layout.addLayout(actions)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._status = QLabel("")
        self._status.setObjectName("Hint")
        root.addWidget(self._status)

    # -- data --------------------------------------------------------------
    def _on_groups(self, groups: object, nodes: object) -> None:
        self._groups = list(groups) if isinstance(groups, list) else []
        self._nodes = dict(nodes) if isinstance(nodes, dict) else {}
        self._group_list.blockSignals(True)
        self._group_list.clear()
        for group in self._groups:
            label = f"{group.name}\n{group.type} · {group.now or '-'}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, group.name)
            self._group_list.addItem(item)
        self._group_list.blockSignals(False)
        if self._groups:
            self._group_list.setCurrentRow(self._preferred_group_row())
        self._status.setText(f"{len(self._groups)} groups, {len(self._nodes)} nodes loaded.")

    def _preferred_group_row(self) -> int:
        """GLOBAL is rarely what a user wants; prefer the first real selector."""
        for index, group in enumerate(self._groups):
            if group.name != "GLOBAL" and group.is_selector:
                return index
        for index, group in enumerate(self._groups):
            if group.name != "GLOBAL":
                return index
        return 0

    def _current_group(self) -> ProxyGroup | None:
        item = self._group_list.currentItem()
        if item is None:
            return None
        name = item.data(Qt.ItemDataRole.UserRole)
        for group in self._groups:
            if group.name == name:
                return group
        return None

    def _on_group_selected(self, _row: int) -> None:
        group = self._current_group()
        self._node_list.clear()
        if group is None:
            self._group_hint.setText("Select a policy group.")
            return
        self._group_hint.setText(f"{group.name} · {group.type} · active: {group.now or '-'}")
        self._use_button.setEnabled(group.is_selector)
        for member in group.members:
            node = self._nodes.get(member)
            delay = group.delay_of(member)
            if delay is None and node is not None:
                delay = node.delay_ms
            label = member
            if delay is not None:
                label += f"    {delay} ms" if delay > 0 else "    timeout"
            if member == group.now:
                label += "   ✓"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, member)
            self._node_list.addItem(item)
            if member == group.now:
                self._node_list.setCurrentItem(item)

    def _proxy_server(self) -> str | None:
        session = self._services.connection.session
        return session.proxy_server if session is not None else None

    def _check_ip(self) -> None:
        if not self._services.connection.is_connected:
            self._status.setText("Connect first.")
            return
        self._status.setText("Checking the public IP…")
        self._services.runner.submit(
            net_tools.fetch_public_ip,
            args=(self._proxy_server(),),
            on_success=lambda result: self._status.setText(
                f"Public IP: {result.address}  ({result.source})"
            ),
            on_error=self._status.setText,
        )

    def _speed_test(self) -> None:
        group = self._current_group()
        item = self._node_list.currentItem()
        api = self._services.connection.api
        if group is None or item is None or api is None:
            self._status.setText("Connect first and pick a node.")
            return
        if not group.is_selector:
            self._status.setText("Speed test needs a Selector group.")
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
            api.select_proxy,
            args=(group.name, node),
            on_success=switched,
            on_error=failed,
        )

    def _filter_nodes(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self._node_list.count()):
            item = self._node_list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    # -- actions -----------------------------------------------------------
    def _activate_current(self) -> None:
        item = self._node_list.currentItem()
        if item is not None:
            self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        group = self._current_group()
        if group is None or not group.is_selector:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if not name:
            return
        self._services.proxy.select(group.name, str(name))
        self._status.setText(f"Switching {group.name} to {name}…")

    def _test_delay(self) -> None:
        group = self._current_group()
        if group is None:
            return
        self._services.proxy.test_group_delay(group.name)
        self._status.setText(f"Testing {group.name}…")

    def _on_error(self, message: str) -> None:
        self._status.setText(message)

    def _on_state(self, state: ConnectionState) -> None:
        connected = state is ConnectionState.CONNECTED
        self._refresh_button.setEnabled(connected)
        self._delay_button.setEnabled(connected)
        self._ip_button.setEnabled(connected)
        self._speed_button.setEnabled(connected)
        self._use_button.setEnabled(connected and (self._current_group() is not None))
        if not connected:
            self._group_list.clear()
            self._node_list.clear()
            self._group_hint.setText("Connect first to load proxy groups.")
            self._status.setText("")
        elif not self._groups:
            self._services.proxy.refresh()
