#!/bin/bash
set -euo pipefail
TARGET="${TARGET:?Set TARGET to root@TARGET_IP}"
DEST="${1:?Usage: capture_gmsl_pair.sh NEW_LOCAL_CAPTURE_DIRECTORY}"
REMOTE="/root/jk-lens-calibration/pair_$(date -u +%Y%m%dT%H%M%SZ)"
read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"
test ! -e "$DEST" || { echo "Refusing to overwrite $DEST" >&2; exit 1; }
ssh "${SSH_ARGV[@]}" "$TARGET" "bash -s -- '$REMOTE'" <<'REMOTE_SCRIPT'
set -euo pipefail
DEST="$1"
mkdir -p "$(dirname "$DEST")"
mkdir "$DEST"
ACTIVE=0
if systemctl is-active --quiet jk-ti-srv-pair; then ACTIVE=1; fi
restore_preview() {
    if [ "$ACTIVE" -eq 1 ]; then
        systemd-run --unit=jk-ti-srv-pair --collect \
            /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 0 /tmp/jk-pair-fullres-live.raw
    fi
}
systemctl stop jk-ti-srv-pair
trap restore_preview EXIT
if fuser /usr/local/Ahsoka/devices/video/gmsl{0,1}; then
    echo "A process still owns the cameras; capture aborted" >&2
    exit 1
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$DEST/captured_utc.txt"
pids=()
for camera in 0 1; do
    device="/usr/local/Ahsoka/devices/video/gmsl$camera"
    v4l2-ctl -d "$device" --get-fmt-video > "$DEST/gmsl$camera.format.txt"
    timeout 20 v4l2-ctl -d "$device" --stream-mmap=4 --stream-skip=30 \
        --stream-count=1 --stream-to="$DEST/gmsl$camera.uyvy" \
        > "$DEST/gmsl$camera.capture.log" 2>&1 &
    pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
test "$status" -eq 0
for camera in 0 1; do
    test "$(stat -c %s "$DEST/gmsl$camera.uyvy")" -eq 4608000
done
REMOTE_SCRIPT
mkdir -p "$(dirname "$DEST")"
scp "${SSH_ARGV[@]}" -r "$TARGET:$REMOTE" "$DEST"
python3 - "$DEST" <<'PY'
from pathlib import Path
import sys
import cv2
import numpy as np
root = Path(sys.argv[1])
previews = []
for camera in (0, 1):
    packed = np.fromfile(root/f'gmsl{camera}.uyvy', np.uint8).reshape(1200, 1920, 2)
    image = cv2.rotate(cv2.cvtColor(packed, cv2.COLOR_YUV2BGR_UYVY), cv2.ROTATE_180)
    cv2.imwrite(str(root/f'gmsl{camera}.png'), image)
    previews.append(cv2.resize(image, (768, 480), interpolation=cv2.INTER_AREA))
cv2.imwrite(str(root/'preview.png'), np.concatenate(previews, axis=1))
PY
printf 'Remote: %s\nLocal: %s\n' "$REMOTE" "$DEST"
