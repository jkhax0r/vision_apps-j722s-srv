#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)
export FLEX_CALIBRATION_DIR="${FLEX_CALIBRATION_DIR:-$ROOT/grid_calibration}"
export FLEX_COMPARE=1
if [[ -z ${CAMERA_ORDER:-} && -f "$FLEX_CALIBRATION_DIR/camera_order.txt" ]]; then
    CAMERA_ORDER=$(<"$FLEX_CALIBRATION_DIR/camera_order.txt")
fi
export CAMERA_ORDER="${CAMERA_ORDER:-0 1 2 3}"
exec "$ROOT/run_flex_stitch.sh" "$@"
