# Shared checker coverage warning policy

Failed job: `/root/jk-calibration-jobs/20260929T231510Z_e132a2`.
Marked calibration passed. Clear-stage camera 1 detected 999/831/1041 corners,
with 763 common intersections. The common hull retained 86.16/99.48/79.96 percent
of the three detection hulls. The previous 80 percent guard rejected pass 3.
Matched-corner median displacement was approximately 0.05 pixel; this was
detector coverage variation around tripod occlusions, not a capture timeout.

The `pass01.npz` through `pass03.npz` fixtures are the original camera-1 clear
detections, copied without modification. Tests reproduce the actual 79.96306
percent case. Original images, detections, and reports remain offline under
`/home/jkauf/flex-calibration-backups/20260929T231510Z_e132a2/`.

## Policy

- Reject below 50 percent retained detection-hull area.
- Warn from 50 percent to below 80 percent; do not auto-accept the resulting fit.
- Keep the existing 300 common intersections, 10 percent absolute image area,
  held-out fit, marker/grid, crop, and independent-mapping checks.
- Retain the full detections. Validate every camera before replacing subsets so
  a late camera failure does not leave earlier cameras partly processed.
- Propagate warnings from both marked and clear stages to the final touch status.

This change deliberately leaves detector search and lens models unchanged.
Changing camera height between complete calibrations is allowed; the marked and
clear captures within a single calibration must still describe the same setup.
Below-50-percent coverage and inadequate absolute coverage still fail with the
measured percentage in the error message.

## Verification

All three clear-stage fits from the failed job passed offline replay using the
original detections and the new policy. The worst camera/pair mapping RMS was
0.5641 pixels, below the unchanged 2-pixel threshold. All crop displacements
were zero, and all cross-pass comparisons passed.

Local suite: 192 discovered, 170 passed, 22 Qt-only tests skipped. New tests cover
the real failed run, exact 50 percent acceptance, below-50 rejection, insufficient
absolute area, insufficient common corners, smaller well-distributed patterns,
narrow patterns, no partial mutation on rejection, and touch warning propagation.

Installed as `/opt/jk-ti-srv-flex/calibration_ui_769184ecc153`, with launcher
rollback under `/opt/jk-ti-srv-flex/before_cal_ui_20260929T233611Z`.
All 43 selected on-device coverage/controller/orchestration/mapping tests passed
in 31.7 seconds against this installed bundle (`target_tests.log`).

## Recovered Live Run

Used the actual touch UI's Retry saved captures button and confirmation to create
`/root/jk-calibration-jobs/20260929T233747Z_0b0c3f`, reusing the failed job's marked
and clear raw bursts. No new capture or marker replacement was required.

The complete on-device replay and application passed in 383.5 seconds: marked
processing 201.3 s, clear refinement 176.6 s, application 5.2 s. The clear stage
retained the original 79.96306 percent detection coverage and generated a warning.
No alternate detection or lower final accuracy thresholds were used.

Worst cross-pass mapping RMS: 0.5641 px. Selected per-camera held-out RMS:
1.0423, 0.8238, 0.5272, 0.5336 px. Rendered crop coverage: 99.9684 percent.
Candidate validation, the UI's completed status/warning, and the durable active
pointer were checked. The native renderer resumed at approximately 18.38 FPS.

Live/boot preset: `/opt/jk-ti-srv-flex/table_20260929T233747Z_0b0c3f`.
Previous preset retained: `/opt/jk-ti-srv-flex/table_20260929T221730Z_15039e`.
`recovered_status.json` and `recovered_report.json` preserve the target results;
`offline_replay.json` preserves the earlier independent workstation replay.

## Subsequent Pixel-Tolerance Change

The user then requested a 50 percent increase in the three repeat-mapping pixel
limits: RMS 3 px, p95 4.5 px, p99 12 px. Crop drift, held-out accuracy, coverage,
averaging and selection policies remain unchanged. Historical recovered reports
above retain the older limits under which that run passed.

Installed as `calibration_ui_f12ab229489f`; launcher backup is
`/opt/jk-ti-srv-flex/before_cal_ui_20260929T234959Z`. The active calibration and
native renderer PID 284805 were unchanged; no calibration was rerun.
The local suite passed 173 tests with 22 Qt-only skips (195 discovered), including
new acceptance-at-limit and rejection-above-limit cases for all three metrics.
See `relaxed_limits_local_tests.log`.
All eight mapping tests also passed on the Flex against the installed bundle.
