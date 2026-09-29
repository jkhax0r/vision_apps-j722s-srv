#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/../.." && pwd)
SESSION=${1:-$HERE/sessions/20260928_four_grid}
TARGET=${TARGET:-root@192.168.20.222}
OUT="$REPO/out/J722S/A53/LINUX/${PROFILE:-release}"
read -r -a SSH_ARGS <<< "${SSH_OPTIONS:--o BatchMode=yes -o ConnectTimeout=6 -o ServerAliveInterval=3 -o ServerAliveCountMax=2 -o UserKnownHostsFile=/home/jkauf/.ssh/known_hosts_flex}"
for file in "$SESSION/four_mesh.bin" "$SESSION/four_blend.bin" "$SESSION/calibration.json" \
    "$OUT/vx_app_jk_srv_live.out" "$OUT/libtivision_apps.so.11.0.0"; do
    test -s "$file"
done
STAGE=$(ssh "${SSH_ARGS[@]}" "$TARGET" 'mktemp -d /tmp/jk-flex-grid.XXXXXX')
scp "${SSH_ARGS[@]}" "$OUT/vx_app_jk_srv_live.out" "$OUT/libtivision_apps.so.11.0.0" \
    "$HERE/run_flex_stitch.sh" "$HERE/run_flex_grid.sh" "$HERE/capture_floor.sh" \
    "$SESSION/four_mesh.bin" "$SESSION/four_blend.bin" "$SESSION/calibration.json" \
    "$TARGET:$STAGE/"
ssh "${SSH_ARGS[@]}" "$TARGET" "STAGE='$STAGE' bash -s" <<'REMOTE'
set -euo pipefail
DEST=/opt/jk-ti-srv-flex
test -x "$DEST/run_flex_four.sh"
if pgrep -f '^/opt/jk-ti-srv-flex/vx_app_jk_srv_live' >/dev/null; then
    echo "Stop the TI stitch before replacing its private runtime." >&2
    exit 1
fi
BACKUP="/root/jk-flex-before-grid-$(date -u +%Y%m%dT%H%M%SZ)"
cp -a "$DEST" "$BACKUP"
install -d "$DEST/grid_calibration"
install -m 0755 "$STAGE/vx_app_jk_srv_live.out" "$STAGE/run_flex_stitch.sh" \
    "$STAGE/run_flex_grid.sh" "$STAGE/capture_floor.sh" "$DEST/"
install -m 0644 "$STAGE/libtivision_apps.so.11.0.0" "$DEST/"
install -m 0644 "$STAGE/four_mesh.bin" "$STAGE/four_blend.bin" \
    "$STAGE/calibration.json" "$DEST/grid_calibration/"
if [ ! -e /root/run_flex_grid.sh ] && [ ! -L /root/run_flex_grid.sh ]; then
    ln -s "$DEST/run_flex_grid.sh" /root/run_flex_grid.sh
fi
rm -r -- "$STAGE"
echo "Previous private runtime: $BACKUP"
echo "Start calibrated comparison: /root/run_flex_grid.sh"
REMOTE
