# Left-Hand Preview Controls

Tap any raw preview to expand that camera across the left half of the wide LCD.
A four-pixel green border marks expanded mode. Tap anywhere in that half again
to return to the quad. CAL and camera controls remain independent touch targets.
The camera settings panel stays open while switching previews; use its X to
close it. Preview selection is disabled while CAL runs.

All four raw previews are rotated **180 degrees in the image plane**, in both
layouts. This is not a left/right mirror. Camera sensor controls, capture data,
calibration images, meshes, the stitched right half and its logo are unchanged.

The full field of view is preserved without stretching or cropping. Native
1920x1200 cameras occupy 480x300 pixels in each quad cell, or 960x600 when
expanded. The latter leaves 60-pixel black bars at top and bottom of the
960x720 left half. The four camera streams continue running in either layout.

## Implementation

- `ui/preview.py` atomically replaces `/run/jk-srv-preview.state` on a tap.
  Values 0..3 select a renderer input; -1 means quad. UI startup and clean
  shutdown return to quad; this display selection is not saved across boots.
- `ui/Calibration.qml` handles the left-side taps and draws the border.
- `kernels/srv/gpu/3dsrv/jk_preview.h` validates selection and computes
  aspect-preserving viewports. Missing/invalid state defaults to quad.
- `render.cpp` reads the tiny tmpfs state once per comparison frame and draws
  one or four existing DMA textures. There are no extra video copies or streams.
- `single_view.cpp` changes texture coordinates only in four-camera comparison
  mode. The stitching shader and LUTs are not modified.

## Reproduce

From the vision-apps repo, with the existing SDK build dependencies:

```sh
JOBS=4 PROFILE=release ./jk_deploy/build.sh
python3 jk_deploy/flex/deploy_calibration_ui.py
python3 jk_deploy/flex/deploy_preview_runtime.py
```

Both deployers default to `root@192.168.20.222` and accept `--target`. The native
deployer installs only the private executable/library pair, verifies uploaded
hashes, backs up the old pair, and restarts the most recent successful table
calibration. It refuses an active calibration or camera command. On launch
failure it restores the previous binaries and retries the same launcher.
It does not replace presets, boot services, launch scripts or system libraries.

Native layout/state tests are included in `test_preview.py` / `test_preview.cpp`.
Qt hit-testing is in `test_camera_ui.py`: all four expansion/return paths,
stitched-half exclusion, menu isolation, settings interaction and failed state
writes, plus the existing camera-control tests.

## September 29 Deployment

- UI bundle: `/opt/jk-ti-srv-flex/calibration_ui_a788d69ef8a0`.
- Previous UI: `/opt/jk-ti-srv-flex/before_cal_ui_20260929T202138Z`.
- Previous native binaries: `/opt/jk-ti-srv-flex/before_preview_20260929T202155Z`.
- The existing `table_20260929T185653Z_4f6252` calibration was retained.
- Release build passed; 90 workstation tests and eight on-device offscreen Qt
  tests passed. The full test discovery includes 98 cases, with Qt skipped on
  the workstation and exercised separately on Flex.
- Actual LCD hit-testing expanded and returned all four cameras without changing
  the renderer PID. Screenshots verified each camera's 180-degree rotation,
  matching enlarged contents, the green border, and unchanged right-side layout.
  The final state was quad, with frames advancing at 18.38 FPS.
