# Mixed-camera calibration, 2026-09-04

This calibration uses the cleared four-camera capture after the front GMSL
camera was tilted upward. Camera order is:

1. front: GMSL1
2. right: analog0
3. back: analog1
4. left: GMSL0

The target corners are recorded in
`../../mixed_camera_points_20260904.json`. Regenerate `CALMAT.BIN` with:

```sh
python3 ../../fit_mixed_camera_calibration.py \
    ../../mixed_camera_points_20260904.json CALMAT.BIN \
    --template CALMAT.BIN
```

The long blue tape edges independently indicate an equisolid focal length of
about 343 pixels for both GMSL cameras and 273 pixels for both analog cameras.
The runtime launcher supplies those per-type values because TI's stock
`LENS.BIN` format has only one shared focal length and radial table. The fitted
corner RMS errors are 0.983, 1.208, 0.766, and 1.370 pixels.

`LENS.BIN` and `CHARTPOS.BIN` are retained for TI file compatibility. The live
app uses a 1.08 mm/LUT-pixel ground scale centered at X=546.1 mm, Y=590.0 mm so
the taped rectangle fills the display without relying on the TI vehicle-length
scale heuristic.

## SHA-256

```text
58a7b15ba358c8e017e124c6bba8fa0b6cc91282227ad0f51da011879e1b1d62  CALMAT.BIN
c075c706d021614ca42e783071dcb1d183a517a943c98d4479accc0e2fffa711  CHARTPOS.BIN
2cb918b0f274c089976d9daa82d5f53201cd98dd5934588319d6805610dcd6bc  LENS.BIN
```
