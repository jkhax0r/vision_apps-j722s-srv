# 4x6 Thermal-Label Calibration Target

## Camera Intrinsic Checkerboard

Use `camera_intrinsics_checkerboard_4x6_edge_anchors.pdf` to measure each
camera's lens distortion before running the TI surround-view calibration. It
contains a `7 x 9` grid with `6 x 8` detectable inner corners and exact `13 mm`
squares. The solid 0.25-inch circles are tangent to the top and bottom label
edges to prevent the thermal-printer path from vertically recentering the
checkerboard.

The fixed-canvas SP410 version is
`camera_intrinsics_checkerboard_4x6_edge_anchors_203dpi.png`. Print either
version at 100%/Actual Size on 4x6-inch media. Verify several squares measure
`13.0 mm` horizontally and vertically, then attach the complete label to a
flat, rigid backing. The circles are printer-registration marks and are not
part of the checkerboard detector.

For calibration, keep the camera rig fixed and capture approximately 20-25
sharp checkerboard views per camera. Move and tilt the board so its detected
corners cover the image center, all four edges, and all four corners. The
entire checkerboard must be visible in each retained frame.

## TI Surround-View Floor Targets

These one-page vector targets are sized for a standard 4x6-inch portrait
thermal label. Choose one placement and print four identical copies:

- `ti_srv_target_4x6_centered.pdf`: vertically centered.
- `ti_srv_target_4x6_10mm_up.pdf`: shifted 10 mm above center.
- `ti_srv_target_4x6_10mm_down.pdf`: shifted 10 mm below center.
- `ti_srv_target_4x6_centered_edge_anchors.pdf`: centered, with 0.25-inch
  registration circles tangent to the top and bottom label edges.
- `ti_srv_target_4x6.pdf`: compatibility alias of the 10 mm-up version.

Fixed-canvas SP410 versions are also provided as 203-DPI PNG files:

- `ti_srv_target_4x6_centered_203dpi.png`
- `ti_srv_target_4x6_10mm_up_203dpi.png`
- `ti_srv_target_4x6_10mm_down_203dpi.png`
- `ti_srv_target_4x6_centered_edge_anchors_203dpi.png`

Use these PNGs if the PDF print application crops the white margins and
recenters the black target. Each PNG contains the complete 4x6-inch label as
an `812x1218` image, so target placement is baked into the page. Print at
100%/Actual Size with 4x6 media and disable Fit, Crop, and content centering.

## Print Settings

- Paper/label size: 4x6 inches.
- Scale: 100% or Actual Size.
- Disable Fit, Shrink, Fill, and borderless expansion.
- Orientation: portrait.
- Darkness: high enough for a uniform black area without distorting edges.

The expected printed dimensions are:

- Outer black square: 3.500 x 3.500 inches.
- Inner white square: 1.167 x 1.167 inches.
- Left and right margins: 0.250 inch.
Vertical margins depend on the selected version:

| Version | Bottom margin | Top margin |
| --- | ---: | ---: |
| Centered | 1.250 inches | 1.250 inches |
| 10 mm up | 1.644 inches | 0.856 inch |
| 10 mm down | 0.856 inch | 1.644 inches |

Measure the outer square horizontally and vertically on the first label. If
either dimension differs materially from 3.500 inches, correct the printer
scaling before printing the remaining labels. Use the actual measured square
size in the calibration configuration.

## Placement

Attach each label to flat cardstock or another rigid backing. Place the four
targets at the corners of a rectangle around the camera rig. Keep every target
flat, mutually parallel, and aligned to the same X/Y axes.

Use the lower-left corner of the bottom-left target as the coordinate origin.
Measure the X/Y location of the lower-left corner of every other target from
that origin. Each camera must see the two complete targets on its side.

## Regenerate The PDF

From this directory, regenerate every PDF with:

```sh
./generate_targets.sh
```

## Capture Camera Images

Mount the cameras in their final positions and place the four targets so each
camera sees the two complete targets on its side. Keep the rig and targets
stationary, then run this from the SDK host:

```sh
TARGET=root@192.168.20.222 ./jk_deploy/capture_and_fetch_calibration.sh
```

The target warms up all four streams, takes a near-simultaneous frame from
each, and restores the stock Ahsoka application afterward. Captures are saved
under `jk_deploy/calibration/captures/TIMESTAMP/` with:

- Four `640x480` NV12 `.yuv` files for TI's `420sp` input fields.
- Four PNG previews for identifying each physical camera direction.
- `manifest.txt` with capture slots, device nodes, format, and checksums.
- `capture.log` with the complete target-side run.

The capture checks each frame's luma range. A uniform decoder no-signal image,
such as the analog inputs' solid blue frame, makes the command fail while
still fetching the archive and PNG previews for diagnosis.

In the TI calibration tool, enter camera count `4`, height `480`, width `640`,
and pitch `640`. Assign each YUV file to front/right/back/left according to the
PNG previews and the final physical mounting. Camera slot names identify the
capture connector only; they do not imply a physical direction.

## Current Tripod Camera Identities

The front and right cameras were physically swapped on 2026-09-04. The current
clockwise mounting is:

| Direction | Capture file prefix | Stable input |
| --- | --- | --- |
| Front | `camera0_front_gmsl1` | `/usr/local/Ahsoka/devices/video/gmsl1` |
| Right | `camera1_right_analog0` | `/usr/local/Ahsoka/devices/video/analog0` |
| Rear | `camera2_back_analog1` | `/usr/local/Ahsoka/devices/video/analog1` |
| Left | `camera3_left_gmsl0` | `/usr/local/Ahsoka/devices/video/gmsl0` |

Viewed from above, the clockwise order is `gmsl1`, `analog0`, `analog1`,
`gmsl0`. Re-verify this table after moving cameras between physical mounts or
rewiring camera inputs.

The JK input path mirrors both analog inputs horizontally to undo their
rear-view camera image. It rotates both TechNexion inputs 180 degrees to match
their physical mounting orientation. These transforms are applied before
writing calibration YUVs or sending frames to the GPU. Calibration output
generated from older YUV orientations must not be reused.

## Current Calibration Output

The active output is `outputs/20260904T185944Z/`. It was fitted from the
cleared post-swap frames in `inputs_20260904T175409Z_full_fov`, using the blue
tape as a straight-line lens check and the target corners listed in
`mixed_camera_points_20260904.json`. It follows the current
front/right/back/left order. The older `20260901T192501Z` and
`20260904T180803Z` outputs remain archived for comparison.
