#!/bin/bash
set -euo pipefail
DEST=${1:?Usage: capture_floor.sh NEW_OUTPUT_DIRECTORY}
RUNTIME=${RUNTIME:-/opt/jk-ti-srv-flex}
if [ -e "$DEST" ]; then
    echo "Refusing to overwrite $DEST" >&2
    exit 1
fi
"$RUNTIME/run_flex_stitch.sh" stop
CAM_WIDTH=1920 CAM_HEIGHT=1200 "$RUNTIME/run_flex_four.sh" configure
mkdir -p "$DEST"
date -u > "$DEST/captured_utc.txt"
media-ctl -d /dev/media0 -p > "$DEST/topology.txt"
# Sequential snapshots are suitable only for a stationary board and rig.
for i in 0 1 2 3; do
    VIDEO=$(media-ctl -d /dev/media0 -e "30102000.ticsi2rx context $((i+1))")
    v4l2-ctl -d "$VIDEO" --get-fmt-video > "$DEST/input$i.format.txt"
    timeout 15 v4l2-ctl -d "$VIDEO" --stream-mmap=4 --stream-skip=30 \
        --stream-count=1 --stream-to="$DEST/input$i.uyvy"
    test "$(stat -c %s "$DEST/input$i.uyvy")" = 4608000
done
echo "Captured native 1920x1200 UYVY snapshots in $DEST"
