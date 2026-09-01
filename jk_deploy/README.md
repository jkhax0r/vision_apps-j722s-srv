# Build And Deployment

## Target Assumptions

The tested target is an OpenViewPro J722S running the matching Linux BSP and
Ahsoka application. Before using the incremental deployer, the target must
already provide:

- TI Vision Apps 11.00.00.06 dependencies and remote-core firmware.
- `/usr/local/Ahsoka/devices/video/gmsl0` and `gmsl1`.
- `/usr/local/Ahsoka/devices/video/analog0` and `analog1`.
- `media-ctl`, `v4l2-ctl`, `LayerManagerControl`, Wayland, and EGL/GLES.
- Cameras connected before boot so all media graph routes and capture nodes
  exist.

The first full target installation used the separate binary deployment bundle
to install the C7x/R5 firmware and firmware symlinks. This source repository
does not commit those generated binaries.

## Data Path

```text
4 V4L2 UYVY capture nodes
  -> mmap dequeue
  -> full-frame fit / analog X mirror / TechNexion 180-degree rotation
  -> OpenVX object array in front/right/back/left order
  -> one-time TI bowl/LDC LUT generation from CALMAT.BIN and LENS.BIN
  -> tivxGlSrvNode calibrated warp/blend on the GPU
  -> RGBX render target
  -> fullscreen xdg-shell Wayland surface
```

The app intentionally enters after the raw-sensor/VISS portion of TI's stock
SRV diagram. TEVS and ISL79987 inputs already arrive as processed UYVY.
The exact TI bowl and GPU-LUT algorithms run once on the A53 during startup;
the target BSP's remote C7 OpenVX path also hangs in TI's minimal C7 sample.
This fallback adds about 0.35 seconds at startup and no per-frame CPU cost.

## Camera Fixture

The printable four-camera tripod hub, adjustable TechNexion and analog camera
carriers, fit coupons, CAD sources, and assembly instructions are under
[`camera_rig/`](camera_rig/README.md).

## Build

```sh
JOBS=4 PROFILE=release ./jk_deploy/build.sh
```

The script performs the proven A53/Linux build and excludes unrelated R5/C7x
firmware rebuilds. That is sufficient for incremental changes to this app and
the host-side Vision Apps library.

## Incremental Deploy

```sh
TARGET=root@192.168.20.222 ./jk_deploy/deploy.sh
```

Optional SSH arguments can be supplied as a single string:

```sh
TARGET=root@TARGET_IP SSH_ARGS='-i ~/.ssh/target_key' ./jk_deploy/deploy.sh
```

The deployer refuses to replace files while `vx_app_jk_srv_live.out` is
running. It saves previous files under `/root/jk-ti-srv-backups/TIMESTAMP/`,
then installs the application, matching `libtivision_apps`, launcher, complete
versioned calibration output, and runtime calibration BIN files.

## Run

```sh
/opt/jk-ti-srv/run_jk_srv_live.sh
```

Useful overrides:

```sh
CAM_WIDTH=1280 CAM_HEIGHT=720 CAM_FPS=60 /opt/jk-ti-srv/run_jk_srv_live.sh
APP_EGL_WIDTH=1280 APP_EGL_HEIGHT=800 /opt/jk-ti-srv/run_jk_srv_live.sh
/opt/jk-ti-srv/run_jk_srv_live.sh 300 /tmp/ti-srv-300-frames.raw
APP_SRV_USE_CALIBRATION=0 /opt/jk-ti-srv/run_jk_srv_live.sh
```

Press `Ctrl-C` to stop and restore Ahsoka. A reboot also returns to the stock
boot application.

## Known Limitations

- CPU full-frame normalization of two 1920x1200 and two 720x480 inputs runs
  this bring-up graph at roughly 15-16 fps. It is correct for static
  calibration capture; the production 30-fps graph should perform these same
  resize/pad transforms with VPAC/MSC.
- No cross-camera timestamp synchronization is performed.
- The current `LENS.BIN` applies one shared lens model to unlike analog and
  TechNexion cameras; independent intrinsic calibration is still required for
  production-quality seams.
- The GMSL2 and analog inputs differ in resolution, timing, lenses, and image
  processing.
- A production implementation should import DMA-BUF/OpenVX buffers and move
  input normalization from the A53 to VPAC/MSC.
