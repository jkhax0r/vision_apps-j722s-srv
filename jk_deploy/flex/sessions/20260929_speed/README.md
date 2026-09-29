# Flex calibration performance - September 29, 2026

Target: root@192.168.20.222, four CPU cores, 3.47 GiB RAM, native four-GMSL
1920x1200 UYVY. Dataset: `/root/jk-calibration-jobs/20260929T221730Z_15039e`.
The original successful Touch CAL took 1154.6 seconds including a 120.3-second
corner-removal wait. Its marked/clear processing steps took 443.9/384.9 seconds.

## Measured results

Single-run wall-clock measurements on the Flex, not desktop estimates:

| Change | Workload | Before | After |
| --- | --- | ---: | ---: |
| CPU workers | Detect one four-camera marked pass, preview frozen | 47.7 s, 1 worker | 34.8 s, 2 workers; 24.3 s, 4 workers |
| Deferred export | Validate three fits and export selected mesh/preview | 48.6 s | 36.2 s |
| Average cache | Prepare four 12-frame bursts | 17.4 s uncached | 1.5 s valid cache hit |
| Sampled motion warnings | Prepare four bursts, no cache | 17.4 s | 9.2 s |
| Persistent camera streams | Capture all three passes on all four cameras | 66.9 s | 48.3 s |

Writing a cold average cache took 20.1 seconds for the four bursts; it is not
free. Checksums and decoding are included in the cache-hit measurement.
Worker counts use 4/2/1 OpenCV threads per worker respectively, with BLAS fixed
to one thread. Counts are capped by available memory in Touch CAL.

Combined saved-capture processing passed both stages: **209.3 + 179.3 = 388.6
seconds (6m 29s)**. The earlier Touch CAL used **828.8 seconds (13m 49s)** for
the same saved inputs. That comparison includes freezing the preview for the
optimized run; the earlier Touch CAL left it live. Acquisition, marker-removal
interaction and final application are not included in these processing totals.
Do not add the component savings together or claim these are a fresh full-CAL
stopwatch measurement.

## Correctness

- All worker counts produced the same checker grids and corner positions within
  0.0001 pixel.
- Cached, uncached and sampled-warning averages were byte-identical.
- Deferred export produced byte-identical selected mesh, blend and preview.
- The combined optimized marked and clear stages produced byte-identical mesh,
  blend and stitched preview compared with the original successful target job.
- All six independent fits, both repeat-consistency checks, clean-stage
  refinement and candidate deployment validation passed.
- Both real capture modes produced all 12 bursts. Every burst had 12 distinct,
  correctly sized frames; a decoded persistent-capture image was visually checked.
- The active calibration and boot pointer were not replaced by benchmark output.

Motion diagnostics now check frames 3/6/9/11 against frame 0 for a 12-frame
burst. Every frame is still averaged and checked for duplication. Brief movement
between sampled frames may not generate a warning. Geometric acceptance limits,
independent fit count, image resolution and lens coefficients are unchanged.

## Reproduction

`benchmark.json` contains timings, task breakdowns and tool-source hashes.
`verification.json` contains output equality and distinct-frame results.
The measured source snapshot, reports and computed outputs remain on the target
at `/root/jk-calibration-benchmarks/20260929_speed_v1`.
The 24 newly captured benchmark raw files (1,327,104,000 bytes) were archived at
`/home/jkauf/flex-calibration-backups/benchmarks/20260929_speed_v1/`.
Every file's SHA256 matched the target before removing only those benchmark
raw files from the unit to reclaim space. Original calibration jobs are untouched.
The subsequent `20260929_speed_v2` snapshot adds cache-metadata integrity checks,
stream cleanup hardening, a bounded systemd query, and Touch CAL controller wiring.

To repeat, use a NEW result directory and a completed two-stage capture job:

```sh
TOOLS=$(dirname "$(readlink -f /opt/jk-ti-srv-flex/run_calibration_ui.sh)")/..
BUNDLE=$(realpath "$TOOLS/../..")
env PYTHONPATH="$BUNDLE/python" OPENBLAS_NUM_THREADS=1 OPENCV_OPENCL_RUNTIME=disabled \
  python3 "$TOOLS/benchmark_calibration.py" \
  /root/jk-calibration-jobs/20260929T221730Z_15039e \
  /root/jk-calibration-benchmarks/new_measurement
```

The script takes the calibration lock, freezes/resumes the native renderer for
compute tests, then captures both ways and restores the previously active
preset. It never applies its calibration results. `--sections workers averages
export combined` runs saved-image tests only; `--sections capture` exercises the
real cameras. Capture tests retain approximately 1.3 GB of raw diagnostic data.

The local suite has 184 tests: 162 passed, 22 Qt-only tests skipped locally.
It covers cache corruption/invalidation, average equality, deferred exports,
worker limits/timeouts/failures, native stream splitting/short reads/cancellation,
preview resume/PID identity, persistent-capture restoration, and the existing
calibration/rollback/retry tests.
The Flex passed 43 selected performance/controller/persistent-capture tests
against the final v2 tools in 61.8 seconds. The initial target test invocation
used the wrong fixture search path; it was corrected and the full selected set
rerun successfully. Both invocation logs are retained in the v2 directory.
All 22 Qt touchscreen tests also passed on the Flex against the installed
bundle in 20.9 seconds (`ui_tests.log`), using offscreen fake camera controls.

## Installation

Installed as `/opt/jk-ti-srv-flex/calibration_ui_c530fa951f07`; previous launcher
backup: `/opt/jk-ti-srv-flex/before_cal_ui_20260929T230528Z`.
The native renderer PID remained 140893 across installation. The active/boot
preset remains `table_20260929T221730Z_15039e`. No benchmark calibration was
applied. Touch CAL now enables the five optimizations and pauses the renderer
only during CPU processing; the interactive overlay remains running.
