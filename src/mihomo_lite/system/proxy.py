"""Windows system proxy management with crash-safe restore.

Design notes
------------
* The authoritative write path is the WinINET per-connection API, mirrored to
  the HKCU Internet Settings keys so that registry readers stay consistent.
* Before the first write we persist a journal containing the previous state and
  the PID that owns the change. If the app dies, the next start restores it.
* Nothing here is Qt aware, so it can be unit tested with a fake backend.
"""

from __future__ import annotations

import ctypes
import logging
import os
import socket
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from mihomo_lite.utils.exceptions import ProxyError
from mihomo_lite.utils.fs import atomic_write_json, read_json
from mihomo_lite.utils.winapi import pid_running

log = logging.getLogger(__name__)

DEFAULT_BYPASS = (
    "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;"
    "172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;"
    "172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;*.local;<local>"
)

PROXY_TYPE_DIRECT = 0x00000001
PROXY_TYPE_PROXY = 0x00000002
PROXY_TYPE_AUTO_PROXY_URL = 0x00000004

INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_PER_CONNECTION_OPTION = 75

INTERNET_PER_CONN_FLAGS = 1
INTERNET_PER_CONN_PROXY_SERVER = 2
INTERNET_PER_CONN_PROXY_BYPASS = 3
INTERNET_PER_CONN_AUTOCONFIG_URL = 4

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

# Windows' dynamic port range starts here. Mihomo Lite picks its mixed port
# from this range, so a dead loopback endpoint in this range is almost always
# a leftover from a previous session rather than the user's real proxy.
_EPHEMERAL_PORT_START = 49152


def _loopback_endpoint(server: str) -> tuple[str, int] | None:
    host, _, raw_port = server.strip().rpartition(":")
    host = host.strip("[]").strip().lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return None
    try:
        port = int(raw_port)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    return host, port


def _loopback_alive(server: str, timeout: float = 0.25) -> bool:
    endpoint = _loopback_endpoint(server)
    if endpoint is None:
        return False
    host, port = endpoint
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _usable_snapshot(state: ProxyState) -> ProxyState:
    """Do not restore a dead ephemeral loopback proxy left by an old session.

    A hard-killed instance can leave the Windows proxy pointing at a random
    mixed port. Preserving that as the "previous" value would permanently break
    the browser after the next normal disconnect, so use direct instead.
    """
    if not state.enabled:
        return state
    endpoint = _loopback_endpoint(state.server)
    if endpoint is None:
        return state
    _host, port = endpoint
    if port < _EPHEMERAL_PORT_START:
        return state
    if _loopback_alive(state.server):
        return state
    log.warning(
        "previous system proxy %s is a dead loopback endpoint; restoring direct instead",
        state.server,
    )
    return state.disabled()


@dataclass(frozen=True)
class ProxyState:
    """A snapshot of the WinINET LAN proxy configuration."""

    flags: int = PROXY_TYPE_DIRECT
    server: str = ""
    bypass: str = DEFAULT_BYPASS
    autoconfig_url: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.flags & PROXY_TYPE_PROXY)

    @property
    def uses_pac(self) -> bool:
        return bool(self.flags & PROXY_TYPE_AUTO_PROXY_URL) and bool(self.autoconfig_url)

    def to_dict(self) -> dict[str, object]:
        return {
            "flags": self.flags,
            "server": self.server,
            "bypass": self.bypass,
            "autoconfig_url": self.autoconfig_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ProxyState:
        return cls(
            flags=int(data.get("flags", PROXY_TYPE_DIRECT)),
            server=str(data.get("server", "")),
            bypass=str(data.get("bypass", DEFAULT_BYPASS)),
            autoconfig_url=str(data.get("autoconfig_url", "")),
        )

    def with_proxy(self, server: str, bypass: str | None = None) -> ProxyState:
        return replace(
            self,
            flags=PROXY_TYPE_DIRECT | PROXY_TYPE_PROXY,
            server=server,
            bypass=bypass if bypass is not None else self.bypass or DEFAULT_BYPASS,
            autoconfig_url="",
        )

    def disabled(self) -> ProxyState:
        return replace(self, flags=PROXY_TYPE_DIRECT, server="", autoconfig_url="")


class ProxyBackend(Protocol):
    """Minimal read/write interface so tests can avoid touching the registry."""

    def read(self) -> ProxyState: ...

    def write(self, state: ProxyState) -> None: ...


class _OptionValue(ctypes.Union):
    _fields_ = [
        ("dwValue", wintypes.DWORD),
        ("pszValue", wintypes.LPWSTR),
        ("ftValue", wintypes.FILETIME),
    ]


class _PerConnOption(ctypes.Structure):
    _fields_ = [("dwOption", wintypes.DWORD), ("Value", _OptionValue)]


class _PerConnOptionList(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("pszConnection", wintypes.LPWSTR),
        ("dwOptionCount", wintypes.DWORD),
        ("dwOptionError", wintypes.DWORD),
        ("pOptions", ctypes.POINTER(_PerConnOption)),
    ]


def _wininet():
    if sys.platform != "win32":
        raise ProxyError("system proxy is only supported on Windows")
    api = ctypes.WinDLL("wininet", use_last_error=True)
    api.InternetQueryOptionW.restype = wintypes.BOOL
    api.InternetQueryOptionW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    api.InternetSetOptionW.restype = wintypes.BOOL
    api.InternetSetOptionW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    return api


class WinInetBackend:
    """Reads and writes the per-connection (LAN) proxy configuration."""

    def _build_options(self, state: ProxyState):
        options = (_PerConnOption * 4)()
        options[0].dwOption = INTERNET_PER_CONN_FLAGS
        options[0].Value.dwValue = state.flags
        options[1].dwOption = INTERNET_PER_CONN_PROXY_SERVER
        options[1].Value.pszValue = state.server
        options[2].dwOption = INTERNET_PER_CONN_PROXY_BYPASS
        options[2].Value.pszValue = state.bypass
        options[3].dwOption = INTERNET_PER_CONN_AUTOCONFIG_URL
        options[3].Value.pszValue = state.autoconfig_url
        return options

    def read(self) -> ProxyState:
        api = _wininet()
        options = (_PerConnOption * 4)()
        for index, option_id in enumerate(
            (
                INTERNET_PER_CONN_FLAGS,
                INTERNET_PER_CONN_PROXY_SERVER,
                INTERNET_PER_CONN_PROXY_BYPASS,
                INTERNET_PER_CONN_AUTOCONFIG_URL,
            )
        ):
            options[index].dwOption = option_id

        option_list = _PerConnOptionList()
        option_list.dwSize = ctypes.sizeof(_PerConnOptionList)
        option_list.pszConnection = None
        option_list.dwOptionCount = 4
        option_list.dwOptionError = 0
        option_list.pOptions = options

        size = wintypes.DWORD(ctypes.sizeof(_PerConnOptionList))
        ok = api.InternetQueryOptionW(
            None,
            INTERNET_OPTION_PER_CONNECTION_OPTION,
            ctypes.byref(option_list),
            ctypes.byref(size),
        )
        if not ok:
            raise ProxyError(f"InternetQueryOption failed (error {ctypes.get_last_error()})")

        def text(value: object) -> str:
            return str(value) if value else ""

        return ProxyState(
            flags=int(options[0].Value.dwValue),
            server=text(options[1].Value.pszValue),
            bypass=text(options[2].Value.pszValue) or DEFAULT_BYPASS,
            autoconfig_url=text(options[3].Value.pszValue),
        )

    def write(self, state: ProxyState) -> None:
        api = _wininet()
        options = self._build_options(state)
        option_list = _PerConnOptionList()
        option_list.dwSize = ctypes.sizeof(_PerConnOptionList)
        option_list.pszConnection = None
        option_list.dwOptionCount = 4
        option_list.dwOptionError = 0
        option_list.pOptions = options

        ok = api.InternetSetOptionW(
            None,
            INTERNET_OPTION_PER_CONNECTION_OPTION,
            ctypes.byref(option_list),
            option_list.dwSize,
        )
        if not ok:
            raise ProxyError(f"InternetSetOption failed (error {ctypes.get_last_error()})")

        api.InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
        api.InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0)
        self._mirror_registry(state)

    def _mirror_registry(self, state: ProxyState) -> None:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, int(state.enabled))
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, state.server)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, state.bypass)
                winreg.SetValueEx(
                    key, "AutoConfigURL", 0, winreg.REG_SZ, state.autoconfig_url
                )
        except OSError as exc:
            log.warning("could not mirror proxy state into the registry: %s", exc)


class RegistryBackend:
    """Fallback backend that only touches HKCU Internet Settings."""

    def read(self) -> ProxyState:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
                enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0])
                server = str(winreg.QueryValueEx(key, "ProxyServer")[0])
                try:
                    bypass = str(winreg.QueryValueEx(key, "ProxyOverride")[0])
                except FileNotFoundError:
                    bypass = DEFAULT_BYPASS
                try:
                    pac = str(winreg.QueryValueEx(key, "AutoConfigURL")[0])
                except FileNotFoundError:
                    pac = ""
        except OSError as exc:
            raise ProxyError(f"cannot read registry proxy settings: {exc}") from exc

        flags = PROXY_TYPE_DIRECT
        if enabled:
            flags |= PROXY_TYPE_PROXY
        if pac:
            flags |= PROXY_TYPE_AUTO_PROXY_URL
        return ProxyState(flags=flags, server=server, bypass=bypass, autoconfig_url=pac)

    def write(self, state: ProxyState) -> None:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, int(state.enabled))
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, state.server)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, state.bypass)
                winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, state.autoconfig_url)
        except OSError as exc:
            raise ProxyError(f"cannot write registry proxy settings: {exc}") from exc

        api = _wininet()
        api.InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
        api.InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0)


def default_backend() -> ProxyBackend:
    if sys.platform != "win32":
        return _NullBackend()
    try:
        backend = WinInetBackend()
        backend.read()
        return backend
    except Exception as exc:  # noqa: BLE001 - fall back to registry
        log.warning("WinINET proxy API unavailable (%s); using registry backend", exc)
        return RegistryBackend()


class _NullBackend:
    """No-op backend for non-Windows development and tests."""

    def __init__(self) -> None:
        self.state = ProxyState()

    def read(self) -> ProxyState:
        return self.state

    def write(self, state: ProxyState) -> None:
        self.state = state


class SystemProxy:
    """Apply, track and restore the Windows system proxy."""

    def __init__(
        self,
        journal_path: Path,
        backend: ProxyBackend | None = None,
        *,
        owner_pid: int | None = None,
        process_checker=pid_running,
        clock=time.time,
    ) -> None:
        self._journal_path = journal_path
        self._backend = backend or default_backend()
        self._owner_pid = owner_pid if owner_pid is not None else os.getpid()
        self._process_checker = process_checker
        self._clock = clock

    @property
    def backend(self) -> ProxyBackend:
        return self._backend

    def read(self) -> ProxyState:
        return self._backend.read()

    def snapshot(self) -> ProxyState:
        return self._backend.read()

    def apply(self, server: str, bypass: str | None = None) -> ProxyState:
        """Point the system proxy at *server*, journaling the previous state."""
        previous = self._backend.read()
        if not self._journal_path.exists():
            self._write_journal(_usable_snapshot(previous))
        applied = previous.with_proxy(server, bypass)
        try:
            self._backend.write(applied)
        except ProxyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProxyError(f"failed to enable the system proxy: {exc}") from exc
        log.info("system proxy enabled -> %s", server)
        return applied

    def disable(self) -> None:
        """Turn the system proxy off (used when the user disables the feature)."""
        current = self._backend.read()
        self._backend.write(current.disabled())
        log.info("system proxy disabled")

    def restore(self) -> bool:
        """Restore the journalled snapshot. Returns True when something changed."""
        journal = self._read_journal()
        if journal is None:
            return False
        try:
            snapshot = ProxyState.from_dict(journal.get("snapshot", {}))
        except (TypeError, ValueError) as exc:
            log.error("proxy journal is corrupt: %s", exc)
            self.clear_journal()
            return False

        snapshot = _usable_snapshot(snapshot)
        self._backend.write(snapshot)
        self.clear_journal()
        log.info("system proxy restored (%s)", snapshot.server or "direct")
        return True

    def recover_if_stale(self) -> str:
        """Restore the proxy if a previous instance died while owning it.

        Returns one of: "none", "restored", "active", "corrupt".
        """
        journal = self._read_journal()
        if journal is None:
            return "none"
        try:
            owner = int(journal.get("pid", 0))
        except (TypeError, ValueError):
            owner = 0
        if owner and self._process_checker(owner):
            log.info("proxy journal belongs to a live process (%s); leaving it", owner)
            return "active"
        try:
            snapshot = ProxyState.from_dict(journal.get("snapshot", {}))
        except (TypeError, ValueError):
            self.clear_journal()
            return "corrupt"
        snapshot = _usable_snapshot(snapshot)
        self._backend.write(snapshot)
        self.clear_journal()
        log.warning("recovered system proxy left behind by pid %s", owner)
        return "restored"

    def repair_stale_loopback(self) -> bool:
        """Clear a dead ephemeral loopback proxy left without a journal."""
        current = self._backend.read()
        fixed = _usable_snapshot(current)
        if fixed == current:
            return False
        self._backend.write(fixed)
        log.warning("cleared a stale loopback system proxy (%s)", current.server)
        return True

    def owns_system_proxy(self) -> bool:
        return self._journal_path.exists()

    def clear_journal(self) -> None:
        try:
            self._journal_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("could not remove proxy journal: %s", exc)

    def _write_journal(self, snapshot: ProxyState) -> None:
        payload = {
            "pid": self._owner_pid,
            "created_at": self._clock(),
            "snapshot": snapshot.to_dict(),
        }
        atomic_write_json(self._journal_path, payload)

    def _read_journal(self) -> dict | None:
        data = read_json(self._journal_path)
        if not isinstance(data, dict):
            if self._journal_path.exists():
                log.warning("discarding an unreadable proxy journal")
                self.clear_journal()
            return None
        return data


def describe_foreign_proxy(state: ProxyState, our_server: str) -> str | None:
    """Explain why an already-enabled third-party proxy blocks us, if it does."""
    if not state.enabled:
        return None
    if state.server.strip().lower() == our_server.strip().lower():
        return None
    owner = state.server or state.autoconfig_url or "unknown"
    return (
        "Another proxy client currently owns the Windows system proxy "
        f"({owner}). Enabling Mihomo Lite will take it over; the previous "
        "setting is restored when you disconnect or quit."
    )
