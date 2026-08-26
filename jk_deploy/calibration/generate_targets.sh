#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/ti_srv_target_4x6.ps"

generate_target() {
    local offset_mm="$1"
    local output="$2"

    gs -q -dSAFER -dBATCH -dNOPAUSE \
        -sDEVICE=pdfwrite \
        -dDEVICEWIDTHPOINTS=288 \
        -dDEVICEHEIGHTPOINTS=432 \
        -dFIXEDMEDIA \
        -dtargetOffsetMM="$offset_mm" \
        -sOutputFile="$SCRIPT_DIR/$output" \
        "$SOURCE"
}

generate_target 0 ti_srv_target_4x6_centered.pdf
generate_target 10 ti_srv_target_4x6_10mm_up.pdf
generate_target -10 ti_srv_target_4x6_10mm_down.pdf
generate_target 10 ti_srv_target_4x6.pdf
