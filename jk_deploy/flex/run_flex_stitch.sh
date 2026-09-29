#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)
UNIT=jk-flex-ti-srv.service
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime-dir}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"

case "${1:-start}" in
    status) systemctl status "$UNIT" --no-pager; exit ;;
    start|stop|quad) ;;
    *) echo "Usage: $0 [start|stop|quad|status]" >&2; exit 2 ;;
esac
if systemctl is-active --quiet "$UNIT"; then
    systemctl stop "$UNIT"
fi
if [ "${1:-start}" = stop ]; then
    LayerManagerControl set surface 1234 visibility 1 >/dev/null 2>&1 || true
    exit 0
fi
if [ "${1:-start}" = quad ]; then
    exec "$ROOT/run_flex_four.sh"
fi

CAL=${FLEX_CALIBRATION_DIR:-$ROOT/calibration}
EXTRA_ENV=()
case "${FLEX_COMPARE:-0}" in
    0) ;;
    1) EXTRA_ENV+=(--setenv=APP_SRV_FOUR_COMPARE=1) ;;
    *) echo "FLEX_COMPARE must be 0 or 1." >&2; exit 2 ;;
esac
test -s "$CAL/four_mesh.bin"
test -s "$CAL/four_blend.bin"
test -e /dev/dma_heap/linux,cma
test -e /dev/dma_heap/carveout_vision_apps_shared-memories
read -r -a ORDER <<< "${CAMERA_ORDER:-0 1 2 3}"
if [ "${#ORDER[@]}" -ne 4 ] || [ "$(printf '%s\n' "${ORDER[@]}" | sort -u | tr '\n' ' ')" != '0 1 2 3 ' ]; then
    echo "CAMERA_ORDER must be a permutation of '0 1 2 3' (front right rear left)." >&2
    exit 1
fi

CAM_WIDTH=1920 CAM_HEIGHT=1200 CAM_FPS=${CAM_FPS:-30} "$ROOT/run_flex_four.sh" configure
DEVICES=()
for i in "${ORDER[@]}"; do
    DEVICES+=("$(media-ctl -d /dev/media0 -e "30102000.ticsi2rx context $((i+1))")")
done
# A private mount namespace redirects only this process's 1 MB TI heap to
# the existing CMA heap. Global /dev, the device tree and boot stay unchanged.
systemd-run --unit="$UNIT" --collect --property=TimeoutStopSec=10 \
    --property=BindPaths=/dev/dma_heap/linux,cma:/dev/dma_heap/carveout_vision_apps_shared-memories \
    --setenv=LD_LIBRARY_PATH="$ROOT" \
    --setenv=APP_SRV_FOUR_LUT="$CAL/four_mesh.bin" \
    --setenv=APP_SRV_FOUR_BLEND="$CAL/four_blend.bin" \
    --setenv=APP_SRV_IMPORT_CAPTURE="${APP_SRV_IMPORT_CAPTURE:-1}" \
    --setenv=APP_EGL_WAYLAND=1 --setenv=APP_EGL_WIDTH=1920 --setenv=APP_EGL_HEIGHT=720 \
    --setenv=APP_EGL_APP_ID=com.enovation.Installer \
    --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" --setenv=WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
    "${EXTRA_ENV[@]}" \
    "$ROOT/vx_app_jk_srv_live.out" "${FRAME_COUNT:-0}" /tmp/jk-flex-ti-last.rgbx "${DEVICES[@]}"

for ((attempt=0; attempt<60; attempt++)); do
    PID=$(systemctl show "$UNIT" -p MainPID --value)
    INFO=$(LayerManagerControl get surface 1000 2>/dev/null || true)
    OWNER=$(awk '/created by pid:/ {print $5}' <<< "$INFO")
    FRAMES=$(awk '/frame counter:/ {print $4}' <<< "$INFO")
    if [ -n "$PID" ] && [ "$PID" != 0 ] && [ "$PID" = "$OWNER" ] && [ "${FRAMES:-0}" -gt 0 ]; then
        # Ahsoka applies its installer geometry asynchronously after creation.
        sleep 1
        LayerManagerControl set surface 1000 destination region 0 0 1920 720
        LayerManagerControl set surface 1000 visibility 1
        LayerManagerControl set surface 1234 visibility 0 >/dev/null 2>&1 || true
        # On this BSP stream-on resets max_fps, even after format setup.
        while IFS= read -r sensor; do
            subdev=$(media-ctl -d /dev/media0 -e "$sensor")
            v4l2-ctl -d "$subdev" --set-ctrl=max_fps="${CAM_FPS:-30}"
        done < <(media-ctl -d /dev/media0 -p | sed -n 's/^- entity [0-9]*: \(tevs [^ ]*\) (.*/\1/p')
        echo "TI four-GMSL renderer running with calibration $CAL"
        if [ ! -f "$CAL/calibration.json" ]; then
            echo "Default poses are approximate, NOT calibrated seams."
        fi
        echo "Return to four raw views: $0 quad"
        if [[ ${FLEX_CAL_UI:-1} == 1 && -x "$ROOT/run_calibration_ui.sh" ]]; then
            "$ROOT/run_calibration_ui.sh" || echo "Calibration controls did not start." >&2
        fi
        exit 0
    fi
    sleep 0.2
done
journalctl -u "$UNIT" -n 40 --no-pager >&2
systemctl stop "$UNIT" || true
echo "TI preview failed; restoring four raw views." >&2
"$ROOT/run_flex_four.sh"
exit 1
