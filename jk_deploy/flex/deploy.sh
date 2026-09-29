#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd -- "$HERE/../.." && pwd)
TARGET=${TARGET:-root@192.168.20.222}
OUT="$REPO/out/J722S/A53/LINUX/${PROFILE:-release}"
read -r -a SSH_ARGS <<< "${SSH_OPTIONS:--o BatchMode=yes -o ConnectTimeout=6 -o ServerAliveInterval=3 -o ServerAliveCountMax=2 -o UserKnownHostsFile=/home/jkauf/.ssh/known_hosts_flex}"
for name in vx_app_jk_srv_live.out libtivision_apps.so.11.0.0; do
    test -s "$OUT/$name"
done
STAGE=$(ssh "${SSH_ARGS[@]}" "$TARGET" 'mktemp -d /tmp/jk-flex-deploy.XXXXXX')
scp "${SSH_ARGS[@]}" "$OUT/vx_app_jk_srv_live.out" "$OUT/libtivision_apps.so.11.0.0" \
    "$HERE/run_flex_four.sh" "$HERE/run_flex_stitch.sh" "$HERE/README.md" "$TARGET:$STAGE/"
scp "${SSH_ARGS[@]}" -r "$HERE/calibration" "$TARGET:$STAGE/"
ssh "${SSH_ARGS[@]}" "$TARGET" "STAGE='$STAGE' bash -s" <<'REMOTE'
set -euo pipefail
DEST=/opt/jk-ti-srv-flex
if pgrep -f '^/opt/jk-ti-srv-flex/vx_app_jk_srv_live' >/dev/null; then
    echo "Stop the TI stitch before replacing its private runtime." >&2
    exit 1
fi
if [ -d "$DEST" ]; then
    BACKUP="/root/jk-flex-backup-$(date -u +%Y%m%dT%H%M%SZ)"
    cp -a "$DEST" "$BACKUP"
    echo "Previous private runtime: $BACKUP"
fi
install -d "$DEST/calibration"
install -m 0755 "$STAGE/vx_app_jk_srv_live.out" "$STAGE/run_flex_four.sh" "$STAGE/run_flex_stitch.sh" "$DEST/"
install -m 0644 "$STAGE/libtivision_apps.so.11.0.0" "$STAGE/README.md" "$DEST/"
install -m 0644 "$STAGE/calibration/four_mesh.bin" "$STAGE/calibration/four_blend.bin" \
    "$STAGE/calibration/settings.json" "$DEST/calibration/"
ln -sfn libtivision_apps.so.11.0.0 "$DEST/libtivision_apps.so"
if [ ! -e /root/run_flex_stitch.sh ] && [ ! -L /root/run_flex_stitch.sh ]; then
    ln -s "$DEST/run_flex_stitch.sh" /root/run_flex_stitch.sh
fi
rm -r -- "$STAGE"
echo "Installed private Flex runtime. No BSP, system library or boot-service changes."
echo "Start: $DEST/run_flex_stitch.sh"
REMOTE
