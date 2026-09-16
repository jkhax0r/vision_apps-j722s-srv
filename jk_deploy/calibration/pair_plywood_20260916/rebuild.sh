#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${CALIB_PYTHONPATH:-/tmp/jk-opencv4:/tmp/jk-scipy}${PYTHONPATH:+:$PYTHONPATH}"
python3 "$HERE/../pair_final_20260908T184734Z/make_pair.py" \
    --session "$HERE" --x -17.75 --y -6.75 --width 22.5 --seam-x -6.5 --feather 1
python3 "$HERE/../pair_final_20260908T184734Z/test_meshes.py" --session "$HERE"
