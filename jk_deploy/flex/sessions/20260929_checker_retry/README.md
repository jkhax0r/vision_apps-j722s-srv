# Checker coverage retry regression

Failure: Flex job `/root/jk-calibration-jobs/20260929T214533Z_92c6cb`.
Installed tools at failure: `calibration_ui_f4fe8b60f409`.
Both capture stages and marker-presence checks passed. The marked fit rejected
camera 1, marker 3 as too far from reliable checker coverage.

The original seed grew a large checker patch but crossed the tripod legs along
only one row near marker 3. Passes 1 and 2 found one row; pass 3 found another.
The common-support intersection therefore removed every nearby point. The
nearest measured checker support became 13.4 cells away, above the unchanged
8-cell limit. This was a detector coverage issue, not the earlier overwritten
`reference` variable and not a motion-warning rejection.

`input0.png` is the exact averaged camera-1 image from failed marked pass 1.
It is a regression fixture, not a new camera capture.

## Change

- Marked-stage detection receives the four selected shared marker IDs, retaining
  the existing rejection of ambiguous IDs and ignoring unshared false IDs.
- A seed is not accepted on global corner count/area alone: each marker needs
  a nearby two-dimensional checker patch, not an isolated row.
- On inadequate support, retry a seed window near each marker before the
  existing rotation/flip retries. Returned coordinates remain native pixels.
- Share the existing marker extrapolation check between detection and final
  alignment. No final alignment, motion, repeat-consistency, or deployment
  acceptance limits were relaxed.
- Clear-stage detection does not require markers. Existing lens coefficients,
  image orientations, renderer, UI, and boot calibration are unchanged.

## Verification

Run from the repository root with the existing local dependency directories:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy OPENCV_OPENCL_RUNTIME=disabled OPENBLAS_NUM_THREADS=1 python3 -m unittest discover -s jk_deploy/flex -p 'test_*.py'
```

Local suite: 169 discovered, 147 passed, 22 Qt-only tests skipped. Five new
tests cover the real missed-corner image, unsupported retries publishing
nothing, clear detection without markers, the unchanged extrapolation limit,
and rejection of isolated-row support. The existing orchestration tests now
also verify marker-ID forwarding only in the marked stage.
All five new regression tests also passed on the Flex against installed bundle
`calibration_ui_319321fdd4df` (72.4 seconds, saved images only).

Full saved-burst replay on the workstation passed all three marked fits, all
three clear fits, and both repeat-consistency checks. Camera 1 retains 947
common intersections instead of 709. Maximum per-camera 99th-percentile
mapping disagreement across repeated fits: 0.70 px marked, 0.73 px clear.
Clear-stage refinement adds 90/63/76/67 intersections and preserves the crop.
These replay results were not applied to the running camera view.

Saved inputs/results and logs are retained offline under
`/home/jkauf/flex-calibration-backups/20260929T214533Z_92c6cb`.
Reproduce with fresh output directories:

```sh
export PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy
export OPENBLAS_NUM_THREADS=1 OPENCV_OPENCL_RUNTIME=disabled
DATA=/home/jkauf/flex-calibration-backups/20260929T214533Z_92c6cb
python3 jk_deploy/flex/calibrate_repeated.py "$DATA/raw" /tmp/marked-replay-new
python3 jk_deploy/flex/calibrate_repeated.py "$DATA/raw_clear" /tmp/clear-replay-new --reference /tmp/marked-replay-new
```

Install code only, preserving the current live/boot calibration:

```sh
python3 jk_deploy/flex/deploy_calibration_ui.py
```

Installed on the Flex as `calibration_ui_319321fdd4df`, with the previous
UI launcher preserved under `before_cal_ui_20260929T221052Z`. Both services are
active. The native renderer PID stayed 2327239, and the boot pointer remains
`table_20260929T212624Z_b08624`. The UI correctly retains the failed job's
status and offers Retry saved captures; only retry after confirming the rig
has not moved since those captures.
