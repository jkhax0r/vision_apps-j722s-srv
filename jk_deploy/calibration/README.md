# 4x6 Thermal-Label Calibration Target

These one-page vector targets are sized for a standard 4x6-inch portrait
thermal label. Choose one placement and print four identical copies:

- `ti_srv_target_4x6_centered.pdf`: vertically centered.
- `ti_srv_target_4x6_10mm_up.pdf`: shifted 10 mm above center.
- `ti_srv_target_4x6_10mm_down.pdf`: shifted 10 mm below center.
- `ti_srv_target_4x6.pdf`: compatibility alias of the 10 mm-up version.

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
