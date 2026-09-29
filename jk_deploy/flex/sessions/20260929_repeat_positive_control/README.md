# Repeated-Capture Positive Control

SIMULATED INPUT, not a new physical camera capture. Do not deploy this result.
`stage_table.py` explicitly refuses its `simulated_input` report flag.

Source images: `20260929T155359Z_marker_inspection/captures/input0..3.png`.
Each 12-frame burst was generated with gain
`0.94 + 0.08*sin(2*pi*frame/12)` plus Gaussian noise (sigma 0.6 BGR levels),
using NumPy RNG seed 52 and OpenCV BGR-to-UYVY conversion. The same first-pass
burst was reordered by 0, 3, and 6 frames for the three passes. Consequently,
their arithmetic means are identical. This checks the entire successful pipeline,
not tolerance to independent real-camera noise or changes in the physical rig.

```sh
env PYTHONPATH=/tmp/jk-opencv4:/tmp/jk-scipy python3 jk_deploy/flex/calibrate_repeated.py \
  /tmp/jk-repeat-control-20260929 \
  jk_deploy/flex/sessions/20260929_repeat_positive_control
```

Result: pass, selected pass 1. The raw test fixture is in the `/tmp` directory
above; averaged images, independent fits, hashes, and measurements are retained
here. Use a new output directory to repeat.

Negative tests also matter:

- `20260929_repeat_simulation` used independently perturbed frames/phases.
  The initial repeatability comparison rejected changes over 10 px near camera
  3's mapping edge and about 0.8 checker cells in a table-corner estimate.
- `20260929_repeat_common_probe` investigated using only checker intersections
  shared by those fits. It rejected camera 2's insufficient common hull coverage
  (about 72% retained, below the 80% gate). These gates were not weakened to pass
  this fixture. The final repeated pipeline selects common support before fitting.
- Comparing the two actual September 29 saved setups, before/after cloth
  adjustment, also rejected the inconsistent mapping/crop.

Workstation unit/regression suite: 53 tests passed. Real burst capture is still
needed to validate the engineering thresholds against the cameras' actual flicker
and noise. These tests do not establish field robustness.

Target change: installed only `/opt/jk-ti-srv-flex/capture_table_bursts.py`.
Its workstation and target SHA-256 match:
`5854134bb6be89e33eab2cc698536fc8c12a5d19d5eec5e8ad1adc147a1ba0ab`.
The helper's `--help` works on the target. No capture, exposure/control changes,
runtime replacement, or live preset switch was performed in this task.
