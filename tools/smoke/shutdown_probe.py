"""Verify that --shutdown replays the proxy journal without changing the live state."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="mihomo-shutdown-probe-")
os.environ["MIHOMO_LITE_HOME"] = HOME
sys.path.insert(0, "src")

from mihomo_lite.system.paths import AppPaths  # noqa: E402
from mihomo_lite.system.proxy import SystemProxy  # noqa: E402
from mihomo_lite.utils.fs import atomic_write_json  # noqa: E402

paths = AppPaths(Path(HOME))
paths.ensure()
proxy = SystemProxy(paths.proxy_journal)
before = proxy.read()
atomic_write_json(
    paths.proxy_journal,
    {"pid": 999999, "created_at": 0.0, "snapshot": before.to_dict()},
)
print("journal written, live state:", before.server or "(direct)")

env = dict(os.environ, MIHOMO_LITE_HOME=HOME)
completed = subprocess.run(
    [sys.executable, "-m", "mihomo_lite", "--shutdown"],
    env=env,
    capture_output=True,
    text=True,
    timeout=40,
)
after = proxy.read()
print("shutdown exit:", completed.returncode)
print("journal removed:", not paths.proxy_journal.exists())
print("state unchanged:", before == after)
print("stderr:", completed.stderr.strip()[:300])
