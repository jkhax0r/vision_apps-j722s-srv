# Two-GMSL Plywood Alignment, September 16

Target: `root@192.168.20.222`. Two TechNexion GMSL cameras; no analog inputs.
The user positioned the checkerboard on nominal 4 ft x 4 ft plywood, with the
3.5-inch TI square and a yellow 57.7 mm diameter, 12 mm tall circle visible
in both cameras. No additional objects were needed.

Square pitch is provisionally 27.25 mm, retained from the earlier cloth.
Confirmation was requested. The plywood dimensions are not used as exact
checker dimensions, and neither the raised circle nor its apparent diameter
is treated as a floor-plane measurement. A change to uniform pitch rescales
physical distances/poses; it does not change the pixel-to-grid correspondence.

## Captures And Fit

Fresh images captured at 2026-09-16T18:45:42Z (DUT clock) from the stable gmsl0/gmsl1
device links. Each packed UYVY file is 1920x1200, 4,608,000 bytes. PNGs are
rotated 180 degrees, consistent with the previous lens calibration. Local
files are under `captures/`; remote originals are under
`/root/jk-lens-calibration/pair_20260916T184543Z`.

Detected 1,085 / 1,351 candidate lattice corners in GMSL0 / GMSL1. The paper,
yellow circle and tripod regions are excluded using the rectangles in
`settings.json`. Seeds describe the black marker's printed TL, TR, BR, BL
corners; the TR corner nearest the yellow circle selects the grid origin.
The marker resolves integer-cell ambiguity; it does not need to be positioned
perfectly on a grid intersection. The fit checks its cross-camera agreement.

The separate ten-pose lens models in `../lens_20260908` remain unchanged.
Only the six-parameter camera poses relative to this checkerboard are fitted.
Pixel RMS after outlier rejection: GMSL0 4.67 px, GMSL1 3.80 px at 1920x1200.
Marker disagreement: 0.148 cells, approximately 4.04 mm at the assumed pitch.
This is a correspondence diagnostic, NOT a claim of 4 mm absolute accuracy.

Lens-based GPU projection is the live default. A cloth-interpolated `measured`
variant is also generated for comparison, with the same crop and occlusion
masks. The cloth still has visible folds and reflections; these and raised
objects are not removed by lens calibration or a floor-plane projection.

The corrected pane crops to x=-17.75, y=-6.75, width=22.5, height=28.125 grid
cells, approximately 613 x 766 mm at the assumed pitch. This is a subset of
the plywood, selected to avoid uncovered corners. The offline validity check
has zero uncovered output pixels for both methods. The raw panes retain each
camera's full field of view. The seam remains at x=-6.5.

The original 1.0-cell (nominal 28.4-pixel) blend is restored as the default
and live setting at the user's request. The narrow-blend experiment used
0.125 grid cells. Its nominal fade is 3.56 display pixels; the GPU interpolates
the sampled weights across one mesh interval, approximately 4.7 pixels.
Only blend weights change, not the camera poses, source-coordinate meshes,
crop, resolution or executable. This reduces cross-fading/ghosting but can
make parallax-induced object clipping and exposure differences more abrupt.

To regenerate the original nominal 28.4-pixel blend instead:

```sh
PAIR_BLEND_CELLS=1 bash jk_deploy/calibration/pair_plywood_20260916/rebuild.sh
```

Before the narrow experiment, the target calibration directory was copied
to `/opt/jk-ti-srv-pair/calibration/plywood_20260916_wide`. After stopping
the current instance, it can be run with `PAIR_ALIGNMENT=plywood_20260916_wide`.

Narrow-blend verification: both methods' camera fits and source-coordinate
meshes remained byte-identical; blend normalization and single-interval
transition checks passed. A 60-frame DUT run exited cleanly at 15.11 fps;
the inspected GPU render is `live_narrow_probe.png` (local only). The narrow
version was subsequently stopped and replaced with the original wider blend.
Its final frame is `/tmp/jk-plywood-narrow-live.raw` on the DUT. To reproduce
the narrow experiment, rebuild with `PAIR_BLEND_CELLS=0.125` and redeploy.

## Reproduce

From the isolated `vision_apps-j722s-srv-pair-test` worktree:

```sh
# Capture to a NEW directory only; do not replace this session's source images.
TARGET=root@192.168.20.222 bash jk_deploy/capture_gmsl_pair.sh /path/to/new/captures

# Recreate this session's meshes using its saved captures and corner files.
bash jk_deploy/calibration/pair_plywood_20260916/rebuild.sh
ssh root@192.168.20.222 systemctl stop jk-ti-srv-pair
TARGET=root@192.168.20.222 bash jk_deploy/deploy_pair_alignment.sh
```

The rebuild uses OpenCV 4.12.0, NumPy and SciPy from the existing isolated
`/tmp/jk-opencv4:/tmp/jk-scipy` paths; `CALIB_PYTHONPATH` can override these.
`fit_intrinsics.detect(Path(image))` produced the two saved `.corners.npz`
files. Scene photos and raw frames are local-only and git-ignored. The ready
BIN files can be deployed without photos or running a calibration fit.

## Run And Roll Back

On the DUT, stop any existing pair instance before running another:

```sh
systemctl stop jk-ti-srv-pair
/opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh
```

Default alignment is now `plywood_20260916`. To compare the interpolated
method use `PAIR_WARP_MODE=measured`; `PAIR_FULL_RES=0` selects the legacy
lower-resolution input path. Both controls retain their matching meshes.

The prior calibration was not overwritten. To select it explicitly:

```sh
PAIR_ALIGNMENT=final_20260908T184734Z /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh
```

It describes the OLD camera/board pose, not this setup. `PAIR_ALIGNMENT` also
selects which version `deploy_pair_alignment.sh` installs.

Exact finite test and final background launch used:

```sh
/opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 120 /tmp/jk-plywood-probe.raw
systemd-run --unit=jk-ti-srv-pair --collect /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 0 /tmp/jk-plywood-live.raw
```

## Verification

- All mesh-coordinate/orientation/blend tests and shell syntax checks passed.
- The shared generator reproduced all six prior-session BIN files byte-for-byte.
- DUT test: 120 frames in 7.754 seconds, 15.48 fps, exit 0. All ten shared
  allocations (23,564,476 bytes) freed. Live playback reached about 15.7 fps.
- Inputs remain native 1920x1200 UYVY, display remains 1280x800. The saved
  `live_probe.png` GPU render was inspected against `lens_preview.png`.
- Wayland surface visible at 0,0 with a 1280x800 source/destination and
  advancing frame counter. GMSL0 raw top-left, GMSL1 raw bottom-left,
  corrected two-camera view on the right.
- Pair executable is unchanged (`bf7688ac...`); this is calibration/launcher
  work only. The four-camera executable and system TI library hashes remain
  unchanged, and no boot services were modified.
