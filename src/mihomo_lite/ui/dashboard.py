"""Dashboard: the one screen that answers 'is it on, and what is it doing'."""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core.services import Services
from mihomo_lite.core.traffic_monitor import TrafficSample, human_bytes, human_speed
from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.ui.widgets.log_view import LogView
from mihomo_lite.ui.widgets.status import KeyValueRow, MetricTile, StatusPill
from mihomo_lite.ui.widgets.toggle import ToggleSwitch


class DashboardPage(QWidget):
    open_settings_requested = Signal()

    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._last_sample = TrafficSample()
        self._build()

        services.connection.state_changed.connect(self._on_state)
        services.connection.session_changed.connect(lambda _s: self._refresh_session())
        services.traffic.sample.connect(self._on_traffic)
        services.profiles.profiles_changed.connect(self._refresh_session)
        services.profiles.active_changed.connect(lambda _p: self._refresh_session())

        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._refresh_uptime)
        self._uptime_timer.start()

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
        root.addLayout(self._build_metrics())
        root.addWidget(self._build_details_card())
        root.addWidget(self._build_log_card(), 1)

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

    def _build_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)
        self._down_tile = MetricTile("Download", "0 B/s")
        self._up_tile = MetricTile("Upload", "0 B/s")
        self._total_down = MetricTile("Session download", "0 B")
        self._total_up = MetricTile("Session upload", "0 B")
        grid.addWidget(self._down_tile, 0, 0)
        grid.addWidget(self._up_tile, 0, 1)
        grid.addWidget(self._total_down, 0, 2)
        grid.addWidget(self._total_up, 0, 3)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        return grid

    def _build_details_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(1)
        self._profile_row = KeyValueRow("Profile")
        self._core_row = KeyValueRow("Mihomo core")
        self._proxy_row = KeyValueRow("Local endpoints")
        self._system_row = KeyValueRow("System proxy")
        for row in (self._profile_row, self._core_row, self._proxy_row, self._system_row):
            layout.addWidget(row)
        return card

    def _build_log_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        header = QHBoxLayout()
        title = QLabel("Core output")
        title.setObjectName("MetricLabel")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)
        self._log = LogView(self)
        self._log.setMinimumHeight(70)
        layout.addWidget(self._log)
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
        uptime = self._uptime_text()
        if session is not None:
            self._profile_row.set_value(session.profile_name)
            self._core_row.set_value(session.core_version or "running")
            self._proxy_row.set_value(
                f"127.0.0.1:{session.mixed_port}  ·  API {session.api_port}"
            )
            if session.mode == "tun":
                self._system_row.set_value(f"TUN mode  ·  up {uptime}")
            elif session.mode == "system":
                self._system_row.set_value(f"system proxy  ·  up {uptime}")
            else:
                self._system_row.set_value(f"off  ·  up {uptime}")
        else:
            settings = self._services.settings.current
            self._profile_row.set_value(profile.name if profile else tr("none selected"))
            self._core_row.set_value(tr("not running"))
            self._proxy_row.set_value("-")
            if settings.tun_enabled:
                self._system_row.set_value(tr("TUN mode (administrator required)"))
            else:
                self._system_row.set_value(
                    tr("will be enabled") if settings.system_proxy else tr("disabled")
                )

    def _on_traffic(self, sample: TrafficSample) -> None:
        self._last_sample = sample
        self._down_tile.set_value(human_speed(sample.down))
        self._up_tile.set_value(human_speed(sample.up))
        self._total_down.set_value(human_bytes(sample.down_total))
        self._total_up.set_value(human_bytes(sample.up_total))

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
