#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${TARGET:?Set TARGET to root@TARGET_IP}"
CAL_DIR="$SCRIPT_DIR/calibration/pair_final_20260908T184734Z"
APP="$SCRIPT_DIR/../out/J722S/A53/LINUX/${PROFILE:-release}/vx_app_jk_srv_live.out"
read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"
FILES=("$CAL_DIR/lens_mesh.bin" "$CAL_DIR/lens_blend.bin"
       "$CAL_DIR/measured_mesh.bin" "$CAL_DIR/measured_blend.bin" "$CAL_DIR/alignment.json"
       "$CAL_DIR/lens_fullres_mesh.bin" "$CAL_DIR/measured_fullres_mesh.bin" "$APP"
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
if pgrep -f '^./vx_app_jk_srv_live.out|^/opt/jk-ti-srv-pair/vx_app_jk_srv_live.out' >/dev/null; then
    echo "Stop the live SRV app before deploying the pair alignment." >&2
    exit 1
fi
CAL_DIR="$DEST/calibration/final_20260908T184734Z"
install -d "$CAL_DIR"
install -m 0644 "$STAGE/"*.bin "$STAGE/alignment.json" "$CAL_DIR/"
install -m 0755 "$STAGE/run_gmsl_pair_test.sh" "$STAGE/run_gmsl_pair_calibrated.sh" "$DEST/"
install -m 0755 "$STAGE/vx_app_jk_srv_live.out" "$DEST/"
rm -r -- "$STAGE"
echo "Installed isolated pair app and alignment. No system library, four-camera app or boot unit changed."
echo "Run $DEST/run_gmsl_pair_calibrated.sh"
REMOTE
