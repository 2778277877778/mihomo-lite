"""System tray integration."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from mihomo_lite.core.services import Services
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.ui.icon import tray_icon


class TrayController(QObject):
    quit_requested = Signal()
    show_requested = Signal()

    def __init__(self, services: Services, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._services = services
        self._icon = QSystemTrayIcon(tray_icon(ConnectionState.STOPPED), self)
        self._icon.setToolTip("Mihomo Lite - disconnected")

        self._menu = QMenu()
        self._toggle_action = QAction("Connect", self._menu)
        self._toggle_action.triggered.connect(self._toggle)
        self._show_action = QAction("Show window", self._menu)
        self._show_action.triggered.connect(self.show_window)
        self._quit_action = QAction("Quit", self._menu)
        self._quit_action.triggered.connect(self.quit_requested.emit)

        self._menu.addAction(self._show_action)
        self._menu.addAction(self._toggle_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)

        services.connection.state_changed.connect(self._on_state)
        services.profiles.active_changed.connect(lambda _p: self._refresh_tooltip())

    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        if self.available():
            self._icon.show()

    def hide(self) -> None:
        self._icon.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self) -> None:
        self.show_requested.emit()

    def notify(self, title: str, message: str) -> None:
        if not self._services.settings.current.notifications or not self.available():
            return
        if not self._icon.isVisible():
            return
        self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _toggle(self) -> None:
        state = self._services.connection.state
        if state in (ConnectionState.CONNECTED, ConnectionState.STARTING):
            self._services.connection.disconnect()
        else:
            self._services.connection.connect()

    def _on_state(self, state: ConnectionState) -> None:
        self._icon.setIcon(tray_icon(state))
        self._toggle_action.setText(
            "Disconnect"
            if state in (ConnectionState.CONNECTED, ConnectionState.STARTING)
            else "Connect"
        )
        self._refresh_tooltip(state)

    def _refresh_tooltip(self, state: ConnectionState | None = None) -> None:
        if state is None:
            state = self._services.connection.state
        profile = self._services.profiles.active_profile()
        name = profile.name if profile else "no profile"
        self._icon.setToolTip(f"Mihomo Lite - {state.label} ({name})")
        if state is ConnectionState.CONNECTED:
            self.notify("Mihomo Lite", "Connected. Traffic is now going through Mihomo.")
        elif state is ConnectionState.ERROR:
            self.notify("Mihomo Lite", "The connection failed. Open the app for details.")
