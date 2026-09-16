#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")"
UNIT=jk-ti-srv-pair.service
ACTION="${1:-toggle}"
case "$ACTION" in
    flat|bowl|toggle|status) ;;
    *) echo "Usage: $0 [flat|bowl|toggle|status]" >&2; exit 2 ;;
esac
exec 9>/run/lock/jk-ti-srv-pair-switch.lock
flock -w 15 9
CURRENT=lens
ENVIRONMENT="$(systemctl show "$UNIT" -p Environment --value 2>/dev/null || true)"
for item in $ENVIRONMENT; do
    case "$item" in PAIR_WARP_MODE=*) CURRENT="${item#*=}" ;; esac
done
STATE="$(systemctl show "$UNIT" -p ActiveState --value 2>/dev/null || true)"
if [ "$ACTION" = status ]; then
    echo "Pair view: ${CURRENT/lens/flat}; service: ${STATE:-not loaded}"
    exit 0
fi
if [ "$ACTION" = toggle ]; then
    if [ "$CURRENT" = bowl ]; then ACTION=flat; else ACTION=bowl; fi
fi
MODE="$ACTION"
if [ "$MODE" = flat ]; then MODE=lens; fi
ALIGNMENT="${PAIR_ALIGNMENT:-plywood_20260916}"
# Validate before interrupting a working display. The A/B pair always uses
# native-resolution inputs and the same alignment, crop and blend.
PAIR_WARP_MODE="$MODE" PAIR_ALIGNMENT="$ALIGNMENT" PAIR_FULL_RES=1 \
    "$SCRIPT_DIR/run_gmsl_pair_calibrated.sh" --check
systemctl stop "$UNIT" 2>/dev/null || true
systemctl reset-failed "$UNIT" 2>/dev/null || true
systemd-run --quiet --unit="$UNIT" --collect \
    --setenv="PAIR_WARP_MODE=$MODE" --setenv="PAIR_ALIGNMENT=$ALIGNMENT" \
    --setenv=PAIR_FULL_RES=1 \
    "$SCRIPT_DIR/run_gmsl_pair_calibrated.sh" 0 "/tmp/jk-pair-$ACTION-live.raw"
INVOCATION="$(systemctl show "$UNIT" -p InvocationID --value)"
for attempt in $(seq 1 60); do
    if ! systemctl is-active --quiet "$UNIT"; then break; fi
    if journalctl "_SYSTEMD_INVOCATION_ID=$INVOCATION" -n 20 --no-pager -o cat | \
            grep -q 'jk_srv_live: frame '; then
        echo "Showing $ACTION (1920x1200 inputs, same wider blend)."
        exit 0
    fi
    sleep 0.1
done
echo "View did not confirm live frames. Inspect: journalctl -u $UNIT -n 40" >&2
exit 1
