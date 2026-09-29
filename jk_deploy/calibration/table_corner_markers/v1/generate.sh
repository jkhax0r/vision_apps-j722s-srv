#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$HERE/generate.py"
python3 "$HERE/test_design.py"
