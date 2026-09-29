# Four-Camera Checker-Plane Calibration, 2026-09-28

Target: Flex, `root@192.168.20.222`. All four inputs are TechNexion AR0234,
1920x1200 UYVY. LCD: 1920x720. Captures taken around 20:39 UTC with a stationary
rig and board, sequentially rather than simultaneously.

## Run

```sh
/root/run_flex_grid.sh       # Left: four originals; right: calibrated stitch
/root/run_flex_grid.sh quad  # Four independent raw views
/root/run_flex_grid.sh stop  # Stop TI view and show Ahsoka again
/root/run_flex_stitch.sh    # Previous approximate surround preset
journalctl -u jk-flex-ti-srv.service -n 20 --no-pager
```

For raw-view teardown use `/opt/jk-ti-srv-flex/run_flex_four.sh stop`.
No boot services, BSP, firmware, or system libraries were changed. The new
renderer and app are private to `/opt/jk-ti-srv-flex`.

## Identity And Layout

| Camera | Marker | Input index | Sensor | Capture context |
| --- | --- | --- | --- | --- |
| 1 | Yellow circle | 0 | tevs 12-0039 | 1, currently /dev/video2 |
| 2 | Green block | 1 | tevs 13-003a | 2, currently /dev/video3 |
| 3 | Blue painter's tape | 2 | tevs 14-003b | 3, currently /dev/video4 |
| 4 | Unmarked | 3 | tevs 15-003c | 4, currently /dev/video5 |

The left pane is camera 1 / 2 above camera 3 / 4. Each original image is fit
without cropping or geometric correction into a 480x360 cell (480x300 image).
The right pane has camera 1 at the top, 2 right, 3 bottom, 4 left.

Crop is 44x45 checker cells, starting at (-16,-13) in camera 1's grid coordinate
system. Physical square pitch was not remeasured. The stitch occupies 704x720
pixels centered in its 960x720 pane, with black side margins to preserve square
geometry. Stretching it to the full half-screen width would distort the grid.

## Calibration And Limitations

The two saved September 8 lens profiles remain the shared lens prior: average
their projected pixel coordinates for each ray, not their coefficients. For
each camera, fit a homography from checker coordinates to undistorted rays;
interpolate remaining pixel residuals smoothly over observed checker corners.
Colored objects resolve integer grid origin and orientation. Actual checker
intersections, not raised marker centroids, determine the precise warp.

Marker component choices in `session.json` were visually checked for this
capture. They are not universal object identifiers. For example, camera 2's
largest blue component is not the intended tape marker. A fresh capture must
recheck these choices, overlap, and crop before accepting a fit.

| Camera | Retained corners | Held-out corners | Held-out RMS, input pixels |
| --- | --- | --- | --- |
| 1 | 884 | 79 | 0.884 |
| 2 | 847 | 75 | 1.132 |
| 3 | 802 | 72 | 0.965 |
| 4 | 860 | 80 | 0.810 |

Validation refits with held-out corners excluded. These are same-plane fit
checks, not independent metrology or new lens calibration. Outside the observed
corner hull, residual correction falls back to zero. Cloth wrinkles, lighting
differences, raised objects, and the tripod can still produce visible seams.
Moving camera mounts or changing their height above the plane needs a new fit.
This is a flat-plane map, not 3D reconstruction or TI's stock bowl calibration.

Live rendering still uses TI OpenVX/GLES and DMA-BUF camera imports. Python only
generates the offline mesh and previews. Original views reuse existing GPU
textures without a second capture pipeline. Only `APP_SRV_FOUR_COMPARE=1`
enables the split layout and associated framebuffer-orientation handling.

## Reproduce

From the repository root, with OpenCV 4.12, NumPy 2.2.6, and SciPy 1.15.3
available (the workstation currently stages these under `/tmp`):

```sh
export PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy
SESSION=jk_deploy/flex/sessions/20260928_four_grid
python3 jk_deploy/flex/prepare_captures.py "$SESSION"
python3 - "$SESSION" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "jk_deploy/calibration/lens_20260908")
from fit_intrinsics import detect
root = Path(sys.argv[1]) / "captures"
for i in range(4):
    detect(root / f"input{i}.png")
PY
python3 jk_deploy/flex/fit_floor.py "$SESSION"
python3 jk_deploy/flex/bake_floor.py "$SESSION"
python3 jk_deploy/flex/test_floor.py
python3 jk_deploy/flex/test_lut.py
JOBS=4 PROFILE=release ./jk_deploy/build.sh
```

Stop the TI view on the target, then deploy and restart:

```sh
ssh -o UserKnownHostsFile=/home/jkauf/.ssh/known_hosts_flex root@192.168.20.222 /root/run_flex_grid.sh stop
bash jk_deploy/flex/deploy_grid.sh "$SESSION"
ssh -o UserKnownHostsFile=/home/jkauf/.ssh/known_hosts_flex root@192.168.20.222 /root/run_flex_grid.sh
```

The deploy helper backs up the private runtime, preserves the approximate
`calibration/` preset, and installs this session into `grid_calibration/`.
Pre-grid runtime backup: `/root/jk-flex-before-grid-20260928T204445Z`.
A second backup, `20260928T204719Z`, contains the first grid version before
fixing display inversion/transparency; it is not the original runtime.

To collect another stationary session, run on the target:

```sh
/opt/jk-ti-srv-flex/capture_floor.sh /root/jk-calibration-captures/NEW_SESSION
```

The helper refuses to overwrite captures, stops the view, configures the media
graph, and saves one native frame per camera after skipping 30 frames. Copy
that new directory to a new local session's `captures/` directory. The current
session used the equivalent commands inline; the helper itself was syntax
checked but not used for the original capture.

## Files And Verification

- `captures/`: native UYVY frames, PNG originals, topology/format records,
  detected corners, and fit overlays. Raw frames and photos are ignored by git.
- `session.json`: selected marker components, camera order, crop, and feather.
- `floor_fits.json`: per-camera local grid fits and colored-object candidates.
- `calibration.json`: final transforms, validation, settings, and binary hashes.
- `four_mesh.bin`, `four_blend.bin`: TI mesh and blend data.
- `stitched.png`, `comparison.png`: offline visual checks; not tracked by git.

Remote originals: `/root/jk-calibration-captures/20260928_four_grid`.
Verified continuous live output at approximately 18.39 fps, all four original
views populated, yellow/top green/right blue/bottom in the stitch, opaque black
margins, and fullscreen 1920x720 placement. Compositor capture:
`/tmp/jk-flex-grid-screen2.bmp` on the target; PNG copy in workstation `/tmp`.
This is measured delivery rate, not the requested 30 fps. No GPU-utilization or
end-to-end latency measurement was made in this session.
