import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from mihomo_lite.mihomo.process import MihomoProcess
from mihomo_lite.mihomo.core_manager import CoreManager
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.core.state_manager import SettingsStore

qt = QApplication([])
tmp = Path(tempfile.mkdtemp())
paths = AppPaths(tmp)
paths.ensure()
settings = SettingsStore(paths)
core = CoreManager(paths, lambda: "")
print("locate ->", ROOT / "tools" / "core" / "extracted" / "mihomo-windows-amd64.exe")
info = core.install_from_file(ROOT / "tools" / "core" / "extracted" / "mihomo-windows-amd64.exe")
print("core info:", info)

cfg = tmp / "runtime" / "generated.yaml"
cfg.parent.mkdir(parents=True, exist_ok=True)
cfg.write_text(
    "mixed-port: 17891\nexternal-controller: 127.0.0.1:19091\nsecret: abc\n"
    "mode: rule\nproxies: []\nrules:\n  - MATCH,DIRECT\n",
    encoding="utf-8",
)
proc = MihomoProcess()
proc.started.connect(lambda pid: print("started pid", pid))
proc.stopped.connect(lambda code, crashed: print("stopped", code, crashed))
proc.failed.connect(lambda m: print("failed", m))
proc.output.connect(lambda line: print("out:", line[:100]))

ok = proc.start(info.path, cfg, cfg.parent)
print("start() returned", ok, "running:", proc.running)
end = time.monotonic() + 5
while time.monotonic() < end:
    qt.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.05)
print("after 5s running:", proc.running, "pid:", proc.pid)
proc.kill_now()
