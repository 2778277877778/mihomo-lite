"""Connection state and persisted application settings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, field_validator

from mihomo_lite.config.defaults import DEFAULT_BYPASS


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
        return {
            ConnectionState.STOPPED: "Disconnected",
            ConnectionState.STARTING: "Connecting…",
            ConnectionState.CONNECTED: "Connected",
            ConnectionState.STOPPING: "Disconnecting…",
            ConnectionState.ERROR: "Error",
        }[self]


class AppSettings(BaseModel):
    """User preferences persisted to settings.json."""

    model_config = {"validate_assignment": True}

    theme: str = "dark"
    system_proxy: bool = True
    bypass: str = DEFAULT_BYPASS
    autostart: bool = False
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    start_minimized: bool = False
    log_level: str = "INFO"
    core_path: str = ""
    mixed_port: int = 0
    api_port: int = 0
    last_profile_id: str = ""
    auto_update_profiles: bool = False
    notifications: bool = True
    window_width: int = 980
    window_height: int = 660

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

    @field_validator("mixed_port", "api_port")
    @classmethod
    def _check_port(cls, value: int) -> int:
        if value != 0 and not (1024 <= value <= 65535):
            raise ValueError("port must be 0 (automatic) or between 1024 and 65535")
        return value
