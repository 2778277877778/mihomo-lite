import os, sys, threading, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, "src")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop
from mihomo_lite.utils.tasks import TaskRunner

app = QApplication([])
runner = TaskRunner()
main_id = threading.get_ident()
seen = []

def work():
    time.sleep(0.2)
    return "result"

def done(value):
    seen.append(("callback", threading.get_ident(), value))

runner.submit(work, on_success=done)

deadline = time.time() + 5
while time.time() < deadline and not seen:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.02)

print("main thread:", main_id)
print("seen:", seen)
print("same thread:", bool(seen) and seen[0][1] == main_id)
