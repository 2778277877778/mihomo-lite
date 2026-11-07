"""Proxy groups and node selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

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
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Proxies")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Pick a policy group, then choose the node you want.")
        subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(lambda: self._services.proxy.refresh())
        self._delay_button = QPushButton("Test latency")
        self._delay_button.clicked.connect(self._test_delay)
        header.addWidget(self._refresh_button)
        header.addWidget(self._delay_button)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._group_list = QListWidget()
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

        self._node_list = QListWidget()
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
        self._use_button.setEnabled(connected and (self._current_group() is not None))
        if not connected:
            self._group_list.clear()
            self._node_list.clear()
            self._group_hint.setText("Connect first to load proxy groups.")
            self._status.setText("")
        elif not self._groups:
            self._services.proxy.refresh()
