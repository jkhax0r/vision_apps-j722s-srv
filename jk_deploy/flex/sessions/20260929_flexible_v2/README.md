# Flexible Marker Calibration Regression

Built from the unmodified `20260929T155359Z_marker_inspection/captures` using:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/flex/calibrate_table.py \
  jk_deploy/flex/sessions/20260929T155359Z_marker_inspection/captures \
  jk_deploy/flex/sessions/20260929_flexible_v2
python3 jk_deploy/flex/stage_table.py jk_deploy/flex/sessions/20260929_flexible_v2
```

Use a different output directory to repeat. No original capture or preset changed.

Passed with held-out per-camera RMS 0.94, 0.80, 0.86, 0.54 input pixels and
99.51% sampled crop coverage. These are not cross-camera registration guarantees.
Corner extrapolation differs by up to 1.59 checker cells between cameras.
The preview still contains parallax on the tripod and cables, and some doubling
on the slightly raised corner holders. Inspect `comparison.png`.

Staged on root@192.168.20.222, NOT launched:

```sh
/opt/jk-ti-srv-flex/table_20260929_flexible_v2_ede77d1318/run.sh
```

All six staged file checksums verified. The existing `jk-flex-ti-srv.service`
remained active as PID 870823, started 2026-09-29 16:09:47 UTC. Restore the old
preset after trying the candidate with `/root/run_flex_markers.sh`.

Workstation verification: 36 unit/regression tests passed; all four choices of
front input also produced the expected cyclic camera order. The sibling
`20260929_flexible_retry_v2` tests the earlier failed capture: camera 3 rejected
its native checker seed, then recovered 829 corners using a rotated seed image.
That candidate also passed end-to-end, but was not staged or launched.
