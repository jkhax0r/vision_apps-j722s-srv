#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${PAIR_WARP_MODE:-lens}"
case "$MODE" in
    flat) MODE=lens ;;
    lens|measured|bowl) ;;
    *) echo "PAIR_WARP_MODE must be lens, measured, or bowl" >&2; exit 1 ;;
esac
ALIGNMENT="${PAIR_ALIGNMENT:-lowered_20260916T1954}"
if [[ ! "$ALIGNMENT" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "Invalid PAIR_ALIGNMENT name" >&2
    exit 1
fi
CAL_DIR="$SCRIPT_DIR/calibration/$ALIGNMENT"
LAYOUT="${PAIR_LAYOUT:-auto}"
if [ "$LAYOUT" = auto ]; then
    LAYOUT=split
    if [ -f "$CAL_DIR/table_settings.json" ] && [ "$MODE" != measured ]; then LAYOUT=table; fi
fi
PREFIX="$MODE"
case "$LAYOUT" in
    split) ;;
    table) PREFIX="${MODE}_table" ;;
    *) echo "PAIR_LAYOUT must be auto, split or table" >&2; exit 1 ;;
esac
export APP_SRV_PAIR_FULL_RES="${PAIR_FULL_RES:-1}"
case "$APP_SRV_PAIR_FULL_RES" in
    1) MESH="${PREFIX}_fullres_mesh.bin" ;;
    0) MESH="${PREFIX}_mesh.bin" ;;
    *) echo "PAIR_FULL_RES must be 0 or 1" >&2; exit 1 ;;
esac
export APP_SRV_PAIR_LUT="$CAL_DIR/$MESH"
export APP_SRV_PAIR_BLEND="$CAL_DIR/${PREFIX}_blend.bin"
test -s "$APP_SRV_PAIR_LUT"
test -s "$APP_SRV_PAIR_BLEND"
if [ "$MODE" = bowl ]; then
    python3 - "$CAL_DIR" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
settings = json.loads((root/'bowl_settings.json').read_text())
expected = dict(settings['artifact_sha256'])
expected['alignment.json'] = settings['alignment_sha256']
for name, digest in expected.items():
    if Path(name).name != name or hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
        sys.exit(f'Stale or damaged bowl calibration: {name}. Rebuild/redeploy before switching.')
if (root/'bowl_blend.bin').read_bytes() != (root/'lens_blend.bin').read_bytes():
    sys.exit('Flat and bowl blend weights differ. Rebuild/redeploy the matched pair.')
PY
fi
if [ "$LAYOUT" = table ]; then
    python3 - "$CAL_DIR" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
settings = json.loads((root/'table_settings.json').read_text())
for name, digest in settings['hashes'].items():
    if Path(name).name != name or hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
        sys.exit(f'Stale or damaged table mapping: {name}. Rebuild/redeploy before switching.')
PY
fi
echo "Pair alignment: $ALIGNMENT, warp=$MODE, layout=$LAYOUT, full-resolution=$APP_SRV_PAIR_FULL_RES"
if [ "${1:-}" = --check ]; then
    exit 0
fi
exec "$SCRIPT_DIR/run_gmsl_pair_test.sh" "$@"
