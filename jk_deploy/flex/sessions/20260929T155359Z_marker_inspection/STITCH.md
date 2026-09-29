# Live Marker-Based Stitch Preview, 2026-09-29

The user requested a stitched version after the second inspection. This preset
uses that inspection's four full-resolution captures. No new capture was needed.

## Live Commands

```sh
/root/run_flex_markers.sh       # New marker-based table fit, raw left / stitch right
/root/run_flex_grid.sh          # September 28 colored-object/grid fit, unchanged
/root/run_flex_markers.sh stop  # Stop the TI display
```

New files on the Flex only:

- `/opt/jk-ti-srv-flex/grid_calibration_20260929_markers/four_mesh.bin`
- `/opt/jk-ti-srv-flex/grid_calibration_20260929_markers/four_blend.bin`
- `/opt/jk-ti-srv-flex/grid_calibration_20260929_markers/calibration.json`
- `/opt/jk-ti-srv-flex/run_flex_markers.sh`
- `/root/run_flex_markers.sh` symlink to that launcher.

Existing calibration directories, executable, TI library, kernel, drivers,
system libraries, and boot services were not replaced. Switching launchers
stops/restarts the same transient TI viewer service. Only the LUT selection is
different. Verified at about 18.39 fps with advancing frame counters.

## How This Fit Was Obtained

1. `fit_floor.py` fitted each previously detected checker grid using the existing
   shared lens prior. It also saved the local grid/pixel correspondence arrays.
2. `align_markers.py` detected canonical corners of ArUco IDs 1-4. The expected
   neighbor pairs are 1/4, 1/2, 2/3, and 3/4 in camera input order.
3. The initial homography-only inverse picked a one-cell-wrong rear-camera
   shift. A gray blend band and opposite black/white checker phase revealed it.
   Nothing from that first attempt was installed on the target.
4. A local thin-plate RBF correction of the inverse grid map, based on the
   detected checker intersections, improved the marker coordinate estimates.
   Enumerating square-grid rotations/reflections and integer translations then
   selected consistent checker phase in all four cameras. An explicit checker
   luminance test now rejects a phase mismatch before baking.
5. The marker-cap geometry extrapolates the four approximate physical table
   corners. Their axis-aligned rectangle defines the provisional crop, about
   44.20 x 45.11 checker cells. This assumes the labels have the intended
   orientation and both holder lips register against the table edges.
6. `bake_floor.py` reuses its existing shared-lens/homography/smooth-residual
   plane mapping and TI mesh/blend encoding. It now accepts explicitly aligned
   models in `session.json`; the old colored-object alignment path is unchanged.

Final global grid transforms, in input order:

```text
0: R=[[-1,0],[0,-1]], shift=[ 0, 0]
1: R=[[-1,0],[0,-1]], shift=[10, 2]
2: R=[[ 0,1],[-1,0]], shift=[ 0,18]
3: R=[[ 1,0],[0, 1]], shift=[-9, 8]
```

Same-plane held-out checker RMS is approximately 0.94, 0.80, 0.86, and 0.54
input pixels. This does not measure cross-camera seam error or metric accuracy.
Marker-corner disagreement remains about 0.11-0.47 checker cells, depending on
the corner. Some marker-edge doubling and lighting differences remain visible.
The labels are above the checker plane, and lens/cloth errors outside dense
checker coverage are still approximate. Raised tripod/strap objects retain
parallax. No new lens intrinsics were fitted.

This is a working preview and an initial marker-aware alignment helper, not the
completed robust calibration workflow: fresh capture orchestration, automatic
checker failure recovery, generalized camera order, stronger edge extrapolation,
and validated table-boundary fitting remain future work. The quarter-turn
orientation and ID pair convention are currently specific to this rig.

## Reproduce On The Workstation

From the repository root, after the inspection's saved corner detections:

```sh
export PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy
SESSION=jk_deploy/flex/sessions/20260929T155359Z_marker_inspection
python3 jk_deploy/flex/fit_floor.py "$SESSION"
python3 jk_deploy/flex/align_markers.py "$SESSION"
python3 jk_deploy/flex/bake_floor.py "$SESSION"
python3 -m unittest discover -s jk_deploy/flex -p 'test_*.py'
```

Inspect `comparison.png` and `stitched.png` before installing. `live_stitch.png`
is the actual compositor screenshot after deployment, not the offline preview.
Binary hashes and quality data are saved in `calibration.json`.

## Deployment Performed

With the existing private Flex runtime already installed, the following commands
created a separate preset. They intentionally do not overwrite the old preset:

```sh
TARGET=root@192.168.20.222
KEYS=/home/jkauf/.ssh/known_hosts_flex
SESSION=jk_deploy/flex/sessions/20260929T155359Z_marker_inspection
DEST=/opt/jk-ti-srv-flex/grid_calibration_20260929_markers
ssh -o UserKnownHostsFile="$KEYS" "$TARGET" "mkdir '$DEST'"
scp -o UserKnownHostsFile="$KEYS" "$SESSION/four_mesh.bin" \
  "$SESSION/four_blend.bin" "$SESSION/calibration.json" "$TARGET:$DEST/"
scp -o UserKnownHostsFile="$KEYS" jk_deploy/flex/run_flex_markers.sh \
  "$TARGET:/opt/jk-ti-srv-flex/run_flex_markers.sh"
ssh -o UserKnownHostsFile="$KEYS" "$TARGET" \
  'chmod 0755 /opt/jk-ti-srv-flex/run_flex_markers.sh'
ssh -o UserKnownHostsFile="$KEYS" "$TARGET" \
  'ln -s /opt/jk-ti-srv-flex/run_flex_markers.sh /root/run_flex_markers.sh'
ssh -o UserKnownHostsFile="$KEYS" "$TARGET" /root/run_flex_markers.sh
```

These first-install commands refuse existing directory/symlink names; use a new
preset name for another calibration rather than overwriting an active preset.
