#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SDK="${RTOS_SDK_ROOT:-$(dirname "$REPO")}"
SIM="$SDK/vxlib/packages/ti/vxlib/src/common/c6xsim"
"${CC_HOST:-cc}" -shared -fPIC -O2 -std=c99 \
    -DHOST_EMULATION -D_HOST_BUILD -D_TMS320C6600 -DTMS320C66X -DLITTLE_ENDIAN_HOST \
    -I"$SDK/vxlib/packages" -I"$SIM" -I"$SDK/tiovx/include" \
    -I"$REPO/kernels/srv/include" -I"$REPO/kernels/srv/c66" \
    "$HERE/ti_bowl_helper.c" "$SIM/C6xSimulator.c" "$SIM/c66_ag_intrins.c" \
    "$SIM/c66_data_sim.c" -Wl,--no-undefined -lm -o "$HERE/ti_bowl_helper.so"
