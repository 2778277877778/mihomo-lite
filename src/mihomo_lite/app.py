"""Application bootstrap: wires services, window, tray and lifecycle."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from mihomo_lite import __app_id__, __app_name__, __version__
from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.proxy_manager import ProxyManager
from mihomo_lite.core.services import Services
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.core.traffic_monitor import TrafficMonitor
from mihomo_lite.mihomo.core_manager import CoreManager
from mihomo_lite.system.paths import app_paths
from mihomo_lite.system.single_instance import SingleInstance
from mihomo_lite.ui.icon import app_icon
from mihomo_lite.ui.main_window import MainWindow
from mihomo_lite.ui.tray import TrayController
from mihomo_lite.utils.logger import setup_logging
from mihomo_lite.utils.tasks import TaskRunner

log = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mihomo-lite", description="Mihomo Lite")
    parser.add_argument("--hidden", action="store_true", help="start minimised to the tray")
    parser.add_argument("--debug", action="store_true", help="verbose console logging")
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


class MihomoLiteApp:
    def __init__(self, argv: list[str]) -> None:
        self._args = _parse_args(argv[1:])
        self.qt = QApplication(argv)
        self.qt.setApplicationName(__app_name__)
        self.qt.setApplicationDisplayName(__app_name__)
        self.qt.setOrganizationName(__app_id__)
        self.qt.setApplicationVersion(__version__)
        self.qt.setWindowIcon(app_icon())
        self.qt.setQuitOnLastWindowClosed(False)

        self.paths = app_paths()
        setup_logging(
            self.paths.logs,
            level=logging.DEBUG if self._args.debug else logging.INFO,
            console=self._args.debug,
        )
        log.info("%s %s starting", __app_name__, __version__)
        log.debug("data directory: %s", self.paths.root)

        self.single = SingleInstance(self.paths.instance_lock)
        self.settings = SettingsStore(self.paths)
        self.settings.load()

        self.runner = TaskRunner()
        self.profiles = ProfileManager(self.paths)
        self.core = CoreManager(self.paths, lambda: self.settings.current.core_path)
        self.traffic = TrafficMonitor()
        self.connection = ConnectionManager(
            self.paths,
            self.settings,
            self.profiles,
            core=self.core,
            runner=self.runner,
            traffic=self.traffic,
        )
        self.proxy = ProxyManager(lambda: self.connection.api, self.runner)
        self.services = Services(
            paths=self.paths,
            settings=self.settings,
            profiles=self.profiles,
            connection=self.connection,
            proxy=self.proxy,
            core=self.core,
            runner=self.runner,
            traffic=self.traffic,
        )
        self.tray = TrayController(self.services)
        self.window = MainWindow(self.services, self.tray)

    def run(self) -> int:
        if self._args.selftest:
            # Used by the packaging pipeline: prove that Qt, the theme and every
            # page can be constructed inside the frozen executable.
            self.window.show()
            self.qt.processEvents()
            for index in range(5):
                self.window.show_page(index)
                self.qt.processEvents()
            print("selftest ok")
            return 0

        if not self.single.is_primary:
            log.info("another instance is already running; asking it to show")
            SingleInstance.notify_existing()
            return 0

        self.single.start_server()
        self.single.activated.connect(self.window.show_and_raise)

        self.connection.recover_after_crash()
        self._restore_last_profile()

        if self.tray.available():
            self.tray.show()
        else:
            log.warning("no system tray available; the window will close the app")

        self.qt.aboutToQuit.connect(self._on_quit)

        hidden = self._args.hidden or self.settings.current.start_minimized
        if not hidden or not self.tray.available():
            self.window.show()
        else:
            self.tray.notify(__app_name__, "Running in the background. Use the tray icon to open.")

        signal_handlers()
        return self.qt.exec()

    def _restore_last_profile(self) -> None:
        settings = self.settings.current
        if self.profiles.active_profile() is not None:
            return
        if settings.last_profile_id and self.profiles.get(settings.last_profile_id):
            try:
                self.profiles.set_active(settings.last_profile_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not restore the last profile: %s", exc)

    def _on_quit(self) -> None:
        log.info("application is quitting")
        try:
            self.settings.update(
                window_width=max(860, self.window.width()),
                window_height=max(580, self.window.height()),
            )
        except Exception:  # noqa: BLE001
            pass
        self.connection.shutdown()
        self.single.release()


def signal_handlers() -> None:
    def _hook(exc_type, exc, tb) -> None:
        log.critical("unhandled exception", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                "Mihomo Lite - unexpected error",
                "".join(traceback.format_exception_only(exc_type, exc)).strip(),
            )

    sys.excepthook = _hook


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    app = MihomoLiteApp(argv)
    return app.run()


def run_from_path(path: Path) -> None:
    """Helper used by the build script to smoke-test a frozen executable."""
    print(f"{__app_name__} {__version__} -> {path}")
