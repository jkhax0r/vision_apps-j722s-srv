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
export APP_SRV_USE_CALIBRATION="${APP_SRV_USE_CALIBRATION:-1}"
if [ "$APP_SRV_USE_CALIBRATION" = 0 ]; then
    export APP_SRV_QUADRANT_MODE=1
else
    unset APP_SRV_QUADRANT_MODE
fi

CAM_MEDIA="${CAM_MEDIA:-/dev/media0}"
CAM_WIDTH="${CAM_WIDTH:-1920}"
CAM_HEIGHT="${CAM_HEIGHT:-1200}"
CAM_FPS="${CAM_FPS:-30}"

AHSOKA_WAS_ACTIVE=0

configure_gmsl() {
    local width="$1"
    local height="$2"
    local fps="$3"
    local fmt="[fmt:UYVY8_1X16/${width}x${height}@1/${fps} field:none colorspace:srgb ycbcr:601 quantization:full-range]"
    local fmt_no_fps="[fmt:UYVY8_1X16/${width}x${height} field:none colorspace:srgb ycbcr:601 quantization:full-range]"
    local fmt_simple="[fmt:UYVY8_1X16/${width}x${height} field:none]"
    local topology
    local max_entity
    local entity
    local subdev
    local index
    local stream
    local -a tevs_entities

    topology="$(media-ctl -d "$CAM_MEDIA" -p)"
    max_entity="$(printf '%s\n' "$topology" | awk -F': | \\(' '/^- entity .*: max96716-tevs / {print $2; exit}')"
    mapfile -t tevs_entities < <(printf '%s\n' "$topology" | awk -F': | \\(' '/^- entity .*: tevs / {print $2}')

    if [ -z "$max_entity" ] || [ "${#tevs_entities[@]}" -ne 2 ]; then
        echo "Expected one MAX96716 and two TEVS sensors on $CAM_MEDIA" >&2
        media-ctl -d "$CAM_MEDIA" -p >&2
        return 1
    fi

    echo "Configuring ${tevs_entities[*]} for ${width}x${height}@${fps}..."
    for index in 0 1; do
        entity="${tevs_entities[$index]}"
        subdev="$(printf '%s\n' "$topology" | awk -v entity="$entity" '
            /^- entity / && index($0, ": " entity " (") { inside=1; next }
            inside && /device node name/ { print $4; exit }
            inside && /^- entity / { exit }
        ')"
        v4l2-ctl -d "$subdev" --set-ctrl=max_fps="$fps" >/dev/null || true
        media-ctl -d "$CAM_MEDIA" -V "\"$entity\":0/0 $fmt" || \
            media-ctl -d "$CAM_MEDIA" -V "\"$entity\":0/0 $fmt_no_fps"
    done

    media-ctl -d "$CAM_MEDIA" -V "\"$max_entity\":0/0 $fmt_simple"
    media-ctl -d "$CAM_MEDIA" -V "\"$max_entity\":0/1 $fmt_simple"

    for stream in 0 1; do
        media-ctl -d "$CAM_MEDIA" -V "\"cdns_csi2rx.30101000.csi-bridge\":0/$stream $fmt_no_fps"
        media-ctl -d "$CAM_MEDIA" -V "\"cdns_csi2rx.30101000.csi-bridge\":1/$stream $fmt_no_fps"
    done

    media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":0/0 $fmt_no_fps"
    media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":0/1 $fmt_no_fps"
    media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":1/0 $fmt_no_fps"
    media-ctl -d "$CAM_MEDIA" -V "\"30102000.ticsi2rx\":2/0 $fmt_no_fps"

    v4l2-ctl -d /usr/local/Ahsoka/devices/video/gmsl0 \
        --set-fmt-video=width="$width",height="$height",pixelformat=UYVY >/dev/null
    v4l2-ctl -d /usr/local/Ahsoka/devices/video/gmsl1 \
        --set-fmt-video=width="$width",height="$height",pixelformat=UYVY >/dev/null
}

restore_ahsoka() {
    trap - EXIT INT TERM
    set +e
    if [ "$AHSOKA_WAS_ACTIVE" -eq 1 ]; then
        echo "Restoring the stock Ahsoka camera configuration..."
        configure_gmsl 1920 1200 30
        systemctl start Ahsoka.Application.service
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
            LayerManagerControl set surface 1001 visibility 1 >/dev/null 2>&1 || true
    fi
}
trap restore_ahsoka EXIT INT TERM

if systemctl is-active --quiet Ahsoka.Application.service; then
    AHSOKA_WAS_ACTIVE=1
    echo "Stopping the stock Ahsoka application..."
    systemctl stop Ahsoka.Application.service
fi

PREVIEW_PIDS="$(pgrep -f '^/usr/local/Ahsoka/current/AhsokaLib/Ahsoka.VideoPlayer ' || true)"
if [ -n "$PREVIEW_PIDS" ]; then
    echo "Stopping remaining Ahsoka camera previews..."
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

configure_gmsl "$CAM_WIDTH" "$CAM_HEIGHT" "$CAM_FPS"

cd /opt/jk-ti-srv
./vx_app_jk_srv_live.out "$@"
