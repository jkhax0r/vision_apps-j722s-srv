# Second Corner-Marker Inspection, 2026-09-29

After this inspection, the user requested a live stitch from these captures.
See [STITCH.md](STITCH.md) for that subsequent calibration and deployment;
the inspection record below describes the earlier, unchanged-runtime check.

User requested another check after adjusting the setup. This is inspection
only: no new calibration, LUT, runtime binary, or launch-script changes.

Fresh native 1920x1200 captures were saved on the Flex at
`/root/jk-calibration-captures/20260929T155359Z_marker_inspection` and copied
locally to `captures/`. The existing `capture_floor.sh` briefly stopped the
TI viewer, configured capture, skipped 30 frames, and saved one frame per camera.
`/root/run_flex_grid.sh` then restored the existing September 28 calibration.

## Results

The same default OpenCV 4.12 `DICT_4X4_50` detector again found all eight marker
observations. The same legacy checker detector now succeeded in all four views:

| Camera | IDs | Checker intersections | Previous capture |
| --- | --- | --- | --- |
| 1 | 1, 4 | 774 | 772 |
| 2 | 1, 2 | 760 | 775 |
| 3 | 2, 3 | 826 | Detection failed |
| 4 | 3, 4 | 790 | 844 |

The cloth looks visibly flatter, especially in camera 2. There are still some
creases. Camera 1 now has a hanging strap and cable obscuring part of the grid;
tuck these out of view for a cleaner calibration baseline. Neither currently
prevents decoding the corner markers.

This is a successful static feature-detection check, NOT completed calibration
or validation of stitching accuracy. The improvement in camera 3 is observed;
the precise cause of the earlier detector failure has not been isolated.
Keep both captures for robustness tests rather than discarding the failure.

## Artifacts

- `marker_contact.png`: four annotated views with camera numbers and marker IDs.
- `inspection.json`: pixel marker corners, shared-ID visibility, checker counts.
- `checker_status.json`: success/failure from individual legacy detector calls.
- `captures/input[0-3].png` and `.uyvy`: full native originals.
- `captures/input[0-3].corners.npz` and `.corners.png`: checker detections.

## Reproduce

From the repository root, with the staged OpenCV/SciPy packages:

```sh
export PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy
python3 jk_deploy/flex/prepare_captures.py \
  jk_deploy/flex/sessions/20260929T155359Z_marker_inspection/captures
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "jk_deploy/calibration/lens_20260908")
from fit_intrinsics import detect
root = Path("jk_deploy/flex/sessions/20260929T155359Z_marker_inspection")
for i in range(4):
    detect(root / "captures" / f"input{i}.png")
sys.path.insert(0, "jk_deploy/flex/sessions/20260929T153920Z_marker_inspection")
import inspect_markers
inspect_markers.ROOT = root
inspect_markers.main()
PY
```

No intrinsic calibration, floor fitting, mesh generation, or deployment was
performed. The live display remains on its previous calibration.
