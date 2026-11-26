"""Settings: core binary, ports, system proxy and application behaviour."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
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
from mihomo_lite.i18n import tr
from mihomo_lite.system import startup, wintun
from mihomo_lite.ui.widgets.controls import Combo
from mihomo_lite.ui.widgets.smooth_scroll import enable_smooth_scroll
from mihomo_lite.ui.widgets.toggle import ToggleSwitch


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    download_progress = Signal(int, int)
    open_downloads_requested = Signal()

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
        enable_smooth_scroll(scroll)
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
        root.addWidget(self._build_downloads_card())
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
        self._force_stop_button = QPushButton("Force stop core")
        self._force_stop_button.setObjectName("Danger")
        self._force_stop_button.clicked.connect(self._force_stop_core)
        buttons.addWidget(self._download_button)
        buttons.addWidget(self._verify_button)
        buttons.addWidget(self._remove_button)
        buttons.addWidget(self._force_stop_button)
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
        self._tun_stack = Combo()
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
        self._mixed_port.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self._mixed_port.setMinimumHeight(32)
        self._mixed_port.setSpecialValueText(tr("Automatic"))
        grid.addWidget(self._mixed_port, 5, 1)

        grid.addWidget(QLabel("API port"), 6, 0)
        self._api_port = QSpinBox()
        self._api_port.setRange(0, 65535)
        self._api_port.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self._api_port.setMinimumHeight(32)
        self._api_port.setSpecialValueText(tr("Automatic"))
        grid.addWidget(self._api_port, 6, 1)

        grid.addWidget(QLabel("Bypass list"), 7, 0)
        self._bypass = QLineEdit()
        self._bypass.setPlaceholderText("localhost;127.*;<local>")
        grid.addWidget(self._bypass, 7, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    def _build_downloads_card(self) -> QWidget:
        card, layout = self._section(
            "Downloads",
            "Optional parallel downloads through the Mihomo core. "
            "Both options are off by default.",
        )

        self._download_multithreaded = ToggleSwitch(width=52, height=30)
        self._download_multithreaded.toggled.connect(self._sync_download_controls)
        row = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(QLabel("Multi-threaded download"))
        description = QLabel("Split one file into parallel segments inside a single node.")
        description.setObjectName("Hint")
        description.setWordWrap(True)
        texts.addWidget(description)
        row.addLayout(texts, 1)
        row.addWidget(self._download_multithreaded, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)

        self._download_multi_node = ToggleSwitch(width=52, height=30)
        row = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(QLabel("Multi-node parallel"))
        description = QLabel(
            "Segments use different nodes through dedicated loopback ports."
        )
        description.setObjectName("Hint")
        description.setWordWrap(True)
        texts.addWidget(description)
        self._download_dependency_hint = QLabel(
            "Requires multi-threaded download. Turn that on first."
        )
        self._download_dependency_hint.setObjectName("Hint")
        self._download_dependency_hint.setWordWrap(True)
        texts.addWidget(self._download_dependency_hint)
        row.addLayout(texts, 1)
        row.addWidget(self._download_multi_node, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self._download_threads = Combo()
        self._download_threads.addItem("Auto (4–16)", 0)
        for count in range(4, 17):
            self._download_threads.addItem(str(count), count)
        grid.setColumnStretch(1, 1)
        grid.addWidget(QLabel("Threads"), 0, 0)
        grid.addWidget(self._download_threads, 0, 1)
        self._download_selected = QLabel("Selected nodes: 0")
        grid.addWidget(self._download_selected, 1, 0, 1, 2)
        nodes_hint = QLabel("Choose nodes on the Downloads page.")
        nodes_hint.setObjectName("Hint")
        nodes_hint.setWordWrap(True)
        grid.addWidget(nodes_hint, 2, 0, 1, 2)
        layout.addLayout(grid)

        start_hint = QLabel(
            "These switches only enable the optimizer. Enter the URL and start the download "
            "on the Downloads page."
        )
        start_hint.setObjectName("Hint")
        start_hint.setWordWrap(True)
        layout.addWidget(start_hint)
        self._open_downloads_button = QPushButton("Open Downloads page")
        self._open_downloads_button.clicked.connect(self.open_downloads_requested.emit)
        layout.addWidget(self._open_downloads_button, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _sync_download_controls(self, _checked: bool | None = None) -> None:
        multithreaded = self._download_multithreaded.isChecked()
        if not multithreaded and self._download_multi_node.isChecked():
            self._download_multi_node.setChecked(False)
        self._download_multi_node.setEnabled(multithreaded)
        self._download_threads.setEnabled(multithreaded)
        self._download_dependency_hint.setVisible(not multithreaded)

    def _update_selected_nodes(self) -> None:
        count = len(self._services.settings.current.download_nodes)
        self._download_selected.setText(tr("Selected nodes: {count}").format(count=count))

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
        self._theme = Combo()
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")
        grid.addWidget(self._theme, 3, 1)

        grid.addWidget(QLabel("Log level"), 4, 0)
        self._log_level = Combo()
        for level in ("INFO", "DEBUG", "WARNING", "ERROR"):
            self._log_level.addItem(level, level)
        grid.addWidget(self._log_level, 4, 1)

        self._auto_update = QCheckBox("Update subscriptions automatically")
        grid.addWidget(self._auto_update, 5, 0, 1, 2)

        grid.addWidget(QLabel("Update interval"), 6, 0)
        self._update_interval = Combo()
        for hours in (1, 3, 6, 12, 24, 48):
            self._update_interval.addItem(f"every {hours} h", hours)
        grid.addWidget(self._update_interval, 6, 1)

        self._start_connected = QCheckBox("Connect on launch")
        grid.addWidget(self._start_connected, 7, 0, 1, 2)

        self._invert_scroll = QCheckBox("Invert scroll direction")
        grid.addWidget(self._invert_scroll, 8, 0, 1, 2)

        grid.addWidget(QLabel("Language"), 9, 0)
        self._language = Combo()
        self._language.addItem("English", "en")
        self._language.addItem("中文", "zh")
        grid.addWidget(self._language, 9, 1)
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
        self._start_connected.setChecked(settings.start_connected)
        self._invert_scroll.setChecked(settings.invert_scroll)
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
        index = self._language.findData(settings.language)
        self._language.setCurrentIndex(max(0, index))
        self._download_multithreaded.setChecked(settings.download_multithreaded)
        self._download_multi_node.setChecked(settings.download_multi_node)
        index = self._download_threads.findData(settings.download_threads)
        self._download_threads.setCurrentIndex(max(0, index))
        self._update_selected_nodes()
        self._sync_download_controls()
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
            self._wintun_hint.setText(tr("wintun.dll not installed (required for TUN)"))
            self._wintun_button.setEnabled(True)
        else:
            self._wintun_hint.setText(f"wintun.dll ready in {found.parent}")
            self._wintun_button.setEnabled(False)

    def _force_stop_core(self) -> None:
        answer = QMessageBox.question(
            self,
            "Force stop the core",
            "Kill the Mihomo core process immediately and restore the system proxy?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._services.connection.force_stop()

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

        previous = self._services.settings.current
        previous_language = previous.language
        multithreaded = self._download_multithreaded.isChecked()
        multi_node = self._download_multi_node.isChecked() and multithreaded
        threads = int(self._download_threads.currentData() or 0)
        download_changed = (
            previous.download_multithreaded != multithreaded
            or previous.download_multi_node != multi_node
            or previous.download_threads != threads
        )
        settings = self._services.settings.update(
            language=self._language.currentData(),
            core_path=self._core_path.text().strip(),
            system_proxy=self._system_proxy.isChecked(),
            tun_enabled=self._tun_enabled.isChecked(),
            tun_stack=self._tun_stack.currentData(),
            tun_dns_hijack=self._tun_dns.isChecked(),
            auto_update_profiles=self._auto_update.isChecked(),
            auto_update_interval_hours=self._update_interval.currentData(),
            start_connected=self._start_connected.isChecked(),
            invert_scroll=self._invert_scroll.isChecked(),
            bypass=self._bypass.text().strip(),
            mixed_port=self._mixed_port.value(),
            api_port=self._api_port.value(),
            autostart=self._autostart.isChecked(),
            close_to_tray=self._close_to_tray.isChecked(),
            minimize_to_tray=self._minimize_to_tray.isChecked(),
            theme=self._theme.currentData(),
            log_level=self._log_level.currentData(),
            download_multithreaded=multithreaded,
            download_multi_node=multi_node,
            download_threads=threads,
            download_nodes=list(previous.download_nodes),
        )
        if settings.language != previous_language:
            QMessageBox.information(
                self,
                "Language",
                "Language changed. Restart Mihomo Lite to apply it."
                if settings.language == "en"
                else "语言已更改，重启 Mihomo Lite 后生效。",
            )
        self.theme_changed.emit(settings.theme)
        from mihomo_lite.ui.widgets.smooth_scroll import set_scroll_inverted

        set_scroll_inverted(settings.invert_scroll)
        self._update_core_hint()
        self._update_wintun_hint()
        self._update_selected_nodes()
        self._sync_download_controls()
        download_note = ""
        if download_changed:
            applied = bool(
                self._services.connection.is_connected
                and self._services.connection.reload_download_config()
            )
            download_note = " " + (
                tr("Download settings applied.")
                if applied
                else tr("Reconnect to apply the download settings.")
            )
        self._status.setText(
            "Saved."
            + ("" if autostart_ok else " Autostart could not be updated.")
            + " Port changes apply on the next connect."
            + download_note
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

    def _set_core_hint_state(self, state: str) -> None:
        self._core_hint.setProperty("state", state)
        self._core_hint.style().unpolish(self._core_hint)
        self._core_hint.style().polish(self._core_hint)

    def _verify_core(self) -> None:
        self._verify_button.setEnabled(False)
        self._set_core_hint_state("")
        self._core_hint.setText(tr("Verifying…"))

        def _done(info: object) -> None:
            version = str(getattr(info, "version", "?"))
            path = str(getattr(info, "path", ""))
            self._core_hint.setText(
                tr("Core verified: {version} at {path}").format(version=version, path=path)
            )
            self._set_core_hint_state("success")
            self._status.setText(tr("Core verified successfully."))
            self._verify_button.setEnabled(True)
            QMessageBox.information(
                self,
                tr("Core verified"),
                f"{tr('The Mihomo core is usable.')}\n\n"
                f"{tr('Version')}: {version}\n{tr('Path')}: {path}",
            )

        def _failed(message: str) -> None:
            self._set_core_hint_state("error")
            self._core_hint.setText(
                tr("Core not usable: {error}").format(error=message)
            )
            self._verify_button.setEnabled(True)

        self._services.runner.submit(
            self._services.core.ensure, on_success=_done, on_error=_failed
        )

    def _download_core(self) -> None:
        self._download_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._set_core_hint_state("")
        self._core_hint.setText(tr("Downloading the Mihomo core…"))

        def _progress(done: int, total: int) -> None:
            self.download_progress.emit(done, total)

        def _done(info: object) -> None:
            self._download_button.setEnabled(True)
            self._progress.setVisible(False)
            self._set_core_hint_state("success")
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
