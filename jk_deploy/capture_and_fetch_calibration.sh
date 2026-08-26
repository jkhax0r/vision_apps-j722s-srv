#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${TARGET:-root@192.168.20.222}"
LOCAL_ROOT="${LOCAL_ROOT:-$SCRIPT_DIR/calibration/captures}"
REMOTE_LOG="$(mktemp)"

cleanup() {
    rm -f "$REMOTE_LOG"
}
trap cleanup EXIT

read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"

set +e
ssh "${SSH_ARGV[@]}" "$TARGET" \
    "WARMUP_FRAMES='${WARMUP_FRAMES:-60}' /opt/jk-ti-srv/capture_calibration_images.sh" \
    | tee "$REMOTE_LOG"
REMOTE_STATUS="${PIPESTATUS[0]}"
set -e

REMOTE_ARCHIVE="$(sed -n 's/^CALIBRATION_ARCHIVE=//p' "$REMOTE_LOG" | tail -n 1)"
if [ -z "$REMOTE_ARCHIVE" ]; then
    echo "The target did not report a calibration archive" >&2
    exit 1
fi

mkdir -p "$LOCAL_ROOT"
LOCAL_ARCHIVE="$LOCAL_ROOT/$(basename "$REMOTE_ARCHIVE")"
scp "${SSH_ARGV[@]}" "$TARGET:$REMOTE_ARCHIVE" "$LOCAL_ARCHIVE"
tar -C "$LOCAL_ROOT" -xzf "$LOCAL_ARCHIVE"

LOCAL_DIR="$LOCAL_ROOT/$(basename "$REMOTE_ARCHIVE" .tar.gz)"
echo "Calibration capture fetched."
echo "LOCAL_CALIBRATION_DIR=$LOCAL_DIR"
echo "LOCAL_CALIBRATION_ARCHIVE=$LOCAL_ARCHIVE"

if [ "$REMOTE_STATUS" -ne 0 ]; then
    echo "Target capture validation failed; inspect the fetched PNG previews" >&2
    exit "$REMOTE_STATUS"
fi
