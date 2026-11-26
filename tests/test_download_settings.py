"""Settings for the optional download features."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.models.app_state import AppSettings


def test_download_defaults_are_off():
    settings = AppSettings()
    assert settings.download_multithreaded is False
    assert settings.download_multi_node is False
    assert settings.download_threads == 0
    assert settings.download_nodes == []


def test_multi_node_requires_multithread():
    settings = AppSettings(download_multithreaded=False, download_multi_node=True)
    assert settings.download_multi_node is False

    settings = AppSettings(download_multithreaded=True, download_multi_node=True)
    assert settings.download_multi_node is True


def test_turning_multithread_off_turns_multi_node_off():
    settings = AppSettings(download_multithreaded=True, download_multi_node=True)
    settings.download_multithreaded = False
    assert settings.download_multi_node is False


def test_thread_count_validation():
    AppSettings(download_threads=0)
    AppSettings(download_threads=4)
    AppSettings(download_threads=16)
    with pytest.raises(ValidationError):
        AppSettings(download_threads=3)
    with pytest.raises(ValidationError):
        AppSettings(download_threads=17)


def test_download_settings_roundtrip(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    store.update(
        download_multithreaded=True,
        download_multi_node=True,
        download_threads=8,
        download_nodes=["p1::node-a", "p2::node-b"],
    )

    reopened = SettingsStore(paths)
    loaded = reopened.load()
    assert loaded.download_multithreaded is True
    assert loaded.download_multi_node is True
    assert loaded.download_threads == 8
    assert loaded.download_nodes == ["p1::node-a", "p2::node-b"]


def test_store_enforces_dependency(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    updated = store.update(download_multi_node=True)
    assert updated.download_multi_node is False
    assert updated.download_multithreaded is False
