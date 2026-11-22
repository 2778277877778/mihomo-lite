"""Frameless, rounded main window with a glass sidebar and a custom title bar."""

from __future__ import annotations

import logging
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite import __app_name__, __version__, i18n
from mihomo_lite.core.services import Services
from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.system import elevation
from mihomo_lite.ui import glass
from mihomo_lite.ui.dashboard import DashboardPage
from mihomo_lite.ui.icon import app_icon
from mihomo_lite.ui.logs_page import LogsPage
from mihomo_lite.ui.profile_page import ProfilePage
from mihomo_lite.ui.proxy_page import ProxyPage
from mihomo_lite.ui.settings_page import SettingsPage
from mihomo_lite.ui.theme import load_stylesheet
from mihomo_lite.ui.tray import TrayController
from mihomo_lite.ui.widgets.toggle import ToggleSwitch

log = logging.getLogger(__name__)

_NAV = ("Dashboard", "Proxies", "Profiles", "Settings", "Logs")
_HT = {
    "client": 1,
    "caption": 2,
    "left": 10,
    "right": 11,
    "top": 12,
    "topleft": 13,
    "topright": 14,
    "bottom": 15,
    "bottomleft": 16,
    "bottomright": 17,
}
_WM_NCHITTEST = 0x0084
_RESIZE_BORDER = 7


class Shell(QWidget):
    """Rounded, clipped surface that paints the aurora behind everything."""

    def __init__(self, backdrop: glass.AuroraBackdrop, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backdrop = backdrop

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        self._backdrop.paint(painter, rect)

        path = QPainterPath()
        path.addRoundedRect(rect, self._backdrop.radius, self._backdrop.radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1.0))
        painter.drawPath(path)


class TitleBar(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 6, 10, 0)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setObjectName("TitleDot")
        title = QLabel(__app_name__.upper())
        title.setObjectName("TitleText")
        layout.addWidget(dot)
        layout.addWidget(title)
        layout.addSpacing(6)
        self.status = QLabel("")
        self.status.setObjectName("TitleStatus")
        layout.addWidget(self.status)
        layout.addStretch(1)

        self._min = self._button("–", "WinButton", self._window.showMinimized)
        self._max = self._button("□", "WinButton", self._window.toggle_maximised)
        self._close = self._button("✕", "WinClose", self._window.request_quit)
        for button in (self._min, self._max, self._close):
            layout.addWidget(button)

        # On Windows the native hit test handles dragging; elsewhere fall back
        # to a manual drag so the frameless window is still usable.
        self._drag_offset = None
        if sys.platform != "win32":
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if sys.platform != "win32" and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if sys.platform != "win32":
            self._window.toggle_maximised()

    def _button(self, text: str, name: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setFixedSize(36, 27)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(slot)
        return button

    def set_state(self, state: ConnectionState) -> None:
        self.status.setText(state.label)
        self.status.setProperty("state", state.value)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class MainWindow(QMainWindow):
    restart_elevated = Signal()

    def __init__(self, services: Services, tray: TrayController, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._tray = tray
        self._force_quit = False
        self._backdrop = glass.AuroraBackdrop(services.settings.current.theme)

        self.setWindowTitle(__app_name__)
        self.setWindowIcon(app_icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(QSize(940, 640))

        settings = services.settings.current
        self.resize(settings.window_width, settings.window_height)

        self._build()
        self._wire()
        self.apply_theme(settings.theme)
        glass.set_window_attributes(self, dark=settings.theme == "dark")
        self._status_label.setText(services.connection.state.label)

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        self._shell = Shell(self._backdrop)
        self.setCentralWidget(self._shell)

        outer = QVBoxLayout(self._shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._titlebar = TitleBar(self)
        outer.addWidget(self._titlebar)

        self._stack = QStackedWidget()
        self._pages: dict[int, QWidget] = {}
        self._factories = [
            lambda: DashboardPage(self._services),
            lambda: ProxyPage(self._services),
            lambda: ProfilePage(self._services),
            lambda: SettingsPage(self._services),
            lambda: LogsPage(self._services),
        ]
        # Only the dashboard is built up front; every other page is created the
        # first time it is opened, which keeps cold start short.
        self._dashboard = self._ensure_page(0)

        body = QHBoxLayout()
        body.setContentsMargins(16, 4, 16, 10)
        body.setSpacing(14)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._stack, 1)
        outer.addLayout(body, 1)

        outer.addWidget(self._build_footer())

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(208)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 16, 10, 14)
        layout.setSpacing(4)

        brand = QLabel("Mihomo Lite")
        brand.setObjectName("Brand")
        sub = QLabel("Simple · Lightweight · Reliable")
        sub.setObjectName("BrandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(10)

        self._nav = QListWidget()
        self._nav.setObjectName("Nav")
        self._nav.setFrameShape(QFrame.Shape.NoFrame)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for name in _NAV:
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(0, 40))
            self._nav.addItem(item)
        self._nav.currentRowChanged.connect(self._show_index)
        layout.addWidget(self._nav, 1)

        version = QLabel(f"v{__version__}")
        version.setObjectName("BrandSub")
        layout.addWidget(version)
        self._nav.setCurrentRow(0)
        return sidebar

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(32)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 0, 18, 0)

        self._footer_message = QLabel("Ready")
        self._footer_message.setObjectName("FooterText")
        self._status_label = QLabel("Disconnected")
        self._status_label.setObjectName("FooterText")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._footer_message)
        layout.addStretch(1)
        layout.addWidget(self._status_label)

        self._footer_timer = QTimer(self)
        self._footer_timer.setSingleShot(True)
        self._footer_timer.timeout.connect(self._clear_flash)
        return footer

    def _wire(self) -> None:
        connection = self._services.connection
        connection.state_changed.connect(self._on_state)
        connection.error_changed.connect(self._on_error)
        connection.warning.connect(self._on_warning)
        connection.session_changed.connect(lambda _s: self._status_label.setText(connection.state.label))
        connection.elevation_required.connect(self._on_elevation_required)

        self._tray.show_requested.connect(self.show_and_raise)
        self._tray.quit_requested.connect(self.request_quit)

    # -- behaviour ---------------------------------------------------------
    def apply_theme(self, theme: str) -> None:
        stylesheet = load_stylesheet(theme)
        app = QApplication.instance()
        if app is not None and stylesheet:
            app.setStyleSheet(stylesheet)
        self._backdrop.set_theme(theme)
        for toggle in self.findChildren(ToggleSwitch):
            toggle.set_theme(theme)
        self._shell.update()
        glass.set_window_attributes(self, dark=theme == "dark")
        blurred = glass.enable_acrylic(
            self, tint=0x99160E0A if theme == "dark" else 0x99F4F6FA
        )
        # Off-screen renders and systems with transparency switched off keep a
        # readable, nearly opaque base instead of an unblurred desktop.
        self._backdrop.flat = not blurred and os.environ.get("MIHOMO_LITE_TRANSLUCENT") != "1"
        self._shell.update()

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _ensure_page(self, index: int) -> QWidget | None:
        if index in self._pages:
            return self._pages[index]
        if not 0 <= index < len(self._factories):
            return None
        page = self._factories[index]()
        if index == 3:  # SettingsPage emits theme changes
            page.theme_changed.connect(self.apply_theme)
        i18n.translate_widget_tree(page)
        self._pages[index] = page
        self._stack.addWidget(page)
        return page

    def _show_index(self, index: int) -> None:
        page = self._ensure_page(index)
        if page is not None:
            self._stack.setCurrentWidget(page)

    def show_page(self, index: int) -> None:
        if 0 <= index < self._nav.count():
            self._nav.setCurrentRow(index)

    def toggle_maximised(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _sync_corner_radius(self) -> None:
        radius = 0.0 if self.isMaximized() else 20.0
        if abs(self._backdrop.radius - radius) > 0.1:
            self._backdrop.radius = radius
            self._shell.update()

    def _flash(self, message: str, msecs: int = 6000) -> None:
        self._footer_message.setText(message)
        self._footer_timer.stop()
        self._footer_timer.start(msecs)

    def _clear_flash(self) -> None:
        self._footer_message.setText("Ready")

    def _on_state(self, state: ConnectionState) -> None:
        self._titlebar.set_state(state)
        self._status_label.setText(state.label)
        if state is ConnectionState.CONNECTED:
            self._flash(tr("Connected - traffic is going through Mihomo."))
        elif state is ConnectionState.STOPPED:
            self._flash(tr("Disconnected."))
        elif state is ConnectionState.ERROR:
            self._flash(tr("Connection error - see Logs for details."), 10000)

    def _on_error(self, message: str) -> None:
        log.error("%s", message)
        self._flash(message, 12000)
        if self._tray.available():
            self._tray.notify("Mihomo Lite", message)

    def _on_warning(self, message: str) -> None:
        log.warning("%s", message)
        self._flash(message, 10000)

    def _on_elevation_required(self, message: str) -> None:
        if not elevation.is_windows():
            QMessageBox.warning(self, tr("TUN mode"), message)
            self._dashboard.sync_state()
            return
        answer = QMessageBox.question(
            self,
            tr("Administrator required"),
            message + "\n\n" + tr("The app will restart and connect again automatically."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._dashboard.sync_state()
            return
        self.restart_elevated.emit()

    def elevation_failed(self) -> None:
        QMessageBox.warning(
            self,
            tr("Restart failed"),
            tr(
                "Mihomo Lite could not restart as administrator. "
                "Start it manually with 'Run as administrator', or turn off TUN mode."
            ),
        )
        self._dashboard.sync_state()

    def request_quit(self) -> None:
        self._force_quit = True
        QApplication.instance().quit()

    # -- window behaviour --------------------------------------------------
    def nativeEvent(self, event_type, message):  # noqa: N802 - Qt naming
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
            except Exception:  # noqa: BLE001
                return super().nativeEvent(event_type, message)
            if msg.message == _WM_NCHITTEST:
                return True, self._hit_test(msg)

        return super().nativeEvent(event_type, message)

    def _hit_test(self, msg) -> int:
        pos = self.mapFromGlobal(self.cursor().pos())
        if self.isMaximized():
            return _HT["client"]

        width, height = self.width(), self.height()
        left = pos.x() < _RESIZE_BORDER
        right = pos.x() >= width - _RESIZE_BORDER
        top = pos.y() < _RESIZE_BORDER
        bottom = pos.y() >= height - _RESIZE_BORDER

        if top and left:
            return _HT["topleft"]
        if top and right:
            return _HT["topright"]
        if bottom and left:
            return _HT["bottomleft"]
        if bottom and right:
            return _HT["bottomright"]
        if left:
            return _HT["left"]
        if right:
            return _HT["right"]
        if top:
            return _HT["top"]
        if bottom:
            return _HT["bottom"]

        if self._titlebar.isVisible() and self._titlebar.geometry().contains(pos):
            child = self.childAt(pos)
            if isinstance(child, QPushButton):
                return _HT["client"]
            return _HT["caption"]
        return _HT["client"]

    # -- window events -----------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        settings = self._services.settings.current
        if not self._force_quit and settings.close_to_tray and self._tray.available():
            event.ignore()
            self.hide()
            self._tray.notify(
                tr("Mihomo Lite is still running"),
                tr("The proxy keeps working. Use the tray icon to reopen or quit."),
            )
            return
        event.accept()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_corner_radius()
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self._services.settings.current.minimize_to_tray
            and self._tray.available()
        ):
            self.hide()
        super().changeEvent(event)
