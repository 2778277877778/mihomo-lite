import hashlib

import pytest

from mihomo_lite.utils.exceptions import IntegrityError
from mihomo_lite.utils.integrity import sha256_file, verify_sha256


def test_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"mihomo-lite")
    assert sha256_file(path) == hashlib.sha256(b"mihomo-lite").hexdigest()


def test_verify_accepts_match(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"ok")
    verify_sha256(path, sha256_file(path), label="test")


def test_verify_rejects_mismatch(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError) as info:
        verify_sha256(path, "0" * 64, label="test")
    assert "SHA-256" in str(info.value)
