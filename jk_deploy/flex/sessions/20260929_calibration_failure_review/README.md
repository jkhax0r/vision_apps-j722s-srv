# Failed Two-Stage CAL: Review And Recovery

See [code review](../../CALIBRATION_RELEASE_CHECK.md) for the bug, fixes, tests,
coverage, operator behavior, and scope.

## Actual Target Replay: Passed

- Original failed job: `/root/jk-calibration-jobs/20260929T210046Z_5ce457`.
- New replay job: `/root/jk-calibration-jobs/20260929T212624Z_b08624`.
- Installed code: `/opt/jk-ti-srv-flex/calibration_ui_f4fe8b60f409`.
- Live/boot preset: `/opt/jk-ti-srv-flex/table_20260929T212624Z_b08624/run.sh`.
- Previous preset retained: `/opt/jk-ti-srv-flex/table_20260929T185653Z_4f6252`.
- Original captures were reused intact. No new pictures or camera movement were
  requested. All three marked passes and three clear passes were fitted again
  on the Flex using its installed Python 3.12/scientific dependencies.
- Marked stage: 417.2 s; clear refinement: 380.9 s; apply: 5.3 s.
  Total: **803.6 seconds / 13:23.6**. This excludes the original capture time.
- Both repeat-consistency gates passed. Final policy is `repeat-confirmed`.
  The original crop and input order `0 1 2 3` were retained.
- Clear-stage newly visible intersections: 84, 67, 66, 102. Shared-point
  displacement RMS: 0.332, 0.299, 0.115, 0.136 pixels. No refinement warnings.
- Six advisory movement/scene warnings from the original bursts were retained;
  they did not prevent a valid calibration from applying.
- Native view stayed at approximately 18.39 FPS during processing. Apply
  restarted the renderer; subsequent UI-only restart kept renderer PID 2277197
  unchanged and restored the completed job status and warning.
- The installed boot selector validated and selected the new launcher. No full
  reboot or power-cut experiment was performed.
- All 41 source/asset entries in the installed manifest matched SHA-256 values.

`live-screen.png` is the actual LCD compositor after apply and UI restart.
`target-result/` contains the copied final report, configuration, mesh/blend,
camera order, and offline previews. The copied candidate passed local artifact
validation too. `status.json` and `job.log` retain the exact target commands.
`marked-target-report.json` is the completed first-stage report.

## Software Tests

- `jk-flex-review-tests.log`: 164 discovered; 142 workstation passes, 22 Qt skips.
- `jk-flex-qt-tests.log`: those 22 Qt tests passed against the installed Flex UI.
- `jk-flex-target-tests.log`: 36 overlapping worker/storage/retry tests passed
  under target Python with temporary fixtures and stub hardware commands.
- `coverage.txt`: workstation line-and-branch coverage; selected module scope.
- `jk-retry-prompt.png`: rendered retry confirmation from target Qt tests.

Before pushing, a clean `git archive` export of commit `3cb327f` passed the
same 142 workstation tests (22 Qt skips), plus all six printable-marker design
tests. See `committed-export-tests.log`. This export contained only committed
files: required native PNG/corner fixtures are explicitly included in Git,
while raw UYVY capture dumps, caches, and redundant prepared imagery stay out.

The target test fixture initially hit the small `/tmp` filesystem's real 3-GiB
space gate. The fixture now supplies deterministic free-space values; an explicit
low-space test separately verifies rejection. No production disk check was relaxed.

Both new orchestration regressions also rejected an in-memory reintroduction of
the original variable collision. The mutation never modified source files or
the target. Production code then passed the unmodified full suite above.

## Reproduction

Use the normal touchscreen **Retry saved captures** confirmation for an existing
failed job only while its physical setup is unchanged. This replay was started
through the actual Qt hit-testing socket: tap Retry at `(670,666)`, confirm at
`(1175,453)`. The UI creates a fresh job and invokes `calibration_worker.py` with
`--reuse <original-job>`; its exact invocation paths are in `status.json`.

For offline processing without changing a target, original raw frames and
workstation fit outputs are preserved at:
`/home/jkauf/flex-calibration-backups/20260929T210046Z_5ce457/`.
From the repository root, use NEW output directories:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy \
  OPENCV_OPENCL_RUNTIME=disabled OPENBLAS_NUM_THREADS=1 \
  python3 jk_deploy/flex/calibrate_repeated.py "$SOURCE/raw" "$OUTPUT/marked"
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy \
  OPENCV_OPENCL_RUNTIME=disabled OPENBLAS_NUM_THREADS=1 \
  python3 jk_deploy/flex/calibrate_repeated.py "$SOURCE/raw_clear" "$OUTPUT/clear" \
  --reference "$OUTPUT/marked"
```
