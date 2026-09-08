# First GMSL Lens Fit

Ten stationary poses, two GMSL cameras per pose, captured September 8, 2026.
Each frame is 1920x1200 UYVY; PNG coordinates are rotated 180 degrees.
Grid pitch is the supplied 27.25 mm. Source images remain local and on the DUT;
measured checker-corner coordinates and fitting code are tracked in Git.

## Result

| Camera | Detected poses | Filtered fit RMS | Held-out pose 8 RMS | Held-out pose 10 RMS |
| --- | --- | --- | --- | --- |
| GMSL0 | 10 | 3.16 px | 4.95 px | 4.92 px |
| GMSL1 | 10 | 4.68 px | 5.22 px | 4.91 px |

All errors refer to full-resolution pixels. The held-out poses were excluded
from both training and training-point filtering, but still need a pose estimate
to measure projection error. Held-out results use all detected points, not the
subset selected by the final model. Results do not quantify ground-distance
accuracy or error against a metrology-grade calibration target.

This is an experimental OpenCV fisheye model with k1/k2, zero skew, and the
principal point constrained to the image center. Separate fx and fy are fitted.
The primary equation is r = theta * (1 + k1*theta^2 + k2*theta^4), followed by
the camera's fx/fy scaling and principal-point offset.

The cloth is not a rigid, measured calibration plate. Wrinkles, printed-square
variations, corner localization, and the constrained lens model can contribute
to residual error. Do not interpret a low training error alone as proof of a
fully calibrated lens. The two held-out poses are a first check, not independent
validation of the cloth's geometry.

Unlike the earlier floor stitch, this model does not flatten the ground or
blend cameras. Local `lens_comparison_pose008.png` shows raw views on the left
and lens-only correction on the right, with GMSL0 above GMSL1. Some black border
and a different perspective are expected in this un-cropped diagnostic view.
The images marked `undistorted` use the all-pose model; held-out error numbers
come from the separate eight-pose models stored in the JSON files.

No DUT application, library, boot configuration, or TI calibration BIN was
changed by this fitting step. This is not yet a TI CSV/LENS.BIN export. In
particular, TI's radial-table format uses one focal scale while these first
models permit separate fx/fy; exporting needs an explicit approximation or
a constrained refit, not silently substituting an averaged focal length.

## Reproduce

Tested fitting dependencies: OpenCV 4.12.0.88 (cv2 reports 4.12.0), NumPy 2.2.6,
SciPy 1.15.3. Packages were staged locally, not installed on the DUT or into the
host's default environment. OpenCV 5.0.0's calibration call errored on the same
variable-size point lists; the 4.12 call succeeds.

From the repository root in the current workspace:

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/calibration/lens_20260908/fit_intrinsics.py fit
```

The saved corner NPZ files allow numerical fitting without the room images.
Preview generation additionally needs the local PNGs. Re-extract corners from
the original captures with `detect --force`; it never alters the raw captures.
Most initial detections used OpenCV 5.0.0; pose_003/GMSL1 was detected with
4.12.0. The saved measurements are the authoritative inputs for these results.

Detection uses OpenCV subpixel corners and a small SB seed, then follows the
repeating lattice. It corrects skipped-cell seeds and reduces oblique integer
bases to square-cell axes. Pose_009/GMSL0 specifically required that latter
correction. Original coordinates are preserved, and applied bases are logged
in the result JSONs. Approximate initial fisheye undistortion plus a homography
rejects inconsistent grid extensions before fitting the camera model.

The first fit removes points with residual above 10 pixels and requires at
least 65 percent of a view's points to remain. It then refits. This is a
first-pass outlier policy, not a claim that all remaining cloth points are
geometrically exact.
