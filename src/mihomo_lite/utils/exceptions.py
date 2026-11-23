"""Typed exceptions used across the application layers."""

from __future__ import annotations


class MihomoLiteError(Exception):
    """Base class for every error raised by this application."""


class ConfigError(MihomoLiteError):
    """A profile could not be read, parsed or validated."""


class CoreError(MihomoLiteError):
    """The Mihomo core binary is missing, broken or failed to start."""


class CoreNotFoundError(CoreError):
    """No usable Mihomo core binary was found."""


class CoreDownloadError(CoreError):
    """Downloading the Mihomo core failed."""


class ApiError(MihomoLiteError):
    """The Mihomo REST API returned an error or could not be reached."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ProxyError(MihomoLiteError):
    """Applying or restoring the Windows system proxy failed."""


class IntegrityError(MihomoLiteError):
    """A downloaded file does not match its expected checksum."""


class StateError(MihomoLiteError):
    """An operation was requested while the connection was in the wrong state."""
