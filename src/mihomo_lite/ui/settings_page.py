"""Settings: core binary, ports, system proxy and application behaviour."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core.services import Services
from mihomo_lite.system import startup, wintun


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    download_progress = Signal(int, int)

    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._build()
        self._load_values()
        self.download_progress.connect(self._on_progress)

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 18, 32, 18)
        root.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Changes are saved locally in your user profile.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._build_core_card())
        root.addWidget(self._build_network_card())
        root.addWidget(self._build_app_card())
        root.addStretch(1)

        actions = QHBoxLayout()
        self._save_button = QPushButton("Save settings")
        self._save_button.setObjectName("Primary")
        self._save_button.clicked.connect(self._save)
        open_folder = QPushButton("Open data folder")
        open_folder.clicked.connect(self._open_data_folder)
        actions.addWidget(self._save_button)
        actions.addWidget(open_folder)
        actions.addStretch(1)
        root.addLayout(actions)

        self._status = QLabel("")
        self._status.setObjectName("Hint")
        root.addWidget(self._status)

    def _section(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
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

    def _build_core_card(self) -> QWidget:
        card, layout = self._section(
            "Mihomo core",
            "A verified Mihomo core ships with the app. You can point it at another "
            "mihomo.exe, or download a newer official Windows build.",
        )
        row = QHBoxLayout()
        self._core_path = QLineEdit()
        self._core_path.setPlaceholderText("Automatic (app data or next to the executable)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_core)
        row.addWidget(self._core_path, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        buttons = QHBoxLayout()
        self._download_button = QPushButton("Download core (≈22 MB)")
        self._download_button.clicked.connect(self._download_core)
        self._verify_button = QPushButton("Verify core")
        self._verify_button.clicked.connect(self._verify_core)
        self._remove_button = QPushButton("Remove downloaded core")
        self._remove_button.clicked.connect(self._remove_downloaded_core)
        buttons.addWidget(self._download_button)
        buttons.addWidget(self._verify_button)
        buttons.addWidget(self._remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        layout.addWidget(self._progress)

        self._core_hint = QLabel("")
        self._core_hint.setObjectName("Hint")
        layout.addWidget(self._core_hint)
        return card

    def _build_network_card(self) -> QWidget:
        card, layout = self._section(
            "Network",
            "Only localhost is exposed. Ports set to 0 pick a free high port on every start.",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        self._system_proxy = QCheckBox("Use the Windows system proxy while connected")
        grid.addWidget(self._system_proxy, 0, 0, 1, 2)

        self._tun_enabled = QCheckBox("TUN mode (captures all traffic, needs administrator)")
        grid.addWidget(self._tun_enabled, 1, 0, 1, 2)

        grid.addWidget(QLabel("TUN stack"), 2, 0)
        self._tun_stack = QComboBox()
        for label, value in (("Mixed", "mixed"), ("System", "system"), ("gVisor", "gvisor")):
            self._tun_stack.addItem(label, value)
        grid.addWidget(self._tun_stack, 2, 1)

        self._tun_dns = QCheckBox("Hijack DNS in TUN mode (recommended)")
        grid.addWidget(self._tun_dns, 3, 0, 1, 2)

        tun_row = QHBoxLayout()
        self._wintun_button = QPushButton("Download wintun")
        self._wintun_button.clicked.connect(self._download_wintun)
        self._wintun_hint = QLabel("")
        self._wintun_hint.setObjectName("Hint")
        tun_row.addWidget(self._wintun_button)
        tun_row.addWidget(self._wintun_hint, 1)
        grid.addLayout(tun_row, 4, 0, 1, 2)

        grid.addWidget(QLabel("Mixed port"), 5, 0)
        self._mixed_port = QSpinBox()
        self._mixed_port.setRange(0, 65535)
        self._mixed_port.setSpecialValueText("Automatic")
        grid.addWidget(self._mixed_port, 5, 1)

        grid.addWidget(QLabel("API port"), 6, 0)
        self._api_port = QSpinBox()
        self._api_port.setRange(0, 65535)
        self._api_port.setSpecialValueText("Automatic")
        grid.addWidget(self._api_port, 6, 1)

        grid.addWidget(QLabel("Bypass list"), 7, 0)
        self._bypass = QLineEdit()
        self._bypass.setPlaceholderText("localhost;127.*;<local>")
        grid.addWidget(self._bypass, 7, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    def _build_app_card(self) -> QWidget:
        card, layout = self._section("Application", "Startup, tray and appearance.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        self._autostart = QCheckBox("Start with Windows")
        grid.addWidget(self._autostart, 0, 0, 1, 2)
        self._close_to_tray = QCheckBox("Close to the tray instead of quitting")
        grid.addWidget(self._close_to_tray, 1, 0, 1, 2)
        self._minimize_to_tray = QCheckBox("Minimise to the tray")
        grid.addWidget(self._minimize_to_tray, 2, 0, 1, 2)

        grid.addWidget(QLabel("Theme"), 3, 0)
        self._theme = QComboBox()
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")
        grid.addWidget(self._theme, 3, 1)

        grid.addWidget(QLabel("Log level"), 4, 0)
        self._log_level = QComboBox()
        for level in ("INFO", "DEBUG", "WARNING", "ERROR"):
            self._log_level.addItem(level, level)
        grid.addWidget(self._log_level, 4, 1)

        self._auto_update = QCheckBox("Update subscriptions automatically")
        grid.addWidget(self._auto_update, 5, 0, 1, 2)

        grid.addWidget(QLabel("Update interval"), 6, 0)
        self._update_interval = QComboBox()
        for hours in (1, 3, 6, 12, 24, 48):
            self._update_interval.addItem(f"every {hours} h", hours)
        grid.addWidget(self._update_interval, 6, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    # -- data --------------------------------------------------------------
    def _load_values(self) -> None:
        settings = self._services.settings.current
        self._core_path.setText(settings.core_path)
        self._system_proxy.setChecked(settings.system_proxy)
        self._tun_enabled.setChecked(settings.tun_enabled)
        index = self._tun_stack.findData(settings.tun_stack)
        self._tun_stack.setCurrentIndex(max(0, index))
        self._tun_dns.setChecked(settings.tun_dns_hijack)
        self._auto_update.setChecked(settings.auto_update_profiles)
        index = self._update_interval.findData(settings.auto_update_interval_hours)
        self._update_interval.setCurrentIndex(max(0, index))
        self._bypass.setText(settings.bypass)
        self._mixed_port.setValue(settings.mixed_port)
        self._api_port.setValue(settings.api_port)
        self._autostart.setChecked(startup.is_enabled())
        self._close_to_tray.setChecked(settings.close_to_tray)
        self._minimize_to_tray.setChecked(settings.minimize_to_tray)
        index = self._theme.findData(settings.theme)
        self._theme.setCurrentIndex(max(0, index))
        index = self._log_level.findData(settings.log_level)
        self._log_level.setCurrentIndex(max(0, index))
        self._update_core_hint()
        self._update_wintun_hint()

    def _update_core_hint(self) -> None:
        downloaded = self._services.core.downloaded_path().exists()
        self._remove_button.setEnabled(downloaded)
        try:
            info = self._services.core.ensure()
        except Exception as exc:  # noqa: BLE001 - hint only
            self._core_hint.setText(f"Core: not ready - {exc}")
        else:
            self._core_hint.setText(f"Core: {info.version} ({info.source}) at {info.path}")

    def _update_wintun_hint(self) -> None:
        try:
            info = self._services.core.ensure()
            found = wintun.locate(info.path)
        except Exception:  # noqa: BLE001 - hint only
            self._wintun_hint.setText("wintun.dll: core not ready")
            self._wintun_button.setEnabled(False)
            return
        if found is None:
            self._wintun_hint.setText("wintun.dll not installed (required for TUN)")
            self._wintun_button.setEnabled(True)
        else:
            self._wintun_hint.setText(f"wintun.dll ready in {found.parent}")
            self._wintun_button.setEnabled(False)

    def _download_wintun(self) -> None:
        self._wintun_button.setEnabled(False)
        self._wintun_hint.setText("Downloading wintun…")

        def _progress(done: int, total: int) -> None:
            self.download_progress.emit(done, total)

        def _install() -> str:
            info = self._services.core.ensure()
            return str(wintun.install(info.path, progress=_progress))

        def _done(path: object) -> None:
            self._wintun_hint.setText(f"wintun.dll installed at {path}")
            self._status.setText("wintun installed. TUN mode is ready to use.")
            self._update_wintun_hint()

        def _failed(message: str) -> None:
            self._wintun_hint.setText(f"wintun: {message}")
            self._wintun_button.setEnabled(True)
            QMessageBox.warning(self, "wintun", message)

        self._services.runner.submit(_install, on_success=_done, on_error=_failed)

    def _remove_downloaded_core(self) -> None:
        self._services.core.remove_installed()
        self._update_core_hint()
        self._status.setText("Removed the downloaded core; the bundled one is used again.")

    def _save(self) -> None:
        autostart_ok = True
        try:
            startup.set_enabled(self._autostart.isChecked())
        except Exception as exc:  # noqa: BLE001
            autostart_ok = False
            QMessageBox.warning(self, "Autostart", str(exc))

        settings = self._services.settings.update(
            core_path=self._core_path.text().strip(),
            system_proxy=self._system_proxy.isChecked(),
            tun_enabled=self._tun_enabled.isChecked(),
            tun_stack=self._tun_stack.currentData(),
            tun_dns_hijack=self._tun_dns.isChecked(),
            auto_update_profiles=self._auto_update.isChecked(),
            auto_update_interval_hours=self._update_interval.currentData(),
            bypass=self._bypass.text().strip(),
            mixed_port=self._mixed_port.value(),
            api_port=self._api_port.value(),
            autostart=self._autostart.isChecked(),
            close_to_tray=self._close_to_tray.isChecked(),
            minimize_to_tray=self._minimize_to_tray.isChecked(),
            theme=self._theme.currentData(),
            log_level=self._log_level.currentData(),
        )
        self.theme_changed.emit(settings.theme)
        self._update_core_hint()
        self._update_wintun_hint()
        self._status.setText(
            "Saved."
            + ("" if autostart_ok else " Autostart could not be updated.")
            + " Port changes apply on the next connect."
        )

    # -- core management ---------------------------------------------------
    def _browse_core(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Select mihomo.exe", "", "Executable (*.exe);;All files (*)"
        )
        if not path:
            return
        self._core_path.setText(path)
        self._verify_core()

    def _verify_core(self) -> None:
        self._verify_button.setEnabled(False)
        self._core_hint.setText("Verifying…")

        def _done(info: object) -> None:
            version = getattr(info, "version", "?")
            self._core_hint.setText(f"Core: {version} at {getattr(info, 'path', '')}")
            self._verify_button.setEnabled(True)

        def _failed(message: str) -> None:
            self._core_hint.setText(f"Core not usable: {message}")
            self._verify_button.setEnabled(True)

        self._services.runner.submit(
            self._services.core.ensure, on_success=_done, on_error=_failed
        )

    def _download_core(self) -> None:
        self._download_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._core_hint.setText("Downloading the Mihomo core…")

        def _progress(done: int, total: int) -> None:
            self.download_progress.emit(done, total)

        def _done(info: object) -> None:
            self._download_button.setEnabled(True)
            self._progress.setVisible(False)
            self._core_hint.setText(
                f"Core {getattr(info, 'version', '')} installed at {getattr(info, 'path', '')}"
            )
            self._remove_button.setEnabled(True)

        def _failed(message: str) -> None:
            self._download_button.setEnabled(True)
            self._progress.setVisible(False)
            self._core_hint.setText(f"Download failed: {message}")
            QMessageBox.warning(self, "Download failed", message)

        self._services.runner.submit(
            self._services.core.download,
            kwargs={"progress": _progress},
            on_success=_done,
            on_error=_failed,
        )

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(int(done * 100 / total))
        else:
            self._progress.setRange(0, 0)
            self._core_hint.setText(f"Downloading… {done / 1024 / 1024:.1f} MB")

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._services.paths.root)))
