#!/usr/bin/env python3
"""Transparent on-device Qt calibration controls for the wide Flex display."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid

from PySide6.QtCore import QObject, Property, QProcess, QTimer, Signal, Slot, Qt, QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from camera_settings import CameraSettings
from preview import Preview
from capture_recovery import saved_capture_source

HERE = Path(__file__).resolve().parent
SURFACE, LAYER = 19001, 102


class Backend(QObject):
    changed = Signal()
    finished = Signal()

    def __init__(self, args):
        super().__init__()
        self.args = args
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.finished.connect(self.done)
        self.process.errorOccurred.connect(self.error)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.job = None
        self.retry_source = None
        self.continue_requested = False
        self.cancel_requested = False
        self.data = {"state": "idle", "phase": "Ready", "elapsed_seconds": 0}
        self.restore_status()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(300)

    @Property(bool, notify=changed)
    def busy(self):
        return self.process.state() != QProcess.NotRunning

    @Property(str, notify=changed)
    def phase(self):
        return self.data.get("phase", "Ready")

    @Property(str, notify=changed)
    def detail(self):
        if self.data.get('persistence_restore_error'):
            return 'Boot calibration could not be restored. Storage needs attention; do not power off.'
        if self.state == "complete" and self.data.get("warning"):
            return self.data["warning"]
        reason = self.data.get("reason", "")
        if self.data.get("restore_error"):
            return "Preview restore failed. "+self.data["restore_error"]
        if 'ufunc' in reason or 'Traceback' in reason:
            return 'Calibration processing failed. Saved captures are retained; the previous calibration is still selected.'
        return (reason.splitlines()[-1] if reason else "")[:400]

    def refresh_retry(self):
        self.retry_source = None
        if self.job and self.state in ('failed', 'cancelled'):
            try:
                saved_capture_source(self.job)
                self.retry_source = self.job
            except (OSError, ValueError, TypeError, KeyError):
                pass

    def restore_status(self):
        jobs = getattr(self.args, 'jobs', None)
        if jobs is None:
            return
        try:
            latest = sorted(jobs.glob('*/status.json'))[-1]
            self.job = latest.parent
            self.data = json.loads(latest.read_text())
            if not isinstance(self.data, dict):
                raise ValueError('Invalid status')
            self.reconcile_status()
        except IndexError:
            return
        except (OSError, ValueError):
            self.data = dict(state='failed', phase='Saved calibration status unavailable',
                             reason='Start a new CAL with all four green markers installed.')
        self.refresh_retry()

    def reconcile_status(self):
        try:
            active = json.loads((self.args.runtime/'active_table_calibration.json').read_text())
            if active.get('job') == str(self.job) and not self.data.get('persistence_restore_error'):
                self.data.update(state='complete', phase='Calibration applied', waiting_action=None)
        except (OSError, ValueError, AttributeError):
            pass
        if self.data.get('state') == 'running':
            self.data.update(state='failed', phase='Calibration interrupted', waiting_action=None,
                             reason='Retry saved captures if the setup has not moved, or start a new CAL.')

    @Property(bool, notify=changed)
    def canRetry(self):
        return not self.busy and self.retry_source is not None

    @Property(str, notify=changed)
    def elapsed(self):
        seconds = int(self.data.get("elapsed_seconds", 0))
        return f"{seconds//60:02d}:{seconds%60:02d}"

    @Property(str, notify=changed)
    def state(self):
        return self.data.get("state", "idle")

    @Property(bool, notify=changed)
    def hasWarning(self):
        return self.state == "complete" and bool(self.data.get("warning"))

    @Property(bool, notify=changed)
    def waitingForRemoval(self):
        return self.busy and self.data.get("waiting_action") == "remove_corners" and not self.continue_requested

    @Slot()
    def continueCapture(self):
        if not self.waitingForRemoval or self.job is None:
            return
        try:
            temporary = self.job/"corners_removed.tmp"
            temporary.write_text(json.dumps({"action": "corners_removed"})+"\n")
            temporary.replace(self.job/"corners_removed.json")
        except OSError as error:
            self.data["reason"] = f"Could not continue: {error}"
        else:
            self.continue_requested = True
        self.changed.emit()

    @Slot()
    def start(self):
        self.launch()

    @Slot()
    def retry(self):
        if not self.canRetry:
            return
        source = self.retry_source
        try:
            saved_capture_source(source)
        except (OSError, ValueError, TypeError, KeyError):
            self.retry_source = None
            self.data['reason'] = 'Saved captures are incomplete. Start a new CAL with the green markers installed.'
            self.changed.emit()
            return
        self.launch(source)

    def launch(self, reuse=None):
        if self.busy:
            return
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:6]
        self.job = self.args.jobs/name
        self.continue_requested = False
        self.cancel_requested = False
        self.retry_source = None
        self.data = {"state": "running", "phase": "Preparing", "elapsed_seconds": 0}
        arguments = [str(HERE/"calibration_worker.py"), str(self.job),
                     "--runtime", str(self.args.runtime), "--support", str(self.args.support)]
        if reuse is not None:
            arguments.extend(['--reuse', str(reuse)])
        self.process.start(sys.executable, arguments)
        print(f"CAL confirmed: {self.job}", flush=True)
        self.changed.emit()

    @Slot()
    def cancel(self):
        if self.busy and not self.cancel_requested:
            self.cancel_requested = True
            self.continue_requested = True
            self.data["phase"] = "Cancelling; restoring preview"
            self.changed.emit()
            self.process.terminate()

    @Slot()
    def dismiss(self):
        if not self.busy:
            self.data = {"state": "idle", "phase": "Ready", "elapsed_seconds": 0}
            self.retry_source = None
            self.changed.emit()

    def poll(self):
        if self.job and self.busy:
            try:
                data = json.loads((self.job/"status.json").read_text())
                if isinstance(data, dict):
                    self.data = data
            except (OSError, ValueError):
                pass
            self.changed.emit()

    def read_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if text.strip():
            print(text, end="", flush=True)

    def done(self, code, exit_status):
        if self.job:
            try:
                self.data = json.loads((self.job/"status.json").read_text())
                if not isinstance(self.data, dict):
                    raise ValueError('Invalid status')
            except (OSError, ValueError):
                self.data = dict(state="failed", phase="Calibration did not finish", reason=f"Worker exit {code}; start a new CAL.")
        self.reconcile_status()
        self.refresh_retry()
        self.changed.emit()
        self.finished.emit()

    def error(self, error):
        if error == QProcess.FailedToStart:
            self.data.update(state="failed", phase="Could not start calibration")
            self.changed.emit()
            self.finished.emit()


def layer_command(*args):
    result = subprocess.run(["LayerManagerControl", *map(str, args)], text=True,
                            capture_output=True, timeout=3)
    if result.returncode or "Interpreter error" in result.stdout:
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout


def install_surface():
    # Ahsoka owns the screen's layer list. Its overlay layer survives renderer restarts.
    info = layer_command("get", "layer", LAYER)
    if "on screen:            0(" not in info:
        raise RuntimeError("Expected Ahsoka overlay layer 102 on screen 0")
    match = re.search(r"surface render order:\s*([^\n]*)", info)
    order = re.findall(r"(\d+)\(0x", match.group(1) if match else "")
    order = [n for n in order if int(n) != SURFACE]
    layer_command("add", "surface", SURFACE, "to", "layer", LAYER)
    layer_command("set", "surface", SURFACE, "source", "region", 0, 0, 1920, 720)
    layer_command("set", "surface", SURFACE, "destination", "region", 0, 0, 1920, 720)
    layer_command("set", "layer", LAYER, "render", "order", *order, SURFACE)
    layer_command("remove", "surface", SURFACE, "from", "layer", 101)
    layer_command("set", "surface", SURFACE, "visibility", 1)
    layer_command("set", "layer", LAYER, "visibility", 1)
    print("CAL overlay on compositor screen 0 / DSI-1", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("/opt/jk-ti-srv-flex"))
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, default=Path("/root/jk-calibration-jobs"))
    args = parser.parse_args()
    args.jobs.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication(sys.argv)
    app.setApplicationName("jk-calibration-ui")
    backend = Backend(args)
    camera_settings = CameraSettings(args.runtime, backend)
    preview = Preview()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("calibration", backend)
    engine.rootContext().setContextProperty("cameraSettings", camera_settings)
    engine.rootContext().setContextProperty("preview", preview)
    engine.load(str(HERE/"Calibration.qml"))
    if not engine.rootObjects():
        sys.exit(1)
    window = engine.rootObjects()[0]
    attempts = 0
    timer = QTimer()
    def arrange():
        nonlocal attempts
        attempts += 1
        try:
            info = layer_command("get", "surface", SURFACE)
            if "original size" not in info:
                raise RuntimeError("Waiting for surface")
            install_surface()
            timer.stop()
        except Exception as error:
            if attempts >= 30:
                print(f"CAL overlay placement failed: {error}", flush=True)
                app.exit(1)
    timer.timeout.connect(arrange)
    timer.start(300)
    # Root-only local test socket exercises actual Qt hit-testing and confirmation.
    server = QLocalServer()
    socket = "/run/jk-calibration-ui.sock"
    QLocalServer.removeServer(socket)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    server.listen(socket)
    def connection():
        peer = server.nextPendingConnection()
        def request():
            if not peer.canReadLine():
                return
            try:
                data = json.loads(bytes(peer.readLine()))
                if data.get("action") == "tap":
                    x, y = int(data["x"]), int(data["y"])
                    if not 0 <= x < 1920 or not 0 <= y < 720:
                        raise ValueError("Outside screen")
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))
                result = dict(backend.data, busy=backend.busy, job=str(backend.job or ""),
                              confirmation=window.property("confirmationVisible"),
                              menu=window.property("toolsVisible"), settings=window.property("settingsVisible"),
                              camera_busy=camera_settings.busy, camera_error=camera_settings.hasError,
                              camera_status=camera_settings.status, selected_camera=camera_settings.selected,
                              preview_camera=preview.selected, preview_error=preview.error)
                result["removal_prompt"] = window.property("removalVisible")
                result['can_retry'] = backend.canRetry
                result['retry_prompt'] = window.property('retryVisible')
                peer.write((json.dumps(result)+"\n").encode())
            except Exception as error:
                peer.write((json.dumps({"error": str(error)})+"\n").encode())
            peer.flush()
            peer.disconnectFromServer()
        peer.readyRead.connect(request)
    server.newConnection.connect(connection)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    code = app.exec()
    preview.set_selection(-1)
    if camera_settings.busy:
        camera_settings.process.terminate()
        camera_settings.process.waitForFinished(30000)
    if backend.busy:
        backend.process.terminate()
        backend.process.waitForFinished(80000)
    try:
        layer_command("remove", "surface", SURFACE, "from", "layer", LAYER)
    except Exception:
        pass
    sys.exit(code)


if __name__ == "__main__":
    main()
