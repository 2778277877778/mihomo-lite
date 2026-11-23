"""Logging setup with secret redaction and an in-memory ring buffer for the UI."""

from __future__ import annotations

import logging
import re
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"
_MAX_RECORDS = 5000

_secrets: set[str] = set()
_secrets_lock = Lock()

_URL_SECRET = re.compile(
    r"(token|secret|password|key|auth|signature|sign)=([^&\s]+)", re.IGNORECASE
)


def register_secret(value: str | None) -> None:
    """Register a value that must never appear in logs (API tokens, etc.)."""
    if not value:
        return
    with _secrets_lock:
        _secrets.add(value)


def clear_secrets() -> None:
    with _secrets_lock:
        _secrets.clear()


def _redact(text: str) -> str:
    if not text:
        return text
    with _secrets_lock:
        secrets = tuple(_secrets)
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "***")
    return text


class SecretFilter(logging.Filter):
    """Scrub registered secrets from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = _redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class RingBufferHandler(logging.Handler):
    """Thread-safe ring buffer consumed by the GUI log view."""

    def __init__(self, capacity: int = _MAX_RECORDS) -> None:
        super().__init__()
        # (sequence, levelno, levelname, text) - the sequence lets consumers keep
        # reading correctly even after the deque starts evicting old records.
        self._records: deque[tuple[int, int, str, str]] = deque(maxlen=capacity)
        self._lock = Lock()
        self._next_seq = 1

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
        except Exception:
            return
        with self._lock:
            self._records.append((self._next_seq, record.levelno, record.levelname, text))
            self._next_seq += 1

    def snapshot(self) -> list[tuple[int, int, str, str]]:
        with self._lock:
            return list(self._records)

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._next_seq - 1

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


_ring = RingBufferHandler()


def get_ring_buffer() -> RingBufferHandler:
    return _ring


def setup_logging(log_dir: Path, *, level: int = logging.INFO, console: bool = False) -> Path:
    """Configure application logging once; returns the log file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mihomo-lite.log"

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    secret_filter = SecretFilter()

    file_handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(secret_filter)
    root.addHandler(file_handler)

    _ring.setFormatter(formatter)
    _ring.addFilter(secret_filter)
    root.addHandler(_ring)

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream.addFilter(secret_filter)
        root.addHandler(stream)

    for noisy in ("httpx", "httpcore", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_path


def redact_url(text: str) -> str:
    """Redact credentials embedded in URLs before showing them to the user."""
    return _URL_SECRET.sub(r"\1=***", text)
