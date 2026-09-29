#!/usr/bin/env python3
"""Measure five calibration optimizations without applying calibration artifacts."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import cv2
import numpy as np

from calibration_runtime import PreviewPause, run_commands
from prepare_burst import prepared_burst
from stage_table import validate_candidate

HERE = Path(__file__).resolve().parent


def benchmark(source, output, runtime, sections):
    output.mkdir(parents=True, exist_ok=False)
    report = dict(source=str(source), sections={}, source_sha256={
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')})
    def save():
        (output/'benchmark.json').write_text(json.dumps(report, indent=2)+'\n')
    def command(args, log):
        started = time.monotonic()
        with log.open('w') as stream:
            process = subprocess.Popen(list(map(str, args)), stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=2400)
                if code:
                    raise RuntimeError(f'Benchmark command failed ({code}); inspect {log}')
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                raise
        return time.monotonic()-started
    try:
        with (runtime/'calibration.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with PreviewPause():
                if 'workers' in sections:
                    results = []
                    for workers in (1, 2, 4):
                        directory = output/f'workers{workers}'
                        directory.mkdir()
                        jobs = []
                        for i in range(4):
                            image = directory/f'input{i}.png'
                            shutil.copy2(source/'marked_result/prepared/pass01'/image.name, image)
                            jobs.append(dict(command=[sys.executable, HERE/'detect_table.py', image,
                                                       '--marker-ids', '1', '2', '3', '4'],
                                             log=image.with_suffix('.log'), label=f'Detecting workers={workers}, camera={i}'))
                        started = time.monotonic()
                        tasks = run_commands(jobs, workers, max(1, 4//workers))
                        results.append(dict(workers=workers, threads=max(1, 4//workers),
                                            seconds=time.monotonic()-started, tasks=tasks))
                        report['sections']['workers'] = results
                        save()
                    for i in range(4):
                        with np.load(output/f'workers1/input{i}.corners.npz') as a:
                            for workers in (2, 4):
                                with np.load(output/f'workers{workers}/input{i}.corners.npz') as b:
                                    np.testing.assert_array_equal(a['grid'], b['grid'])
                                    np.testing.assert_allclose(a['points'], b['points'], rtol=0, atol=1e-4)
                    report['sections']['worker_output_check'] = 'same grids and subpixel points within 0.0001 px'
                if 'averages' in sections:
                    results, hashes = {}, {}
                    for name, cache, mode in [('cache_cold', output/'cache', 'all'),
                                              ('cache_warm', output/'cache', 'all'),
                                              ('uncached_all', None, 'all'), ('uncached_sampled', None, 'sampled')]:
                        started = time.monotonic()
                        items, pixels = [], []
                        for i in range(4):
                            image, quality, metadata = prepared_burst(source/f'raw/pass01/input{i}.uyvy', 12, cache, mode)
                            pixels.append(hashlib.sha256(image.tobytes()).hexdigest())
                            items.append(dict(camera=i, metadata=metadata, motion_checks=len(quality['motion'])))
                        results[name] = dict(seconds=time.monotonic()-started, cameras=items)
                        hashes[name] = pixels
                        report['sections']['averages'] = results
                        save()
                    if len({tuple(v) for v in hashes.values()}) != 1:
                        raise ValueError('Averaging optimization changed image pixels')
                    report['sections']['averaged_pixel_check'] = 'all four modes byte-identical'
                if 'export' in sections:
                    results = {}
                    selected = json.loads((source/'marked_result/report.json').read_text())['repeat_consistency']['selected_pass']
                    for mode in ('all', 'deferred'):
                        started = time.monotonic()
                        for p in range(1, 4):
                            directory = output/mode/f'pass{p:02d}'
                            original = source/f'marked_result/passes/pass{p:02d}'
                            shutil.copytree(original/'captures', directory/'captures')
                            for name in ('session.json', 'floor_fits.json'):
                                shutil.copy2(original/name, directory/name)
                            options = ['--validate-only'] if mode == 'deferred' else []
                            command([sys.executable, HERE/'bake_floor.py', directory, *options], directory/'bake.log')
                        if mode == 'deferred':
                            directory = output/mode/f'pass{selected:02d}'
                            command([sys.executable, HERE/'bake_floor.py', directory, '--use-fitted'], directory/'export.log')
                        results[mode] = time.monotonic()-started
                        report['sections']['export'] = results
                        save()
                    for name in ('four_mesh.bin', 'four_blend.bin', 'stitched.png'):
                        a, b = [output/mode/f'pass{selected:02d}'/name for mode in ('all', 'deferred')]
                        if a.read_bytes() != b.read_bytes():
                            raise ValueError(f'Deferred export changed {name}')
                    report['sections']['export_output_check'] = 'selected mesh, blend and preview byte-identical'
                if 'combined' in sections:
                    results = {}
                    for stage, raw in (('marked', 'raw'), ('clear', 'raw_clear')):
                        directory = output/stage
                        options = ['--workers', '4', '--defer-bake', '--motion-mode', 'sampled', '--cache', output/'combined_cache']
                        if stage == 'clear':
                            options += ['--reference', output/'marked']
                        results[stage] = command([sys.executable, HERE/'calibrate_repeated.py', source/raw, directory, *options],
                                                 output/(stage+'.log'))
                        validate_candidate(directory)
                        report['sections']['combined'] = results
                        save()
            if 'capture' in sections:
                launcher = Path(json.loads((runtime/'active_table_calibration.json').read_text())['launcher'])
                results = {}
                for mode in ('legacy', 'persistent'):
                    directory = output/('capture_'+mode)
                    options = ['--persistent'] if mode == 'persistent' else []
                    results[mode] = command([sys.executable, HERE/'capture_table_bursts.py', directory,
                                            '--runtime', runtime, '--resume', launcher, *options], output/(mode+'.log'))
                    manifest = json.loads((directory/'burst_manifest.json').read_text())
                    if manifest['status'] != 'complete':
                        raise ValueError('Benchmark capture incomplete')
                    for path in directory.glob('pass*/input*.uyvy'):
                        if path.stat().st_size != 12*1920*1200*2:
                            raise ValueError(f'Wrong frame size: {path}')
                    report['sections']['capture'] = results
                    save()
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', reason=str(error))
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runtime', type=Path, default=Path('/opt/jk-ti-srv-flex'))
    parser.add_argument('--sections', nargs='+', choices=('workers', 'averages', 'export', 'capture', 'combined'),
                        default=['workers', 'averages', 'export', 'capture', 'combined'])
    args = parser.parse_args()
    def stop(signum, frame):
        raise KeyboardInterrupt('Benchmark interrupted')
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps(benchmark(args.source, args.output, args.runtime, args.sections), indent=2))


if __name__ == '__main__':
    main()
