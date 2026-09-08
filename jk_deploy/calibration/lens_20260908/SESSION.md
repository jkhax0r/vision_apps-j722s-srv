# GMSL Lens Calibration Capture Session

Target: root@192.168.20.222
Remote root: /root/jk-lens-calibration/session_20260908
Local root: this directory in vision_apps-j722s-srv-pair-test.

Each user "go" requests ONE new pose with both GMSL cameras. Never overwrite
earlier poses. Pose folders are pose_001, pose_002, etc.; create with mkdir
without -p for the leaf directory so accidental reuse fails.

Saved pose_001 through pose_010: both 1920x1200 packed UYVY frames (4,608,000 bytes each),
V4L2 format/capture logs, UTC timestamp, full-resolution PNGs, preview.png.
PNG conversion is OpenCV COLOR_YUV2BGR_UYVY followed by ROTATE_180.
Scene photos are local-only and git-ignored. Visual inspection: all 20 frames
show checkerboard detail. The cloth square pitch is 27.25 mm. Detected corner
coordinates are tracked separately; no scene photos are committed.

Capture method used:
1. Stop jk-ti-srv-pair; ensure both GMSL nodes are unowned.
2. For each stable /usr/local/Ahsoka/devices/video/gmslN, save --get-fmt-video.
3. Run both v4l2-ctl captures concurrently, each with --stream-mmap=4,
   --stream-skip=30 --stream-count=1 --stream-to=POSE/gmslN.uyvy,
   bounded by timeout 20. Wait for both and verify exact byte count.
4. Restart the transient pair preview with:
   systemd-run --unit=jk-ti-srv-pair --collect /opt/jk-ti-srv-pair/run_gmsl_pair_test.sh 0 /tmp/jk-pair-live-rgbx.raw
5. Fetch the entire pose directory, convert both images and inspect them.

On the first attempt, stopping the pair preview restored Ahsoka, then an
immediate Ahsoka stop canceled its startup job. Ahsoka ended failed with a
VideoService registration timeout; no camera was held. Capture was retried
successfully. The current pair preview was started while Ahsoka was inactive,
so stopping it for subsequent captures should not restart Ahsoka. Do not
change boot services or restart Ahsoka between poses. Pair preview is running.

Collect about 10-15 genuinely different positions/tilts, holding the rig still
at each capture. Move the entire rig; retain individual camera mount angles.
Moving just the TI marker or taking repeated frames at one pose does not give
new calibration geometry. Keep the cloth as flat and unstretched as possible.

## First Fit (Ten Poses)

The first offline fit is complete; see README.md, fit_intrinsics.py and the
two gmslN_intrinsics.json files. Both cameras have detections for all ten poses.
This is a lens-only OpenCV fisheye model, not the earlier scene-specific mesh.
Poses 8 and 10 were withheld from a separate validation fit. The final model
uses all poses; the held-out results are retained separately in each JSON.
No new lens model has been deployed, and no TI LENS.BIN has been overwritten.

GMSL0: filtered calibration RMS 3.16 pixels, held-out RMS 4.95/4.92 pixels.
GMSL1: filtered calibration RMS 4.68 pixels, held-out RMS 5.22/4.91 pixels.
These are full-resolution image-pixel errors, not physical-distance accuracy.
The remaining error and cloth flatness/printing uncertainty make this an
experimental calibration, not a validated production lens model.
