"""Application data locations and resource resolution.

Everything the app writes lives under one directory so that uninstalling is a
single folder removal and so that tests can redirect it with the environment
variable MIHOMO_LITE_HOME.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "MihomoLite"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    """Directory that contains the running executable (or repo root in dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return PACKAGE_ROOT


def data_dir() -> Path:
    override = os.environ.get("MIHOMO_LITE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def profiles(self) -> Path:
        return self.root / "profiles"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def core(self) -> Path:
        return self.root / "core"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def profiles_index(self) -> Path:
        return self.profiles / "index.json"

    @property
    def runtime_config(self) -> Path:
        return self.runtime / "generated.yaml"

    @property
    def runtime_log(self) -> Path:
        return self.runtime / "mihomo.log"

    @property
    def proxy_journal(self) -> Path:
        return self.root / "proxy.journal.json"

    @property
    def session_file(self) -> Path:
        return self.runtime / "session.json"

    @property
    def instance_lock(self) -> Path:
        return self.root / "instance.lock"

    def ensure(self) -> None:
        for directory in (self.root, self.profiles, self.runtime, self.logs, self.core):
            directory.mkdir(parents=True, exist_ok=True)

    def core_candidates(self) -> list[Path]:
        """Where a Mihomo binary may live, most preferred first."""
        candidates = [self.core / "mihomo.exe"]
        if is_frozen():
            candidates.append(executable_dir() / "mihomo.exe")
            candidates.append(executable_dir() / "runtime" / "mihomo.exe")
        else:
            candidates.append(executable_dir().parent / "runtime" / "mihomo.exe")
            candidates.append(executable_dir().parent.parent / "runtime" / "mihomo.exe")
        return candidates


def app_paths() -> AppPaths:
    paths = AppPaths(root=data_dir())
    paths.ensure()
    return paths


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource such as resources/styles/app.qss."""
    return PACKAGE_ROOT.joinpath(*parts)


def bundled_resource_dir() -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return PACKAGE_ROOT
