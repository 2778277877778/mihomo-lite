"""Session and daily traffic statistics persisted to disk."""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from PySide6.QtCore import QObject, Signal

from mihomo_lite.core.traffic_monitor import TrafficMonitor, TrafficSample
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.utils.fs import atomic_write_json, read_json

log = logging.getLogger(__name__)

HISTORY_SECONDS = 120
_SAVE_EVERY_SECONDS = 15.0


@dataclass(frozen=True)
class TrafficSnapshot:
    today_down: int = 0
    today_up: int = 0
    session_down: int = 0
    session_up: int = 0
    peak_down: int = 0
    peak_up: int = 0
    samples: tuple[tuple[int, int], ...] = field(default_factory=tuple)


class TrafficStats(QObject):
    updated = Signal(object)

    def __init__(
        self,
        paths: AppPaths,
        traffic: TrafficMonitor,
        *,
        clock: Callable[[], float] = time.time,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._file = paths.root / "traffic_stats.json"
        self._clock = clock
        self._day = date.today()
        self._today_down = 0
        self._today_up = 0
        self._session_down = 0
        self._session_up = 0
        self._peak_down = 0
        self._peak_up = 0
        self._samples: deque[tuple[int, int]] = deque(maxlen=HISTORY_SECONDS)
        self._last_total_down = 0
        self._last_total_up = 0
        self._last_save = 0.0
        self._load()
        traffic.sample.connect(self._on_sample)

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        data = read_json(self._file, default={})
        if not isinstance(data, dict):
            return
        if str(data.get("date")) != self._day.isoformat():
            return
        self._today_down = int(data.get("down", 0) or 0)
        self._today_up = int(data.get("up", 0) or 0)

    def flush(self) -> None:
        try:
            atomic_write_json(
                self._file,
                {
                    "date": self._day.isoformat(),
                    "down": self._today_down,
                    "up": self._today_up,
                },
            )
            self._last_save = self._clock()
        except OSError as exc:
            log.debug("cannot save traffic stats: %s", exc)

    def reset_today(self) -> None:
        self._today_down = 0
        self._today_up = 0
        self.flush()
        self._emit()

    # -- live data ---------------------------------------------------------
    def _roll_day(self) -> None:
        today = date.today()
        if today != self._day:
            self.flush()
            self._day = today
            self._today_down = 0
            self._today_up = 0

    def _on_sample(self, sample: TrafficSample) -> None:
        self._roll_day()
        if sample.down_total < self._last_total_down or sample.up_total < self._last_total_up:
            # A new core session restarted the counters.
            self._last_total_down = 0
            self._last_total_up = 0
        delta_down = max(0, sample.down_total - self._last_total_down)
        delta_up = max(0, sample.up_total - self._last_total_up)
        self._last_total_down = sample.down_total
        self._last_total_up = sample.up_total

        self._today_down += delta_down
        self._today_up += delta_up
        self._session_down = sample.down_total
        self._session_up = sample.up_total
        self._peak_down = max(self._peak_down, sample.down)
        self._peak_up = max(self._peak_up, sample.up)
        self._samples.append((sample.down, sample.up))

        now = self._clock()
        if now - self._last_save >= _SAVE_EVERY_SECONDS:
            self.flush()
        self._emit()

    def _emit(self) -> None:
        self.updated.emit(
            TrafficSnapshot(
                today_down=self._today_down,
                today_up=self._today_up,
                session_down=self._session_down,
                session_up=self._session_up,
                peak_down=self._peak_down,
                peak_up=self._peak_up,
                samples=tuple(self._samples),
            )
        )

    @property
    def snapshot(self) -> TrafficSnapshot:
        return TrafficSnapshot(
            today_down=self._today_down,
            today_up=self._today_up,
            session_down=self._session_down,
            session_up=self._session_up,
            peak_down=self._peak_down,
            peak_up=self._peak_up,
            samples=tuple(self._samples),
        )
