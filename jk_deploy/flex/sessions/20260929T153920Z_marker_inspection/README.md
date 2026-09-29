# First Physical Corner-Marker Inspection, 2026-09-29

Inspection only. The user requested a look at the table before developing an
automatic calibration script. No new calibration or mesh was generated, and
no runtime binaries or launch scripts were changed.

Target: `root@192.168.20.222`, Flex with four native 1920x1200 TEVS cameras.
Raw captures: `/root/jk-calibration-captures/20260929T153920Z_marker_inspection`.
Local copies are in `captures/`. Captures were sequential with 30 skipped
frames and one saved frame per camera. The old live demo was temporarily
stopped, then restarted with `/root/run_flex_grid.sh` using the same September
28 calibration in `/opt/jk-ti-srv-flex/grid_calibration`.

## Observations

OpenCV 4.12's default `DICT_4X4_50` detector, on the original input images,
decoded all eight expected marker observations without custom preprocessing:

| Camera | Visible IDs | Legacy checker intersections |
| --- | --- | --- |
| 1 | 1, 4 | 772 |
| 2 | 1, 2 | 775 |
| 3 | 2, 3 | Failed: insufficient consistent checker corners |
| 4 | 3, 4 | 844 |

Every ID connects two neighboring views. All four views show substantial
checkerboard coverage and the full marker patterns. Native marker edge lengths
are approximately 65-100 pixels. These are detections from a single stationary
capture per camera, not a measured detection rate over motion or lighting.

Wrinkles/folds are visible, especially in camera 2 and the right side of camera
3. Smooth the cloth without stretching for the cleanest geometric baseline.
Camera 3 nevertheless shows many visually clear checker intersections; the
legacy seeded-grid detector's failure is an important software robustness case,
not proof that this physical arrangement is unusable. The cause of that
detector failure was not diagnosed or fixed during this inspection.

Green plastic is fine: ID decoding used the black-and-white patterns, not
holder color. Physical label scale, holder seating, and marker/table-plane
offset were not measured from these images. Confirm label dimensions and edge
registration before relying on their metric offsets for automated cropping.

## Artifacts And Reproduction

- `marker_contact.png`: camera-numbered 2x2 view with detected IDs outlined.
- `inspection.json`: detected IDs, pixel corners, visibility, and available
  checker counts.
- `captures/input0.png` through `input3.png`: full-resolution originals.
- `captures/*.corners.npz` / `*.corners.png`: successful legacy checker outputs.
- `captures/input2.corners.*` is intentionally absent because that detection
  failed; no substituted or manually edited points were used.

From the repository root:

```sh
env PYTHONPATH=/tmp/jk-opencv4 python3 \
  jk_deploy/flex/prepare_captures.py \
  jk_deploy/flex/sessions/20260929T153920Z_marker_inspection/captures
env PYTHONPATH=/tmp/jk-opencv4 python3 \
  jk_deploy/flex/sessions/20260929T153920Z_marker_inspection/inspect_markers.py
```

The checker diagnostic called `fit_intrinsics.detect()` from
`jk_deploy/calibration/lens_20260908/fit_intrinsics.py` separately on each native
PNG, with `/tmp/jk-opencv4:/tmp/jk-scipy` in `PYTHONPATH`. It did not call the
intrinsic fitting, floor fitting, LUT generation, or deployment functions.

Keep this immutable capture as the first real-marker regression case for the
planned automatic calibration workflow. The display still uses the old fit
and should not be interpreted as a calibration of the new setup.
