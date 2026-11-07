"""Run blocking work off the GUI thread and deliver the result via Qt signals."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)


class _Signals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        log.debug("background task started: %s", getattr(self.fn, "__name__", self.fn))
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            log.error("background task failed: %s\n%s", exc, traceback.format_exc(limit=3))
            self.signals.failed.emit(str(exc))
        else:
            log.debug("background task succeeded: %s", result if isinstance(result, (str, int)) else type(result))
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


class TaskRunner(QObject):
    """Small facade over QThreadPool with per-call callbacks."""

    def __init__(self, parent: QObject | None = None, max_threads: int = 4) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._alive: list[_Task] = []

    def submit(
        self,
        fn: Callable[..., Any],
        *,
        args: tuple = (),
        kwargs: dict | None = None,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        task = _Task(fn, args, dict(kwargs or {}))
        # PySide keeps only a weak reference to plain Python callables used as
        # slots; hold them here so the queued signal still finds a live target.
        task.callbacks = [cb for cb in (on_success, on_error, on_finished) if cb is not None]
        self._alive.append(task)

        def _cleanup() -> None:
            if task in self._alive:
                self._alive.remove(task)

        if on_success is not None:
            task.signals.succeeded.connect(on_success)
        if on_error is not None:
            task.signals.failed.connect(on_error)
        if on_finished is not None:
            task.signals.finished.connect(on_finished)
        task.signals.finished.connect(_cleanup)
        self._pool.start(task)

    def wait(self, msecs: int = 5000) -> bool:
        return self._pool.waitForDone(msecs)
