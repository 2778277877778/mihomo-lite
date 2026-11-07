"""Persisted application settings."""

from __future__ import annotations

import logging

from pydantic import ValidationError
from PySide6.QtCore import QObject, Signal

from mihomo_lite.models.app_state import AppSettings
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.utils.fs import atomic_write_json, read_json

log = logging.getLogger(__name__)


class SettingsStore(QObject):
    changed = Signal(object)

    def __init__(self, paths: AppPaths, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._paths = paths
        self._settings = AppSettings()

    @property
    def current(self) -> AppSettings:
        return self._settings

    def load(self) -> AppSettings:
        raw = read_json(self._paths.settings_file, default=None)
        if isinstance(raw, dict):
            try:
                self._settings = AppSettings.model_validate(raw)
            except ValidationError as exc:
                log.warning("settings file is invalid, falling back to defaults: %s", exc)
                self._settings = AppSettings()
        else:
            self._settings = AppSettings()
        return self._settings

    def save(self) -> None:
        try:
            atomic_write_json(self._paths.settings_file, self._settings.model_dump())
        except OSError as exc:
            log.error("cannot save settings: %s", exc)

    def update(self, **changes: object) -> AppSettings:
        data = self._settings.model_dump()
        data.update(changes)
        try:
            self._settings = AppSettings.model_validate(data)
        except ValidationError as exc:
            log.warning("rejected settings update: %s", exc)
            return self._settings
        self.save()
        self.changed.emit(self._settings)
        return self._settings
