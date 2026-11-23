import sys
import traceback
from pathlib import Path

sys.path.insert(0, "src")
from mihomo_lite.system import wintun

target = Path("runtime/mihomo.exe")
print("core exists:", target.exists())
try:
    path = wintun.install(target)
    print("installed:", path, path.stat().st_size)
except Exception as exc:
    print("FAILED:", type(exc).__name__, exc)
    traceback.print_exc(limit=1)
