# Lowered Tripod Calibration

Captured September 16, 2026 at 19:54:19 UTC from both GMSL cameras after
lowering the tripod. Target: `root@192.168.20.222`. Remote originals:
`/root/jk-lens-calibration/pair_20260916T195420Z`; local images are in `captures/`.
The prior `plywood_20260916` session is preserved, not overwritten.

The marker's printed bottom-right black-square corner is nearest the yellow
circle in these images. That corner anchors the 27.25 mm checker lattice.
The circle is a correspondence cue, not a floor-plane or height measurement.
Paper, circle, tools, cup, book/display and tripod regions are masked from
the floor fit. Settings and hand-seeded marker corners are in `settings.json`.

## Result

- GMSL0: 648 detected lattice candidates; 400 retained after masking/rejection.
- GMSL1: 669 candidates; 503 retained.
- Pose reprojection RMS: 4.81 / 3.90 native pixels.
- Marker cross-camera mismatch: 0.104 cell, about 2.84 mm at assumed pitch.
  This is a fit diagnostic, not independently measured absolute accuracy.
- Estimated camera heights above the board: 410 / 401 mm; baseline about 165 mm.
- Each camera retains its own unchanged K/D from `../lens_20260908`.

The old crop had about 19.5% uncovered pixels at the lower height. The new
crop is x=-10.5, y=-7.5, width=13.5, height=16.875 checker cells, roughly
368 x 460 mm. It keeps the marker/circle region and has zero uncovered
pixels in flat and bowl modes. The seam is x=-3.75; the wider one-cell
blend is retained (about 47 display pixels at this crop).

`lens` is the flat, lens-corrected physical floor projection; `measured` is
the optional checker-interpolated map. `bowl` uses TI's bowl generator via
the existing two-camera adapter, with 0-50 mm rise over the new crop and
approximately 132 mm base half-size. Flat and bowl blend bytes are identical.
See [the bowl implementation notes](../pair_plywood_20260916/BOWL.md).
Raised objects still have parallax; the calibration aligns the board plane.

Native inputs remain 1920x1200 UYVY. The fullscreen 1280x800 layout retains
unwarped GMSL0/GMSL1 on the left and the corrected pair on the right.
Cropping the corrected pane does not reduce capture resolution or raw FOV.

## Use / Reproduce

On the DUT, this is now the default calibration:

```sh
~/srv_view.sh flat
~/srv_view.sh bowl
~/srv_view.sh          # toggle, retaining the active calibration session
~/srv_view.sh status
```

From the isolated `vision_apps-j722s-srv-pair-test` worktree:

```sh
# Already run; capture always uses a new directory.
TARGET=root@192.168.20.222 PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy \
  bash jk_deploy/capture_gmsl_pair.sh jk_deploy/calibration/pair_lowered_20260916T1954/captures

# After capture, fit_intrinsics.detect() produced each gmsl*.corners.npz.
# Rebuild all maps from saved corner files, images and settings:
bash jk_deploy/calibration/pair_lowered_20260916T1954/rebuild.sh
ssh root@192.168.20.222 systemctl stop jk-ti-srv-pair
TARGET=root@192.168.20.222 bash jk_deploy/deploy_pair_alignment.sh
ssh root@192.168.20.222 'PAIR_ALIGNMENT=lowered_20260916T1954 /root/srv_view.sh flat'
```

The session contains the saved poses, all nine deployment BIN files,
bowl hash manifest/surface, detector corner NPZ files and rebuild script.
Camera photos/raw frames and previews remain local-only. To inspect the
previous calibration explicitly, set `PAIR_ALIGNMENT=plywood_20260916`
when invoking `srv_view.sh`; it describes the OLD tripod position.

## Verification

Mesh tests and all five bowl tests pass for this session; the original
session's five tests still pass. The failure-preservation test now injects
an incompatible blend into a temporary session instead of assuming that
a particular bowl height will always fail for every camera pose.

Finite DUT test used `run_gmsl_pair_calibrated.sh 90 /tmp/jk-lowered-flat-probe.raw`:
90 frames in 5.815 seconds, 15.48 fps, exit 0, all shared allocations freed.
The GPU render was inspected as `live_flat_probe.png`; no black crop gaps.
Both new bowl and flat modes were exercised live, leaving flat running.
No executable, system GPU library or boot service changes were needed.
