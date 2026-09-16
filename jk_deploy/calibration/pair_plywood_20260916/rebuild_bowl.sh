#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${CALIB_PYTHONPATH:-/tmp/jk-opencv4:/tmp/jk-scipy}${PYTHONPATH:+:$PYTHONPATH}"
bash "$HERE/build_bowl_helper.sh"
python3 "$HERE/make_bowl.py" "$@"
python3 "$HERE/test_bowl.py"
