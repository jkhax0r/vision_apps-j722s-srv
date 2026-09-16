#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$HERE/../pair_plywood_20260916"
export PYTHONPATH="${CALIB_PYTHONPATH:-/tmp/jk-opencv4:/tmp/jk-scipy}${PYTHONPATH:+:$PYTHONPATH}"
python3 "$HERE/../pair_final_20260908T184734Z/make_pair.py" \
    --session "$HERE" --x -10.5 --y -7.5 --width 13.5 --seam-x -3.75 --feather 1
python3 "$HERE/../pair_final_20260908T184734Z/test_meshes.py" --session "$HERE"
bash "$TOOLS/build_bowl_helper.sh"
python3 "$TOOLS/make_bowl.py" --session "$HERE" --height-mm 50
python3 "$TOOLS/test_bowl.py" --session "$HERE"
python3 "$HERE/make_table.py"
python3 "$HERE/test_table.py"
