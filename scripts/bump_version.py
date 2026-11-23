"""Bump the version in the three places that must always agree.

Usage: python scripts/bump_version.py 0.4.3
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    (ROOT / "src" / "mihomo_lite" / "__init__.py", r'__version__ = "([^"]+)"'),
    (ROOT / "pyproject.toml", r'^version = "([^"]+)"'),
    (ROOT / "packaging" / "installer.iss", r'#define MyAppVersion "([^"]+)"'),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", argv[1]):
        print("usage: python scripts/bump_version.py X.Y.Z")
        return 2
    version = argv[1]
    for path, pattern in TARGETS:
        text = path.read_text(encoding="utf-8")
        updated, count = re.subn(
            pattern,
            lambda match: match.group(0).replace(match.group(1), version),
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            print(f"FAILED: pattern not found in {path}")
            return 1
        path.write_text(updated, encoding="utf-8")
        print(f"updated {path.relative_to(ROOT)} -> {version}")
    print()
    print("Next: update README, RELEASE_NOTES.md, commit, tag and push.")
    print("Full checklist: docs/RELEASE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
