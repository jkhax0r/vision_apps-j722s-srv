# 4x6 Thermal-Label Calibration Target

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
