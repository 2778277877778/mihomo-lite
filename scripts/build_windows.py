"""Build the Windows onedir package (and optionally the installer).

The Mihomo core is bundled into the package so a fresh install works offline.
It is never committed to git: the script uses a local copy under tools/core
when present, otherwise it downloads the pinned upstream release.

Usage:
    python scripts/build_windows.py
    python scripts/build_windows.py --installer
    python scripts/build_windows.py --no-core        # do not bundle the core
    python scripts/build_windows.py --clean-only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "mihomo-lite.spec"
DIST = ROOT / "dist" / "MihomoLite"
OUTPUT = ROOT / "packaging" / "output"
CORE_CACHE = ROOT / "tools" / "core"

sys.path.insert(0, str(ROOT / "src"))

from mihomo_lite.config.defaults import (  # noqa: E402
    CORE_ASSET_NAME,
    CORE_DOWNLOAD_URL,
    CORE_RELEASE_TAG,
)


def _run(command: list[str], *, cwd: Path = ROOT) -> int:
    print("+", " ".join(command))
    return subprocess.call(command, cwd=cwd)


def clean() -> None:
    for path in (ROOT / "build", ROOT / "dist"):
        if path.exists():
            print(f"removing {path}")
            shutil.rmtree(path, ignore_errors=True)


def _core_version(binary: Path) -> str:
    completed = subprocess.run(
        [str(binary), "-v"], capture_output=True, timeout=30, check=False
    )
    text = (completed.stdout or b"").decode("utf-8", "replace").strip()
    return text.splitlines()[0] if text else "unknown"


def ensure_local_core() -> Path:
    """Return a usable core binary, downloading the pinned release if needed."""
    extracted = CORE_CACHE / "extracted" / CORE_ASSET_NAME
    if extracted.exists():
        return extracted

    CORE_CACHE.mkdir(parents=True, exist_ok=True)
    archive = CORE_CACHE / "mihomo.zip"
    if not archive.exists():
        print(f"downloading {CORE_DOWNLOAD_URL}")
        urllib.request.urlretrieve(CORE_DOWNLOAD_URL, archive)  # noqa: S310 - pinned https URL

    with zipfile.ZipFile(archive) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".exe")]
        if not members:
            raise SystemExit("the core archive does not contain an executable")
        member = next((n for n in members if Path(n).name == CORE_ASSET_NAME), members[0])
        extracted.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, extracted.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 256)
    extracted.chmod(0o755)
    return extracted


def bundle_core(target: Path) -> Path:
    binary = ensure_local_core()
    version = _core_version(binary)
    if CORE_RELEASE_TAG not in version:
        print(f"WARNING: local core reports '{version}', expected {CORE_RELEASE_TAG}")
    destination = target / "runtime" / "mihomo.exe"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, destination)
    print(f"bundled core {version} -> {destination}")
    return destination


def copy_licenses(target: Path) -> None:
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)
    licenses = ROOT / "licenses"
    if licenses.exists():
        shutil.copytree(licenses, target / "licenses", dirs_exist_ok=True)


def build(*, with_core: bool = True) -> Path:
    if _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)]) != 0:
        raise SystemExit("PyInstaller failed")

    if not DIST.exists():
        raise SystemExit(f"expected output at {DIST}")

    copy_licenses(DIST)
    if with_core:
        bundle_core(DIST)

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"package: {DIST} ({total / 1024 / 1024:.1f} MB)")
    return DIST


def find_iscc() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = shutil.which("ISCC.exe")
    return Path(found) if found else None


def build_installer() -> Path:
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit("Inno Setup 6 was not found; install it or skip --installer")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if _run([str(iscc), str(ROOT / "packaging" / "installer.iss")]) != 0:
        raise SystemExit("ISCC failed")
    installers = sorted(OUTPUT.glob("*.exe"), key=lambda p: p.stat().st_mtime)
    if not installers:
        raise SystemExit("no installer was produced")
    print(f"installer: {installers[-1]}")
    return installers[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Mihomo Lite for Windows")
    parser.add_argument("--installer", action="store_true", help="also build the Inno Setup installer")
    parser.add_argument("--no-core", action="store_true", help="do not bundle the Mihomo core")
    parser.add_argument("--clean-only", action="store_true", help="remove build artefacts and exit")
    parser.add_argument("--no-clean", action="store_true", help="keep the previous build directory")
    args = parser.parse_args()

    if args.clean_only:
        clean()
        return 0
    if not args.no_clean:
        clean()

    build(with_core=not args.no_core)
    if args.installer:
        build_installer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
