"""Build the Windows onedir package (and optionally the installer).

Usage:
    python scripts/build_windows.py
    python scripts/build_windows.py --installer
    python scripts/build_windows.py --clean-only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "mihomo-lite.spec"
DIST = ROOT / "dist" / "MihomoLite"
OUTPUT = ROOT / "packaging" / "output"


def _run(command: list[str], *, cwd: Path = ROOT) -> int:
    print("+", " ".join(command))
    return subprocess.call(command, cwd=cwd)


def clean() -> None:
    for path in (ROOT / "build", ROOT / "dist"):
        if path.exists():
            print(f"removing {path}")
            shutil.rmtree(path, ignore_errors=True)


def build() -> Path:
    if _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)]) != 0:
        raise SystemExit("PyInstaller failed")

    if not DIST.exists():
        raise SystemExit(f"expected output at {DIST}")

    for name in ("README.md", "LICENSE"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, DIST / name)

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
    return shutil.which("ISCC.exe") and Path(shutil.which("ISCC.exe"))


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
    parser.add_argument("--clean-only", action="store_true", help="remove build artefacts and exit")
    parser.add_argument("--no-clean", action="store_true", help="keep the previous build directory")
    args = parser.parse_args()

    if args.clean_only:
        clean()
        return 0
    if not args.no_clean:
        clean()

    build()
    if args.installer:
        build_installer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
