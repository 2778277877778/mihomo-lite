import pytest

from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.models.profile import ProfileKind
from mihomo_lite.utils.exceptions import ConfigError

VALID = """
proxies:
  - name: a
    type: socks5
    server: 127.0.0.1
    port: 1
rules:
  - MATCH,DIRECT
"""

INVALID = """
proxies:
  - name: a
    type: socks5
    server: 127.0.0.1
    port: 1
  - name: a
    type: http
    server: 127.0.0.1
    port: 2
rules:
  - MATCH,DIRECT
"""


@pytest.fixture
def manager(paths, qapp):
    return ProfileManager(paths)


def test_import_file_stores_the_original(manager, paths, tmp_path):
    source = tmp_path / "my-profile.yaml"
    source.write_text(VALID, encoding="utf-8")

    profile = manager.import_file(source, name="Home")

    assert profile.name == "Home"
    assert profile.kind is ProfileKind.LOCAL
    assert profile.proxy_count == 1
    assert profile.rule_count == 1
    assert manager.profile_path(profile.id).read_text(encoding="utf-8") == VALID
    assert manager.active_id == profile.id


def test_invalid_profile_is_rejected_without_side_effects(manager, paths, tmp_path):
    source = tmp_path / "bad.yaml"
    source.write_text(INVALID, encoding="utf-8")

    with pytest.raises(ConfigError):
        manager.import_file(source)

    assert manager.profiles == []
    assert not any(paths.profiles.glob("*/original.yaml"))


def test_missing_file_is_reported(manager, tmp_path):
    with pytest.raises(ConfigError):
        manager.import_file(tmp_path / "nope.yaml")


def test_wrong_extension_is_rejected(manager, tmp_path):
    source = tmp_path / "profile.txt"
    source.write_text(VALID, encoding="utf-8")
    with pytest.raises(ConfigError):
        manager.import_file(source)


def test_index_survives_a_restart(manager, paths):
    source = paths.root / "p.yaml"
    source.write_text(VALID, encoding="utf-8")
    profile = manager.import_file(source, name="Persisted")

    reopened = ProfileManager(paths)
    assert [p.id for p in reopened.profiles] == [profile.id]
    assert reopened.active_id == profile.id


def test_subscription_refresh_backs_up_the_previous_file(manager, paths):
    source = paths.root / "sub.yaml"
    source.write_text(VALID, encoding="utf-8")
    profile = manager.import_text(
        VALID, name="Sub", kind=ProfileKind.SUBSCRIPTION, url="https://example.test/sub"
    )

    updated = VALID.replace("port: 1", "port: 2")
    manager.refresh(profile.id, fetcher=lambda url: updated)

    original = manager.profile_path(profile.id).read_text(encoding="utf-8")
    previous = manager.previous_path(profile.id).read_text(encoding="utf-8")
    assert "port: 2" in original
    assert previous == VALID


def test_refresh_keeps_the_old_file_when_the_new_one_is_invalid(manager, paths):
    profile = manager.import_text(
        VALID, name="Sub", kind=ProfileKind.SUBSCRIPTION, url="https://example.test/sub"
    )

    with pytest.raises(ConfigError):
        manager.refresh(profile.id, fetcher=lambda url: INVALID)

    assert manager.profile_path(profile.id).read_text(encoding="utf-8") == VALID
    assert not manager.previous_path(profile.id).exists()


def test_refresh_rejects_local_profiles(manager, paths):
    source = paths.root / "local.yaml"
    source.write_text(VALID, encoding="utf-8")
    profile = manager.import_file(source)
    with pytest.raises(ConfigError):
        manager.refresh(profile.id)


def test_delete_removes_files_and_reassigns_active(manager, paths):
    source = paths.root / "p.yaml"
    source.write_text(VALID, encoding="utf-8")
    first = manager.import_file(source, name="One")
    second = manager.import_file(source, name="Two")
    manager.set_active(first.id)

    manager.delete(second.id)
    assert manager.get(second.id) is None
    assert not manager.profile_dir(second.id).exists()

    manager.delete(first.id)
    assert manager.profiles == []
    assert manager.active_id == ""


def test_validate_active_reports_missing_selection(manager):
    ok, message = manager.validate_active()
    assert not ok
    assert "no profile" in message.lower()
