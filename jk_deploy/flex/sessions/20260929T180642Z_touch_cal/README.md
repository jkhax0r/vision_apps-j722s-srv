# First Successful On-Device Touch CAL

Target job: `/root/jk-calibration-jobs/20260929T180642Z_7b29f0`.
Tool bundle: `/opt/jk-ti-srv-flex/calibration_ui_f24e5a1b0d8b`.

Triggered through the actual Atmel input device using injected Linux touch
events, passing through libinput's existing Y-flip and DSI-1 mapping, Wayland,
and Qt. CAL opened the modal; Cancel closed it without starting a job. A second
CAL / Start CAL sequence ran the complete job. This verifies the software touch
path, not a human finger press during this test.

Timing from the target's monotonic clock:

- Capture, including restoring the old live preview: 73.2 seconds.
- Average, motion checks, independent fits, and consistency: 372.5 seconds.
- Apply and verify the new renderer starts: 4.7 seconds.
- Total: **450.6 seconds (7 minutes 31 seconds)**.

Three independent passes, 12 native 1920x1200 frames per camera per pass.
All three pairwise comparisons passed; pass 2 was selected as the medoid.
Largest mapping RMS disagreement: 0.237 native pixels; largest p95: 0.424 px.
Largest inferred table-corner displacement: 0.094 checker cells. These measure
repeatability, not absolute or cross-camera seam accuracy. The shared two-camera
lens prior, checker cloth irregularities, planar approximation, and elevated
objects remain limitations. One successful stationary rig trial is not a
field-robustness validation.

Applied launcher:
`/opt/jk-ti-srv-flex/table_20260929T180642Z_7b29f0/run.sh`.
Restore the preceding preset with `/root/run_flex_markers.sh`.

Root artifacts, status, report, and screen capture are copied here. All raw
bursts and intermediate fits remain in the target job directory. No system
libraries, TI binary, firmware, or boot services were replaced. Local and
deployed UI/worker/launcher hashes matched after installation.

The first attempt (`20260929T174412Z_bdf00f`) timed out during checker detection
after 469.4 seconds, leaving the old preset live. An isolated probe exposed
OpenCV OpenCL kernel compilation failures; disabling OpenCL **only in calibration
subprocesses** reduced that same detection to 8.97 seconds. The separate live
TI renderer still uses GLES. The GUI overlay was also moved to existing Ahsoka
layer 102 so renderer restarts cannot hide it.

Verification: 61 automated regression tests passed; syntax checks passed;
on-target screenshots confirmed the button, modal, progress, and completed state.
