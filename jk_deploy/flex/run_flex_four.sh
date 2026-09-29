#!/bin/bash
set -euo pipefail

# Flex/MAX96724 four-camera proof only: independent views, no stitching.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime-dir}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
MEDIA=/dev/media0
MAX='max96724 4-002e'
BRIDGE=cdns_csi2rx.30101000.csi-bridge
CSI=30102000.ticsi2rx
WIDTH=${CAM_WIDTH:-1280}
HEIGHT=${CAM_HEIGHT:-720}
FPS=${CAM_FPS:-30}
FMT="[fmt:UYVY8_1X16/${WIDTH}x${HEIGHT} field:none colorspace:srgb ycbcr:601 quantization:full-range]"

stop_views() {
    for i in 0 1 2 3; do
        if systemctl is-active --quiet "jk-flex-camera-$i.service"; then
            systemctl stop "jk-flex-camera-$i.service"
        fi
    done
    LayerManagerControl set surface 1234 visibility 1 >/dev/null 2>&1 || true
}

case "${1:-start}" in
    stop) stop_views; exit 0 ;;
    status)
        for i in 0 1 2 3; do
            systemctl is-active "jk-flex-camera-$i.service" || true
            LayerManagerControl get surface "$((18001+i))"
        done
        exit 0
        ;;
    start|configure) ;;
    *) echo "Usage: $0 [start|stop|status|configure]" >&2; exit 2 ;;
esac

for module in max96724 max96717_tevs tevs cdns_csi2rx j721e_csi2rx cdns_dphy_rx; do
    modprobe "$module"
done
# Subdevices may finish binding after modprobe returns.
for ((attempt=0; attempt<50; attempt++)); do
    TOPOLOGY=$(media-ctl -d "$MEDIA" -p 2>/dev/null || true)
    COUNT=$(awk '/^- entity .*: tevs / { n++ } END { print n+0 }' <<< "$TOPOLOGY")
    [ "$COUNT" -eq 4 ] && break
    sleep 0.2
done
if [ "$COUNT" -ne 4 ]; then
    echo "Expected four TEVS sensors, found $COUNT. Connect cameras before boot." >&2
    exit 1
fi

declare -a SENSORS PADS VIDEOS
MAX_ROUTES= BRIDGE_ROUTES= CSI_ROUTES=
for i in 0 1 2 3; do
    alias=$(printf '%04x' "$((0x39+i))")
    SENSORS[$i]=$(sed -n "s/^- entity [0-9]*: \(tevs [0-9]*-$alias\) (.*/\1/p" <<< "$TOPOLOGY")
    PADS[$i]=$(awk -v sensor="${SENSORS[$i]}" '
        /^- entity / { inside=index($0, ": " sensor " (") > 0 }
        inside && /-> "max96724 / { split($0, a, "\":"); split(a[2], b, " "); print b[1] }
    ' <<< "$TOPOLOGY")
    if [ -z "${SENSORS[$i]}" ] || [[ ! ${PADS[$i]} =~ ^[1-4]$ ]]; then
        echo "Cannot resolve TEVS alias $alias and its MAX96724 sink pad." >&2
        exit 1
    fi
    VIDEOS[$i]=$(media-ctl -d "$MEDIA" -e "$CSI context $((i+1))")
    MAX_ROUTES+="${MAX_ROUTES:+, }${PADS[$i]}/0 -> 0/$i [1]"
    BRIDGE_ROUTES+="${BRIDGE_ROUTES:+, }0/$i -> 1/$i [1]"
    CSI_ROUTES+="${CSI_ROUTES:+, }0/$i -> $((i+1))/0 [1]"
done

stop_views
if systemctl is-active --quiet jk-flex-camera-preview.service; then
    systemctl stop jk-flex-camera-preview.service
fi
for video in "${VIDEOS[@]}"; do
    if fuser "$video" >/dev/null 2>&1; then
        echo "Camera $video is busy; stop its current viewer first." >&2
        exit 1
    fi
done
for i in 0 1 2 3; do
    if LayerManagerControl get surfaces | grep -q "Surface $((18001+i)) "; then
        echo "Preview surface $((18001+i)) is already in use." >&2
        exit 1
    fi
done
media-ctl -d "$MEDIA" -R "\"$MAX\" [$MAX_ROUTES]"
media-ctl -d "$MEDIA" -R "\"$BRIDGE\" [$BRIDGE_ROUTES]"
media-ctl -d "$MEDIA" -R "\"$CSI\" [$CSI_ROUTES]"
for i in 0 1 2 3; do
    sensor=${SENSORS[$i]}
    subdev=$(media-ctl -d "$MEDIA" -e "$sensor")
    media-ctl -d "$MEDIA" -V "\"$sensor\":0/0 [fmt:UYVY8_1X16/${WIDTH}x${HEIGHT}@1/${FPS} field:none colorspace:srgb ycbcr:601 quantization:full-range]"
    media-ctl -d "$MEDIA" -V "\"$MAX\":${PADS[$i]}/0 $FMT"
    media-ctl -d "$MEDIA" -V "\"$MAX\":0/$i $FMT"
    media-ctl -d "$MEDIA" -V "\"$BRIDGE\":0/$i $FMT"
    media-ctl -d "$MEDIA" -V "\"$BRIDGE\":1/$i $FMT"
    media-ctl -d "$MEDIA" -V "\"$CSI\":0/$i $FMT"
    media-ctl -d "$MEDIA" -V "\"$CSI\":$((i+1))/0 $FMT"
    v4l2-ctl -d "${VIDEOS[$i]}" --set-fmt-video=width="$WIDTH",height="$HEIGHT",pixelformat=UYVY
    echo "View $((i+1)): $sensor -> MAX sink ${PADS[$i]} -> VC $i -> ${VIDEOS[$i]}"
done
# TEVS set_fmt resets max_fps. Set controls after all format propagation.
for sensor in "${SENSORS[@]}"; do
    subdev=$(media-ctl -d "$MEDIA" -e "$sensor")
    v4l2-ctl -d "$subdev" --set-ctrl=max_fps="$FPS"
done

if [ "${1:-start}" = configure ]; then
    exit 0
fi

trap 'stop_views' ERR
for i in 0 1 2 3; do
    systemd-run --unit="jk-flex-camera-$i" --collect \
        --setenv=XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        --setenv=WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
        --setenv=GLIMAGESINK_SURFACE_ID="$((18001+i))" \
        --setenv=GST_GL_WINDOW=wayland --setenv=GST_GL_PLATFORM=egl \
        gst-launch-1.0 -e v4l2src device="${VIDEOS[$i]}" io-mode=dmabuf \
        ! "video/x-raw,format=UYVY,width=$WIDTH,height=$HEIGHT,framerate=$FPS/1" \
        ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 leaky=downstream \
        ! glimagesink sync=false
    sleep 0.3
done
for i in 0 1 2 3; do
    ready=0
    for ((attempt=0; attempt<50; attempt++)); do
        PID=$(systemctl show "jk-flex-camera-$i.service" -p MainPID --value)
        INFO=$(LayerManagerControl get surface "$((18001+i))")
        OWNER=$(awk '/created by pid:/ { print $5 }' <<< "$INFO")
        FRAMES=$(awk '/frame counter:/ { print $4 }' <<< "$INFO")
        if [ -n "$PID" ] && [ "$PID" != 0 ] && [ "$OWNER" = "$PID" ] && [ "${FRAMES:-0}" -gt 0 ]; then
            ready=1
            break
        fi
        sleep 0.2
    done
    if [ "$ready" -ne 1 ]; then
        journalctl -u "jk-flex-camera-$i.service" -n 20 --no-pager >&2
        stop_views
        exit 1
    fi
    LayerManagerControl set surface "$((18001+i))" destination region "$((160+960*(i%2)))" "$((360*(i/2)))" 640 360
    LayerManagerControl set surface "$((18001+i))" visibility 1
done
# Stream-on can also reset the sensor control on this BSP.
for sensor in "${SENSORS[@]}"; do
    subdev=$(media-ctl -d "$MEDIA" -e "$sensor")
    v4l2-ctl -d "$subdev" --set-ctrl=max_fps="$FPS"
done
LayerManagerControl set surface 1234 visibility 0 >/dev/null 2>&1 || true
echo "Four independent live views: top-left 1, top-right 2, bottom-left 3, bottom-right 4."
echo "Stop and show the Ahsoka window again: $0 stop"
