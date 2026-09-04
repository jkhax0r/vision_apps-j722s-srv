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
CALIBRATION_DIR="${CALIBRATION_DIR:-}"
REMOTE_STAGE="/tmp/jk-ti-srv-deploy-$$"

read -r -a SSH_ARGV <<< "${SSH_ARGS:-}"

for file in "$APP" "$LIB" "$LAUNCHER" "$CAPTURE_LAUNCHER"; do
    if [ ! -f "$file" ]; then
        echo "Missing build output: $file" >&2
        echo "Run ./jk_deploy/build.sh first." >&2
        exit 1
    fi
done

if [ -n "$CALIBRATION_DIR" ]; then
    for file in CALMAT.BIN LENS.BIN CHARTPOS.BIN; do
        if [ ! -f "$CALIBRATION_DIR/$file" ]; then
            echo "Missing calibration output: $CALIBRATION_DIR/$file" >&2
            exit 1
        fi
    done
fi

ssh "${SSH_ARGV[@]}" "$TARGET" "mkdir -p '$REMOTE_STAGE'"
scp "${SSH_ARGV[@]}" "$APP" "$LIB" "$LAUNCHER" "$CAPTURE_LAUNCHER" \
    "$TARGET:$REMOTE_STAGE/"
if [ -n "$CALIBRATION_DIR" ]; then
    scp "${SSH_ARGV[@]}" -r "$CALIBRATION_DIR" \
        "$TARGET:$REMOTE_STAGE/calibration-output"
fi

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

if [ -d "$REMOTE_STAGE/calibration-output" ]; then
    backup_path /opt/jk-ti-srv/calibration-output
    backup_path /opt/jk-ti-srv/psdkra/srv/srv_app/CALMAT.BIN
    backup_path /opt/jk-ti-srv/psdkra/srv/srv_app/LENS.BIN
    backup_path /opt/jk-ti-srv/psdkra/srv/srv_app/CHARTPOS.BIN

    install -d /opt/jk-ti-srv/psdkra/srv/srv_app
    rm -rf /opt/jk-ti-srv/calibration-output
    cp -a "$REMOTE_STAGE/calibration-output" /opt/jk-ti-srv/calibration-output
    install -m 0644 "$REMOTE_STAGE/calibration-output/CALMAT.BIN" \
        /opt/jk-ti-srv/psdkra/srv/srv_app/CALMAT.BIN
    install -m 0644 "$REMOTE_STAGE/calibration-output/LENS.BIN" \
        /opt/jk-ti-srv/psdkra/srv/srv_app/LENS.BIN
    install -m 0644 "$REMOTE_STAGE/calibration-output/CHARTPOS.BIN" \
        /opt/jk-ti-srv/psdkra/srv/srv_app/CHARTPOS.BIN
fi
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
