# Flat / TI Bowl A/B Test

On the DUT (`root@192.168.20.222`):

```sh
~/srv_view.sh flat
~/srv_view.sh bowl
~/srv_view.sh          # toggle between the two
~/srv_view.sh status
```

The switch restarts only `jk-ti-srv-pair.service`. Measured command completion
is 4.4-5.7 seconds, including camera setup and confirmation of 30 live frames.
There is a short display interruption, not an instantaneous mesh reload.
The service is transient; this does not change what boots next time.
The original four-camera app, its calibration, and system TI library are untouched.

Both modes use native 1920x1200 GMSL0/GMSL1 inputs and the same fullscreen
1280x800 layout: raw GMSL0 top-left, raw GMSL1 bottom-left, stitch on the right.
Both retain the same crop, camera poses and wider one-cell blend. Blend bytes
and both raw-pane meshes are identical. `flat` selects the existing `lens`
mode; `bowl` selects the additional bowl mesh. The previous flat artifacts
have not been regenerated or overwritten by this experiment.

## Lens Models And Surface

**Yes, both views use the two separate lens calibrations** from September 8:

- `../lens_20260908/gmsl0_intrinsics.json`
- `../lens_20260908/gmsl1_intrinsics.json`

The generator verifies each camera's saved K/D against its own lens file.
Only the assumed projection surface changes; no new lens or camera-pose fit
is performed. This uses the September 16 saved images and checkerboard poses.
If the cameras move relative to the board or each other, capture/refit first.

This is the **actual TI `svGenerate_3D_Bowl` geometry generator**, called on
the host from unmodified `kernels/srv/c66/core_generate_3dbowl.c`, through a
small two-camera adapter. TI expects four pose slots for centering/scaling;
the adapter supplies the two physical centers symmetrically in those slots.
Those auxiliary poses are not used for projection. The frozen real camera
poses and each camera's own fisheye K/D project the bowl into image pixels.
TI's Y-up coordinates are converted to the checkerboard's Y-down frame;
height toward the cameras is negative board Z.

The stock shape has a rectangular flat bottom and rising sides. For this
small tabletop experiment the base half-size is approximately 128 mm and
the rise is scaled to **0-50 mm over the visible crop**. This is not TI's
stock vehicle-size bowl configuration. A 100 mm trial changed source
coverage/blending, so it was rejected to retain a fair A/B comparison.

The existing TI GPU renderer displays the baked projections in the same
top-down comparison pane. This is not a new movable 3D viewpoint or the
unmodified four-camera TI calibration workflow. No runtime bowl generation,
additional capture processing, or GPU shader change is needed.

The bowl assumes height; it does not measure scene depth. Floor grid lines
can become less aligned where the bowl rises. A raised hand can align better
only where its height resembles the assumed surface. Neither mode can align
the floor and arbitrary raised objects simultaneously across separated cameras.

## Repeatable Build / Deploy

From the isolated `vision_apps-j722s-srv-pair-test` worktree:

```sh
bash jk_deploy/calibration/pair_plywood_20260916/rebuild_bowl.sh
ssh root@192.168.20.222 systemctl stop jk-ti-srv-pair
TARGET=root@192.168.20.222 bash jk_deploy/deploy_pair_alignment.sh
ssh root@192.168.20.222 /root/srv_view.sh bowl
```

Rebuilding needs the saved captures/corner files, existing OpenCV/NumPy/SciPy
environment, host C compiler and adjacent RTOS SDK headers/C6x simulator.
`CALIB_PYTHONPATH` and `RTOS_SDK_ROOT` override the local dependency locations.
The target needs only the generated BIN/JSON files and shell launchers;
the host `.so` and Python calibration tools are not installed on the target.

`rebuild_bowl.sh --height-mm 25` tries a shallower bowl. Rebuild the bowl after
any flat alignment change. Failed coverage checks leave prior bowl files
untouched. Before a switch, the launcher verifies the alignment/artifact
hashes and identical blend files, rejecting stale/mixed calibration before
stopping the active view.

## Files

- `ti_bowl_helper.c`, `build_bowl_helper.sh`: host adapter and shared-library build.
- `make_bowl.py`: frozen pose/lens loading, TI surface conversion and GPU LUT bake.
- `bowl_mesh.bin`, `bowl_fullres_mesh.bin`, `bowl_blend.bin`: ready GPU artifacts.
- `bowl_settings.json`: dimensions, height, source/calibration/artifact hashes.
- `ti_bowl_surface.npz`: generated XYZ surface and height scale for inspection.
- `rebuild_bowl.sh`, `test_bowl.py`: reproducible generation and focused tests.
- `flat_vs_bowl.png`, `bowl_height.png`, `live_bowl_probe.png`: local-only previews.
- `../../switch_gmsl_pair_view.sh`: installed as `/root/srv_view.sh` via symlink.
- `../../run_gmsl_pair_calibrated.sh`: mode selection and non-destructive preflight.
- `../../deploy_pair_alignment.sh`: installs optional bowl assets in private runtime.

## Verification, September 16

Five bowl tests pass: geometry/raw-pane invariance, identical blend weights,
surface/hash checks, zero-height byte-for-byte flat reproduction, rejection
of a changed alignment, and preservation of artifacts after a failed bake
(some assertions are grouped in one test). Existing full-resolution mesh
tests and shell syntax checks also pass.

Finite DUT run:

```sh
PAIR_WARP_MODE=bowl /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 90 /tmp/jk-bowl-probe.raw
```

90 frames in 5.895 seconds, 15.27 fps; exit 0, all ten shared allocations
freed. GPU RGBX capture inspected. Both inputs report 1920x1200 UYVY with
3840-byte stride, no CPU orientation transform. Visible Wayland surface
reports source/destination 1280x800 at 0,0 with advancing frame counter.
`bowl`, `flat`, `toggle`, and `status` were exercised on the DUT. The unchanged
missing sedan-model warning is harmless for this two-camera comparison.

Unchanged executable/library SHA256:

```text
45a0bd264d7d78a6859b11623e89c52ed55794076e4738bf9571e60d519f9f1f  /opt/jk-ti-srv/vx_app_jk_srv_live.out
cdcfeaf755847f4e3993ffb107a8f147fd4679145480e9704df50a20faeff02a  /usr/lib/libtivision_apps.so.11.0.0
bf7688ac02639e24fba7ee03349e13e44a44088372806f01c608adcb5f82df2d  /opt/jk-ti-srv-pair/vx_app_jk_srv_live.out
```
