"""QProcess wrapper around the Mihomo core.

QProcess is used instead of subprocess because it gives us process lifecycle
signals on the Qt event loop (started / finished / errorOccurred) without a
polling thread.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

log = logging.getLogger(__name__)


class MihomoProcess(QObject):
    started = Signal(int)
    stopped = Signal(int, bool)  # exit code, crashed
    output = Signal(str)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._terminating = False
        self._expected = False
        self._kill_timer: QTimer | None = None

    # -- lifecycle ---------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    @property
    def pid(self) -> int:
        return int(self._process.processId())

    def start(self, core: Path, config: Path, workdir: Path, *, extra_env: dict | None = None) -> bool:
        if self.running:
            log.warning("core is already running; start ignored")
            return False
        if not core.exists():
            self.failed.emit(f"core binary not found: {core}")
            return False

        self._terminating = False
        self._expected = False
        env = QProcessEnvironment.systemEnvironment()
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env.remove(key)
        for key, value in (extra_env or {}).items():
            env.insert(key, str(value))

        self._process.setProcessEnvironment(env)
        self._process.setWorkingDirectory(str(workdir))
        self._process.setProgram(str(core))
        self._process.setArguments(["-d", str(workdir), "-f", str(config)])
        log.info("starting core: %s -d %s -f %s", core.name, workdir, config.name)
        self._process.start()
        return True

    def stop(self, *, graceful_ms: int = 1200) -> None:
        """Ask the core to exit, then force-kill if it ignores us."""
        if not self.running:
            return
        self._terminating = True
        log.info("stopping core (pid %s)", self.pid)

        self._process.terminate()
        if self._kill_timer is not None:
            self._kill_timer.stop()
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_kill)
        self._kill_timer.start(graceful_ms)

    def _force_kill(self) -> None:
        if self.running:
            log.warning("core did not exit gracefully; killing it")
            self._process.kill()

    def kill_now(self, wait_ms: int = 1500) -> None:
        """Synchronous kill used on application shutdown."""
        self._terminating = True
        if self.running:
            self._process.kill()
            self._process.waitForFinished(wait_ms)

    @property
    def terminating(self) -> bool:
        return self._terminating

    # -- slots -------------------------------------------------------------
    def _on_output(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line:
                self.output.emit(line)

    def _on_started(self) -> None:
        self._expected = True
        log.info("core started (pid %s)", self.pid)
        self.started.emit(self.pid)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._kill_timer is not None:
            self._kill_timer.stop()
            self._kill_timer = None
        crashed = (not self._terminating) and (
            exit_code != 0 or exit_status == QProcess.ExitStatus.CrashExit
        )
        log.info(
            "core exited (code=%s status=%s crashed=%s)", exit_code, exit_status.name, crashed
        )
        self.stopped.emit(exit_code, crashed)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            message = f"the core failed to start: {self._process.errorString()}"
            log.error(message)
            self.failed.emit(message)
        elif error == QProcess.ProcessError.Crashed and not self._terminating:
            log.error("core process crashed: %s", self._process.errorString())


def core_environment(extra: dict | None = None) -> dict[str, str]:
    """Environment helpers for testing/headless runs."""
    base = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    base.update(extra or {})
    return base
