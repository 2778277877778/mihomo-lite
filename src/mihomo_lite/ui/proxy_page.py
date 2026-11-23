"""Proxy groups as a chip row, nodes as a clickable list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
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


class ProxyPage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._groups: list[ProxyGroup] = []
        self._nodes: dict[str, ProxyNode] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._current_group: str = ""
        self._build()

        services.proxy.groups_updated.connect(self._on_groups)
        services.proxy.node_stats.connect(self._on_stats)
        services.proxy.failed.connect(self._on_error)
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
        self._delay_button = QPushButton("Test all delays")
        self._delay_button.clicked.connect(self._test_delay)
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
        self._group_hint = QLabel("")
        self._group_hint.setObjectName("Hint")
        row.addWidget(self._group_hint)
        root.addLayout(row)

        self._node_list = QListWidget()
        self._node_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
            return
        for member in group.members:
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
            self._node_list.addItem(item)
        self._filter_nodes(self._filter.text())

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
        self._services.proxy.select(group.name, node)
        self._status.setText(f"Switching {group.name} to {node}…")

    def _test_delay(self) -> None:
        group = self._group()
        if group is None:
            return
        self._services.proxy.test_group_delay(group.name)
        self._status.setText(f"Testing every node in {group.name}…")

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
        for button in (self._refresh_button, self._delay_button, self._ip_button, self._speed_button):
            button.setEnabled(connected)
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
