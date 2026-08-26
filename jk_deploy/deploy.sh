#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROFILE="${PROFILE:-release}"
TARGET="${TARGET:?Set TARGET to root@TARGET_IP}"
OUT_DIR="$REPO_DIR/out/J722S/A53/LINUX/$PROFILE"
APP="$OUT_DIR/vx_app_jk_srv_live.out"
LIB="$OUT_DIR/libtivision_apps.so.11.0.0"
LAUNCHER="$SCRIPT_DIR/run_jk_srv_live.sh"
CAPTURE_LAUNCHER="$SCRIPT_DIR/capture_calibration_images.sh"
REMOTE_STAGE="/tmp/jk-ti-srv-deploy-$$"

read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"

for file in "$APP" "$LIB" "$LAUNCHER" "$CAPTURE_LAUNCHER"; do
    if [ ! -f "$file" ]; then
        echo "Missing build output: $file" >&2
        echo "Run ./jk_deploy/build.sh first." >&2
        exit 1
    fi
done

ssh "${SSH_ARGV[@]}" "$TARGET" "mkdir -p '$REMOTE_STAGE'"
scp "${SSH_ARGV[@]}" "$APP" "$LIB" "$LAUNCHER" "$CAPTURE_LAUNCHER" \
    "$TARGET:$REMOTE_STAGE/"

ssh "${SSH_ARGV[@]}" "$TARGET" "REMOTE_STAGE='$REMOTE_STAGE' bash -s" <<'REMOTE'
set -euo pipefail

if pgrep -f '[v]x_app_jk_srv_live.out' >/dev/null; then
    echo "Stop vx_app_jk_srv_live.out before deploying." >&2
    exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/root/jk-ti-srv-backups/$STAMP"

backup_path() {
    local path="$1"
    if [ -e "$path" ] || [ -L "$path" ]; then
        mkdir -p "$BACKUP_DIR$(dirname "$path")"
        cp -a "$path" "$BACKUP_DIR$path"
    fi
}

mkdir -p "$BACKUP_DIR" /opt/jk-ti-srv
backup_path /opt/jk-ti-srv/vx_app_jk_srv_live.out
backup_path /opt/jk-ti-srv/run_jk_srv_live.sh
backup_path /opt/jk-ti-srv/capture_calibration_images.sh
backup_path /usr/lib/libtivision_apps.so.11.0.0
backup_path /usr/lib/libtivision_apps.so

install -m 0755 "$REMOTE_STAGE/vx_app_jk_srv_live.out" \
    /opt/jk-ti-srv/vx_app_jk_srv_live.out
install -m 0755 "$REMOTE_STAGE/run_jk_srv_live.sh" \
    /opt/jk-ti-srv/run_jk_srv_live.sh
install -m 0755 "$REMOTE_STAGE/capture_calibration_images.sh" \
    /opt/jk-ti-srv/capture_calibration_images.sh
install -m 0644 "$REMOTE_STAGE/libtivision_apps.so.11.0.0" \
    /usr/lib/libtivision_apps.so.11.0.0
ln -sfn libtivision_apps.so.11.0.0 /usr/lib/libtivision_apps.so
ldconfig 2>/dev/null || true
rm -rf "$REMOTE_STAGE"
sync

echo "Installed JK TI SRV runtime."
echo "Backup: $BACKUP_DIR"
echo "Run: /opt/jk-ti-srv/run_jk_srv_live.sh"
REMOTE
