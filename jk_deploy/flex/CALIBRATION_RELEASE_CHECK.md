# Calibration Reliability Review - September 29, 2026

## Later Checker-Coverage Failure

Job `20260929T214533Z_92c6cb` exposed a separate detector limitation: sparse
checker rows across the tripod legs disappeared when intersecting three passes.
Marker-guided seed retries recover the visible grid without relaxing final
acceptance limits. Saved marked and clear bursts both pass reprocessing; the
local suite now has 169 discovered tests, 147 passed and 22 Qt-only skipped.
See [the regression record](sessions/20260929_checker_retry/README.md).
The sections below retain the evidence from the earlier reference-variable fix.

## Failure And Fixes

The failure in job `20260929T210046Z_5ce457` was a software bug, not a failed
capture or someone walking past the table. Both marked/clear captures and marker
checks passed. In `calibrate_repeated.py`, a motion-comparison image reused the
name `reference`, overwriting the optional reference-directory argument. The
fitter subsequently attempted NumPy array division instead of joining a path.

The image now has a separate name. Two regression tests run the outer three-pass
averaging/comparison orchestration and verify that the reference remains `None`
for the first stage and the original `Path` for the second. Previous tests did
not exercise that entire orchestration; their passing result was insufficient.
An isolated in-memory mutation reintroduced the original variable collision;
both new tests rejected it at the reference-argument check. No files or target
code were changed by that negative-control check.

The review also addressed:

- Boot-pointer save failure after launching a new calibration: restore both the
  old live preset and its original boot-pointer bytes, including failures after
  the pointer was renamed. Surface a rollback failure instead of hiding it.
- Candidate persistence: validate the copied files, sync them and their directory,
  publish to a new directory, then durably commit the boot pointer.
- Completion-status write failure: do not report a committed calibration as
  discarded. The UI reconciles the job against the committed boot pointer.
- UI restart: retain the latest completed/failed/interrupted job result instead
  of silently returning to Ready. Do not reopen a stale removal prompt.
- Console-free reprocessing: offer **Retry saved captures** only when both
  complete native capture sets, marker checks, and removal acknowledgement exist.
  Confirm that cameras/table/cloth have not moved; process into a new job without
  changing the original captures. Missing/truncated files disable retry.
- Repeated Cancel taps: send only one termination request, so a second tap does
  not interrupt the worker while it is restoring the previous view.
- Tracebacks remain in job logs for diagnosis after the show.

No firmware, camera driver, TI renderer, lens model, preview orientation, or
geometric acceptance threshold was changed by this review.

## Automated Evidence

Local suite: **164 discovered, 142 passed, 22 Qt tests skipped locally**.
Those **22 Qt tests passed on the Flex**, using Qt's actual hit-testing and
software rendering with fake cameras. **36 worker/storage/retry tests also
passed on the Flex**; these overlap the workstation count, not additional tests.
They use temporary files and stub capture/launch commands, not the live cameras.

Fault cases include rejected fits, incomplete captures, missing/duplicate IDs,
camera/label permutations, corrupt candidate files, interrupted capture,
cancel during apply, timed-out child cleanup, insufficient disk space, copy/sync
failures, pointer failures before/after replacement, failed restoration,
malformed status, UI restart, missing retry data, and explicit confirmation.

Measured workstation line-and-branch coverage: calibration worker **90%**,
saved-capture eligibility **91%**, repeated-calibration orchestration **81%**,
clean refinement **95%**, boot orchestration **93%**, capture **82%**.
Eight selected calibration/boot modules total **82%**.
This excludes target-only Qt execution and separately launched scientific
subprocesses. It is not whole-product coverage or a field-reliability estimate.
Uncovered areas include some CLI/bootstrap and SSH staging paths.

Reproduce the workstation suite from the repository root:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy \
  OPENCV_OPENCL_RUNTIME=disabled OPENBLAS_NUM_THREADS=1 \
  python3 -m unittest discover -s jk_deploy/flex -p 'test_*.py' -v
```

These PYTHONPATH entries refer to this workstation's pinned scientific packages;
see `TABLE_CALIBRATION.md` for dependency versions. Tests also use the saved
imagery under `jk_deploy/flex/sessions/`. Do not substitute empty fixtures.

Full raw data from the actual failed job is preserved offline at:
`/home/jkauf/flex-calibration-backups/20260929T210046Z_5ce457/`.
Both complete three-pass marked and clear fits passed on the workstation with
real detection and fitting, not mocked detection. The clear fit added
84/67/66/102 checker intersections across the four cameras while preserving crop.

The target replay passed and applied successfully as job `20260929T212624Z_b08624`,
started using the actual UI's Retry confirmation from the original saved captures.
All six fits and both repeat checks passed; total processing/apply time was 803.6 s.
The UI-only restart also restored its completed state without restarting video.
Its final result and
deployment evidence are recorded in
`sessions/20260929_calibration_failure_review/README.md`.

Installed source bundle: `/opt/jk-ti-srv-flex/calibration_ui_f4fe8b60f409`.
Previous UI backup: `/opt/jk-ti-srv-flex/before_cal_ui_20260929T212545Z`.
The bundle contains a SHA-256 manifest and isolated pinned scientific packages.

## Operator Recovery

1. A rejected calibration leaves the previous preset selected. Read the on-screen
   error, restore all four green holders, and use CAL / Recalibrate to recapture.
2. **Retry saved captures** reruns processing only. Use it only if the physical
   setup has not moved since those captures. It does not fix bad/missing markers.
3. Cancel stops the current operation and attempts to restore the previous view.
   Allow it to finish; repeatedly tapping does not speed it up.
4. After an unexpected restart, the UI shows the previous job outcome. An
   interrupted job is not automatically resumed or assumed successful.
5. A storage/restore warning is not a successful calibration. Do not keep
   retrying a full disk. Storage cleanup is currently a pre-show/service task,
   not a touchscreen operation; automatic deletion is intentionally not enabled.

## Scope

The requested work is code review, regression/fault-injection tests, and replay
of the saved failing input. No new physical captures or manual test checklist
are required from the user to complete this repair.

This review did not perform destructive power-cut tests or an overnight hardware
soak. Hard process kills cannot execute cleanup; missing cameras, damaged
storage, corrupt boot metadata, and BSP/compositor failures remain outside what
these software tests prove. File syncing does not guarantee power-loss survival
of the underlying SD/eMMC. A flat-table fit also cannot align raised objects.

Storage note: two raw sets cost about 1.33 GB per CAL plus intermediate files.
Around 12 GB remained during this review. No old captures were deleted.
