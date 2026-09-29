# Touchscreen Camera Settings

Tap **CAL** for **Recalibrate** or **Camera settings**. Recalibrate keeps the
existing confirmation and validated-result workflow. Camera settings opens a
right-side panel, leaving all four original views visible on the left.

Select Camera 1..4, labeled by their positions in those original views. The helper
follows the running renderer's input list through the active media graph to each
TEVS subdevice; it does not assume `/dev/videoN` or subdevice numbering. Enable
**Apply to all** to send subsequent changes to all four cameras. Displayed values
remain those of the selected camera, not an average of mixed settings.

- **Auto:** automatic shutter and gain.
- **Auto gain (AGC):** manual shutter, automatic gain.
- **Manual:** manual shutter and gain; both sliders become available.
- **Brightness:** the driver's brightness control, normalized so its default is
  100%. This is not exposure compensation or an AE target-value control.
- **Shutter setpoint:** TEVS exposure register value displayed in milliseconds
  (driver microseconds divided by 1000). The driver reports a cached setpoint,
  not the currently measured automatic exposure. Switching to Manual uses that
  setpoint; this is not an AE-freeze operation. The UI and helper cap manual
  shutter at the requested frame period: 33.333 ms with the current 30 FPS
  setting, rather than exposing the driver's full one-second range.
- **Auto shutter limit:** `ae_exposure_max`, available in Auto. Its minimum is
  the current `ae_exposure_upper` threshold. Long shutter times can lower FPS;
  there is no guarantee of 30 FPS simply because `max_fps` requests it. The
  maximum is bounded to the larger of the frame period and the driver default
  (66.666 ms on this unit).
- **Anti-flicker:** Off / 50 Hz / 60 Hz / Auto. 60 Hz is a useful option to test
  under US mains-powered lights; it cannot guarantee removal of LED PWM flicker.
- **Reset defaults:** resets only these managed controls on the selected camera,
  or all four if Apply to all is checked. It does not change zoom, orientation,
  resolution, routing, trigger mode, or firmware/bootloader controls.

Sliders commit when released; device I/O runs in a subprocess, not the UI thread.
The panel is unavailable during CAL. The helper validates the entire requested
batch before writing, reads settings back, and attempts rollback on write or
save failure. Errors are shown in the panel, including a failed rollback.

Successful edits are atomically stored in
`/opt/jk-ti-srv-flex/camera_settings.json`, keyed by sensor alias/physical port
0039..003c. Settings follow the port, not the camera module's serial number.
`run_ui.sh` restores them after the live launcher has started the streams, even
when the CAL UI is already running. Thus boot, preview restart, and post-CAL
preview restoration use saved values. No new boot service or video copies are
introduced. Changes made outside this panel are not automatically saved.

## Files And Reproduction

- `ui/camera_controls.py`: stdlib CLI, discovery, validation, rollback, settings.
- `ui/camera_settings.py`: asynchronous QProcess adapter for Qt.
- `ui/CameraPanel.qml`: selection, modes, sliders and error/status display.
- `ui/Calibration.qml`: CAL menu plus unchanged recalibration confirmation/logo.
- `ui/run_ui.sh`: restores settings before checking whether the UI already runs.
- `ui/sliders-horizontal.svg`, `x.svg`, `rotate-ccw.svg`: Lucide icons, covered by
  the existing `ui/LICENSE.lucide.txt`.

Deploy with `python3 jk_deploy/flex/deploy_calibration_ui.py`. The installer checks
for running calibration/camera-control commands before replacing the UI. The
TI binary, camera pipeline, calibration binaries and BSP remain unchanged.

On-target diagnostics (resolve the active bundle first):

```sh
UI=$(dirname "$(readlink -f /opt/jk-ti-srv-flex/run_calibration_ui.sh)")
python3 "$UI/camera_controls.py" list
python3 "$UI/camera_controls.py" set --sensor 0039 --updates '{"exposure_mode":0}'
python3 "$UI/camera_controls.py" set --sensor 0039 --updates '{"exposure":10000,"gain":1}'
python3 "$UI/camera_controls.py" defaults --sensor 0039
```

Driver mode definitions were cross-checked with TechNexion's source:
https://github.com/TechNexion-Vision/ti-evk-camera/blob/tn-ti_6.1.46_09.01.00.006/drivers/media/i2c/tevs/tevs_main.c
The target's `v4l2-ctl --list-ctrls-menus` remains authoritative for available
controls/ranges on its newer BSP. All four reported Auto on initial inspection,
brightness 4096, shutter setpoint 10000, gain 1, and anti-flicker disabled.

## September 29 Verification

Installed bundle: `/opt/jk-ti-srv-flex/calibration_ui_74f8be771fd6`.
Previous UI backup: `/opt/jk-ti-srv-flex/before_cal_ui_20260929T201157Z`.

- 89 non-Qt regression tests passed on the workstation, including rejection of
  shutter values beyond the live-view limits.
- Four additional Qt tests passed on the Flex using an offscreen window and fake
  cameras: actual mouse hit-testing for the selector/slider, Manual mode, Apply
  to all, and the separate recalibration confirmation. They do not touch sensors.
- Live sensor tests accepted Manual, exposure 8000, gain 2, brightness 4400,
  60 Hz anti-flicker, and auto exposure maximum 33333. Individual helper writes
  and readbacks took about 35-85 ms. Original values were restored afterward.
- Native screen capture confirmed layout and all four live previews. CAL menu,
  confirmation/cancel, and settings discovery were exercised on the live UI.
- Saved-control restoration through `run_calibration_ui.sh` was verified without
  changing the native renderer PID. A reboot was not needed or performed.
- During subsequent live use of the initial unrestricted slider, Camera 4 was
  set to a 339.036 ms manual shutter, then `/dev/video5` timed out and the native
  renderer exited. This correlation is not proof of the exact driver failure.
  The shutter was shortened and the last successful calibration relaunched;
  no calibration or native binary was changed. The profile before recovery is
  saved at `/opt/jk-ti-srv-flex/camera_settings.before_shutter_limit.json`.
  The final bundle includes the limits above. After installation, frame numbers
  continued advancing at about 18.39 FPS for over three minutes.

Tests: `python3 -m unittest discover -s jk_deploy/flex -p 'test_*.py'` with the
scientific PYTHONPATH from TABLE_CALIBRATION.md. The four Qt cases skip when
PySide6 is absent. To run them on a separate staged UI, set `JK_UI_DIR` to the
UI directory and put both test files plus the bundle's `tools/flex` on PYTHONPATH.
