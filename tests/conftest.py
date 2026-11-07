import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from mihomo_lite.system.paths import AppPaths


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHOMO_LITE_HOME", str(tmp_path))
    app_paths = AppPaths(root=tmp_path)
    app_paths.ensure()
    return app_paths


@pytest.fixture
def sample_profile():
    return {
        "mixed-port": 7890,
        "mode": "rule",
        "allow-lan": True,
        "external-controller": "0.0.0.0:9090",
        "proxies": [
            {"name": "node-a", "type": "socks5", "server": "127.0.0.1", "port": 1080},
            {"name": "node-b", "type": "http", "server": "127.0.0.1", "port": 8080},
        ],
        "proxy-groups": [
            {"name": "Proxy", "type": "select", "proxies": ["node-a", "node-b", "DIRECT"]}
        ],
        "rules": ["MATCH,Proxy"],
    }
