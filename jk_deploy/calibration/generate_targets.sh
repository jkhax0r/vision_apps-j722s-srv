#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/ti_srv_target_4x6.ps"
CHECKERBOARD_SOURCE="$SCRIPT_DIR/camera_intrinsics_checkerboard_4x6.ps"

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

gs -q -dSAFER -dBATCH -dNOPAUSE \
    -sDEVICE=pdfwrite \
    -dDEVICEWIDTHPOINTS=288 \
    -dDEVICEHEIGHTPOINTS=432 \
    -dFIXEDMEDIA \
    -dtargetOffsetMM=0 \
    -dedgeAnchors=true \
    -sOutputFile="$SCRIPT_DIR/ti_srv_target_4x6_centered_edge_anchors.pdf" \
    "$SOURCE"

gs -q -dSAFER -dBATCH -dNOPAUSE \
    -sDEVICE=pdfwrite \
    -dDEVICEWIDTHPOINTS=288 \
    -dDEVICEHEIGHTPOINTS=432 \
    -dFIXEDMEDIA \
    -sOutputFile="$SCRIPT_DIR/camera_intrinsics_checkerboard_4x6_edge_anchors.pdf" \
    "$CHECKERBOARD_SOURCE"

render_sp410_png() {
    local input="$1"
    local output="$2"

    # A complete 4x6-inch label at the SP410 native 203 DPI. Baking the white
    # margins into a fixed raster stops PDF viewers from cropping/recentering.
    gs -q -dSAFER -dBATCH -dNOPAUSE \
        -sDEVICE=pngmono \
        -r203 \
        -g812x1218 \
        -dFIXEDMEDIA \
        -dPDFFitPage \
        -sOutputFile="$SCRIPT_DIR/$output" \
        "$SCRIPT_DIR/$input"
}

render_sp410_png ti_srv_target_4x6_centered.pdf ti_srv_target_4x6_centered_203dpi.png
render_sp410_png ti_srv_target_4x6_10mm_up.pdf ti_srv_target_4x6_10mm_up_203dpi.png
render_sp410_png ti_srv_target_4x6_10mm_down.pdf ti_srv_target_4x6_10mm_down_203dpi.png
render_sp410_png ti_srv_target_4x6_centered_edge_anchors.pdf ti_srv_target_4x6_centered_edge_anchors_203dpi.png
render_sp410_png camera_intrinsics_checkerboard_4x6_edge_anchors.pdf camera_intrinsics_checkerboard_4x6_edge_anchors_203dpi.png
