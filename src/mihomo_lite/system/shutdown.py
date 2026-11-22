"""Graceful shutdown used by the uninstaller.

Windows uninstallers usually just kill the process, which would leave the system
proxy pointing at a port that no longer exists. This helper asks the running
instance to quit (it restores the proxy on exit), waits for it, and then repairs
anything left behind.
"""

from __future__ import annotations

import logging
import time

from mihomo_lite.system.paths import app_paths
from mihomo_lite.system.proxy import SystemProxy
from mihomo_lite.system.single_instance import SingleInstance
from mihomo_lite.utils.fs import read_json
from mihomo_lite.utils.logger import setup_logging
from mihomo_lite.utils.winapi import pid_running, process_image_name, terminate_pid

log = logging.getLogger(__name__)


def run_shutdown(argv: list[str]) -> int:
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication(list(argv))  # noqa: F841 - required for QLocalSocket
    paths = app_paths()
    setup_logging(paths.logs)

    notified = SingleInstance.notify_existing("quit")
    if notified:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and paths.session_file.exists():
            time.sleep(0.1)
        time.sleep(0.3)

    restored = False
    try:
        proxy = SystemProxy(paths.proxy_journal)
        if proxy.owns_system_proxy():
            restored = proxy.restore()
    except Exception:  # noqa: BLE001 - best effort during uninstall
        log.exception("shutdown: could not restore the system proxy")

    _reap_core(paths.session_file)
    log.info("shutdown helper finished (notified=%s restored=%s)", notified, restored)
    return 0


def _reap_core(session_file) -> None:
    data = read_json(session_file, default=None)
    if isinstance(data, dict):
        try:
            pid = int(data.get("pid", 0))
        except (TypeError, ValueError):
            pid = 0
        if pid and pid_running(pid):
            image = (process_image_name(pid) or "").lower()
            if "mihomo" in image:
                terminate_pid(pid)
                log.info("shutdown: terminated leftover core %s", pid)
    try:
        session_file.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.debug("shutdown: cannot remove session file: %s", exc)
