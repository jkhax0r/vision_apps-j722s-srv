#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROFILE="${PROFILE:-release}"
JOBS="${JOBS:-$(nproc)}"

exec make -C "$REPO_DIR" \
    TISDK_IMAGE=adas \
    SOC=j722s \
    PROFILE="$PROFILE" \
    BUILD_TARGET_MODE=yes \
    BUILD_EMULATION_MODE=no \
    BUILD_CPU_MPU1=yes \
    BUILD_CPU_MCU2_0=no \
    BUILD_CPU_C7x_1=no \
    BUILD_CPU_C7x_2=no \
    BUILD_LINUX_MPU=yes \
    BUILD_QNX_MPU=no \
    -j"$JOBS"
