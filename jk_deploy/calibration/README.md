# 4x6 Thermal-Label Calibration Target

`ti_srv_target_4x6.pdf` is a one-page, vector calibration target sized for a
standard 4x6-inch portrait thermal label. Print four identical copies.

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

From this directory:

```sh
gs -q -dSAFER -dBATCH -dNOPAUSE \
  -sDEVICE=pdfwrite \
  -dDEVICEWIDTHPOINTS=288 -dDEVICEHEIGHTPOINTS=432 \
  -dFIXEDMEDIA \
  -sOutputFile=ti_srv_target_4x6.pdf \
  ti_srv_target_4x6.ps
```
