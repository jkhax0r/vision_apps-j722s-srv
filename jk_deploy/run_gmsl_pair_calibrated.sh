#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${PAIR_WARP_MODE:-lens}"
case "$MODE" in
    lens|measured) ;;
    *) echo "PAIR_WARP_MODE must be lens or measured" >&2; exit 1 ;;
esac
CAL_DIR="$SCRIPT_DIR/calibration/final_20260908T184734Z"
export APP_SRV_PAIR_FULL_RES="${PAIR_FULL_RES:-1}"
case "$APP_SRV_PAIR_FULL_RES" in
    1) MESH="${MODE}_fullres_mesh.bin" ;;
    0) MESH="${MODE}_mesh.bin" ;;
    *) echo "PAIR_FULL_RES must be 0 or 1" >&2; exit 1 ;;
esac
export APP_SRV_PAIR_LUT="$CAL_DIR/$MESH"
export APP_SRV_PAIR_BLEND="$CAL_DIR/${MODE}_blend.bin"
echo "Pair alignment: final_20260908T184734Z, warp=$MODE, full-resolution=$APP_SRV_PAIR_FULL_RES"
exec "$SCRIPT_DIR/run_gmsl_pair_test.sh" "$@"
