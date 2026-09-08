# Repositioned Two-GMSL Alignment

Fresh full-resolution captures taken September 8 at the user's final tripod
position. The TI marker's bottom-left black corner (printed orientation) is
the checker-grid anchor nearest the yellow circle. Both original 1920x1200
UYVY frames, PNGs rotated 180 degrees, timestamps and V4L2 logs are retained
locally under `captures/`, and on the DUT under
`/root/jk-lens-calibration/final_20260908T184734Z`. Scene photos are not committed.

## Two Comparable Warps

- `lens`: the ten-pose per-camera OpenCV fisheye parameters are held fixed.
  Only each camera's six-parameter pose against the floor grid is fitted.
  The resulting ground projection is baked directly into TI's GPU mesh.
- `measured`: the earlier scene-specific smooth interpolation method, fitted
  to this SAME capture and the same corresponding grid. It can absorb cloth
  wrinkles and local errors rather than estimating a reusable camera model.

Both modes use 27.25 mm square pitch, the same crop and the same one-cell
blend region. Marker paper, yellow cap and tools are masked from checker
correspondences in both methods. Marker pixels are used only to resolve the
repeating grid's orientation and integer-cell translation.

Fixed-lens ground-pose RMS: GMSL0 3.17 pixels, GMSL1 4.81 pixels at 1920x1200.
Marker-corner disagreement between views is about 0.31 cells, or 8.5 mm in
the fitted floor coordinates. This is enough to identify the lattice match,
not evidence of millimeter-accurate calibration. Camera calibration error,
paper curl, physical positioning and corner localization remain contributors.
The marker is not treated as an exact measured 3D rigid target.

The corrected half covers 30 x 37.5 cells (817.5 x 1021.875 mm). Roughly
0.15 percent is outside valid camera/grid coverage, mostly at the upper edge.
The origin/crop is recorded in `alignment.json`; positive X follows the
marker's printed top edge and positive Y follows its left edge downward.

The pair executable now supports full-resolution 1920x1200 GPU inputs, enabled
by default in `run_gmsl_pair_calibrated.sh`. It copies each native UYVY frame
row-wise without resizing or rotating. The `_fullres_mesh.bin` files reverse
both source axes in the GPU and address native pixel centers. The existing
TI GPU library performs the warp and filtering; no library change was needed.
The 1280x800 display layout, floor crop, lens fits and blending are unchanged.

`PAIR_FULL_RES=0` selects the previous 640x400-in-640x480 path and its matching
mesh. Full-resolution inputs retain nine times as many active source pixels.
This avoids the CPU decimation's strong checkerboard aliasing, but the LCD
resolution, perspective magnification and GPU sampling still limit detail.
Raised objects can also split at the seam because this is a floor-plane warp.

## Reproduce

From the `vision_apps-j722s-srv-pair-test` worktree:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/calibration/pair_final_20260908T184734Z/make_pair.py
python3 jk_deploy/calibration/pair_final_20260908T184734Z/test_meshes.py
JOBS=4 PROFILE=release ./jk_deploy/build.sh
ssh root@192.168.20.222 systemctl stop jk-ti-srv-pair
TARGET=root@192.168.20.222 bash jk_deploy/deploy_pair_alignment.sh
```

Detected corner files, fixed lens JSONs, marker seeds/masks and fitted poses
are saved. The script produces both GPU meshes, byte blend tables and offline
previews. It uses the saved local images to refine marker corners and produce
previews; ready-made BIN files can be deployed without the photographs.

The deployment is limited to `/opt/jk-ti-srv-pair`: the pair executable,
versioned calibration files and shell launchers. It refuses to replace a
running app. It does not overwrite any four-camera TI
app binary, system library, boot service or TI `LENS.BIN`/`CALMAT.BIN`.
Separate fx/fy from the fitted model are preserved in the GPU coordinates;
there is no lossy conversion to TI's single-focal radial CSV format.

## Run On The DUT

Stop the currently running pair service before starting another instance:

```sh
systemctl stop jk-ti-srv-pair
/opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh
```

Lens-based correction is the default. To compare the cloth-fitted method at
the same new camera position, stop the current app and run:

```sh
PAIR_WARP_MODE=measured /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh
```

For the previous lower-resolution input path with the SAME alignment:

```sh
PAIR_FULL_RES=0 /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh
```

The launcher selects the mesh and `APP_SRV_PAIR_FULL_RES` together. Do not
mix native-orientation full-resolution meshes with CPU-rotated low-resolution
inputs. Full-resolution mode rejects other camera dimensions and the legacy
640x480 calibration-capture option instead of silently saving mislabeled data.

For a background run that does not change boot behavior:

```sh
systemd-run --unit=jk-ti-srv-pair --collect /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh
```

The older `/opt/jk-ti-srv-pair/run_gmsl_pair_test.sh` default and its original
meshes remain available, but those meshes describe the earlier tripod pose.
Use `PAIR_WARP_MODE=measured` above for a meaningful same-position comparison.

## Verification

- Both 4,608,000-byte captures saved and visually inspected.
- GPU mesh dimensions, texture-coordinate bounds, raw-view slots and blend
  sums checked for both generated modes.
- Shared square-lattice helper refactor checked against all twenty earlier
  corner sets; their recorded coordinate bases are unchanged.
- Original low-resolution DUT test: 120 frames, 18.59 fps, exit status 0, all ten shared
  allocations freed. Captured render is local `live_probe.png`.
- Lens mode restarted as the transient `jk-ti-srv-pair` service.
- Fullscreen layout remains GMSL0 raw top-left, GMSL1 raw bottom-left,
  corrected two-camera stitch on the right.

## Full-Resolution Verification (September 8)

- Release build, shell syntax checks and `test_meshes.py` passed.
- Low-resolution fallback regression: 60 frames, 18.78 fps, exit 0, all ten
  allocations freed. Invalid full-resolution use without a pair mesh was
  rejected before opening any camera.
- Regenerating the meshes left the original low-resolution meshes, blend
  files and alignment JSON byte-identical. Calibration was not refitted to
  compensate for a different camera mode; capture remains 1920x1200.
- Full-resolution test: 120 frames in 7.766 seconds, 15.45 fps, exit 0.
  Sustained live playback reached approximately 15.6 fps; the prior long
  low-resolution run was 18.39 fps. These are end-to-end rates, not sensor FPS.
- Full-resolution stage totals: capture wait 0.024 s, copy/map/unmap 11.378 s,
  SRV graph 1.921 s. Capture and copy times sum both parallel workers and
  must not be added to interpret wall time. Larger CPU frame transfers are
  the dominant cost; avoiding those copies is a future optimization.
- All ten shared allocations (23,564,476 bytes) freed after the finite test.
- Deployed executable and full-resolution lens mesh hashes match local
  artifacts. Original four-camera executable and system TI library hashes
  are unchanged. The prior pair executable was retained on the DUT as
  `vx_app_jk_srv_live.out.pre-fullres-20260908` before replacement.
- `fullres_probe.png` is the inspected 1280x800 GPU render; `lowres_before.png`
  is the preceding output. These photographs remain local, not committed.
- Wayland surface verified visible, source and destination 1280x800 at 0,0,
  with an advancing frame counter. Full-resolution mode left running as the
  transient service; boot behavior unchanged.

Exact target test/restart commands, after deployment:

```sh
/opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 120 /tmp/jk-pair-fullres-probe.raw
PAIR_FULL_RES=0 /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 60 /tmp/jk-pair-lowres-regression.raw
systemd-run --unit=jk-ti-srv-pair --collect /opt/jk-ti-srv-pair/run_gmsl_pair_calibrated.sh 0 /tmp/jk-pair-fullres-live.raw
```
