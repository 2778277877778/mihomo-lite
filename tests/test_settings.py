import json

import pytest
from pydantic import ValidationError

from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.models.app_state import AppSettings, ConnectionState


def test_defaults_are_sane():
    settings = AppSettings()
    assert settings.system_proxy is True
    assert settings.mixed_port == 0
    assert settings.theme in {"dark", "light"}


def test_settings_roundtrip(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    store.update(theme="light", mixed_port=34567, system_proxy=False)

    reopened = SettingsStore(paths)
    loaded = reopened.load()
    assert loaded.theme == "light"
    assert loaded.mixed_port == 34567
    assert loaded.system_proxy is False


def test_corrupt_settings_fall_back_to_defaults(paths, qapp):
    paths.settings_file.write_text("{ broken", encoding="utf-8")
    store = SettingsStore(paths)
    assert store.load().theme == "dark"


def test_invalid_theme_is_rejected():
    with pytest.raises(ValidationError) as info:
        AppSettings(theme="neon")
    assert "theme" in str(info.value)


def test_invalid_port_is_rejected():
    with pytest.raises(ValidationError):
        AppSettings(mixed_port=70000)


def test_settings_store_rejects_bad_update(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    before = store.current.theme
    store.update(theme="neon")
    assert store.current.theme == before


def test_saved_file_is_valid_json(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    store.update(api_port=45678)
    data = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert data["api_port"] == 45678


def test_connection_state_labels():
    assert ConnectionState.STOPPED.label == "Disconnected"
    assert ConnectionState.STARTING.is_busy
    assert not ConnectionState.ERROR.is_busy
    assert ConnectionState.CONNECTED.is_running
