#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! python3 -c 'import cadquery' >/dev/null 2>&1; then
    cat >&2 <<'EOF'
CadQuery is required to regenerate these files.

Install it in a virtual environment, then rerun this script:
  python3 -m venv .venv
  .venv/bin/pip install cadquery
  PATH="$PWD/.venv/bin:$PATH" ./generate.sh
EOF
    exit 1
fi

python3 "$SCRIPT_DIR/generate_camera_rig.py" \
    --output-dir "$SCRIPT_DIR/generated" "$@"
python3 "$SCRIPT_DIR/render_preview.py" \
    --input-dir "$SCRIPT_DIR/generated" \
    --output "$SCRIPT_DIR/camera_rig_preview.png"
