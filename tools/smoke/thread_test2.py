import os, sys, threading, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, "src")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop
from mihomo_lite.utils.tasks import TaskRunner

app = QApplication([])
runner = TaskRunner()
seen = []

class Receiver:
    def method(self, value):
        seen.append(("method", threading.get_ident(), value))

recv = Receiver()
runner.submit(lambda: {"v": 1}, on_success=lambda v: seen.append(("lambda", threading.get_ident(), v)))
runner.submit(lambda: {"v": 2}, on_success=recv.method)
runner.submit(lambda: 42, on_success=print)

deadline = time.time() + 6
while time.time() < deadline and len(seen) < 2:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.02)
print("main:", threading.get_ident())
print("seen:", seen)
