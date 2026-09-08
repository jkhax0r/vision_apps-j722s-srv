#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${TARGET:?Set TARGET to root@TARGET_IP}"
CAL_DIR="$SCRIPT_DIR/calibration/pair_final_20260908T184734Z"
read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"
FILES=("$CAL_DIR/lens_mesh.bin" "$CAL_DIR/lens_blend.bin"
       "$CAL_DIR/measured_mesh.bin" "$CAL_DIR/measured_blend.bin" "$CAL_DIR/alignment.json"
       "$SCRIPT_DIR/run_gmsl_pair_test.sh" "$SCRIPT_DIR/run_gmsl_pair_calibrated.sh")
for file in "${FILES[@]}"; do
    test -s "$file" || { echo "Missing $file" >&2; exit 1; }
done
STAGE="$(ssh "${SSH_ARGV[@]}" "$TARGET" 'mktemp -d /tmp/jk-pair-alignment.XXXXXX')"
scp "${SSH_ARGV[@]}" "${FILES[@]}" "$TARGET:$STAGE/"
ssh "${SSH_ARGV[@]}" "$TARGET" "STAGE='$STAGE' bash -s" <<'REMOTE'
set -euo pipefail
DEST=/opt/jk-ti-srv-pair
test -x "$DEST/vx_app_jk_srv_live.out"
CAL_DIR="$DEST/calibration/final_20260908T184734Z"
install -d "$CAL_DIR"
install -m 0644 "$STAGE/"*.bin "$STAGE/alignment.json" "$CAL_DIR/"
install -m 0755 "$STAGE/run_gmsl_pair_test.sh" "$STAGE/run_gmsl_pair_calibrated.sh" "$DEST/"
rm -r -- "$STAGE"
echo "Installed pair alignment only. No app binary, library or boot unit changed."
echo "Run $DEST/run_gmsl_pair_calibrated.sh"
REMOTE
