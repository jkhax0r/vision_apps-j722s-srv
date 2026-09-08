#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export APP_SRV_RUNTIME_DIR="$SCRIPT_DIR"
export LD_LIBRARY_PATH="$SCRIPT_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export APP_SRV_PAIR_LUT="$SCRIPT_DIR/calibration/split_mesh.bin"
export APP_SRV_PAIR_BLEND="$SCRIPT_DIR/calibration/split_blend.bin"
export APP_SRV_USE_CALIBRATION=1
export VX_TEST_DATA_PATH="${VX_TEST_DATA_PATH:-/opt/jk-ti-srv}"
for file in "$APP_SRV_PAIR_LUT" "$APP_SRV_PAIR_BLEND" \
    "$SCRIPT_DIR/lib/libtivision_apps.so.11.0.0"; do
    if [ ! -s "$file" ]; then
        echo "Missing pair-test file: $file" >&2
        exit 1
    fi
done
exec "$SCRIPT_DIR/run_jk_srv_live.sh" "$@"
