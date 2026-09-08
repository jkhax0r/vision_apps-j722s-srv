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

The executable and TI library are unchanged from the isolated pair test.
There is no new per-frame CPU lens-correction stage. Input normalization
still reduces each full-FOV frame to 640x400 before GPU rendering. That limits
sharpness and can alias the distant checker squares even with correct geometry.
Raised objects can also split at the seam because this is a floor-plane warp.

## Reproduce

From the `vision_apps-j722s-srv-pair-test` worktree:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/calibration/pair_final_20260908T184734Z/make_pair.py
TARGET=root@192.168.20.222 bash jk_deploy/deploy_pair_alignment.sh
```

Detected corner files, fixed lens JSONs, marker seeds/masks and fitted poses
are saved. The script produces both GPU meshes, byte blend tables and offline
previews. It uses the saved local images to refine marker corners and produce
previews; ready-made BIN files can be deployed without the photographs.

The deployment is limited to `/opt/jk-ti-srv-pair`: versioned calibration
files and shell launchers only. It does not overwrite any four-camera TI
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
- Lens-mode DUT test: 120 frames, 18.59 fps, exit status 0, all ten shared
  allocations freed. Captured render is local `live_probe.png`.
- Lens mode restarted as the transient `jk-ti-srv-pair` service.
- Fullscreen layout remains GMSL0 raw top-left, GMSL1 raw bottom-left,
  corrected two-camera stitch on the right.
