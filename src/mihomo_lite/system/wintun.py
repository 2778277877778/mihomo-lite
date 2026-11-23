"""Locate or install wintun.dll, which the Mihomo core needs for TUN mode.

Wintun is an independent project (https://www.wintun.net, GPL-2.0) and is not
shipped with Mihomo Lite; the user installs it on demand, exactly like the core.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx

from mihomo_lite.utils.exceptions import MihomoLiteError

log = logging.getLogger(__name__)

WINTUN_VERSION = "0.14.1"
WINTUN_URL = f"https://www.wintun.net/builds/wintun-{WINTUN_VERSION}.zip"
WINTUN_MEMBER = "bin/amd64/wintun.dll"
MIN_DLL_BYTES = 64 * 1024

ProgressCallback = Callable[[int, int], None]


class WintunError(MihomoLiteError):
    """wintun.dll is missing or could not be installed."""


def system32_wintun() -> Path:
    root = os.environ.get("SYSTEMROOT", "C:/Windows")
    return Path(root) / "System32" / "wintun.dll"


def locate(core_path: Path) -> Path | None:
    """Find a usable wintun.dll near the core or in the system directory."""
    for candidate in (Path(core_path).parent / "wintun.dll", system32_wintun()):
        try:
            if candidate.is_file() and candidate.stat().st_size >= MIN_DLL_BYTES:
                return candidate
        except OSError:
            continue
    return None


def install(core_path: Path, *, progress: ProgressCallback | None = None) -> Path:
    """Download the official build and place wintun.dll next to the core."""
    if not sys.platform == "win32":
        raise WintunError("wintun can only be installed on Windows")

    target = Path(core_path).parent / "wintun.dll"
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mihomo-lite-wintun-") as tmp:
        archive = Path(tmp) / "wintun.zip"
        try:
            with httpx.Client(
                follow_redirects=True, timeout=60.0
            ) as client, client.stream("GET", WINTUN_URL) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0) or 0)
                done = 0
                with archive.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1024 * 64):
                        handle.write(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)
        except httpx.HTTPError as exc:
            raise WintunError(f"download failed: {exc}") from exc

        try:
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                member = next(
                    (
                        name
                        for name in names
                        if name.replace("\\", "/").lower().endswith("amd64/wintun.dll")
                    ),
                    None,
                ) or next(
                    (
                        name
                        for name in names
                        if name.replace("\\", "/").lower().endswith("wintun.dll")
                    ),
                    None,
                )
                if member is None:
                    raise WintunError("the archive does not contain an amd64 wintun.dll")
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 64)
        except zipfile.BadZipFile as exc:
            raise WintunError("the downloaded archive is corrupt") from exc

    try:
        size = target.stat().st_size
    except OSError as exc:
        raise WintunError(f"cannot read the installed wintun.dll: {exc}") from exc
    if size < MIN_DLL_BYTES:
        target.unlink(missing_ok=True)
        raise WintunError("the downloaded wintun.dll looks truncated")

    log.info("installed wintun %s at %s", WINTUN_VERSION, target)
    return target
