"""Main window: sidebar navigation plus the page stack."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite import __app_name__, __version__
from mihomo_lite.core.services import Services
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.ui.dashboard import DashboardPage
from mihomo_lite.ui.icon import app_icon
from mihomo_lite.ui.logs_page import LogsPage
from mihomo_lite.ui.profile_page import ProfilePage
from mihomo_lite.ui.proxy_page import ProxyPage
from mihomo_lite.ui.settings_page import SettingsPage
from mihomo_lite.ui.theme import load_stylesheet
from mihomo_lite.ui.tray import TrayController

log = logging.getLogger(__name__)

_NAV = ("Dashboard", "Proxies", "Profiles", "Settings", "Logs")


class MainWindow(QMainWindow):
    def __init__(self, services: Services, tray: TrayController, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._tray = tray
        self._force_quit = False

        self.setWindowTitle(__app_name__)
        self.setWindowIcon(app_icon())
        settings = services.settings.current
        self.resize(settings.window_width, settings.window_height)
        self.setMinimumSize(QSize(860, 580))

        self._build()
        self._wire()

        self.apply_theme(settings.theme)
        self._status_label.setText(services.connection.state.label)

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._dashboard = DashboardPage(self._services)
        self._proxies = ProxyPage(self._services)
        self._profiles = ProfilePage(self._services)
        self._settings = SettingsPage(self._services)
        self._logs = LogsPage(self._services)
        for page in (self._dashboard, self._proxies, self._profiles, self._settings, self._logs):
            self._stack.addWidget(page)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._stack, 1)

        self._status_label = QLabel("Disconnected")
        self._status_label.setObjectName("Hint")
        self.statusBar().addPermanentWidget(self._status_label)
        self.statusBar().showMessage("Ready")

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(214)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        brand = QLabel("Mihomo Lite")
        brand.setObjectName("Brand")
        sub = QLabel("Simple · Lightweight · Reliable")
        sub.setObjectName("BrandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)

        self._nav = QListWidget()
        self._nav.setObjectName("Nav")
        self._nav.setFrameShape(QFrame.Shape.NoFrame)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for name in _NAV:
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(0, 38))
            self._nav.addItem(item)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        layout.addWidget(self._nav, 1)

        version = QLabel(f"v{__version__}")
        version.setObjectName("BrandSub")
        layout.addWidget(version)
        self._nav.setCurrentRow(0)
        return sidebar

    def _wire(self) -> None:
        connection = self._services.connection
        connection.state_changed.connect(self._on_state)
        connection.error_changed.connect(self._on_error)
        connection.warning.connect(self._on_warning)
        connection.session_changed.connect(lambda _s: self._status_label.setText(connection.state.label))

        self._settings.theme_changed.connect(self.apply_theme)
        self._tray.show_requested.connect(self.show_and_raise)
        self._tray.quit_requested.connect(self.request_quit)

    # -- behaviour ---------------------------------------------------------
    def apply_theme(self, theme: str) -> None:
        stylesheet = load_stylesheet(theme)
        app = QApplication.instance()
        if app is not None and stylesheet:
            app.setStyleSheet(stylesheet)

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_page(self, index: int) -> None:
        if 0 <= index < self._nav.count():
            self._nav.setCurrentRow(index)

    def _on_state(self, state: ConnectionState) -> None:
        self._status_label.setText(state.label)
        if state is ConnectionState.ERROR:
            self.statusBar().showMessage("Connection error - see the log for details.", 8000)
        elif state is ConnectionState.CONNECTED:
            self.statusBar().showMessage("Connected.", 5000)
        elif state is ConnectionState.STOPPED:
            self.statusBar().showMessage("Disconnected.", 5000)

    def _on_error(self, message: str) -> None:
        log.error("%s", message)
        self.statusBar().showMessage(message, 12000)
        if self._tray.available():
            self._tray.notify("Mihomo Lite", message)

    def _on_warning(self, message: str) -> None:
        log.warning("%s", message)
        self.statusBar().showMessage(message, 10000)

    def request_quit(self) -> None:
        self._force_quit = True
        QApplication.instance().quit()

    # -- window events -----------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        settings = self._services.settings.current
        if not self._force_quit and settings.close_to_tray and self._tray.available():
            event.ignore()
            self.hide()
            self._tray.notify(
                "Mihomo Lite is still running",
                "The proxy keeps working. Use the tray icon to reopen or quit.",
            )
            return
        event.accept()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self._services.settings.current.minimize_to_tray
            and self._tray.available()
        ):
            self.hide()
        super().changeEvent(event)
