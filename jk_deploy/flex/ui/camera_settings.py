"""Asynchronous Qt adapter for the camera-control helper."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Property, QProcess, QTimer, Signal, Slot


class CameraSettings(QObject):
    changed = Signal()

    def __init__(self, runtime, calibration):
        super().__init__()
        self.runtime, self.calibration = runtime, calibration
        self.rows, self.index, self.message, self.failure = [], 0, "", False
        self.process = QProcess(self)
        self.process.finished.connect(self.done)
        self.process.errorOccurred.connect(self.error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    @Property(bool, notify=changed)
    def busy(self):
        return self.process.state() != QProcess.NotRunning

    @Property('QVariantList', notify=changed)
    def cameras(self):
        return self.rows

    @Property('QVariantMap', notify=changed)
    def controls(self):
        return self.rows[self.index]["controls"] if self.rows else {}

    @Property(str, notify=changed)
    def identity(self):
        if not self.rows:
            return ""
        camera = self.rows[self.index]
        return camera["entity"]+"  |  "+camera["video"]

    @Property(int, notify=changed)
    def selected(self):
        return self.index

    @Property(str, notify=changed)
    def status(self):
        return self.message

    @Property(bool, notify=changed)
    def hasError(self):
        return self.failure

    def command(self, action, *args):
        if self.busy or self.calibration.busy:
            return
        self.message, self.failure = "Reading cameras" if action == "list" else "Applying settings", False
        self.process.start(sys.executable, [str(Path(__file__).with_name("camera_controls.py")), action,
                           "--runtime", str(self.runtime), *args])
        self.timer.start(60000)
        self.changed.emit()

    @Slot()
    def refresh(self):
        self.command("list")

    @Slot(int)
    def select(self, index):
        if not self.busy and 0 <= index < len(self.rows):
            self.index = index
            self.message, self.failure = "", False
            self.changed.emit()

    @Slot(str, int, bool)
    def setControl(self, name, value, all_cameras):
        if self.rows:
            sensor = "all" if all_cameras else self.rows[self.index]["identity"]
            self.command("set", "--sensor", sensor, "--updates", json.dumps({name: value}))

    @Slot(bool)
    def defaults(self, all_cameras):
        if self.rows:
            self.command("defaults", "--sensor", "all" if all_cameras else self.rows[self.index]["identity"])

    def done(self, code, status):
        self.timer.stop()
        output = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        try:
            data = json.loads(output)
            if code or "error" in data:
                raise ValueError(data.get("error", "Camera command failed"))
            self.rows = data["cameras"]
            self.index = min(self.index, len(self.rows)-1)
            self.message, self.failure = data.get("message", ""), False
        except Exception as error:
            self.message, self.failure = str(error), True
        self.changed.emit()

    def error(self, error):
        if error == QProcess.FailedToStart:
            self.timer.stop()
            self.message, self.failure = "Could not start camera controls", True
            self.changed.emit()

    def timeout(self):
        # Terminate allows the helper's normal error path to report failure.
        self.process.terminate()
        self.message, self.failure = "Camera command timed out; refresh camera state", True
        self.changed.emit()
