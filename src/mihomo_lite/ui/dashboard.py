"""Dashboard: the one screen that answers 'is it on, and what is it doing'."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core import net_tools
from mihomo_lite.core.services import Services
from mihomo_lite.core.traffic_monitor import TrafficSample, human_bytes
from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.ui.widgets.latency_chart import LatencyChart
from mihomo_lite.ui.widgets.status import KeyValueRow, StatusPill
from mihomo_lite.ui.widgets.toggle import ToggleSwitch
from mihomo_lite.utils.net import local_ip


class DashboardPage(QWidget):
    open_settings_requested = Signal()

    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._last_sample = TrafficSample()
        self._public_ip: str | None = None
        self._ip_busy = False
        self._build()

        services.connection.state_changed.connect(self._on_state)
        services.connection.session_changed.connect(lambda _s: self._refresh_session())
        services.traffic.sample.connect(self._on_traffic)
        services.proxy.groups_updated.connect(lambda _g, _n: self._refresh_current_node())
        services.proxy.node_stats.connect(self._on_node_stats)
        services.proxy.mode_changed.connect(self._sync_mode)
        services.connection.state_changed.connect(self._on_mode_state)
        services.profiles.profiles_changed.connect(self._refresh_session)
        services.profiles.active_changed.connect(lambda _p: self._refresh_session())

        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._refresh_uptime)
        self._uptime_timer.start()

        # Periodic latency/jitter sampling for the node shown on the dashboard.
        self._delay_timer = QTimer(self)
        self._delay_timer.setInterval(20000)
        self._delay_timer.timeout.connect(self._probe_current_node)
        self._delay_timer.start()
        QTimer.singleShot(3000, self._probe_current_node)

        self._public_ip: str | None = None
        self._ip_busy = False
        self._ip_timer = QTimer(self)
        self._ip_timer.setInterval(60000)
        self._ip_timer.timeout.connect(self._check_public_ip)
        self._ip_timer.start()

        self._on_state(services.connection.state)
        self._refresh_session()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Start, stop and watch your traffic.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        header.addStretch(1)
        self._pill = StatusPill()
        header.addWidget(self._pill, 0)
        root.addLayout(header)

        root.addWidget(self._build_connection_card())
        root.addWidget(self._build_mode_bar())
        root.addWidget(self._build_details_card())
        root.addWidget(self._build_latency_card(), 1)

    def _build_connection_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("HeroCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(18)

        self._switch = ToggleSwitch(width=64, height=34)
        self._switch.toggled.connect(self._on_switch)
        layout.addWidget(self._switch, 0)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._headline = QLabel("Disconnected")
        self._headline.setObjectName("Metric")
        self._headline_sub = QLabel("No configuration is active yet.")
        self._headline_sub.setObjectName("Hint")
        texts.addWidget(self._headline)
        texts.addWidget(self._headline_sub)
        layout.addLayout(texts)
        layout.addStretch(1)

        self._action_button = QPushButton("Connect")
        self._action_button.setObjectName("Primary")
        self._action_button.setMinimumWidth(120)
        self._action_button.clicked.connect(self._toggle_connection)
        layout.addWidget(self._action_button)
        return card

    def _build_mode_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)
        heading = QLabel("Outbound mode")
        heading.setObjectName("Hint")
        layout.addWidget(heading)

        self._mode_buttons: dict[str, QPushButton] = {}
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for label, mode in (("Rule", "rule"), ("Global", "global"), ("Direct", "direct")):
            button = QPushButton(label)
            button.setObjectName("Chip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumWidth(78)
            button.setEnabled(False)
            self._mode_group.addButton(button)
            self._mode_buttons[mode] = button
            layout.addWidget(button)
            button.clicked.connect(lambda _checked=False, m=mode: self._set_mode(m))
        layout.addStretch(1)
        self._ip_button = QPushButton("Check IP")
        self._ip_button.setObjectName("Chip")
        self._ip_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ip_button.setMinimumWidth(78)
        self._ip_button.setEnabled(False)
        self._ip_button.clicked.connect(self._on_ip_button)
        layout.addWidget(self._ip_button)
        return bar

    def _build_details_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(1)
        self._profile_row = KeyValueRow("Profile")
        self._node_row = KeyValueRow("Current node")
        self._latency_row = KeyValueRow("Latency")
        self._usage_row = KeyValueRow("Session usage")
        self._ip_row = KeyValueRow("IP address")
        for row in (
            self._profile_row,
            self._node_row,
            self._latency_row,
            self._usage_row,
            self._ip_row,
        ):
            layout.addWidget(row)
        return card

    def _build_latency_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel("Latency fluctuation (current node)")
        title.setObjectName("MetricLabel")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)
        self._latency_chart = LatencyChart(self)
        layout.addWidget(self._latency_chart)
        return card

    # -- behaviour ---------------------------------------------------------
    def _toggle_connection(self) -> None:
        state = self._services.connection.state
        if state in (ConnectionState.CONNECTED, ConnectionState.STARTING):
            self._services.connection.disconnect()
        else:
            self._services.connection.connect()

    def _on_switch(self, checked: bool) -> None:
        state = self._services.connection.state
        if checked and state is not ConnectionState.CONNECTED:
            self._services.connection.connect()
        elif not checked and state in (ConnectionState.CONNECTED, ConnectionState.STARTING):
            self._services.connection.disconnect()
        # connect() can bail out before changing state (missing profile, elevation
        # prompt declined); resync the switch so it never lies about the state.
        self.sync_state()

    def sync_state(self) -> None:
        self._on_state(self._services.connection.state)

    def _on_state(self, state: ConnectionState) -> None:
        self._pill.set_state(state)
        self._switch.blockSignals(True)
        self._switch.setChecked(state is ConnectionState.CONNECTED)
        self._switch.setEnabled(not state.is_busy)
        self._switch.blockSignals(False)

        self._action_button.setEnabled(not state.is_busy)
        self._action_button.setText(
            tr("Disconnect")
            if state in (ConnectionState.CONNECTED, ConnectionState.STARTING)
            else tr("Connect")
        )
        if state is ConnectionState.STOPPED:
            self._headline.setText(tr("Disconnected"))
            self._headline_sub.setText(tr("Traffic is going straight to the internet."))
        elif state is ConnectionState.STARTING:
            self._headline.setText(tr("Connecting…"))
            self._headline_sub.setText(tr("Validating the profile and starting the core."))
        elif state is ConnectionState.CONNECTED:
            self._headline.setText(tr("Connected"))
            self._headline_sub.setText(tr("Your system proxy points at the local Mihomo instance."))
        elif state is ConnectionState.STOPPING:
            self._headline.setText(tr("Disconnecting…"))
            self._headline_sub.setText(tr("Restoring the previous system proxy."))
        else:
            self._headline.setText(tr("Something went wrong"))
            self._headline_sub.setText(tr("Open the Logs page for the exact reason."))
        self._refresh_session()

    def _refresh_session(self) -> None:
        session = self._services.connection.session
        profile = self._services.profiles.active_profile()
        if session is not None:
            self._profile_row.set_value(f"{session.profile_name}  ·  up {self._uptime_text()}")
            self._ip_row.set_value(self._ip_text(local_ip()))
            self._refresh_current_node()
        else:
            self._profile_row.set_value(profile.name if profile else tr("none selected"))
            self._node_row.set_value("-")
            self._latency_row.set_value("-")
            self._usage_row.set_value("-")
            self._ip_row.set_value(self._ip_text(local_ip()))

    def _ip_text(self, lan: str) -> str:
        public = self._public_ip or "-"
        return f"{public}  ·  LAN {lan}"

    def _current_group(self):
        for group in self._services.proxy.groups:
            if group.name != "GLOBAL" and group.now:
                return group
        for group in self._services.proxy.groups:
            if group.now:
                return group
        return None

    def _refresh_current_node(self) -> None:
        group = self._current_group()
        if group is None:
            self._node_row.set_value("-")
            self._latency_row.set_value("-")
            self._latency_chart.clear()
            return
        self._node_row.set_value(f"{group.now}  ({group.name})")
        stats = self._services.proxy.stats.get(group.now, {})
        delay = stats.get("delay")
        jitter = stats.get("jitter")
        if delay is None:
            self._latency_row.set_value("-")
        elif jitter:
            self._latency_row.set_value(f"{delay} ms  ±{jitter} ms")
        else:
            self._latency_row.set_value(f"{delay} ms")
        self._latency_chart.set_series(
            list(stats.get("history", [])), int(jitter or 0)
        )

    def _on_node_stats(self, _stats: object) -> None:
        self._refresh_current_node()

    def _check_public_ip(self) -> None:
        if not self._services.connection.is_connected or self._ip_busy:
            return
        session = self._services.connection.session
        if session is None:
            return
        self._ip_busy = True

        def _ok(result: object) -> None:
            self._ip_busy = False
            address = getattr(result, "address", None)
            if address:
                self._public_ip = str(address)
                self._ip_row.set_value(self._ip_text(local_ip()))

        def _failed(_message: str) -> None:
            self._ip_busy = False

        self._services.runner.submit(
            net_tools.fetch_public_ip, args=(session.proxy_server,), on_success=_ok, on_error=_failed
        )

    def _on_ip_button(self) -> None:
        self._public_ip = None
        self._ip_row.set_value(f"{tr('Checking…')}  ·  LAN {local_ip()}")
        self._check_public_ip()

    def _probe_current_node(self) -> None:
        if not self._services.connection.is_connected:
            return
        group = self._current_group()
        if group is not None and group.now:
            self._services.proxy.test_node_delay(group.now)

    def _set_mode(self, mode: str) -> None:
        if self._services.connection.is_connected:
            self._services.proxy.set_mode(mode)

    def _sync_mode(self, mode: str) -> None:
        button = self._mode_buttons.get(mode)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def _on_mode_state(self, state: ConnectionState) -> None:
        for button in self._mode_buttons.values():
            button.setEnabled(state is ConnectionState.CONNECTED)
        self._ip_button.setEnabled(state is ConnectionState.CONNECTED)
        if state is ConnectionState.CONNECTED:
            self._services.proxy.refresh()
            self._services.proxy.load_config()
            QTimer.singleShot(1500, self._check_public_ip)
        elif state in (ConnectionState.STOPPED, ConnectionState.ERROR):
            self._public_ip = None
            self._ip_row.set_value(f"-  ·  LAN {local_ip()}")

    def _on_traffic(self, sample: TrafficSample) -> None:
        self._last_sample = sample
        if self._services.connection.session is not None:
            total = sample.down_total + sample.up_total
            self._usage_row.set_value(human_bytes(total))

    def _uptime_text(self) -> str:
        session = self._services.connection.session
        if session is None:
            return "-"
        seconds = max(0, int(time.time() - session.started_at))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {seconds:02d}s"

    def _refresh_uptime(self) -> None:
        if self._services.connection.session is not None:
            self._refresh_session()
