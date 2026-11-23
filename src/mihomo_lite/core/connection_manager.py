"""The single owner of the connection lifecycle.

Every other component (UI, tray, proxy manager) observes state through this
class instead of probing the core on its own.

Connect:  validate -> generate -> start core -> wait for API -> enable proxy
Disconnect: restore proxy -> stop core -> clear session
"""

from __future__ import annotations

import logging
import secrets
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from mihomo_lite.config.generator import generate_runtime_config, write_runtime_config
from mihomo_lite.config.validator import validate_config
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.core.traffic_monitor import TrafficMonitor
from mihomo_lite.mihomo.api import MihomoAPI
from mihomo_lite.mihomo.core_manager import CoreManager
from mihomo_lite.mihomo.health import wait_for_api
from mihomo_lite.mihomo.process import MihomoProcess
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.system import elevation, wintun
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.system.proxy import SystemProxy
from mihomo_lite.utils.exceptions import ConfigError, CoreError, ProxyError
from mihomo_lite.utils.fs import atomic_write_json, read_json
from mihomo_lite.utils.logger import register_secret
from mihomo_lite.utils.net import find_free_port
from mihomo_lite.utils.tasks import TaskRunner
from mihomo_lite.utils.winapi import pid_running, process_image_name, terminate_pid

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionInfo:
    profile_name: str
    mixed_port: int
    api_port: int
    core_version: str
    started_at: float
    mode: str = "system"

    @property
    def api_base_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def proxy_server(self) -> str:
        return f"127.0.0.1:{self.mixed_port}"


class ConnectionManager(QObject):
    state_changed = Signal(object)
    session_changed = Signal(object)
    error_changed = Signal(str)
    warning = Signal(str)
    core_log = Signal(str)
    core_started = Signal(int)
    elevation_required = Signal(str)

    def __init__(
        self,
        paths: AppPaths,
        settings: SettingsStore,
        profiles: ProfileManager,
        *,
        process: MihomoProcess | None = None,
        proxy: SystemProxy | None = None,
        core: CoreManager | None = None,
        runner: TaskRunner | None = None,
        api_factory: Callable[..., MihomoAPI] = MihomoAPI,
        traffic: TrafficMonitor | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._settings = settings
        self._profiles = profiles
        self._process = process or MihomoProcess(self)
        self._proxy = proxy or SystemProxy(paths.proxy_journal)
        self._core = core or CoreManager(paths, lambda: settings.current.core_path)
        self._runner = runner or TaskRunner(self)
        self._api_factory = api_factory
        self._traffic = traffic or TrafficMonitor(self)

        self._state = ConnectionState.STOPPED
        self._session: SessionInfo | None = None
        self._api: MihomoAPI | None = None
        self._secret = ""
        self._mix_port = 0
        self._api_port = 0
        self._profile_name = ""
        self._generation = 0
        self._stop_reason: str | None = None
        self._mode = "system"
        self._connect_attempts = 0
        self._max_connect_attempts = 3
        self._recent_output: deque[str] = deque(maxlen=300)

        self._process.started.connect(self._on_core_started)
        self._process.stopped.connect(self._on_core_stopped)
        self._process.output.connect(self._on_core_output)
        self._process.failed.connect(self._on_core_failed)

    # -- public state ------------------------------------------------------
    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def session(self) -> SessionInfo | None:
        return self._session

    @property
    def api(self) -> MihomoAPI | None:
        return self._api

    @property
    def traffic(self) -> TrafficMonitor:
        return self._traffic

    @property
    def is_connected(self) -> bool:
        return self._state is ConnectionState.CONNECTED

    # -- startup recovery --------------------------------------------------
    def recover_after_crash(self) -> str:
        """Restore a proxy journal and reap a core left by a previous run."""
        result = self._proxy.recover_if_stale()
        if result == "restored":
            self.warning.emit(
                "The previous session ended unexpectedly. Your original system proxy setting was restored."
            )
        elif result == "corrupt":
            self.warning.emit("A damaged proxy recovery record was found and discarded.")
        self._reap_orphan_core()
        return result

    def _reap_orphan_core(self) -> None:
        data = read_json(self._paths.session_file, default=None)
        if not isinstance(data, dict):
            return
        try:
            pid = int(data.get("pid", 0))
        except (TypeError, ValueError):
            pid = 0
        if pid and pid_running(pid):
            image = (process_image_name(pid) or "").lower()
            if "mihomo" in image and terminate_pid(pid):
                log.warning("terminated orphaned core process %s", pid)
        self._clear_session_file()

    # -- connect -----------------------------------------------------------
    def connect(self) -> None:
        self._connect_attempts = 0
        self._begin_connect()

    def _begin_connect(self) -> None:
        if self._state in (
            ConnectionState.STARTING,
            ConnectionState.CONNECTED,
            ConnectionState.STOPPING,
        ):
            return
        self._connect_attempts += 1

        self._generation += 1
        token = self._generation
        self._stop_reason = None

        profile = self._profiles.active_profile()
        if profile is None:
            self._fail("Import a configuration profile before connecting.")
            return

        settings = self._settings.current
        use_tun = settings.tun_enabled
        if use_tun:
            if sys.platform != "win32":
                self._fail("TUN mode is only supported on Windows.")
                return
            if not elevation.is_admin():
                self.elevation_required.emit(
                    "TUN mode needs administrator rights. Restart Mihomo Lite as administrator?"
                )
                return

        use_proxy = settings.system_proxy and not use_tun
        self._mode = "tun" if use_tun else ("system" if use_proxy else "none")
        try:
            data = self._profiles.load_active_config()
            result = validate_config(data)
            if not result.ok:
                raise ConfigError("; ".join(result.errors))

            mixed_port = find_free_port(settings.mixed_port)
            api_port = find_free_port(settings.api_port, avoid={mixed_port})
            dns_port = (
                find_free_port(0, avoid={mixed_port, api_port})
                if isinstance(data.get("dns"), dict)
                else None
            )
            secret = secrets.token_urlsafe(24)
            register_secret(secret)
            generated = generate_runtime_config(
                data,
                mixed_port=mixed_port,
                api_port=api_port,
                secret=secret,
                log_level=settings.log_level,
                system_proxy=use_proxy,
                tun=use_tun,
                tun_stack=settings.tun_stack,
                tun_dns_hijack=settings.tun_dns_hijack,
                dns_port=dns_port,
            )
            write_runtime_config(self._paths.runtime_config, generated)
            for note in generated.notes:
                log.debug("config: %s", note)
        except (ConfigError, OSError, ValueError) as exc:
            self._fail(str(exc))
            return

        try:
            core_info = self._core.ensure()
        except CoreError as exc:
            self._fail(str(exc))
            return

        if use_tun and wintun.locate(core_info.path) is None:
            self._fail(
                "TUN mode needs wintun.dll next to the core. "
                "Open Settings -> Network and press 'Download wintun'."
            )
            return

        self._secret = secret
        self._mix_port = mixed_port
        self._api_port = api_port
        self._profile_name = profile.name
        self._api = self._api_factory(
            f"http://127.0.0.1:{api_port}", secret, timeout=4.0
        )

        self._set_state(ConnectionState.STARTING)
        log.debug("launching core %s with %s", core_info.path, self._paths.runtime_config)
        if not self._process.start(
            core_info.path, self._paths.runtime_config, self._paths.runtime
        ):
            self._fail("The Mihomo core could not be launched.")
            return

        self._runner.submit(
            wait_for_api,
            args=(self._api,),
            kwargs={"timeout": 45.0, "is_cancelled": lambda: self._generation != token},
            on_success=lambda version: self._on_api_ready(token, version),
            on_error=lambda message: self._on_api_failed(token, message),
        )

    def _on_api_ready(self, token: int, version: object) -> None:
        log.debug(
            "api ready callback: token=%s generation=%s state=%s",
            token,
            self._generation,
            self._state.value,
        )
        if token != self._generation or self._state is not ConnectionState.STARTING:
            return
        try:
            self._finish_connect(version)
        except Exception as exc:  # noqa: BLE001 - must never leave STARTING behind
            log.exception("connect failed while finalising the session")
            self._stop_reason = "error"
            self._teardown()
            self._fail(f"Could not finish connecting: {exc}")

    def _finish_connect(self, version: object) -> None:
        core_version = ""
        if isinstance(version, dict):
            core_version = str(version.get("version", ""))

        settings = self._settings.current
        if self._mode == "system":
            try:
                self._proxy.apply(f"127.0.0.1:{self._mix_port}", settings.bypass)
            except ProxyError as exc:
                log.error("could not enable the system proxy: %s", exc)
                self.warning.emit(
                    f"Connected, but the system proxy could not be enabled: {exc}"
                )

        self._traffic.start(self._api_port, self._secret)
        self._session = SessionInfo(
            profile_name=self._profile_name,
            mixed_port=self._mix_port,
            api_port=self._api_port,
            core_version=core_version,
            started_at=time.time(),
            mode=self._mode,
        )
        self._write_session_file()
        self._set_state(ConnectionState.CONNECTED)
        self.session_changed.emit(self._session)
        if self._mode == "tun":
            QTimer.singleShot(2500, self._verify_tun_started)
        log.info(
            "connected: profile=%s mixed=%s api=%s core=%s",
            self._profile_name,
            self._mix_port,
            self._api_port,
            core_version,
        )

    def _verify_tun_started(self) -> None:
        """The core answers /version even when the TUN device failed to open.

        Watch the first seconds of core output and turn a silent failure into a
        visible warning instead of a green light that proxies nothing.
        """
        if self._mode != "tun" or self._state is not ConnectionState.CONNECTED:
            return
        lines = [line.lower() for line in self._recent_output]
        problems = [
            line
            for line in lines
            if ("tun" in line or "wintun" in line)
            and ("error" in line or "failed" in line or "cannot" in line)
        ]
        if problems:
            self.warning.emit(
                "TUN did not start cleanly: " + problems[-1][:200]
            )
            return
        started = any(
            "tun" in line and ("listening" in line or "started" in line) for line in lines
        )
        if not started:
            self.warning.emit(
                "TUN status is unconfirmed; check Logs if traffic does not go through Mihomo."
            )

    def reload_active_config(self) -> bool:
        """Rewrite the runtime config from the active profile and ask the core to reload."""
        if self._state is not ConnectionState.CONNECTED or self._api is None:
            return False
        settings = self._settings.current
        try:
            data = self._profiles.load_active_config()
            result = validate_config(data)
            if not result.ok:
                raise ConfigError("; ".join(result.errors))
            generated = generate_runtime_config(
                data,
                mixed_port=self._mix_port,
                api_port=self._api_port,
                secret=self._secret,
                log_level=settings.log_level,
                system_proxy=self._mode == "system",
                tun=self._mode == "tun",
                tun_stack=settings.tun_stack,
                tun_dns_hijack=settings.tun_dns_hijack,
            )
            write_runtime_config(self._paths.runtime_config, generated)
        except (ConfigError, OSError, ValueError) as exc:
            self.warning.emit(f"Could not reload the updated profile: {exc}")
            return False

        api = self._api
        self._runner.submit(
            api.reload_config,
            args=(str(self._paths.runtime_config),),
            on_success=lambda _result: self.warning.emit("The active profile was reloaded."),
            on_error=lambda message: self.warning.emit(f"Core reload failed: {message}"),
        )
        return True

    def _on_api_failed(self, token: int, message: str) -> None:
        if token != self._generation:
            return
        if self._state is not ConnectionState.STARTING:
            return
        self._stop_reason = "error"
        self._teardown()
        self._fail(f"The Mihomo core did not become ready: {message}")

    def _on_core_output(self, line: str) -> None:
        self._recent_output.append(line)
        lowered = line.lower()
        if "level=error" in lowered or "level=fatal" in lowered:
            log.error("core: %s", line)
        elif "level=warning" in lowered:
            log.warning("core: %s", line)
        else:
            log.info("core: %s", line)
        self.core_log.emit(line)

    def _on_core_started(self, pid: int) -> None:
        self.core_started.emit(pid)
        self._write_session_file(pid=pid)

    def _on_core_failed(self, message: str) -> None:
        if self._state is ConnectionState.STARTING:
            self._stop_reason = "error"
            self._teardown()
            self._fail(message)

    # -- disconnect --------------------------------------------------------
    def disconnect(self) -> None:
        if self._state in (ConnectionState.STOPPED, ConnectionState.STOPPING):
            return
        self._stop_reason = "user"
        self._generation += 1
        self._set_state(ConnectionState.STOPPING)
        self._teardown()
        if not self._process.running:
            self._finish_stop()

    def _teardown(self) -> None:
        """Order matters: the system proxy is restored before the core stops."""
        self._traffic.stop()
        try:
            if self._proxy.owns_system_proxy():
                self._proxy.restore()
        except ProxyError as exc:
            log.error("could not restore the system proxy: %s", exc)
            self.warning.emit(f"Could not restore the system proxy: {exc}")
        self._close_api()
        if self._process.running:
            self._process.stop()
        else:
            self._finish_stop()

    def _close_api(self) -> None:
        if self._api is not None:
            try:
                self._api.close()
            except Exception:  # noqa: BLE001 - closing must never fail the flow
                pass
            self._api = None

    def _on_core_stopped(self, exit_code: int, crashed: bool) -> None:
        if self._state is ConnectionState.STOPPING:
            self._finish_stop()
            return
        if (
            self._state is ConnectionState.STARTING
            and self._stop_reason is None
            and exit_code != 0
            and self._connect_attempts < self._max_connect_attempts
        ):
            log.warning(
                "core exited during startup (attempt %s/%s); retrying with fresh ports",
                self._connect_attempts,
                self._max_connect_attempts,
            )
            self._close_api()
            self._set_state(ConnectionState.STOPPED)
            QTimer.singleShot(500, self._begin_connect)
            return

        if self._state in (ConnectionState.STARTING, ConnectionState.CONNECTED):
            self._stop_reason = "crash"
            self._teardown()
            tail = [line for line in list(self._recent_output)[-4:] if line.strip()]
            detail = f" Last output: {tail[-1][:300]}" if tail else ""
            self._fail(
                f"The Mihomo core exited unexpectedly (code {exit_code}).{detail}"
            )
            return
        log.debug("core stopped while already %s", self._state.value)

    def _finish_stop(self) -> None:
        self._traffic.stop()
        self._close_api()
        self._clear_session_file()
        self._session = None
        self.session_changed.emit(None)
        if self._state is not ConnectionState.ERROR:
            self._set_state(ConnectionState.STOPPED)

    def _fail(self, message: str) -> None:
        log.error("%s", message)
        self._stop_reason = None
        self._set_state(ConnectionState.ERROR)
        self.error_changed.emit(message)

    def _set_state(self, state: ConnectionState) -> None:
        if state is self._state:
            return
        self._state = state
        self.state_changed.emit(state)

    # -- session journal ---------------------------------------------------
    def _write_session_file(self, pid: int | None = None) -> None:
        if pid is None:
            pid = self._process.pid
        if not pid and not self._mix_port:
            return
        try:
            atomic_write_json(
                self._paths.session_file,
                {
                    "pid": int(pid or 0),
                    "mixed_port": self._mix_port,
                    "api_port": self._api_port,
                    "started_at": time.time(),
                },
            )
        except OSError as exc:
            log.debug("cannot write session file: %s", exc)

    def _clear_session_file(self) -> None:
        try:
            Path(self._paths.session_file).unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.debug("cannot remove session file: %s", exc)

    # -- shutdown ----------------------------------------------------------
    def force_stop(self) -> None:
        """Hard-stop the core and repair the proxy, whatever state we are in."""
        log.warning("force stopping the core")
        self._generation += 1
        self._stop_reason = "force"
        self._set_state(ConnectionState.STOPPING)
        try:
            self._traffic.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._proxy.owns_system_proxy():
                self._proxy.restore()
        except ProxyError as exc:
            log.error("force stop: could not restore the system proxy: %s", exc)
        self._close_api()
        try:
            self._process.kill_now()
        except Exception:  # noqa: BLE001
            pass
        self._clear_session_file()
        self._session = None
        self.session_changed.emit(None)
        self._set_state(ConnectionState.STOPPED)
        self.warning.emit("The Mihomo core was force-stopped and the system proxy was restored.")

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Best-effort cleanup used on application exit."""
        log.info("shutting down the connection manager")
        self._generation += 1
        self._stop_reason = "shutdown"
        try:
            self._traffic.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._proxy.owns_system_proxy():
                self._proxy.restore()
        except ProxyError as exc:
            log.error("shutdown: could not restore the system proxy: %s", exc)
        self._close_api()
        try:
            self._process.kill_now(timeout_ms)
        except Exception:  # noqa: BLE001
            pass
        self._clear_session_file()
        self._session = None
        self._state = ConnectionState.STOPPED
