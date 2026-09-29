#!/usr/bin/env python3
"""Safety and result-equivalence tests for bounded calibration optimizations."""
import contextlib
import io
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from average_burst import average_frames, FRAME_BYTES
from bake_floor import bake
from calibration_runtime import PreviewPause, available_workers, run_commands
from persistent_bursts import capture_bursts, read_frame
from prepare_burst import prepared_burst
from stage_table import validate_candidate

HERE = Path(__file__).resolve().parent


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_sampled_warnings_preserve_all_averaged_pixels(self):
        frames = [np.full((1200, 1920, 3), 80+i*3, np.uint8) for i in range(12)]
        with patch('average_burst.motion_diagnostic', return_value={'passed': True}) as motion:
            full, a = average_frames(frames)
            self.assertEqual(motion.call_count, 11)
            motion.reset_mock()
            sampled, b = average_frames(frames, 'sampled')
            self.assertEqual(motion.call_count, 4)
        np.testing.assert_array_equal(full, sampled)
        self.assertEqual(b['motion_checked_frames'], [3, 6, 9, 11])
        self.assertEqual(a['distinct_frames'], b['distinct_frames'])
        with self.assertRaises(ValueError):
            average_frames(frames, 'none')

    def test_cache_hits_and_corruption_rebuilds(self):
        raw = self.root/'input.uyvy'
        with raw.open('wb') as stream:
            stream.truncate(6*FRAME_BYTES)
        image = np.full((1200, 1920, 3), 92, np.uint8)
        quality = {'frames': 6, 'motion_mode': 'all', 'motion': []}
        cache = self.root/'cache'
        with patch('prepare_burst.average_burst.average_raw', return_value=(image, quality)) as average:
            a, _, first = prepared_burst(raw, 6, cache)
            b, _, second = prepared_burst(raw, 6, cache)
            self.assertFalse(first['cache_hit'])
            self.assertTrue(second['cache_hit'])
            self.assertEqual(average.call_count, 1)
            np.testing.assert_array_equal(a, b)
            next(cache.glob('*.png')).write_bytes(b'broken')
            self.assertFalse(prepared_burst(raw, 6, cache)[2]['cache_hit'])
            self.assertEqual(average.call_count, 2)
            metadata = next(cache.glob('*.json'))
            altered = json.loads(metadata.read_text())
            altered['quality']['motion'] = 'corrupt'
            metadata.write_text(json.dumps(altered))
            self.assertFalse(prepared_burst(raw, 6, cache)[2]['cache_hit'])
            self.assertEqual(average.call_count, 3)
            with raw.open('r+b') as stream:
                stream.write(b'new')
            self.assertFalse(prepared_burst(raw, 6, cache)[2]['cache_hit'])
            self.assertEqual(average.call_count, 4)
            with self.assertRaisesRegex(ValueError, 'length'):
                prepared_burst(raw, 12, cache)

    def test_cache_motion_mode_is_part_of_identity(self):
        raw = self.root/'input.uyvy'
        with raw.open('wb') as stream:
            stream.truncate(6*FRAME_BYTES)
        image = np.zeros((1200, 1920, 3), np.uint8)
        def average(path, count, mode):
            return image, {'frames': count, 'motion_mode': mode, 'motion': []}
        with patch('prepare_burst.average_burst.average_raw', side_effect=average) as call:
            prepared_burst(raw, 6, self.root/'cache', 'all')
            prepared_burst(raw, 6, self.root/'cache', 'sampled')
            self.assertEqual(call.call_count, 2)

    def job(self, name, source, timeout=5):
        return dict(label=name, command=[sys.executable, '-c', source], log=self.root/(name+'.log'), timeout=timeout)

    def test_worker_thread_budget_and_nonzero_exit(self):
        source = "import os; assert os.environ['JK_CAL_THREADS']=='1'; assert os.environ['OPENBLAS_NUM_THREADS']=='1'"
        self.assertEqual(len(run_commands([self.job(str(i), source) for i in range(4)], 4, 1)), 4)
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            run_commands([self.job('bad', 'raise SystemExit(2)')], 1)
        with self.assertRaises(ValueError):
            run_commands([], 5)

    def test_worker_timeout_reaps_child(self):
        pidfile = self.root/'pid'
        source = f"import os,time; from pathlib import Path; Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
        with self.assertRaises(TimeoutError):
            run_commands([self.job('timeout', source, .3)])
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)

    def test_worker_count_reserves_memory_and_respects_cpu_count(self):
        for available, cpus, expected in ((3300*1024, 4, 4), (2048*1024, 4, 2),
                                           (800*1024, 4, 1), (3300*1024, 2, 2)):
            with patch('calibration_runtime.Path.read_text', return_value=f'MemAvailable: {available} kB\n'), \
                 patch('calibration_runtime.os.cpu_count', return_value=cpus):
                self.assertEqual(available_workers(), expected)

    def test_worker_spawn_failure_reaps_other_children(self):
        import subprocess
        original = subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            process = original(*args, **kwargs)
            children.append(process)
            return process
        jobs = [self.job('sleeping', 'import time; time.sleep(30)'),
                dict(label='missing', command=[str(self.root/'nonexistent')], log=self.root/'missing.log')]
        with patch('calibration_runtime.subprocess.Popen', side_effect=launch), self.assertRaises(FileNotFoundError):
            run_commands(jobs, 2)
        self.assertIsNotNone(children[0].poll())

    def test_preview_resumes_after_failure_but_not_reused_pid(self):
        with patch('calibration_runtime.subprocess.check_output', return_value='123'), \
             patch.object(PreviewPause, 'process_identity', return_value='start'), \
             patch('calibration_runtime.os.kill') as kill:
            with self.assertRaisesRegex(ValueError, 'fit'):
                with PreviewPause():
                    raise ValueError('fit failed')
            self.assertEqual(kill.call_args_list[-1].args, (123, signal.SIGCONT))
        with patch('calibration_runtime.subprocess.check_output', return_value='123'), \
             patch.object(PreviewPause, 'process_identity', side_effect=['old', 'new']), \
             patch('calibration_runtime.os.kill') as kill:
            with PreviewPause():
                pass
            kill.assert_called_once_with(123, signal.SIGSTOP)

    def test_persistent_stream_splits_exact_frames_and_exits(self):
        paths = [self.root/f'pass{i}.raw' for i in range(3)]
        source = "import os,time; os.write(1, bytes(range(120))); time.sleep(30)"
        observations = capture_bursts([sys.executable, '-c', source], paths, 2, 8, 0, self.root/'stream.log')
        self.assertEqual([o['bytes'] for o in observations], [16, 16, 16])
        for i, path in enumerate(paths):
            self.assertEqual(path.read_bytes(), bytes(range(i*16, (i+1)*16)))

    def test_short_persistent_stream_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'mid-frame'):
            capture_bursts([sys.executable, '-c', "import os; os.write(1,b'short')"],
                           [self.root/'short.raw'], 2, 8, 0, self.root/'short.log')

    def test_cancelled_persistent_stream_reaps_child(self):
        processes = []
        import subprocess
        original = subprocess.Popen
        def launch(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process
        with patch('persistent_bursts.subprocess.Popen', side_effect=launch), \
             patch('persistent_bursts.read_frame', side_effect=KeyboardInterrupt), \
             self.assertRaises(KeyboardInterrupt):
            capture_bursts([sys.executable, '-c', 'import time; time.sleep(30)'],
                           [self.root/'cancel.raw'], 2, 8, 0, self.root/'cancel.log')
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)

    def test_no_frame_timeout(self):
        read, write = os.pipe()
        with os.fdopen(read, 'rb') as stream, os.fdopen(write, 'wb'), selectors.DefaultSelector() as selector:
            selector.register(stream, selectors.EVENT_READ)
            with self.assertRaises(TimeoutError):
                read_frame(stream, 8, selector, timeout=.02)

    def test_deferred_export_preserves_mesh_blend_and_preview(self):
        original = HERE/'sessions/20260929T155359Z_marker_inspection'
        for name in ('full', 'deferred'):
            directory = self.root/name
            shutil.copytree(original/'captures', directory/'captures')
            for filename in ('session.json', 'floor_fits.json'):
                shutil.copy2(original/filename, directory/filename)
        with contextlib.redirect_stdout(io.StringIO()):
            bake(self.root/'full')
            result = bake(self.root/'deferred', validate_only=True)
            self.assertTrue(result['artifacts_deferred'])
            self.assertFalse((self.root/'deferred/four_mesh.bin').exists())
            result['schema_version'] = 2
            (self.root/'deferred/calibration.json').write_text(json.dumps(result))
            (self.root/'deferred/report.json').write_text('{"status":"passed","artifacts_deferred":true}')
            with self.assertRaisesRegex(ValueError, 'Deferred'):
                validate_candidate(self.root/'deferred')
            bake(self.root/'deferred', use_fitted=True)
        for name in ('four_mesh.bin', 'four_blend.bin', 'stitched.png'):
            self.assertEqual((self.root/'full'/name).read_bytes(), (self.root/'deferred'/name).read_bytes())


if __name__ == '__main__':
    unittest.main()
