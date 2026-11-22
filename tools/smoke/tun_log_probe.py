"""Check which log lines Mihomo emits when TUN cannot start (non-admin, no wintun)."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "src")
from mihomo_lite.system.elevation import is_admin

CORE = Path("dist/MihomoLite/runtime/mihomo.exe")
if not CORE.exists():
    CORE = Path("tools/core/extracted/mihomo-windows-amd64.exe")

print("admin:", is_admin())
if is_admin():
    print("skipped: elevated, refusing to create a TUN adapter in this test")
    raise SystemExit(0)

tmp = Path(tempfile.mkdtemp())
config = tmp / "config.yaml"
config.write_text(
    "mixed-port: 17891\nexternal-controller: 127.0.0.1:19091\nsecret: abc\n"
    "mode: rule\nlog-level: info\nproxies: []\nrules:\n  - MATCH,DIRECT\n"
    "tun:\n  enable: true\n  stack: mixed\n  auto-route: true\n  auto-detect-interface: true\n"
    "  device: MihomoLiteTest\n",
    encoding="utf-8",
)
proc = subprocess.Popen(
    [str(CORE), "-d", str(tmp), "-f", str(config)],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
)
time.sleep(4)
proc.terminate()
try:
    out, _ = proc.communicate(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    out, _ = proc.communicate()

lines = [line for line in out.splitlines() if "tun" in line.lower() or "wintun" in line.lower()]
print(json.dumps(lines, indent=1, ensure_ascii=False))
