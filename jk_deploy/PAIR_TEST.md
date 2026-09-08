# Two-GMSL Checkerboard Test

Isolated worktree/branch: `vision_apps-j722s-srv-pair-test`,
`test/gmsl-pair-checkerboard`, based on `82d8ca6`.
Do not use the normal `deploy.sh` for this branch: its library changes are
specific to this test. Use `deploy_pair_test.sh` below.

## Display And Data Path

Fullscreen 1280x800 comparison:

- Top left: GMSL0, unwarped full field of view.
- Bottom left: GMSL1, unwarped full field of view.
- Right half: both cameras rectified onto the same floor grid and blended.

The cameras capture 1920x1200 UYVY, rotate 180 degrees, and use the existing
640x400 fit inside 640x480 OpenVX images. "Raw" means unwarped processed
camera video, not sensor Bayer RAW or full-resolution rendering.
Only the two GMSL devices are opened. The TI object array retains four slots;
unused slots are initialized but never selected by this test's renderer.
TI's existing OpenVX/GLES SRV node performs the live warp/blend; Python only
generates the mesh offline. No analog camera or remote DSP/R5 processing is
needed. Host IPC and shared descriptor memory remain initialized.

## Calibration Scope

The September 8 capture has 27.25 mm checker squares and a common TI marker
near a yellow circular object. Lattice growth identifies 1815 and 1666 grid
corners. An approximate equisolid/homography fit rejects outliers and uses
the corresponding marker corners to resolve the repeating pattern's rotation
and integer-cell offset. It is not manufacturer lens calibration.

A smooth interpolation of the measured corners maps the common ground grid
back into each camera. The test covers approximately 872 x 1090 mm (32 x 40
squares), with a short blend near the common marker. Fit details are in
`calibration/pair_20260908/fit.json` and `split_settings.json`.

This is a scene-specific floor-plane test, not general intrinsic calibration
or a complete replacement for TI bowl calibration. Cloth wrinkles and elevated
objects violate the plane assumption; the tripod/foam can split or double.
Changing camera pose requires recalibration. Moving the cloth requires new
captures/seed selection if regenerating the fit. Repeating squares alone do
not establish identity; keep a distinguishable shared marker in overlap.
The reduced live input resolution also limits sharpness away from the cameras.

## Build, Deploy, Run

From this worktree on the development host:

```sh
JOBS=4 PROFILE=release ./jk_deploy/build.sh
TARGET=root@192.168.20.222 bash ./jk_deploy/deploy_pair_test.sh
```

Installs only `/opt/jk-ti-srv-pair`, including a private `libtivision_apps`.
It does not replace `/opt/jk-ti-srv`, `/usr/lib/libtivision_apps*`, boot units,
or any TI calibration BIN files. Existing BSP/Wayland/TI dependencies are used.

On the DUT, launch interactively:

```sh
/opt/jk-ti-srv-pair/run_gmsl_pair_test.sh
```

Or run independently of SSH, without enabling it on boot:

```sh
systemd-run --unit=jk-ti-srv-pair --collect /opt/jk-ti-srv-pair/run_gmsl_pair_test.sh
journalctl -fu jk-ti-srv-pair
systemctl stop jk-ti-srv-pair
```

The launcher stops Ahsoka before taking the cameras and restores it on exit
if it was running. Camera configuration runs each launch. Keep both cameras
connected before boot. Stop other manually launched camera/SRV processes first.

A finite run also saves the last rendered RGBX frame:

```sh
/opt/jk-ti-srv-pair/run_gmsl_pair_test.sh 120 /tmp/jk-pair-rgbx.raw
```

The first live probe completed 120 frames at 18.58 fps (camera mode requested
30 fps). These are measured application frames, not a 30 fps or latency claim.
Capture/conversion/GPU timing is printed at exit; parallel worker times are
summed and therefore are not additive wall-clock stages.

After limiting IPC to the host, the repeat probe completed 120 frames at
18.48 fps, exited with status 0, released all ten shared-memory allocations,
and restored Ahsoka. The live Wayland surface was verified visible with source
and destination both 1280x800 at (0,0). `/proc/PID/maps` confirms the private
library; only `/dev/video2` and `/dev/video3` are open as capture devices.
Checksums of the original app and system Vision Apps library were unchanged.
The saved rendered frame is `calibration/pair_20260908/live_probe.png` (local).

## Reproduce The Fit

Host dependencies: Python 3, NumPy, OpenCV and SciPy. No Python/scientific
packages are added to the DUT. In this workspace SciPy is staged under
`/tmp/jk-scipy`; use a normal virtual environment for a persistent installation.

Local scene images are in `calibration/pair_20260908/captures/` and deliberately
git-ignored. The raw captures are 1920x1200 packed UYVY, 3840-byte stride.
They were taken after stopping Ahsoka with:

```sh
v4l2-ctl -d /usr/local/Ahsoka/devices/video/gmsl0 --stream-mmap=4 --stream-skip=30 --stream-count=1 --stream-to=/tmp/jk-pair-gmsl0.uyvy
v4l2-ctl -d /usr/local/Ahsoka/devices/video/gmsl1 --stream-mmap=4 --stream-skip=30 --stream-count=1 --stream-to=/tmp/jk-pair-gmsl1.uyvy
```

For PNG input, convert packed UYVY using OpenCV `COLOR_YUV2BGR_UYVY` and rotate
180 degrees. Filenames are `captures/gmsl0.png` and `captures/gmsl1.png`.
The inspected corner seeds/masks are specific to these saved images.

```sh
env PYTHONPATH=/tmp/jk-scipy python3 jk_deploy/calibration/pair_20260908/detect_grid.py
env PYTHONPATH=/tmp/jk-scipy python3 jk_deploy/calibration/pair_20260908/fit_pair.py
env PYTHONPATH=/tmp/jk-scipy python3 jk_deploy/calibration/pair_20260908/make_mesh.py
```

Saved `grid*.npz`/`fit.npz` preserve measured coordinates. `split_mesh.bin` and
`split_blend.bin` are ready to deploy without rerunning fitting. Preview PNGs
stay local. The generated mesh includes exact viewport boundaries and uses
the full TI vertex index grid, so the center split is not overscanned.

## Changed Files

- `main.c`: optional pair LUT, opens only GMSL slots, initializes unused slots.
- `srv.cpp`: pair texture selection, external blend weights, exact viewport mesh.
- `platform/j722s/linux/app_init.c`: pair mode enables only host IPC to avoid
  failed C7 endpoints and the subsequent teardown crash on this BSP.
- `run_jk_srv_live.sh`: runtime directory override in this copy only.
- `run_gmsl_pair_test.sh`: private library and LUT selection.
- `deploy_pair_test.sh`: isolated target deployment.
- `calibration/pair_20260908/`: captured-point data, offline fit/mesh scripts,
  generated mesh/blend, and fit metadata.
