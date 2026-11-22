"""Administrator detection and relaunch for TUN mode."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

SW_SHOWNORMAL = 1


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    """True when the current process has administrator rights."""
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as exc:  # noqa: BLE001 - treat as not elevated
        log.debug("cannot query elevation state: %s", exc)
        return False


def _launcher() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        return sys.executable, []
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    interpreter = str(pythonw if pythonw.exists() else python)
    return interpreter, ["-m", "mihomo_lite"]


def relaunch_as_admin(extra_args: list[str]) -> bool:
    """Relaunch this application elevated; returns False if the user declined."""
    if not is_windows():
        return False
    executable, base_args = _launcher()
    parameters = " ".join([*base_args, *extra_args])
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, parameters, None, SW_SHOWNORMAL
        )
    except Exception as exc:  # noqa: BLE001
        log.error("could not relaunch elevated: %s", exc)
        return False
    if int(result) <= 32:
        log.info("elevation was declined (code %s)", result)
        return False
    log.info("relaunched elevated with: %s", parameters)
    return True
