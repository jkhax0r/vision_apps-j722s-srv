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
  -> centered 640x480 host copy / analog field reweave
  -> OpenVX object array with 4 images
  -> tivxGlSrvNode on the GPU
  -> RGBX render target
  -> fullscreen xdg-shell Wayland surface
```

The app intentionally enters after the raw-sensor/VISS portion of TI's stock
SRV diagram. TEVS and ISL79987 inputs already arrive as processed UYVY.

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
then installs the application, matching `libtivision_apps`, and launcher.

## Run

```sh
/opt/jk-ti-srv/run_jk_srv_live.sh
```

Useful overrides:

```sh
CAM_FPS=30 /opt/jk-ti-srv/run_jk_srv_live.sh
APP_EGL_WIDTH=1280 APP_EGL_HEIGHT=800 /opt/jk-ti-srv/run_jk_srv_live.sh
/opt/jk-ti-srv/run_jk_srv_live.sh 300 /tmp/ti-srv-300-frames.raw
```

Press `Ctrl-C` to stop and restore Ahsoka. A reboot also returns to the stock
boot application.

## Known Limitations

- Four host copies cost roughly 80 percent of one A53 core.
- No cross-camera timestamp synchronization is performed.
- The identity layout has no calibration, overlap warping, or blending.
- The GMSL2 and analog inputs differ in resolution, timing, lenses, and image
  processing.
- A production implementation should import DMA-BUF/OpenVX buffers and use a
  calibrated GPU LUT for the final camera set and mounting geometry.
