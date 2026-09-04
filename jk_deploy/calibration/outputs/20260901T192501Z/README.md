# Archived Calibration Output 20260901T192501Z

This output is incompatible with the current mounting after analog0 and GMSL1
were physically swapped on 2026-09-04. It records the old layout and must not
be enabled for the current camera positions.

Generated with TI's Windows 3D surround-view calibration tool from the
full-field-of-view `640x480` NV12 captures in:

```text
tools/3d_calibration_tool/exe_out/jk/inputs_20260901T185521Z_full_fov
```

Camera order is:

1. Front: analog0
2. Right: GMSL1
3. Back: analog1
4. Left: GMSL0

`CALMAT.BIN`, `LENS.BIN`, and `CHARTPOS.BIN` are installed by
`jk_deploy/deploy.sh`. The remaining files preserve all calibration-tool
outputs needed to inspect or reproduce this result.

Runtime file SHA-256 checksums:

```text
8cdb4ac552cb9a2f4879a812626ff447c7b9258dc803386fa464fdfe3a5d1394  CALMAT.BIN
2cb918b0f274c089976d9daa82d5f53201cd98dd5934588319d6805610dcd6bc  LENS.BIN
c075c706d021614ca42e783071dcb1d183a517a943c98d4479accc0e2fffa711  CHARTPOS.BIN
```

This bring-up calibration uses one shared lens LUT for the unlike analog and
TechNexion cameras. Generate independent camera intrinsics before treating
the seams as production calibration.
