#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${PAIR_WARP_MODE:-lens}"
case "$MODE" in
    lens|measured) ;;
    *) echo "PAIR_WARP_MODE must be lens or measured" >&2; exit 1 ;;
esac
CAL_DIR="$SCRIPT_DIR/calibration/final_20260908T184734Z"
export APP_SRV_PAIR_LUT="$CAL_DIR/${MODE}_mesh.bin"
export APP_SRV_PAIR_BLEND="$CAL_DIR/${MODE}_blend.bin"
echo "Pair alignment: final_20260908T184734Z, warp=$MODE"
exec "$SCRIPT_DIR/run_gmsl_pair_test.sh" "$@"
