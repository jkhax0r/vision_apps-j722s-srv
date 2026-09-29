#!/usr/bin/env python3
"""Boot the existing Flex runtime without interrupting a CAL or waiting on network."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from stage_table import validate_candidate


def select_launcher(runtime):
    metadata = runtime/"active_table_calibration.json"
    if metadata.exists():
        launcher = Path(json.loads(metadata.read_text())["launcher"]).resolve()
        if not launcher.is_relative_to(runtime.resolve()) or launcher.name != "run.sh":
            raise ValueError("Active calibration launcher is outside the private runtime")
        validate_candidate(launcher.parent)
    else:
        launcher = runtime/"run_flex_markers.sh"
        for name in ("four_mesh.bin", "four_blend.bin"):
            if not (runtime/"grid_calibration_20260929_markers"/name).is_file():
                raise ValueError("No saved calibration or initial marker preset")
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise ValueError(f"Missing executable calibration launcher: {launcher}")
    return launcher


def active(unit):
    return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=5).returncode == 0


def wait_display(timeout=60):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(["LayerManagerControl", "get", "layer", "102"],
                                    text=True, capture_output=True, timeout=3)
            if result.returncode == 0 and re.search(r"on screen:\s*0\(", result.stdout):
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(.5)
    raise TimeoutError("DSI-1 overlay layer is not ready; systemd will retry")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("/opt/jk-ti-srv-flex"))
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp/xdg-runtime-dir")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-1")
    if args.stop:
        # Allow an active worker to finish cancelling/restoring before stopping video.
        subprocess.run(["systemctl", "stop", "jk-calibration-ui.service"], timeout=95, check=False)
        subprocess.run([str(runtime/"run_flex_stitch.sh"), "stop"], timeout=12, check=True)
        return
    with (runtime/"calibration.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A calibration already owns the cameras; leaving its session running.", flush=True)
            return
        wait_display()
        if not active("jk-flex-ti-srv.service"):
            launcher = select_launcher(runtime)
            print(f"Starting saved calibration: {launcher}", flush=True)
            subprocess.run([str(launcher)], check=True, timeout=90,
                           env=dict(os.environ, FLEX_CAL_UI="1"))
        subprocess.run([str(runtime/"run_calibration_ui.sh")], check=True, timeout=10)
        if not active("jk-flex-ti-srv.service") or not active("jk-calibration-ui.service"):
            raise RuntimeError("Camera renderer or CAL controls did not start")
        print("Four-camera stitching and CAL controls started.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.exit(f"Boot launch failed: {error}")
