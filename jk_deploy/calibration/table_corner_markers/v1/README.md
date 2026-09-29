# Table Corner Calibration Markers, v1

Print four identical yellow bases and attach the four different black-and-white
labels. Color identifies the holder visually; the printed ArUco ID identifies
the corner automatically, including its rotation. Different filament colors
are optional and are not part of the identification scheme.

This is a printable prototype, not a physically verified fit. Nothing on the
Flex or its running calibration was changed. The existing colored-object
calibration does not yet consume these IDs automatically; that is a separate
software step. PDFs and synthetic detection tests are included now.

## Files To Use

- `generated/table_corner_cap.stl`: print **four** copies; already oriented
  label-face DOWN on the bed, lips pointing up. No supports intended.
- `generated/corner_markers_4x6.pdf`: four 4x6-inch pages, one ID per page.
  Includes top/bottom circles tangent to the paper edges for the label feeder.
- `generated/corner_1_4x6.pdf` through `corner_4_4x6.pdf`: separate labels.
- `generated/corner_markers_letter.pdf` and `corner_markers_a4.pdf`: alternate
  paper sizes, one full-size target per page.
- `generated/flat_marker_plate.stl`: optional lip-free plate for a table with
  an incompatible edge. Tape it in place; this variant does NOT locate the
  physical table corner automatically.
- STEP files: editable solids in mounted orientation, rather than print pose.
- `generated/corner_marker_preview.png`: top and underside views.
- `generated/marker_geometry.json`: precise sizes, coordinate conventions,
  and known offset from the registered table corner to the marker.
- `generated/corner_cap_reference.stl`: mounted pose for rendering, NOT the
  recommended print orientation. Print `table_corner_cap.stl` instead.

## Dimensions And Fit

| Feature | Size |
| --- | --- |
| Top plate | 130 x 130 mm, approximately 5.1 x 5.1 inches |
| Total width including edge lips | 133 x 133 mm |
| Plate above tabletop | 2 mm, plus paper thickness |
| Edge lips | 3 mm thick, extending 16 mm below tabletop |
| Open corner relief | 40 mm along both edges |
| White label cutout | 100 x 100 mm |
| Black marker outer square | 80 x 80 mm |
| White quiet border | 10 mm on every side |
| Marker center from virtual table corner | 72 mm inward along each edge |

The two downward lips are **locating stops, not spring clamps**. There is no
under-table jaw and no prescribed table thickness. Use removable tape to keep
the holder from lifting or sliding. This is not a structural bracket.

Each stop begins 40 mm from the virtual corner and continues to 124 mm. That
leaves room for modestly rounded corners; aim for corner radius <=35 mm so
there is margin. This is a geometric allowance, not a tested universal card
table fit. A large rolled rim, beveled sidewall, fabric draped over the edge,
or a larger corner radius can prevent proper registration. The tabletop must
be flat under the plate and both lips must contact straight, vertical sides.
Check that all four sit flat without rocking. Use the flat plate or adjust the
source dimensions when the edge does not fit. Do not force it onto the table.

Suggested first print: 0.2 mm layers, 3-4 perimeters, PLA for an indoor fit
test; PETG is another option if that is already a reliable material on your
printer. The thin plate will be mostly solid at normal top/bottom settings.
Print one cap and check the actual table before printing the other three.

## Apply The Labels

1. Print at **100% / actual size**, with no fit, shrink, or auto-crop. The
   4x6 PDF page is exactly 101.6 x 152.4 mm. A label has only 0.8 mm side
   clearance on that stock. Use the letter/A4 alternative if the driver
   cannot preserve size. The circles help feeder alignment, not print scale.
2. Measure the black square: it must be 80 mm on both axes. The 4x6 page also
   has a separate 50 mm scale check. Do not resize the STL to compensate for
   a printer setting.
3. Cut along the faint 100 mm outline, including its 5 mm clipped lower-left
   corner. Keep the full white border. Leave the heading and feeder circles
   off the finished target.
4. Attach it between the shallow L alignment guides. Point the clipped label
   corner toward the chamfered/open outside corner of the plastic base.
   The slight clip is entirely in the white margin, not in the black pattern.
5. Use matte white paper or your white thermal labels. Do not cover the target
   with shiny clear tape or paint over the marker. Keep adhesive underneath.
   Replace faded or damaged labels rather than correcting bits by hand.

No multicolor 3D printer is required. Do not print the base in black and expect
an unprinted yellow surface to substitute for the white marker border.

## Place On The Table

Put one ID at each corner. Suggested convention, viewed from above, clockwise:

| ID | Between cameras |
| --- | --- |
| 1 | Cameras 1 and 2 |
| 2 | Cameras 2 and 3 |
| 3 | Cameras 3 and 4 |
| 4 | Cameras 4 and 1 |

Both neighboring cameras must see the **entire black square and white border**,
not merely a yellow corner. Keep the tabletop checkerboard flat and visible
around the targets. Move cameras if a pattern is severely foreshortened or
cropped. The intended test is for a card-table-scale setup with a low tripod;
80 mm is a starting size, not a guaranteed detection range.

Table width and tripod height do not have to match the previous setup. The
shared marker IDs connect views; checkerboard intersections provide the dense
plane fit. When the caps register correctly, their fixed local offset can
also locate the virtual table corners for cropping, without prescribing the
table's overall dimensions. IDs are unique, not metric world coordinates.

The labels sit 2 mm plus paper above the checker plane. The geometry manifest
records that offset; do not silently treat the marker plane as exactly the
checker plane in precision calibration. Use them for correspondence/orientation
and derive the accurate floor warp from the checker intersections. Raised
hands and other objects will still have parallax in a flat-plane stitch.

## Regenerate And Test

Create a Python environment using `requirements.txt`, then:

```sh
bash generate.sh
```

The preview reuses the renderer in `jk_deploy/camera_rig/v2/render_preview.py`;
run this inside the repository. The STL/STEP/PDF outputs are standalone and do
not need Python or the SDK to print.

On the current workstation, the existing staged packages can be used:

```sh
env PYTHONPATH=/tmp/jk-camera-rig-cadquery-pkgs-20260826:/tmp/jk-opencv4:/tmp/jk-pdf-render-pkgs-20260826 \
  bash jk_deploy/calibration/table_corner_markers/v1/generate.sh
```

Checks cover CAD validity, one connected solid, closed nondegenerate STL
meshes, print dimensions/orientation, exact PDF page size and marker scale,
all four marker IDs under rotation/downsampling, and a synthetic perspective
view. These do not establish physical fit or live-camera detection performance.

ArUco generation and detection use OpenCV's established implementation, not
custom bit patterns: [OpenCV ArUco documentation](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html).
