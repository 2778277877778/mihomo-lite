"""Core binary verification and API readiness checks."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from mihomo_lite.mihomo.api import MihomoAPI
from mihomo_lite.utils.exceptions import ApiError, CoreNotFoundError

log = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"v?\d+\.\d+\.\d+")
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def check_core_binary(path: Path, *, timeout: float = 8.0) -> tuple[bool, str]:
    """Run '<core> -v' and return (usable, version-or-error)."""
    if not path.exists():
        raise CoreNotFoundError(f"core binary not found: {path}")
    if not path.is_file():
        raise CoreNotFoundError(f"core path is not a file: {path}")
    try:
        completed = subprocess.run(  # noqa: S603 - explicit user-selected binary
            [str(path), "-v"],
            capture_output=True,
            timeout=timeout,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"cannot execute the core binary: {exc}"

    output = (completed.stdout or b"") + (completed.stderr or b"")
    text = output.decode("utf-8", errors="replace").strip()
    match = _VERSION_RE.search(text)
    if completed.returncode == 0 and match:
        return True, match.group(0)
    if match:
        return True, match.group(0)
    return False, text[:200] or "the binary did not report a version"


def wait_for_api(
    api: MihomoAPI,
    *,
    timeout: float = 20.0,
    interval: float = 0.25,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Poll /version until the core answers or the timeout expires."""
    deadline = time.monotonic() + timeout
    last_error: str = "no response"
    while time.monotonic() < deadline:
        if is_cancelled and is_cancelled():
            raise ApiError("startup cancelled")
        try:
            version = api.version()
            if version:
                log.debug("core API is ready after %.1fs", timeout - (deadline - time.monotonic()))
                return version
        except ApiError as exc:
            last_error = str(exc)
            log.debug("waiting for the core API: %s", last_error)
        time.sleep(interval)
    raise ApiError(f"the core API did not become ready in time ({last_error})")


def wait_for_shutdown(
    api: MihomoAPI, *, timeout: float = 5.0, interval: float = 0.1
) -> bool:
    """Wait until the API stops answering (i.e. the core really exited)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            api.version()
        except ApiError:
            return True
        time.sleep(interval)
    return False
