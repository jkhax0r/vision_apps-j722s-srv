#!/bin/bash
set -euo pipefail

RUNTIME_DIR="${RUNTIME_DIR:-/opt/jk-ti-srv}"
CAPTURE_ROOT="${CAPTURE_ROOT:-/root/jk-calibration-captures}"
WARMUP_FRAMES="${WARMUP_FRAMES:-60}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_DIR="${OUTPUT_DIR:-$CAPTURE_ROOT/$STAMP}"
COMPOSITE_RAW="/tmp/jk-calibration-composite-$$.raw"

cleanup() {
    rm -f "$COMPOSITE_RAW"
}
trap cleanup EXIT

mkdir -p "$OUTPUT_DIR"

echo "Capturing calibration frame after $WARMUP_FRAMES warm-up frames..."
APP_CALIB_CAPTURE_DIR="$OUTPUT_DIR" \
APP_CALIB_CAPTURE_FRAME="$WARMUP_FRAMES" \
    "$RUNTIME_DIR/run_jk_srv_live.sh" "$WARMUP_FRAMES" "$COMPOSITE_RAW" \
    2>&1 | tee "$OUTPUT_DIR/capture.log"

mapfile -t YUV_FILES < <(find "$OUTPUT_DIR" -maxdepth 1 -type f \
    -name 'camera*_640x480_nv12.yuv' | sort)
declare -a LUMA_SUMMARIES=()
INVALID_CAMERAS=0

if [ "${#YUV_FILES[@]}" -ne 4 ]; then
    echo "Expected four calibration YUV files, found ${#YUV_FILES[@]}" >&2
    exit 1
fi

for file in "${YUV_FILES[@]}"; do
    size="$(stat -c %s "$file")"
    if [ "$size" -ne 460800 ]; then
        echo "$file has unexpected size $size; expected 460800 bytes" >&2
        exit 1
    fi

    if command -v ffmpeg >/dev/null 2>&1; then
        ffmpeg -y -loglevel error \
            -f rawvideo -pixel_format nv12 -video_size 640x480 \
            -i "$file" -frames:v 1 "${file%.yuv}.png"

        stats="$(ffmpeg -hide_banner \
            -f rawvideo -pixel_format nv12 -video_size 640x480 \
            -i "$file" -vf 'signalstats,metadata=print' \
            -frames:v 1 -f null - 2>&1)"
        ymin="$(printf '%s\n' "$stats" | sed -n 's/.*lavfi.signalstats.YMIN=//p' | head -n 1)"
        ymax="$(printf '%s\n' "$stats" | sed -n 's/.*lavfi.signalstats.YMAX=//p' | head -n 1)"
        if [ -n "$ymin" ] && [ -n "$ymax" ]; then
            luma_range=$((ymax - ymin))
            LUMA_SUMMARIES+=("$(basename "$file"): YMIN=$ymin YMAX=$ymax range=$luma_range")
            if [ "$luma_range" -lt 8 ]; then
                echo "WARNING: $(basename "$file") is effectively uniform; camera likely has no signal" >&2
                INVALID_CAMERAS=$((INVALID_CAMERAS + 1))
            fi
        fi
    fi
done

{
    echo "TI SRV calibration capture"
    echo "captured_utc=$STAMP"
    echo "format=NV12 (Y plane followed by interleaved UV; TI 420sp)"
    echo "width=640"
    echo "height=480"
    echo "pitch=640"
    echo "camera_count=4"
    echo
    echo "Capture slots and current compositor positions:"
    echo "camera0: /usr/local/Ahsoka/devices/video/gmsl0, top-left"
    echo "camera1: /usr/local/Ahsoka/devices/video/gmsl1, top-right"
    echo "camera2: /usr/local/Ahsoka/devices/video/analog0, bottom-right"
    echo "camera3: /usr/local/Ahsoka/devices/video/analog1, bottom-left"
    echo
    echo "Resolve each slot to front/right/back/left from the physical mounting."
    echo "The slot names do not assert a physical camera direction."
    echo "Analog frames include the same field reweave used by the live SRV app."
    echo "All inputs preserve the complete field of view seen by the GPU node."
    echo "GMSL 1920x1200 frames are fit to 640x400 with 40-pixel top/bottom bars."
    echo "Analog 720x480 samples are normalized to the complete 640x480 image."
    if [ "${#LUMA_SUMMARIES[@]}" -gt 0 ]; then
        echo
        echo "Luma validation:"
        printf '%s\n' "${LUMA_SUMMARIES[@]}"
    fi
    echo
    echo "Resolved device nodes:"
    for device in gmsl0 gmsl1 analog0 analog1; do
        path="/usr/local/Ahsoka/devices/video/$device"
        echo "$device=$(readlink -f "$path")"
    done
    echo
    echo "SHA-256:"
    (
        cd "$OUTPUT_DIR"
        sha256sum -- "${YUV_FILES[@]##*/}"
    )
} > "$OUTPUT_DIR/manifest.txt"

ARCHIVE="$OUTPUT_DIR.tar.gz"
tar -C "$(dirname "$OUTPUT_DIR")" -czf "$ARCHIVE" "$(basename "$OUTPUT_DIR")"
sync

echo "Calibration images captured."
echo "CALIBRATION_DIR=$OUTPUT_DIR"
echo "CALIBRATION_ARCHIVE=$ARCHIVE"
if [ "$INVALID_CAMERAS" -ne 0 ]; then
    echo "CALIBRATION_VALID=0"
    echo "$INVALID_CAMERAS camera input(s) produced a uniform no-signal frame" >&2
    exit 2
fi
echo "CALIBRATION_VALID=1"
