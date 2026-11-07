import pytest

from mihomo_lite.mihomo import core_manager
from mihomo_lite.mihomo.core_manager import CoreManager
from mihomo_lite.utils.exceptions import CoreNotFoundError


def test_downloaded_core_wins_over_bundled(paths, monkeypatch, tmp_path):
    downloaded = paths.core / "mihomo.exe"
    downloaded.write_bytes(b"x")
    monkeypatch.setattr(core_manager, "is_frozen", lambda: True)
    monkeypatch.setattr(core_manager, "executable_dir", lambda: tmp_path)
    bundled = tmp_path / "runtime" / "mihomo.exe"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_bytes(b"y")

    manager = CoreManager(paths, lambda: "")
    assert manager.locate_info() == (downloaded, "downloaded")
    assert manager.bundled_path() == bundled

    manager.remove_installed()
    assert manager.locate_info() == (bundled, "bundled")
    assert manager.downloaded_path().exists() is False


def test_settings_path_has_priority(paths, monkeypatch, tmp_path):
    custom = tmp_path / "custom.exe"
    custom.write_bytes(b"x")
    monkeypatch.setattr(core_manager, "is_frozen", lambda: True)
    monkeypatch.setattr(core_manager, "executable_dir", lambda: tmp_path)
    bundled = tmp_path / "runtime" / "mihomo.exe"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_bytes(b"y")

    manager = CoreManager(paths, lambda: str(custom))
    assert manager.locate_info() == (custom, "settings")


def test_no_core_at_all(paths, monkeypatch, tmp_path):
    monkeypatch.setattr(core_manager, "is_frozen", lambda: True)
    monkeypatch.setattr(core_manager, "executable_dir", lambda: tmp_path)
    manager = CoreManager(paths, lambda: "")
    assert manager.locate() is None
    assert manager.bundled_path() is None
    with pytest.raises(CoreNotFoundError):
        manager.ensure()


def test_ensure_reports_the_source(paths, monkeypatch, tmp_path):
    monkeypatch.setattr(core_manager, "is_frozen", lambda: True)
    monkeypatch.setattr(core_manager, "executable_dir", lambda: tmp_path)
    bundled = tmp_path / "runtime" / "mihomo.exe"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_bytes(b"y")
    monkeypatch.setattr(core_manager, "check_core_binary", lambda path: (True, "v1.19.33"))

    info = CoreManager(paths, lambda: "").ensure()

    assert info.version == "v1.19.33"
    assert info.source == "bundled"
    assert info.path == bundled


def test_ensure_rejects_a_broken_binary(paths, monkeypatch):
    paths.core.mkdir(parents=True, exist_ok=True)
    (paths.core / "mihomo.exe").write_bytes(b"not a binary")
    monkeypatch.setattr(core_manager, "check_core_binary", lambda path: (False, "not executable"))

    with pytest.raises(CoreNotFoundError) as info:
        CoreManager(paths, lambda: "").ensure()
    assert "not usable" in str(info.value)
