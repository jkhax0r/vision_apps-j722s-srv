#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET="${TARGET:?Set TARGET to root@TARGET_IP}"
OUT_DIR="$REPO_DIR/out/J722S/A53/LINUX/${PROFILE:-release}"
CAL_DIR="$SCRIPT_DIR/calibration/pair_20260908"
read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"
FILES=("$OUT_DIR/vx_app_jk_srv_live.out" "$OUT_DIR/libtivision_apps.so.11.0.0"
    "$SCRIPT_DIR/run_jk_srv_live.sh" "$SCRIPT_DIR/run_gmsl_pair_test.sh"
    "$CAL_DIR/split_mesh.bin" "$CAL_DIR/split_blend.bin" "$CAL_DIR/split_settings.json")
for file in "${FILES[@]}"; do
    test -s "$file" || { echo "Missing $file" >&2; exit 1; }
done

STAGE="$(ssh "${SSH_ARGV[@]}" "$TARGET" 'mktemp -d /tmp/jk-pair-deploy.XXXXXX')"
scp "${SSH_ARGV[@]}" "${FILES[@]}" "$TARGET:$STAGE/"
ssh "${SSH_ARGV[@]}" "$TARGET" "STAGE='$STAGE' bash -s" <<'REMOTE'
set -euo pipefail
DEST=/opt/jk-ti-srv-pair
if pgrep -f '^./vx_app_jk_srv_live.out|^/opt/jk-ti-srv-pair/vx_app_jk_srv_live.out' >/dev/null; then
    echo "Stop the live SRV app before deploying the pair test." >&2
    exit 1
fi
install -d "$DEST/lib" "$DEST/calibration"
install -m 0755 "$STAGE/vx_app_jk_srv_live.out" "$STAGE/run_jk_srv_live.sh" \
    "$STAGE/run_gmsl_pair_test.sh" "$DEST/"
install -m 0644 "$STAGE/libtivision_apps.so.11.0.0" "$DEST/lib/"
ln -sfn libtivision_apps.so.11.0.0 "$DEST/lib/libtivision_apps.so"
install -m 0644 "$STAGE/split_mesh.bin" "$STAGE/split_blend.bin" \
    "$STAGE/split_settings.json" "$DEST/calibration/"
rm -r -- "$STAGE"
echo "Installed isolated test: $DEST/run_gmsl_pair_test.sh"
echo "The four-camera runtime and system libraries were not replaced."
REMOTE
