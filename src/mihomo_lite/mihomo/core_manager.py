"""Locate, verify, install and (optionally) download the Mihomo core.

The application deliberately does not ship the core binary. It uses a local
copy when the user already has one, otherwise the user explicitly triggers a
download from the upstream GitHub release.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from mihomo_lite.config.defaults import CORE_ASSET_NAME, CORE_DOWNLOAD_URL
from mihomo_lite.mihomo.health import check_core_binary
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.utils.exceptions import CoreDownloadError, CoreNotFoundError

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class CoreInfo:
    path: Path
    version: str
    source: str


class CoreManager:
    def __init__(self, paths: AppPaths, settings_core_path: Callable[[], str]) -> None:
        self._paths = paths
        self._settings_core_path = settings_core_path

    def candidates(self) -> list[tuple[Path, str]]:
        candidates: list[tuple[Path, str]] = []
        configured = self._settings_core_path().strip()
        if configured:
            candidates.append((Path(configured), "settings"))
        for path in self._paths.core_candidates():
            candidates.append((path, "portable" if path.parent != self._paths.core else "app data"))
        return candidates

    def locate(self) -> Path | None:
        for path, _source in self.candidates():
            if path.is_file():
                return path
        return None

    def ensure(self, *, progress: ProgressCallback | None = None) -> CoreInfo:
        path = self.locate()
        if path is None:
            raise CoreNotFoundError(
                "No Mihomo core was found. Download it first, or point Settings at an existing mihomo.exe."
            )
        ok, info = check_core_binary(path)
        if not ok:
            raise CoreNotFoundError(f"the core at {path} is not usable: {info}")
        return CoreInfo(path=path, version=info, source="local")

    def install_from_file(self, source: Path) -> CoreInfo:
        source = Path(source)
        if source.suffix.lower() not in (".exe", ""):
            raise CoreNotFoundError("please select the mihomo executable (mihomo.exe)")
        ok, info = check_core_binary(source)
        if not ok:
            raise CoreNotFoundError(f"that file is not a working Mihomo core: {info}")
        target = self._paths.core / "mihomo.exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        log.info("installed core %s from %s", info, source)
        return CoreInfo(path=target, version=info, source="manual")

    def download(self, *, progress: ProgressCallback | None = None) -> CoreInfo:
        target = self._paths.core / "mihomo.exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading core from %s", CORE_DOWNLOAD_URL)

        with tempfile.TemporaryDirectory(prefix="mihomo-lite-core-") as tmp:
            archive = Path(tmp) / "core.zip"
            try:
                self._download_archive(archive, progress)
            except httpx.HTTPError as exc:
                raise CoreDownloadError(f"download failed: {exc}") from exc

            try:
                with zipfile.ZipFile(archive) as zf:
                    names = [n for n in zf.namelist() if n.lower().endswith(".exe")]
                    if not names:
                        raise CoreDownloadError("the archive does not contain a Windows executable")
                    member = next(
                        (n for n in names if Path(n).name.lower() == CORE_ASSET_NAME),
                        names[0],
                    )
                    with zf.open(member) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 256)
            except zipfile.BadZipFile as exc:
                raise CoreDownloadError("the downloaded archive is corrupt") from exc

        ok, info = check_core_binary(target)
        if not ok:
            target.unlink(missing_ok=True)
            raise CoreDownloadError(f"the downloaded core does not run: {info}")

        log.info("core %s installed at %s", info, target)
        return CoreInfo(path=target, version=info, source="download")

    @staticmethod
    def _download_archive(archive: Path, progress: ProgressCallback | None) -> None:
        with httpx.Client(
            follow_redirects=True, timeout=60.0, trust_env=True
        ) as client, client.stream("GET", CORE_DOWNLOAD_URL) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0) or 0)
            done = 0
            with archive.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 128):
                    handle.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)

    def remove_installed(self) -> None:
        target = self._paths.core / "mihomo.exe"
        try:
            os.remove(target)
        except FileNotFoundError:
            pass
