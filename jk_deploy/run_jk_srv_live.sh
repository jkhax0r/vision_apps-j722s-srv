#!/bin/bash
set -euo pipefail

export SOC="${SOC:-j722s}"
export VX_TEST_DATA_PATH="${VX_TEST_DATA_PATH:-/opt/jk-ti-srv}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime-dir}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
export APP_EGL_WAYLAND=1
export APP_EGL_WIDTH="${APP_EGL_WIDTH:-1280}"
export APP_EGL_HEIGHT="${APP_EGL_HEIGHT:-800}"
export APP_EGL_APP_ID="${APP_EGL_APP_ID:-com.enovation.Installer}"
export APP_SRV_QUADRANT_MODE="${APP_SRV_QUADRANT_MODE:-1}"

CAM_MEDIA="${CAM_MEDIA:-/dev/media0}"
CAM_WIDTH="${CAM_WIDTH:-1280}"
CAM_HEIGHT="${CAM_HEIGHT:-720}"
CAM_FPS="${CAM_FPS:-60}"
CAM_FMT="[fmt:UYVY8_1X16/${CAM_WIDTH}x${CAM_HEIGHT}@1/${CAM_FPS} field:none colorspace:srgb ycbcr:601 quantization:full-range]"
CAM_FMT_NO_FPS="[fmt:UYVY8_1X16/${CAM_WIDTH}x${CAM_HEIGHT} field:none colorspace:srgb ycbcr:601 quantization:full-range]"
CAM_FMT_SIMPLE="[fmt:UYVY8_1X16/${CAM_WIDTH}x${CAM_HEIGHT} field:none]"

APP_MAIN_PID=

restore_ahsoka() {
    trap - EXIT INT TERM
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
        LayerManagerControl set surface 1001 visibility 1 >/dev/null 2>&1 || true
    if [ -n "$APP_MAIN_PID" ] && kill -0 "$APP_MAIN_PID" 2>/dev/null; then
        echo "Resuming the stock Ahsoka application..."
        kill -CONT "$APP_MAIN_PID" 2>/dev/null || true
    fi
}
trap restore_ahsoka EXIT INT TERM

if systemctl is-active --quiet Ahsoka.Application.service; then
    APP_MAIN_PID="$(systemctl show Ahsoka.Application.service -p MainPID --value)"
    if [ "${APP_MAIN_PID:-0}" -gt 0 ]; then
        echo "Freezing Ahsoka controller (PID $APP_MAIN_PID)..."
        kill -STOP "$APP_MAIN_PID"
    fi
fi

PREVIEW_PIDS="$(pgrep -f '^/usr/local/Ahsoka/current/AhsokaLib/Ahsoka.VideoPlayer ' || true)"
if [ -n "$PREVIEW_PIDS" ]; then
    echo "Stopping Ahsoka camera previews..."
    kill -TERM $PREVIEW_PIDS
fi

for attempt in $(seq 1 50); do
    if ! fuser /usr/local/Ahsoka/devices/video/gmsl0 \
            /usr/local/Ahsoka/devices/video/gmsl1 \
            /usr/local/Ahsoka/devices/video/analog0 \
            /usr/local/Ahsoka/devices/video/analog1 >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 50 ]; then
        echo "Timed out waiting for Ahsoka to release the cameras" >&2
        exit 1
    fi
    sleep 0.1
done

XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
    LayerManagerControl set surface 1001 visibility 0 >/dev/null 2>&1 || true

MEDIA_TOPOLOGY="$(media-ctl -d "$CAM_MEDIA" -p)"
MAX_ENTITY="$(printf '%s\n' "$MEDIA_TOPOLOGY" | awk -F': | \\(' '/^- entity .*: max96716-tevs / {print $2; exit}')"
mapfile -t TEVS_ENTITIES < <(printf '%s\n' "$MEDIA_TOPOLOGY" | awk -F': | \\(' '/^- entity .*: tevs / {print $2}')

if [ -z "$MAX_ENTITY" ] || [ "${#TEVS_ENTITIES[@]}" -ne 2 ]; then
    echo "Expected one MAX96716 and two TEVS sensors on $CAM_MEDIA" >&2
    media-ctl -d "$CAM_MEDIA" -p >&2
    exit 1
fi

echo "Configuring ${TEVS_ENTITIES[*]} for ${CAM_WIDTH}x${CAM_HEIGHT}@${CAM_FPS}..."
for index in 0 1; do
    entity="${TEVS_ENTITIES[$index]}"
    subdev="$(printf '%s\n' "$MEDIA_TOPOLOGY" | awk -v entity="$entity" '
        /^- entity / && index($0, ": " entity " (") { inside=1; next }
        inside && /device node name/ { print $4; exit }
        inside && /^- entity / { exit }
    ')"
    v4l2-ctl -d "$subdev" --set-ctrl=max_fps="$CAM_FPS" >/dev/null || true
    media-ctl -d "$CAM_MEDIA" -V "\"$entity\":0/0 $CAM_FMT" || \
        media-ctl -d "$CAM_MEDIA" -V "\"$entity\":0/0 $CAM_FMT_NO_FPS"
done

media-ctl -d "$CAM_MEDIA" -V "\"$MAX_ENTITY\":0/0 $CAM_FMT_SIMPLE"
media-ctl -d "$CAM_MEDIA" -V "\"$MAX_ENTITY\":0/1 $CAM_FMT_SIMPLE"

for stream in 0 1; do
    media-ctl -d "$CAM_MEDIA" -V "\"cdns_csi2rx.30101000.csi-bridge\":0/$stream $CAM_FMT_NO_FPS"
    media-ctl -d "$CAM_MEDIA" -V "\"cdns_csi2rx.30101000.csi-bridge\":1/$stream $CAM_FMT_NO_FPS"
done

media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":0/0 $CAM_FMT_NO_FPS"
media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":0/1 $CAM_FMT_NO_FPS"
media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":1/0 $CAM_FMT_NO_FPS"
media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":2/0 $CAM_FMT_NO_FPS"

v4l2-ctl -d /usr/local/Ahsoka/devices/video/gmsl0 \
    --set-fmt-video=width="$CAM_WIDTH",height="$CAM_HEIGHT",pixelformat=UYVY >/dev/null
v4l2-ctl -d /usr/local/Ahsoka/devices/video/gmsl1 \
    --set-fmt-video=width="$CAM_WIDTH",height="$CAM_HEIGHT",pixelformat=UYVY >/dev/null

cd /opt/jk-ti-srv
./vx_app_jk_srv_live.out "$@"
