"""Prove the CoreManager finds the core inside the built package layout."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mihomo_lite.mihomo import core_manager  # noqa: E402
from mihomo_lite.mihomo.core_manager import CoreManager  # noqa: E402
from mihomo_lite.system.paths import AppPaths  # noqa: E402

DIST = ROOT / "dist" / "MihomoLite"
core_manager.is_frozen = lambda: True
core_manager.executable_dir = lambda: DIST

paths = AppPaths(root=ROOT / "tools" / "smoke" / "bundled-home")
paths.ensure()
manager = CoreManager(paths, lambda: "")

found = manager.locate_info()
print("locate_info:", found)
info = manager.ensure()
print("ensure:", info.version, "|", info.source)
print("bundled_path:", manager.bundled_path())
assert info.source == "bundled", info.source
assert str(info.path).startswith(str(DIST))
print("OK: the packaged core is discovered as 'bundled'")
