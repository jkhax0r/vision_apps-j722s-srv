# Flex Four-GMSL TI Surround Demo

2026-09-23, Enovation Controls Flex, kernel
`6.12.43-ti-rt-01025-gaf3896fca24b-dirty`, four TEVS-AR0234 cameras on MAX96724.
Development branch: `test/flex-four-gmsl`, based on the working pair-test branch.

See the [calibration code review and regression record](CALIBRATION_RELEASE_CHECK.md)
for the two-stage failure fix, recovery behavior, test coverage, and successful
saved-capture replay. Required test fixtures are committed; raw camera bursts
and redundant processing images remain excluded from Git.

## Boot Into Stitching

`jk-flex-autostart.service` is now enabled on the Flex. It starts the most recently
successful calibration and the CAL controls. The old Ahsoka demo and installer
are disabled; shared display, touch, driver, and network services remain enabled.
See [boot installation, operation, and rollback](boot/README.md).

## September 29 Corner-Marker Preview

The [automatic table-calibration workflow](TABLE_CALIBRATION.md) now accepts
unordered marker IDs, infers camera adjacency, retries checker detection, and
validates a separate candidate before staging. Existing live presets are unchanged.
It also supports 12-frame averages with three independent calibration passes,
advisory motion warnings, and fit-repeatability gates. Movement alone does not
abort calibration. See the burst workflow in that guide.

The wide touch LCD now has a lower-left **CAL** menu with **Recalibrate** and
[per-camera settings](CAMERA_SETTINGS.md). Recalibration retains confirmation,
elapsed status, cancellation, and validated-result application. Calculation runs
locally on the Flex. See [installation and operation](TABLE_CALIBRATION.md#touchscreen-cal-button).
CAL now captures with the green corners installed, shows a centered removal
prompt, then captures again to refine the newly exposed checkerboard while
preserving the first stage's camera identities and table crop.
The private stitch launcher starts the controls; the boot wrapper above launches
the last successful calibration automatically.

The CAL overlay displays the Helios Technologies H emblem in the center of the
stitched pane. See [asset provenance and placement](ui/HELIOS_ASSET.md).

Tap any of the four left-hand previews to expand it across the left half with a
green border; tap again to return to the quad. These previews are rotated 180
degrees for this rig, independently of the stitch and calibration images.
See [preview controls and deployment](PREVIEW_CONTROLS.md).

`/root/run_flex_markers.sh` loads the latest checker-plane fit using printed
corner IDs. The earlier `/root/run_flex_grid.sh` preset remains unchanged.
See [marker-stitch reproduction and limitations](sessions/20260929T155359Z_marker_inspection/STITCH.md).

## September 28 Calibrated Grid Comparison

Run `/root/run_flex_grid.sh` for the current rig: four original views on the
left, a measured checker-plane stitch on the right. Camera order is clockwise:
1 yellow circle, 2 green block, 3 blue tape, 4 unmarked. This is a separate
preset; the approximate September 23 geometry described below is preserved.
See [session instructions and measurements](sessions/20260928_four_grid/README.md)
for captures, calibration, tests, deployment, and limitations.

## Run On The Flex

```sh
/root/run_flex_stitch.sh       # Approximate TI surround view
/root/run_flex_stitch.sh quad  # Four independent raw camera previews
/root/run_flex_stitch.sh stop  # Stop the TI view
```

The full launcher path is `/opt/jk-ti-srv-flex/run_flex_stitch.sh`.
Connect all cameras before boot. The existing Ahsoka application remains installed
but is disabled. `stop` stops the TI view without restoring the old application;
to stop raw previews instead, run `/opt/jk-ti-srv-flex/run_flex_four.sh stop`.
Use `systemctl stop jk-flex-autostart.service` to stop both the CAL controls and
TI view.

## What Is And Is Not Calibrated

This uses the previous modified **TI `tivxGlSrvNode` / OpenVX / GLES renderer**,
not a Python live stitch or the earlier GStreamer oval compositor.

All four slots now use the same shared lens mapping: for each ray, project it
through both saved September 8 GMSL fisheye models, then average the pixel
coordinates equally. This preserves the model's separate x/y focal scales and
avoids independently averaging correlated focal/distortion coefficients.
Original per-camera JSON files are unchanged. Source hashes and coefficients
are recorded in `calibration/settings.json`.

The two original projections differ by median 7.15 px and maximum 12.39 px
over the sampled common field at 1920x1200. Their original held-out residuals
were around 5 px. These are experimental cloth-derived fits, NOT manufacturer
calibration or validation of the two new cameras' lenses.

**Extrinsics are assumed, not measured.** Default slots are front/right/rear/left,
90 degrees apart, height 760 mm, ring radius 100 mm, pitch 55 degrees down.
The flat ground view is 2800x1050 mm; blend width 100 mm; center mask 120 mm
radius. Native input is rotated 180 degrees in the mesh, matching the previous
calibration-image convention. Cameras currently lying on the floor or aimed
elsewhere will not produce aligned ground seams. Do not interpret this view
as a completed four-camera rig calibration.

The shared lens model does not replace camera order, roll, pitch, height, or
translation calibration. Mount them rigidly with common ground overlap, then
capture identifiable markers/checkerboard points to solve each pose.
This demo projects onto a flat ground plane, not TI's stock 3D bowl.

## Data Path And Measurements

`TEVS ISP UYVY -> MAX96724 -> CSI0/V4L2 -> DMA-BUF import -> four OpenVX images
-> TI GPU lens/ground warp and blend -> 1920x720 Wayland LCD`.

- Each camera captures **1920x1200 UYVY**, without the old 640x480 input fit.
- Capture runs in four workers and drains queued older frames. There is no
  timestamp matching. Processing still waits for all four current input workers.
- V4L2 buffers are held until the synchronous TI GPU graph (including glFinish)
  finishes, then returned to capture. External handles are detached before free.
- SDK import updates pointers but not cached DMA FD fields. The new four-camera
  GPU path resolves current FDs from registered pointers each frame. Other modes
  keep their original path.
- Initial CPU-copy test: 120 frames / 12.481 s = **9.61 fps**.
- Direct-import test: 120 frames / 6.539 s = **18.35 fps**. Summed worker import
  time: 0.025 s; graph time: 1.978 s. Worker times are not additive wall time.
- All 26 tracked TI allocations were freed after the finite test, zero open.
- A continuous run reported about 8.3% of one CPU core (ps sample), not total
  system utilization. No GPU utilization or end-to-end latency claim is made.
- Final continuous check after the post-stream-on control fix: **18.39 fps**,
  7.5% of one CPU core (ps), all four sensors reporting `max_fps: 30`, compositor
  source and destination both 1920x720. Consult current frame-rate logs rather
  than assuming the requested rate.
- `CAM_FPS=30` is requested, not a delivery guarantee. TEVS resets `max_fps`
  during format setup AND stream-on on this BSP; launchers reapply it afterward.
- GPU view was checked by a compositor surface dump and advancing frame counters.

The dedicated TI DMA heap in this Flex DT is only 1 MB. The transient service
binds the existing `linux,cma` DMA heap over that path **inside its own mount
namespace**. Host device nodes and the DT are unchanged. The process uses host
IPC/descriptor memory only; no DSP/R5 firmware replacement or startup is needed.
The existing stock sedan model is not installed, so TI logs a missing decorative
`.pod` model. Camera rendering works without it; the center stays masked.

## Camera Identity

| Slot / assumed direction | Sensor after four-camera boot | MAX pad | VC | Capture |
| --- | --- | --- | --- | --- |
| 0 / front | tevs 12-0039 | 4 | 0 | /dev/video2 |
| 1 / right | tevs 13-003a | 3 | 1 | /dev/video3 |
| 2 / rear | tevs 14-003b | 2 | 2 | /dev/video4 |
| 3 / left | tevs 15-003c | 1 | 3 | /dev/video5 |

0039 is the original physical Video 1 camera. Other connector labels and rig
directions must be confirmed by covering lenses. Discovery uses graph links,
not hard-coded subdevice numbers. Example reordering:

```sh
CAMERA_ORDER='2 0 3 1' /root/run_flex_stitch.sh
```

## Reproduce On The Workstation

From the `vision_apps-j722s-srv-pair-test` repository:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/flex/make_lut.py
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/flex/test_lut.py
JOBS=4 ./jk_deploy/build.sh
# Stop the TI process on the target before deploying.
TARGET=root@192.168.20.222 bash jk_deploy/flex/deploy.sh
```

LUT generation/tests only require NumPy on the workstation; the temporary
PYTHONPATH above selects the already-staged NumPy 2.2.6 environment. The base
runtime deploy script does not install Python packages; the separate CAL UI
installer provides isolated scientific packages under its private bundle.
The deploy script uses the
separate `known_hosts_flex` file and installs a private app/library, never
`/usr/lib/libtivision_apps*`. `SSH_OPTIONS` can override SSH options.

`make_lut.py --help` lists assumed geometry settings. Regenerate/deploy to change
them; this is not automatic pose calibration. Generated artifacts are 1,035,776
bytes (mesh) and 147,968 bytes (blend), with hashes in settings.json.

## Diagnostics

```sh
journalctl -u jk-flex-ti-srv -n 50 --no-pager
/root/run_flex_stitch.sh status
FRAME_COUNT=120 /root/run_flex_stitch.sh
APP_SRV_IMPORT_CAPTURE=0 /root/run_flex_stitch.sh  # Slower CPU-copy fallback
```

A finite run saves `/tmp/jk-flex-ti-last.rgbx`, 1920x720 RGBX (5,529,600 bytes).
Raw readback has OpenGL's row orientation; compositor screenshots show LCD
orientation. A successful test must have actual images, no texture-import
errors, advancing frame counters, and zero outstanding allocations at teardown.

Files: `run_flex_four.sh` discovers/configures MAX96724/CSI and starts raw views;
`run_flex_stitch.sh` switches modes and launches the private TI service;
`make_lut.py` generates the shared-lens approximate mesh; `test_lut.py` checks
projection, mesh encoding, weights, and quadrant continuity; `deploy.sh` copies
the runtime with backups. No Wi-Fi, boot services, DT, firmware, or system GPU
libraries are changed.
