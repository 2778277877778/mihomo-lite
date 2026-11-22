"""Background subscription updates.

Profiles are refreshed one at a time through the shared TaskRunner, so a slow
provider never blocks the UI. Failed downloads keep the previous working file
and are retried no more often than half an interval.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.models.profile import Profile, ProfileKind
from mihomo_lite.utils.tasks import TaskRunner

log = logging.getLogger(__name__)

_TICK_MS = 15 * 60 * 1000
_FIRST_CHECK_MS = 2 * 60 * 1000


class UpdateScheduler(QObject):
    started = Signal()
    profile_updated = Signal(object)
    profile_failed = Signal(str, str)
    finished = Signal(int, int)
    active_profile_updated = Signal(object)

    def __init__(
        self,
        settings: SettingsStore,
        profiles: ProfileManager,
        runner: TaskRunner,
        *,
        clock: Callable[[], float] = time.time,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._profiles = profiles
        self._runner = runner
        self._clock = clock
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._first_check = QTimer(self)
        self._first_check.setSingleShot(True)
        self._first_check.setInterval(_FIRST_CHECK_MS)
        self._first_check.timeout.connect(self._tick)

        self._queue: list[Profile] = []
        self._busy = False
        self._updated = 0
        self._failed = 0
        self._attempted: dict[str, float] = {}

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start(self) -> None:
        self._timer.start()
        self._first_check.start()

    def stop(self) -> None:
        self._timer.stop()
        self._first_check.stop()

    # -- scheduling --------------------------------------------------------
    def due_profiles(self, *, force: bool = False, now: float | None = None) -> list[Profile]:
        interval = max(1, self._settings.current.auto_update_interval_hours) * 3600
        moment = self._clock() if now is None else now
        due: list[Profile] = []
        for profile in self._profiles.profiles:
            if profile.kind is not ProfileKind.SUBSCRIPTION or not profile.url:
                continue
            last_download = profile.updated_at or 0.0
            last_attempt = self._attempted.get(profile.id, 0.0)
            if force:
                due.append(profile)
                continue
            if moment - max(last_download, last_attempt) >= interval:
                due.append(profile)
        return due

    def update_all(self, *, force: bool = False) -> bool:
        """Queue every due subscription. Returns False when nothing was queued."""
        if self._busy:
            log.debug("subscription update already running")
            return False
        if not force and not self._settings.current.auto_update_profiles:
            return False

        self._queue = self.due_profiles(force=force)
        if not self._queue:
            return False

        log.info("updating %s subscription(s)", len(self._queue))
        self._busy = True
        self._updated = 0
        self._failed = 0
        self.started.emit()
        self._run_next()
        return True

    def _tick(self) -> None:
        if not self._settings.current.auto_update_profiles or self.is_busy:
            return
        self.update_all()

    # -- execution ---------------------------------------------------------
    def _run_next(self) -> None:
        if not self._queue:
            self._finish()
            return
        profile = self._queue.pop(0)
        self._attempted[profile.id] = self._clock()

        self._runner.submit(
            self._profiles.refresh,
            args=(profile.id,),
            on_success=self._on_refreshed,
            on_error=lambda message, name=profile.name: self._on_failed(name, message),
        )

    def _on_refreshed(self, profile: object) -> None:
        if isinstance(profile, Profile):
            self._updated += 1
            self.profile_updated.emit(profile)
            log.info("subscription updated: %s", profile.name)
            if profile.id == self._profiles.active_id:
                self.active_profile_updated.emit(profile)
        self._run_next()

    def _on_failed(self, name: str, message: str) -> None:
        self._failed += 1
        self.profile_failed.emit(name, message)
        log.warning("subscription update failed for %s: %s", name, message)
        self._run_next()

    def _finish(self) -> None:
        self._busy = False
        self.finished.emit(self._updated, self._failed)
        log.info(
            "subscription update finished: %s updated, %s failed", self._updated, self._failed
        )
