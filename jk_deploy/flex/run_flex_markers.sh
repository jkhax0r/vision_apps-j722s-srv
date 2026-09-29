#!/bin/bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)
export FLEX_CALIBRATION_DIR="${FLEX_CALIBRATION_DIR:-$ROOT/grid_calibration_20260929_markers}"
exec "$ROOT/run_flex_grid.sh" "$@"
