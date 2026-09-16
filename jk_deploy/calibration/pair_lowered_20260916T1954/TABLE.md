# Fullscreen Table View

The default live view now uses the entire 1280x800 LCD for one stitched
projection. Both raw-camera panels are removed. This is a new GPU LUT;
the executable, GPU library and camera poses/lens fits are unchanged.

## Framing And Coverage

`table_bounds.json` uses the nominal 4x4-foot (1219.2 mm square) table.
Its far-left corner is estimated from the saved GMSL0 image at (885,53);
the opposite far corner in GMSL1 at (895,79) cross-checks the table width.
These are approximate edges, not newly surveyed corner positions.

The active `fill` framing reaches both side edges and the far edge. It
shows the full 48-inch width and 30 inches of depth, preserving square
checker proportions on the 16:10 LCD. The near 18 inches of table are
outside this crop. `contain` in the JSON instead fits all 48x48 inches
with side margins; it is not the active layout.

The expanded view extrapolates the calibrated floor plane beyond the hull
of detected checker corners, but never samples outside either camera's
actual image or behind a camera. Missing coverage is black, not stretched
edge pixels or fabricated content. At this lowered camera position:

- Flat `fill` has approximately 8.26% uncovered area, near the tripod.
- Bowl `fill` has approximately 8.44% uncovered area.
- A full-table `contain` check found approximately 35.6% of the table
  outside both cameras' views; changing layout cannot recover that region.

Both modes keep the existing one-cell feather and seam x=-3.75. Camera
fallback weights can differ near the image limits, so unlike the tight
split-pane test, the full-table blend BINs are not byte-identical. Bowl
uses the same physical surface scale; the wider table reaches heights
up to about 77 mm rather than the tight crop's 50 mm. Flat is left running.

## Use And Rebuild

```sh
# On DUT: mode switches retain the full-table layout.
~/srv_view.sh flat
~/srv_view.sh bowl

# Optional return to the previous raw-left / stitched-right layout.
PAIR_LAYOUT=split ~/srv_view.sh flat
PAIR_LAYOUT=table ~/srv_view.sh flat
```

`PAIR_LAYOUT=auto` chooses table for sessions containing table artifacts,
and split for older sessions or the checker-interpolated `measured` mode.

From the isolated worktree:

```sh
# Rebuild poses, split maps, bowl maps and table maps, then run tests.
bash jk_deploy/calibration/pair_lowered_20260916T1954/rebuild.sh
ssh root@192.168.20.222 systemctl stop jk-ti-srv-pair
TARGET=root@192.168.20.222 bash jk_deploy/deploy_pair_alignment.sh
ssh root@192.168.20.222 'PAIR_LAYOUT=table /root/srv_view.sh flat'
```

For framing-only edits, change `table_bounds.json` and run `make_table.py`
and `test_table.py` with the existing calibration Python environment,
then deploy. `table_settings.json` stores hashes of the six new BINs and
their calibration/bounds dependencies. Launcher preflight rejects stale
or mismatched files before stopping a working live view.

`make_table.py` creates corrected mappings for all four GPU mesh quadrants
instead of using quadrants 0/3 for raw views. It retains the native
1920x1200 source coordinates, orientation, and GPU texture-slot order.
`test_table.py` checks quadrant continuity, bounds, blend normalization,
aspect ratio, the actual blind region, hashes and launcher selection.

## Verification

All five table tests, five prior bowl tests, native-mesh tests and shell
syntax checks pass. The DUT 90-frame flat test exited cleanly: 5.821 seconds,
15.46 fps, all shared allocations freed. Live performance returns toward
15.7 fps after startup. `/tmp/jk-table-flat-probe.raw` was inspected locally
as `live_table_probe.png`. It shows one full-screen corrected view, with
no raw side panels; the blind region is intentionally visible.

No system libraries, original four-camera app or boot services changed.
