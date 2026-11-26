"""Connection state and persisted application settings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from mihomo_lite.config.defaults import DEFAULT_BYPASS
from mihomo_lite.i18n import tr


class ConnectionState(StrEnum):
    """The single source of truth for the connection lifecycle."""

    STOPPED = "stopped"
    STARTING = "starting"
    CONNECTED = "connected"
    STOPPING = "stopping"
    ERROR = "error"

    @property
    def is_busy(self) -> bool:
        return self in (ConnectionState.STARTING, ConnectionState.STOPPING)

    @property
    def is_running(self) -> bool:
        return self is ConnectionState.CONNECTED

    @property
    def label(self) -> str:
        return tr(
            {
                ConnectionState.STOPPED: "Disconnected",
                ConnectionState.STARTING: "Connecting…",
                ConnectionState.CONNECTED: "Connected",
                ConnectionState.STOPPING: "Disconnecting…",
                ConnectionState.ERROR: "Error",
            }[self]
        )


class AppSettings(BaseModel):
    """User preferences persisted to settings.json."""

    model_config = {"validate_assignment": True}

    language: str = "en"
    theme: str = "dark"
    system_proxy: bool = True
    bypass: str = DEFAULT_BYPASS
    autostart: bool = False
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    start_minimized: bool = False
    start_connected: bool = False
    invert_scroll: bool = False
    log_level: str = "INFO"
    core_path: str = ""
    mixed_port: int = 0
    api_port: int = 0
    last_profile_id: str = ""
    auto_update_profiles: bool = False
    auto_update_interval_hours: int = 12
    notifications: bool = True
    tun_enabled: bool = False
    tun_stack: str = "mixed"
    tun_dns_hijack: bool = True
    download_multithreaded: bool = False
    download_multi_node: bool = False
    download_threads: int = 0
    download_nodes: list[str] = Field(default_factory=list)
    window_width: int = 980
    window_height: int = 660

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        if value not in {"en", "zh"}:
            raise ValueError("language must be 'en' or 'zh'")
        return value

    @field_validator("theme")
    @classmethod
    def _check_theme(cls, value: str) -> str:
        if value not in {"dark", "light"}:
            raise ValueError("theme must be 'dark' or 'light'")
        return value

    @field_validator("log_level")
    @classmethod
    def _check_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        value = value.upper()
        if value not in allowed:
            raise ValueError("log_level must be one of " + ", ".join(sorted(allowed)))
        return value

    @field_validator("tun_stack")
    @classmethod
    def _check_stack(cls, value: str) -> str:
        value = value.lower()
        if value not in {"system", "gvisor", "mixed"}:
            raise ValueError("tun_stack must be system, gvisor or mixed")
        return value

    @field_validator("auto_update_interval_hours")
    @classmethod
    def _check_interval(cls, value: int) -> int:
        if value not in {1, 3, 6, 12, 24, 48}:
            raise ValueError("auto_update_interval_hours must be one of 1, 3, 6, 12, 24, 48")
        return value

    @field_validator("download_threads")
    @classmethod
    def _check_download_threads(cls, value: int) -> int:
        if value != 0 and not (4 <= value <= 16):
            raise ValueError("download_threads must be 0 (automatic) or between 4 and 16")
        return value

    @model_validator(mode="after")
    def _enforce_download_dependency(self) -> AppSettings:
        # "Multi-node" only makes sense inside a multi-threaded download. Assign
        # through object.__setattr__ so validate_assignment does not recurse.
        if not self.download_multithreaded and self.download_multi_node:
            object.__setattr__(self, "download_multi_node", False)
        return self

    @field_validator("mixed_port", "api_port")
    @classmethod
    def _check_port(cls, value: int) -> int:
        if value != 0 and not (1024 <= value <= 65535):
            raise ValueError("port must be 0 (automatic) or between 1024 and 65535")
        return value
