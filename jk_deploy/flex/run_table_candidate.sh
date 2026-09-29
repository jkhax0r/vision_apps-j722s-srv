#!/bin/bash
set -euo pipefail
CAL=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)
export FLEX_CALIBRATION_DIR="$CAL"
export FLEX_COMPARE=1
export CAMERA_ORDER="$(<"$CAL/camera_order.txt")"
exec "$CAL/../run_flex_stitch.sh" "$@"
