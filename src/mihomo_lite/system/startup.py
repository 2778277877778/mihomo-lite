"""Start-with-Windows support via the per-user Run key."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from mihomo_lite.utils.exceptions import MihomoLiteError

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Mihomo Lite"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}" --hidden'
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else python
    return f'"{interpreter}" -m mihomo_lite --hidden'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def set_enabled(enabled: bool) -> None:
    if sys.platform != "win32":
        raise MihomoLiteError("autostart is only supported on Windows")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        raise MihomoLiteError(f"cannot update autostart entry: {exc}") from exc
    log.info("autostart %s", "enabled" if enabled else "disabled")
