"""SHA-256 helpers for downloaded artefacts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from mihomo_lite.utils.exceptions import IntegrityError

_CHUNK = 1024 * 256


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str, *, label: str = "file") -> None:
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise IntegrityError(
            f"{label} failed its SHA-256 check (expected {expected[:12]}..., got {actual[:12]}...)"
        )
