# J722S Mixed-Camera TI SRV Bring-Up

This is an unofficial derivative of Texas Instruments' `vision_apps` source
for Processor SDK Analytics 11.00.00.06. It preserves TI's Git history and adds
a working four-input J722S surround-view bring-up for the OpenViewPro target.

The repository is based on:

- Upstream: <https://git.ti.com/git/processor-sdk/vision_apps.git>
- Tag: `REL.PSDK.ANALYTICS.11.00.00.06`
- Commit: `e2129bc1923c200ab66d2d1bee0445c8d227021d`

The Git remote named `upstream` points to TI. The commits after the tag keep
TI's J722S enablement, target memory-map compatibility, the application, GPU
presentation changes, and deployment tooling separate for review.

## Current Result

`vx_app_jk_srv_live` captures four UYVY V4L2 inputs:

- Two 1280x720 GMSL2 TEVS cameras.
- Two 720x480 analog cameras through the ISL79987 decoder.

Each input is normalized to a centered 640x480 image and passed to TI's
`tivxGlSrvNode`. The current uncalibrated mode renders a full-screen 2x2 view:

| Position | Input |
| --- | --- |
| Top left | GMSL0 |
| Top right | GMSL1 |
| Bottom left | Analog1 |
| Bottom right | Analog0 |

The analog stacked fields are rewoven during the host copy. Output is a
1280x800 fullscreen Wayland surface. On the tested target the mixed-camera
pipeline sustained 30 fps, used about 6.1 ms per SRV graph execution, and used
about 80 percent of one A53 core. The analog inputs set the 30 fps pace.

This is a live compositor baseline, not a calibrated bird's-eye stitch. Final
surround view still requires camera calibration, lens/placement-specific LUTs,
overlap geometry, and blending.

## Build

Place this checkout at the same level as the other Processor SDK RTOS
11.00.00.06 components so the existing relative component paths resolve, then
run:

```sh
./jk_deploy/build.sh
```

The main outputs are:

```text
out/J722S/A53/LINUX/release/vx_app_jk_srv_live.out
out/J722S/A53/LINUX/release/libtivision_apps.so.11.0.0
```

## Deploy And Run

The incremental deployer expects a target that already has the matching TI
Vision Apps remote-core firmware and the OpenViewPro/Ahsoka camera device
links. It backs up every target file that it replaces.

```sh
TARGET=root@TARGET_IP ./jk_deploy/deploy.sh
ssh root@TARGET_IP /opt/jk-ti-srv/run_jk_srv_live.sh
```

The launcher temporarily freezes the stock Ahsoka controller, releases its
four camera previews, configures both GMSL2 streams, and assigns the TI output
to the fullscreen Ahsoka surface. On exit it restores the stock application.
The stock Ahsoka application remains the boot default.

See [`jk_deploy/README.md`](jk_deploy/README.md) for prerequisites, environment
overrides, and the exact data path.

## Source Layout

- `apps/srv_demos/app_jk_srv_live`: mixed-camera V4L2/OpenVX application.
- `kernels/srv/gpu`: identity-quadrant mode and Wayland presentation support.
- `utils/opengl/src/a72`: optional xdg-shell EGL window path.
- `platform/j722s/rtos`: target IPC and memory-map compatibility changes.
- `jk_deploy`: repeatable build, deploy, and launch scripts.

## Licensing

This repository contains TI source with per-file TI Limited License notices.
Those notices restrict redistribution and resulting derivative works to use
with TI devices. They must be retained. The generated xdg-shell protocol files
carry their own permissive notice in the generated source. No additional
license is granted by this repository.
