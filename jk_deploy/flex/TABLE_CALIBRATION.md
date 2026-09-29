# Automatic Checker-Table Calibration

This calibrates the four-GMSL Flex rig, either on a workstation or locally using
the Flex's CAL button. No AI service is involved. It generates mesh/blend files
for the existing live TI GPU renderer, using the same shared lens prior. It does
not recalibrate lenses.

## Touchscreen CAL Button

The wide 1920x720 touch LCD is DSI-1, compositor **screen 0**, regardless of its
physical display numbering. The other compositor outputs are separate displays.
The lower-left **CAL** menu offers **Recalibrate** and camera settings. Recalibrate
opens a Cancel / Start CAL confirmation. A two-stage capture is now used:

1. Start with all four green corner holders and labels installed. Capture three
   averaged bursts and check that the four corner IDs are visible as required.
2. A large **centered, modal prompt** says **Remove all four green corners**.
   The live preview is restored while it waits. Remove the holders without
   moving the cameras, table or cloth, step away, then tap **Continue**.
3. Capture three more averaged bursts of the clear checkerboard. Check that the
   original marker IDs are gone, then fit both stages and validate the result.

Cancel works at the removal prompt and during processing. Outside taps and Escape
do not dismiss the removal prompt or start capture. Waiting expires after 30
minutes without applying anything. An elapsed timer and current stage remain
visible, and a second job cannot start while busy. Start the next CAL with the
holders reinstalled; they need not remain on the table after a successful CAL.

The marked stage establishes camera identity, checker-grid coordinates and crop.
The clear stage transfers those coordinates through unchanged shared checker
intersections, then refits from the unobstructed checker measurements. Only an
integer grid orientation/origin is transferred, not a free image registration
that could hide camera movement. At least 150 reciprocal matches across 65% of
the old checker hull are required; matches must be within 3 pixels and less than
20% of local checker spacing, with an exact integer-grid/color-phase match.
Small residual displacement is reported as a warning. New checker counts and
coverage beyond the old hull are recorded in `clean_refinement` in the report.
If no new intersections appear, a completion warning says so. This cannot improve
blank areas where there is no checkerboard underneath the holders.

Motion/scene-change checks are **warning-only**. Every captured frame is included
in the average; motion never aborts the run or silently discards frames. When a
calibration succeeds with detected changes, the completion panel shows an amber
movement warning. Moving through the background is allowed. Moving the rig or
covering the targets can still blur the average or produce inconsistent geometry,
which the separate calibration-validity checks may reject.

The preview pauses for capture and returns while calculation runs. Only a
validated two-stage, three-pass result is applied. Rejected fits leave the current preset
running; an application failure attempts to restore that preset. Loss of power
or SIGKILL cannot execute cleanup; reboot selects the last committed preset.
The button performs the existing
table/pose calibration, **not new per-camera lens calibration**.

Failed jobs with both complete capture sets offer **Retry saved captures**.
Confirm that the cameras, table and cloth have not moved since capture; this
processes into a new job without taking new pictures. Otherwise start a new CAL.
The latest job outcome is retained after UI restart. Failed boot-pointer saves
attempt to restore both the previous view and previous boot selection.
See [code review and regression tests](CALIBRATION_RELEASE_CHECK.md)
for the September 29 bug fix, regression coverage, and remaining limits.

Install from this repository on a workstation with pip, SSH access, and internet
access for the pinned wheels (downloads are cached):

```sh
python3 jk_deploy/flex/deploy_calibration_ui.py
```

This installer currently targets AArch64 Python 3.12 and the existing Flex BSP's
PySide6/QtQuick, evdev, IVI compositor, layer 102, and four-camera TI runtime. It
checks the launcher hash before modifying it and refuses replacement during an
active job. A versioned private bundle contains OpenCV 4.12.0.88, NumPy 2.2.6,
SciPy 1.15.3, source files, both lens priors, holder geometry, and file hashes.
It does not replace system Python packages, the TI binary, firmware, or boot
services. The stitch launcher is backed up before adding the UI launch hook.

`/root/run_calibration_ui.sh` starts the controls; append `stop` to stop them.
They also start after the private stitch launcher succeeds. The service is
transient, not boot-enabled. `FLEX_CAL_UI=0` suppresses automatic UI launch.
The separate [boot launcher](boot/README.md), now enabled on this Flex, starts
the saved stitch preset and these controls at startup.
The overlay uses the existing Ahsoka overlay layer rather than modifying the
screen's platform-owned layer list. The local root-only test socket is not a
network service.

Jobs remain in `/root/jk-calibration-jobs/<UTC>_<id>/`, containing `status.json`,
`job.log`, `raw/` (marked bursts), `raw_clear/`, marker-presence checks,
`corners_removed.json` (explicit acknowledgement), `marked_result/`, `result/`,
per-pass fits, final reports, and `resume_previous.sh`.
Successful candidates are published to new `/opt/jk-ti-srv-flex/table_.../`
directories with a `run.sh` launcher; `active_table_calibration.json` records
the last applied launcher. Older named launchers still select their old presets.
Archive job directories periodically: both sets of raw bursts consume about
1.33 GB/job before prepared images and intermediate results.
The UI refuses a new run when less than 3 GiB is free.

Calibration subprocesses disable OpenCV OpenCL on this BSP because its OpenCL
compiler rejected OpenCV's kernels and the initial run stalled. This does not
disable the separate live renderer's GLES GPU acceleration. Diagnostics:

```sh
journalctl -u jk-calibration-ui.service -n 60 --no-pager
cat /root/jk-calibration-jobs/<job>/status.json
```

Implementation: `ui/calibration_ui.py` is the Qt controller, `Calibration.qml`
defines controls, `calibration_worker.py` captures/fits/validates/applies with
rollback, and `run_ui.sh` creates the transient service. `scan-line.svg` is a
Lucide icon with its accompanying ISC license. `test_calibration_worker.py`
exercises publication, failures, and restoration without target hardware.

The earlier **single-stage** September 29 hardware run took **7 minutes 31 seconds**: 73.2 seconds for
capture/preview restoration, 372.5 seconds for processing, and 4.7 seconds to
apply. All three passes agreed and the new preset was applied. Expect timing
to vary with scene complexity and retries; this is one measured run, not a
guaranteed duration. See the [hardware run record](sessions/20260929T180642Z_touch_cal/README.md).
The two-stage workflow has two capture/fit sets; budget roughly twice the old
runtime plus the time spent removing the holders. That is an estimate, not a new
hardware timing measurement. The removal prompt appears after the first capture
and marker check, before either expensive full fit.

For offline reproduction of an already captured two-stage job:

```sh
python3 jk_deploy/flex/calibrate_repeated.py "$JOB/raw" "$OUTPUT/marked"
python3 jk_deploy/flex/calibrate_repeated.py "$JOB/raw_clear" "$OUTPUT/clear" --reference "$OUTPUT/marked"
```

Use new output directories and the scientific PYTHONPATH described below.
`refine_clean_table.py` implements coordinate transfer and preserves the marked
crop; `check_calibration_markers.py` does the early marked/clear checks. The
live renderer, sensor orientation, lens prior and runtime GPU cost are unchanged.

Initial two-stage deployment on September 29 (superseded after a real-run bug): bundle
`/opt/jk-ti-srv-flex/calibration_ui_70dc270eb931`, previous UI backup
`/opt/jk-ti-srv-flex/before_cal_ui_20260929T204413Z`. Verification passed 109
workstation tests (including the real mesh-generation pipeline using saved
imagery with marker decoding mocked for the clean stage) and 12 offscreen Qt
touch tests on Flex. A synthetic held-out-corner test verifies that new corner
measurements replace zero residual correction outside the old support. The
centered prompt was visually inspected and tested for Continue, Cancel, outside
taps, Escape and failed acknowledgement writes. The active calibration remained
`table_20260929T185653Z_4f6252`, with frames advancing at 18.39 FPS. A physical
two-stage run and its corner-quality improvement have **not yet been measured**;
the operator must remove the actual holders at the prompt for that validation.

## Setup

- Use four **different** printed ArUco DICT_4X4_50 labels on the existing corner
  holders. IDs can be in **any order**, not necessarily 1,2,3,4 clockwise.
- Each camera must see two complete corner markers; every marker must be visible
  to exactly two adjacent cameras. Include the white borders. An optional
  `--marker-ids 7 12 23 45` excludes unrelated labels in the scene.
- Automatic ID selection uses labels shared between cameras, ignoring isolated
  one-view detections such as tiny checker-texture false positives. Exactly four
  shared IDs must remain; ambiguous extra shared IDs still require correction or
  an explicit filter. Selected IDs retain all size, border, uniqueness, and ring
  checks. `marker_selection` records the selected and ignored IDs.
- Keep labels in the designed position/orientation on their holders: the clipped
  label corner faces the physical outside table corner. Seat both holder fences.
  Arbitrary ID placement does **not** mean arbitrary label rotation on a holder.
- Keep the cloth flat and reasonably regular, with substantial shared checker
  coverage. It need not align with the rectangular table edges. Corners can be
  outside the cloth, but excessive extrapolation is rejected.
- Cameras and cloth must stay still throughout both stages. Holders stay in
  place for stage one and are removed only at the centered prompt.
  Move hands and loose cables away. Raised objects will still have parallax.
- Input 0 is the front by default. `--front-input 2` instead makes physical input
  2 the front. The script infers the other cameras' order. Keep the existing
  inverted native camera mounting convention; arbitrary camera roll is not
  automatically supported.

The crop is the best-fit rectangular table frame inferred from the holders,
inset by 0.5% per edge. `--inset-percent 2` leaves a larger safety margin.
The right-hand 960x720 pane preserves aspect ratio, so a square table has side
margins. Crop estimates are approximate, especially beyond the checker coverage;
holders are slightly above the calibrated plane.

## Burst Capture And Repeat Checks

The preferred workflow now averages **12 frames per camera** and independently
calibrates **three passes**. It reduces temporal brightness variation in static
calibration images; it does not smooth the live display or guarantee removal of
lighting flicker. Correlated flicker/banding can remain after averaging.

Install `capture_table_bursts.py` alongside the existing private target runtime
(already installed on this Flex). It requires only the target's Python standard
library and the existing V4L2/media tools. Then run on target:

```sh
python3 /opt/jk-ti-srv-flex/capture_table_bursts.py \
  /root/jk-calibration-captures/show_bursts_01 \
  --resume /root/run_flex_markers.sh
```

This stops the preview, configures the four native inputs, discards 60 warmup
frames before each burst, and captures each camera sequentially. It waits one
second between passes. Keep the entire scene still, including hands and cables,
until complete. `--resume` specifies the actual preset to restore, including
after a capture failure; omit it to leave the preview stopped. SIGKILL, loss of
power, or a failing resume launcher cannot be automatically recovered.

Defaults save 144 frames, about **664 MB / 633 MiB** of raw data. Options:
`--frames 6..32`, `--passes 3..5`, `--warmup 0..300`, `--gap 0..30` seconds.
Frame rate is whatever the camera delivers, not assumed from requested FPS.

Copy the complete directory, including `burst_manifest.json`, to the workstation:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 \
  jk_deploy/flex/calibrate_repeated.py /path/to/show_bursts_01 \
  jk_deploy/flex/sessions/show_bursts_01
```

The same `--front-input`, `--marker-ids`, `--geometry`, and `--inset-percent`
options apply. All output paths must be new.

Processing is deliberately conservative:

1. Check every burst frame against its reference for feature motion and local
   texture changes, recording warnings only. Brightness normalization is used
   only for these diagnostics. Stalled/duplicated or malformed bursts still fail.
2. Average all captured frames arithmetically, at native resolution. No frames
   are discarded for movement and no registration/warping hides camera movement.
3. Compare averaged images between passes for advisory scene-change warnings.
4. Detect checkers independently, then retain the physical intersections found
   in every pass, using each pass's own measured pixel positions. Require at least
   300 common intersections per camera, covering at least 10% of the image and
   retaining 80% of each detection's hull area. Preserve full detections alongside
   the selected subset. Fit the marker/checker calibration independently per pass.
5. Resolve differing checker-grid origins/bases, then compare camera mappings
   at common floor points and compare the estimated table corners.
6. Only after all comparisons pass, select the most representative pass (lowest
   summed disagreement with the others). Do not average unrelated calibration
   matrices or silently pick a lucky pass from a failed set.

Initial motion warning thresholds are 0.75 px median and 2 px p95 at native
resolution; local texture changes over 6% of tested tiles also produce a warning.
These diagnostics never reject the burst. Independent
mapping limits are 2 px RMS, 3 px p95, and 8 px p99; table-corner estimates must
agree within half a checker cell. These are engineering starting thresholds,
not validated accuracy guarantees. Inspect actual-capture reports before
tuning them. Motion checks can miss small/local movement and cannot prove that
a consistently incorrect lens/cloth model is correct.

The root `report.json` contains per-frame mean brightness, advisory motion checks,
`motion_policy: warn_only`, detailed `motion_warnings`, common checker support, raw
file hashes, all pairwise consistency results, and the selected pass. Intermediate
results live in `prepared/` and `passes/`. **Stage only the root result**, using
`stage_table.py` below; individual passes and marked simulations are refused.
Any rejection leaves the existing target preset untouched.

The single-sensor probe on September 29 reported `power_line_frequency=0`
(disabled), with 50 Hz, 60 Hz, and Auto available. These controls were not changed.
Matching the anti-flicker setting to the lighting supply is a separate possible
live-video fix; LED PWM and exposure/frame-rate interactions need verification.

## Single-Frame Fallback

On the target, capture into a NEW directory. This stops the live TI view:

```sh
/opt/jk-ti-srv-flex/capture_floor.sh /root/jk-calibration-captures/show_test_01
/root/run_flex_markers.sh
```

Copy that capture directory to the workstation. Run from the repository root:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 \
  jk_deploy/flex/calibrate_table.py /path/to/show_test_01 \
  jk_deploy/flex/sessions/show_test_01
```

The input directory must contain native `input0.png` through `input3.png`, or
1920x1200 UYVY files with those basenames. PNGs take precedence if both exist.
Do not crop, resize, rotate, or mirror them. The output directory must **not
already exist**; a failed attempt remains available for diagnosis.

The temporary PYTHONPATH above selects this workstation's staged environment:
Python 3.10, OpenCV 4.12 with ArUco, NumPy 2.2.6, SciPy 1.15.3. A different
workstation needs those packages and the repo's two saved lens JSON files.

## Checks And Outputs

The script checks marker uniqueness/visibility, minimum size, image-edge margin,
four-camera ring connectivity, checker coverage and square-cell geometry,
integer grid alignment, black/white phase, loop closure, table geometry,
held-out checker prediction, and source coverage over the proposed crop.

The checker detector retries alternate image orientations to find a different
seed; pixel coordinates are transformed back to native orientation before fitting.
This is not a rotation of the live video.

- `report.json`: pass/reject, commands, timestamps, source/input hashes, lens
  parameters, package versions, and quality measurements.
- `calibration.log`: full stage output and failure details.
- `captures/*.detection.json`: attempted checker seeds and rejection reasons.
- `session.json`, `calibration.json`, `holder_geometry.json`: reproducible fit,
  camera order, crop, and holder assumptions.
- `comparison.png`, `stitched.png`: **inspect these before deployment**.
- `four_mesh.bin`, `four_blend.bin`, `camera_order.txt`: live runtime artifacts.

A rejection removes deployable artifacts and never touches the running target.
A pass is an engineering gate, not proof of perfect registration: the held-out
pixel error measures each camera's checker fit, not cross-camera seam accuracy.
The coverage gate allows up to 1.5% uncovered area; minor edge holes can remain.
Raised objects and wrinkles cannot be fixed by a single flat-plane mapping.

## Stage And Switch

After inspecting the preview:

```sh
python3 jk_deploy/flex/stage_table.py jk_deploy/flex/sessions/show_test_01
```

This verifies the pass report, file sizes, hashes, and camera order, then copies
only the calibration and its launcher into a NEW private target directory.
Target checksums are verified before publishing it. It refuses replacement of
an existing candidate. No runtime binary, system library, boot setup, or running
process is changed. Run the printed `/opt/jk-ti-srv-flex/table_.../run.sh` path
on the target to switch; `/root/run_flex_markers.sh` restores the previous preset.
The target must already have the working four-GMSL Flex TI runtime installed.

Do not use the older `deploy_grid.sh` for these candidates: that script replaces
the older grid preset and its runtime rather than staging a calibration only.

## Verification And Next Tests

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 -m unittest discover \
  -s jk_deploy/flex -p 'test_*.py' -v
```

September 29 regression results: both saved marker captures passed end-to-end.
The earlier failed camera-3 detection recovered 829 intersections on its second
attempt. Tests exercise all 24 ID permutations and all 24 camera-connection
permutations, rotated rectangular crops, invalid geometry, and failure isolation.
These permutations are software tests, not 24 physical rig trials.

Next physical trial: shuffle the holders' IDs while keeping labels correctly
oriented, recapture, then change tripod height/table placement and repeat.
Multi-capture stability checks and the CAL confirmation/status UI are implemented
above. Per-camera lens calibration and a guided setup wizard remain future work.

Burst validation: 67 unit/regression tests passed, including exact arithmetic
averaging of moving frames, successful apply with a movement warning, and rejection
of ambiguous or poor-quality shared markers. The end-to-end simulated
positive control passed, while independently perturbed data exposed unstable
edge fits and was rejected. The first complete on-device hardware run passed
three independently captured bursts per camera and applied the new preset;
this single stationary-rig trial does not make the thresholds field-validated. See the
[simulation record](sessions/20260929_repeat_positive_control/README.md).
