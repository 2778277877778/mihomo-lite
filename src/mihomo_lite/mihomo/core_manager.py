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
from mihomo_lite.system.paths import PACKAGE_ROOT, AppPaths, executable_dir, is_frozen
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
        # Running '<core> -v' takes a moment (and antivirus may scan the binary),
        # so remember the last verified file for the lifetime of the process.
        self._verified: tuple[str, float, str] | None = None

    def candidates(self) -> list[tuple[Path, str]]:
        """Where a core may live, most preferred first.

        A path chosen in Settings always wins, then a core the user downloaded
        (so updates do not require reinstalling), then the bundled one.
        """
        candidates: list[tuple[Path, str]] = []
        configured = self._settings_core_path().strip()
        if configured:
            candidates.append((Path(configured), "settings"))

        candidates.append((self._paths.core / "mihomo.exe", "downloaded"))

        if is_frozen():
            candidates.append((executable_dir() / "runtime" / "mihomo.exe", "bundled"))
            candidates.append((executable_dir() / "mihomo.exe", "bundled"))
        else:
            repo_root = PACKAGE_ROOT.parents[1]
            candidates.append((repo_root / "runtime" / "mihomo.exe", "portable"))
            candidates.append(
                (repo_root / "tools" / "core" / "extracted" / "mihomo-windows-amd64.exe", "dev")
            )
        return candidates

    def locate(self) -> Path | None:
        for path, _source in self.candidates():
            if path.is_file():
                return path
        return None

    def locate_info(self) -> tuple[Path, str] | None:
        for path, source in self.candidates():
            if path.is_file():
                return path, source
        return None

    def bundled_path(self) -> Path | None:
        for path, source in self.candidates():
            if source == "bundled" and path.is_file():
                return path
        return None

    def downloaded_path(self) -> Path:
        return self._paths.core / "mihomo.exe"

    def ensure(self, *, progress: ProgressCallback | None = None) -> CoreInfo:
        found = self.locate_info()
        if found is None:
            raise CoreNotFoundError(
                "No Mihomo core is available. Reinstall the app, download a core, "
                "or point Settings at an existing mihomo.exe."
            )
        path, source = found
        version = self._verify(path)
        return CoreInfo(path=path, version=version, source=source)

    def _verify(self, path: Path) -> str:
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            raise CoreNotFoundError(f"cannot read the core at {path}: {exc}") from exc

        if self._verified is not None:
            cached_path, cached_mtime, cached_version = self._verified
            if cached_path == str(path) and cached_mtime == mtime:
                return cached_version

        ok, info = check_core_binary(path)
        if not ok:
            raise CoreNotFoundError(f"the core at {path} is not usable: {info}")
        self._verified = (str(path), mtime, info)
        return info

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
        target = self.downloaded_path()
        try:
            os.remove(target)
        except FileNotFoundError:
            pass
