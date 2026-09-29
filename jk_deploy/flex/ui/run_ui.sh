#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)
BUNDLE=$(cd -- "$HERE/../../.." && pwd)
UNIT=jk-calibration-ui.service
if [[ ${1:-start} == stop ]]; then
    systemctl stop "$UNIT"
    exit
fi
# This launcher is also called after each live camera stream restart.
if [[ -f /opt/jk-ti-srv-flex/camera_settings.json ]]; then
    /usr/bin/python3 "$HERE/camera_controls.py" restore || echo "Saved camera settings could not be restored." >&2
fi
if systemctl is-active --quiet "$UNIT"; then
    exit
fi
exec systemd-run --unit="$UNIT" --collect --property=TimeoutStopSec=90 \
    --setenv=XDG_RUNTIME_DIR=/tmp/xdg-runtime-dir --setenv=WAYLAND_DISPLAY=wayland-1 \
    --setenv=QT_QPA_PLATFORM=wayland --setenv=QT_WAYLAND_SHELL_INTEGRATION=ivi-shell \
    --setenv=QT_IVI_SURFACE_ID=19001 --setenv=QT_QUICK_BACKEND=software \
    --setenv=QT_QUICK_CONTROLS_STYLE=Basic --setenv=PYTHONUNBUFFERED=1 \
    /usr/bin/python3 "$HERE/calibration_ui.py" --support "$BUNDLE/python"
