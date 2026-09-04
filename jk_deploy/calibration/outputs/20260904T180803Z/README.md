# Calibration Output 20260904T180803Z

Generated with TI's Windows 3D surround-view calibration tool from:

```text
tools/3d_calibration_tool/exe_out/jk/inputs_20260904T175409Z_full_fov
```

Camera order is:

1. Front: GMSL1
2. Right: analog0
3. Back: analog1
4. Left: GMSL0

The calibration tool emitted the new `CALMAT.BIN`, `calmat.c`,
`CHARTPOS.BIN`, `chartPrms.mat`, `test_out.png`, and MAT parameter files into
its previously selected output directory. They were collected at
`2026-09-04T18:08:03Z`. The unchanged lens LUT files are carried forward as
runtime dependencies.

Runtime file SHA-256 checksums:

```text
aa2648531f6f292a993be61906b945e9e152a275108c8ba015b2f35e33caa535  CALMAT.BIN
2cb918b0f274c089976d9daa82d5f53201cd98dd5934588319d6805610dcd6bc  LENS.BIN
c075c706d021614ca42e783071dcb1d183a517a943c98d4479accc0e2fffa711  CHARTPOS.BIN
```

The lens data still uses one shared model for the unlike analog and
TechNexion cameras. This is suitable for bring-up but not final seam quality.
