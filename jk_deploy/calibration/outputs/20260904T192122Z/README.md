# Refined Mixed-camera Calibration, 2026-09-04

This calibration refines the target corners in the cleared four-camera
capture after the front camera was tilted upward. Camera order is:

1. front: GMSL1
2. right: analog0
3. back: analog1
4. left: GMSL0

The image and measured world points are recorded in
`../../mixed_camera_points_20260904_refined.json`. Regenerate `CALMAT.BIN`
with:

```sh
python3 ../../fit_mixed_camera_calibration.py \
    ../../mixed_camera_points_20260904_refined.json CALMAT.BIN \
    --template CALMAT.BIN
```

The physical taped rectangle is 1092.2 by 1244.6 mm (43 by 49 inches); it is
intentionally not square. The fitted corner RMS errors are 1.004, 1.344,
1.015, and 1.939 pixels. The runtime uses a flat ground plane at 1.17
mm/LUT-pixel, centered at X=546.1 mm and Y=622.3 mm.

`LENS.BIN` and `CHARTPOS.BIN` remain TI-format runtime dependencies. The
runtime supplies separate focal lengths for the TechNexion and analog pairs,
but a checkerboard intrinsic calibration is still required to replace the
shared approximate radial lens LUT.

## SHA-256

```text
79a75be44c262548bd13b89b75b23bd929c29b61177d86747b6bf1e0066622c6  CALMAT.BIN
c075c706d021614ca42e783071dcb1d183a517a943c98d4479accc0e2fffa711  CHARTPOS.BIN
2cb918b0f274c089976d9daa82d5f53201cd98dd5934588319d6805610dcd6bc  LENS.BIN
```
