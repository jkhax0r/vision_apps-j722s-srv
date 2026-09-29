#!/usr/bin/env python3
"""Burst averaging, repeatability gates, and capture cleanup regression tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from average_burst import average_frames, average_raw, check_stationary, motion_diagnostic
from calibrate_repeated import calibrate_bursts, validate_manifest
from capture_table_bursts import FRAME_BYTES, capture
from repeat_consistency import common_checker_support, compare_pair
from stage_table import validate_candidate

HERE = Path(__file__).resolve().parent


class BurstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = cv2.imread(str(HERE/"sessions/20260929T155359Z_marker_inspection/captures/input0.png"))

    def test_stationary_exposure_flicker_averages_without_warp(self):
        frames = [np.clip(self.image.astype(float)*gain, 0, 255).astype(np.uint8)
                  for gain in (.75, .85, .95, 1., 1.05, 1.15)]
        averaged, report = average_frames(frames)
        expected = ((np.stack(frames).sum(0)+3)//6).astype(np.uint8)
        np.testing.assert_array_equal(averaged, expected)
        self.assertGreater(report["mean_luma_peak_to_peak"], 20)
        self.assertEqual(report["frames"], 6)

    def test_global_motion_rejected(self):
        shifted = cv2.warpAffine(self.image, np.float32([[1, 0, 5], [0, 1, 0]]), (1920, 1200))
        with self.assertRaises(ValueError):
            check_stationary(self.image, shifted)

    def test_local_obstruction_rejected(self):
        blocked = self.image.copy()
        blocked[200:750, 550:1250] = (60, 120, 170)
        with self.assertRaises(ValueError):
            check_stationary(self.image, blocked)

    def test_moving_frames_are_averaged_and_warned_not_rejected(self):
        frames = [cv2.warpAffine(self.image, np.float32([[1, 0, shift], [0, 1, 0]]), (1920, 1200))
                  for shift in (0, 5, 10, 15, 20, 25)]
        averaged, report = average_frames(frames)
        expected = ((np.stack(frames).sum(0)+3)//6).astype(np.uint8)
        np.testing.assert_array_equal(averaged, expected)
        self.assertEqual(report["motion_policy"], "warn_only")
        self.assertTrue(any(item.get("warning") for item in report["motion"]))

    def test_unreliable_motion_measurement_only_warns(self):
        blank = np.zeros_like(self.image)
        result = motion_diagnostic(blank, blank)
        self.assertFalse(result["passed"])
        self.assertIn("features", result["warning"])

    def test_duplicate_and_short_bursts_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            average_frames([self.image]*6)
        with self.assertRaisesRegex(ValueError, "6..32"):
            average_frames([self.image]*2)

    def test_wrong_raw_byte_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"input.uyvy"
            path.write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "length"):
                average_raw(path, 12)

    def test_manifest_requires_complete_independent_passes(self):
        manifest = {"schema_version": 1, "status": "complete", "width": 1920, "height": 1200,
                    "format": "UYVY", "frames_per_burst": 12,
                    "passes": [{"directory": f"pass{i:02d}"} for i in range(1, 4)]}
        self.assertEqual(validate_manifest(manifest), (["pass01", "pass02", "pass03"], 12))
        for change in ({"status": "failed"}, {"frames_per_burst": 2},
                       {"passes": [{"directory": "pass01"}]*3},
                       {"passes": [{"directory": "../bad"}, {"directory": "pass02"}, {"directory": "pass03"}]}):
            with self.assertRaises(ValueError):
                validate_manifest(dict(manifest, **change))

    def test_rejected_repeat_session_cannot_publish_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/"source", Path(tmp)/"candidate"
            source.mkdir()
            (source/"burst_manifest.json").write_text('{"status":"failed"}')
            with self.assertRaises(ValueError):
                calibrate_bursts(source, output)
            self.assertEqual(json.loads((output/"report.json").read_text())["status"], "rejected")
            self.assertFalse((output/"four_mesh.bin").exists())

    def test_partial_pass_cannot_be_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/"calibration.json").write_text('{"schema_version":2}')
            for report in ({"status": "passed", "deployment_policy": "repeat-child"},
                           {"status": "passed", "simulated_input": True},
                           {"status": "passed", "deployment_policy": "repeat-confirmed", "repeat_consistency": {"passed": False}}):
                (path/"report.json").write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    validate_candidate(path)


class BurstOrchestrationTests(unittest.TestCase):
    def exercise(self, use_reference):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root/'raw', root/'result'
            source.mkdir()
            names = ['pass01', 'pass02', 'pass03']
            manifest = {'schema_version': 1, 'status': 'complete', 'width': 1920, 'height': 1200,
                        'format': 'UYVY', 'frames_per_burst': 12,
                        'passes': [{'directory': name} for name in names]}
            (source/'burst_manifest.json').write_text(json.dumps(manifest))
            for name in names:
                (source/name).mkdir()
                for i in range(4):
                    (source/name/f'input{i}.uyvy').write_bytes(b'test-only frames')
            reference = root/'marked_reference' if use_reference else None
            if reference:
                reference.mkdir()
                (reference/'report.json').write_text('{"motion_warnings":[]}')
            observed = []
            def fit(source, destination, *args, **kwargs):
                observed.append(kwargs['reference'])
                self.assertEqual(kwargs['reference'], reference)
                destination.mkdir(parents=True)
                (destination/'captures').mkdir()
                report = {key: {} for key in ('artifact_sha256', 'capture_order', 'corner_ids_clockwise_from_front_right',
                          'marker_selection', 'crop_quality', 'crop_coverage', 'heldout_grid_errors',
                          'versions', 'lens_sources', 'source_sha256')}
                report['clean_refinement'] = {'passed': True, 'cameras': [
                    {'input': i, 'warning': '', 'new_checker_intersections': 2} for i in range(4)]}
                (destination/'report.json').write_text(json.dumps(report))
                for name in ('four_mesh.bin', 'four_blend.bin', 'calibration.json', 'session.json',
                             'floor_fits.json', 'holder_geometry.json', 'camera_order.txt', 'comparison.png', 'stitched.png'):
                    (destination/name).write_bytes(b'test artifact')
            image = np.full((32, 32, 3), 100, np.uint8)
            with patch('calibrate_repeated.average_raw', return_value=(image, {'motion': []})), \
                 patch('calibrate_repeated.motion_diagnostic', return_value={'passed': True}) as motion, \
                 patch('calibrate_repeated.subprocess.run') as run, \
                 patch('calibrate_repeated.validate_marker_views', return_value=([], {'selected_ids': [1, 2, 3, 4]})), \
                 patch('calibrate_repeated.common_checker_support', return_value=[]), \
                 patch('calibrate_repeated.calibrate', side_effect=fit), \
                 patch('calibrate_repeated.compare_sessions', return_value={'passed': True, 'selected_pass': 1}):
                result = calibrate_bursts(source, output, reference=reference)
            self.assertEqual(result['status'], 'passed')
            self.assertEqual(len(observed), 3)
            self.assertEqual(motion.call_count, 12)
            self.assertEqual('clean_refinement' in result, use_reference)
            self.assertEqual(run.call_count, 12)
            for call in run.call_args_list:
                command = call.args[0]
                self.assertEqual('--marker-ids' in command, not use_reference)
                if not use_reference:
                    self.assertEqual(command[-5:], ['--marker-ids', '1', '2', '3', '4'])

    def test_marked_stage_reference_stays_none_after_image_comparisons(self):
        self.exercise(False)

    def test_clean_stage_keeps_reference_path_after_image_comparisons(self):
        self.exercise(True)


class MappingTests(unittest.TestCase):
    def test_common_corners_keep_independent_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            directories = [Path(tmp)/f"pass{i}" for i in range(3)]
            x, y = np.meshgrid(np.arange(20), np.arange(20))
            grid = np.c_[x.ravel(), y.ravel()]
            points = grid*[60., 45.]+[300., 150.]
            for p, directory in enumerate(directories):
                directory.mkdir()
                for i in range(4):
                    np.savez(directory/f"input{i}.corners.npz", grid=grid+[p, -p], points=points+p*.1)
            results = common_checker_support(directories)
            self.assertEqual(results[0]["passes"][0]["common"], 400)
            a = np.load(directories[0]/"input0.corners.npz")["points"]
            b = np.load(directories[2]/"input0.corners.npz")["points"]
            np.testing.assert_allclose(b-a, .2)
            self.assertTrue((directories[0]/"input0.corners.full.npz").exists())
            with self.assertRaisesRegex(ValueError, "already selected"):
                common_checker_support(directories)

    def sample_fit(self, shift=(0, 0)):
        shift = np.array(shift)
        x, y = np.meshgrid(np.arange(-9, 10), np.arange(-9, 10))
        class Camera:
            def __init__(self):
                self.grid = np.c_[x.ravel(), y.ravel()].astype(float)+shift
                self.points = (self.grid-shift)*30+[960, 600]
                self.offset = np.zeros(2)
            def map(self, world):
                return (world-shift)*30+[960, 600]+self.offset, np.ones(len(world), bool)
        corners = np.array([[10, -10], [10, 10], [-10, 10], [-10, -10]])+shift
        config = {"capture_order": [0, 1, 2, 3], "front_input": 0,
                  "corner_ids_clockwise_from_front_right": [1, 2, 3, 4], "holder_geometry": {},
                  "crop_cells": [-10, -10, 20, 20], "feather_cells": 1.5,
                  "table_corner_estimates_cells": {str(i+1): p.tolist() for i, p in enumerate(corners)}}
        return config, [Camera() for _ in range(4)]

    def test_identical_and_shifted_grid_origins_pass(self):
        for shift in ((0, 0), (7, -4), (-12, 8)):
            result = compare_pair(self.sample_fit(), self.sample_fit(shift))
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["cameras"][0]["mapping_rms_px"], 0)

    def test_mapping_drift_rejected(self):
        candidate = self.sample_fit()
        candidate[1][2].offset[:] = [6, 0]
        result = compare_pair(self.sample_fit(), candidate)
        self.assertFalse(result["passed"])
        self.assertAlmostEqual(result["cameras"][2]["mapping_rms_px"], 6)

    def test_crop_drift_rejected(self):
        candidate = self.sample_fit()
        candidate[0]["table_corner_estimates_cells"]["1"][0] += 1
        result = compare_pair(self.sample_fit(), candidate)
        self.assertFalse(result["passed"])
        self.assertIn("crop moved", result["reasons"][0])

    def test_changed_camera_order_rejected(self):
        candidate = self.sample_fit()
        candidate[0]["capture_order"] = [0, 2, 1, 3]
        with self.assertRaisesRegex(ValueError, "capture_order"):
            compare_pair(self.sample_fit(), candidate)


class CaptureTests(unittest.TestCase):
    def test_complete_capture_has_three_passes_and_restores_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root/"runtime"
            runtime.mkdir()
            (runtime/"run_flex_stitch.sh").touch()
            resume = root/"resume.sh"
            resume.touch()
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                for option in command:
                    if option.startswith("--stream-to="):
                        with Path(option.split("=", 1)[1]).open("wb") as stream:
                            stream.truncate(6*FRAME_BYTES)
                output = "/dev/video2\n" if command[0] == "media-ctl" and "-e" in command else ""
                return subprocess.CompletedProcess(command, 0, output)
            with patch("capture_table_bursts.subprocess.run", side_effect=run):
                capture(root/"bursts", runtime, frames=6, gap=0, resume=resume)
            self.assertEqual(calls[-1], [str(resume)])
            manifest = json.loads((root/"bursts/burst_manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual([len(p["inputs"]) for p in manifest["passes"]], [4, 4, 4])
            self.assertEqual(validate_manifest(manifest), (["pass01", "pass02", "pass03"], 6))

    def test_failure_resumes_preview_and_records_partial_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root/"runtime"
            runtime.mkdir()
            (runtime/"run_flex_stitch.sh").touch()
            resume = root/"resume.sh"
            resume.touch()
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                if command[0] == "media-ctl" and "-e" in command:
                    text = "/dev/video2\n"
                else:
                    text = ""
                if "--stream-count=6" in command:
                    return subprocess.CompletedProcess(command, 1, "simulated capture error")
                return subprocess.CompletedProcess(command, 0, text)
            with patch("capture_table_bursts.subprocess.run", side_effect=run):
                with self.assertRaisesRegex(RuntimeError, "simulated capture error"):
                    capture(root/"bursts", runtime, frames=6, resume=resume)
            self.assertEqual(calls[-1], [str(resume)])
            manifest = json.loads((root/"bursts/burst_manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["resumed_with"], str(resume))

    def test_existing_directory_refuses_before_touching_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"run_flex_stitch.sh").touch()
            with patch("capture_table_bursts.subprocess.run") as run:
                with self.assertRaises(FileExistsError):
                    capture(root, root)
                run.assert_not_called()

    def test_bad_options_and_missing_runtime_never_stop_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('capture_table_bursts.subprocess.run') as run:
                for options in (dict(passes=2), dict(frames=2), dict(warmup=301), dict(gap=31), {}):
                    with self.subTest(options=options), self.assertRaises(ValueError):
                        capture(root/'new', root, **options)
                (root/'run_flex_stitch.sh').touch()
                with self.assertRaisesRegex(ValueError, 'resume'):
                    capture(root/'new', root, resume=root/'missing')
                run.assert_not_called()

    def test_low_space_never_stops_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'run_flex_stitch.sh').touch()
            with patch('capture_table_bursts.shutil.disk_usage', return_value=SimpleNamespace(free=1)), \
                    patch('capture_table_bursts.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'free'):
                    capture(root/'new', root)
                run.assert_not_called()

    def test_timeout_cancel_short_frame_and_failed_resume_are_recorded(self):
        for failure in ('timeout', 'cancel', 'short', 'restore'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'run_flex_stitch.sh').touch()
                resume = root/'resume.sh'
                resume.touch()
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    if command == [str(resume)] and failure == 'restore':
                        return subprocess.CompletedProcess(command, 1, 'preview unavailable')
                    if '--stream-count=6' in command:
                        if failure == 'timeout':
                            raise subprocess.TimeoutExpired(command, 45)
                        if failure in ('cancel', 'restore'):
                            raise KeyboardInterrupt('Cancelled')
                        path = next(x.split('=', 1)[1] for x in command if x.startswith('--stream-to='))
                        Path(path).write_bytes(b'truncated')
                    return subprocess.CompletedProcess(command, 0, '/dev/video2\n')
                with patch('capture_table_bursts.subprocess.run', side_effect=run), \
                        self.assertRaises((subprocess.TimeoutExpired, KeyboardInterrupt, ValueError, RuntimeError)):
                    capture(root/'new', root, frames=6, resume=resume)
                self.assertEqual(calls[-1], [str(resume)])
                manifest = json.loads((root/'new/burst_manifest.json').read_text())
                self.assertEqual(manifest['status'], 'failed')
                if failure == 'restore':
                    self.assertIn('preview unavailable', manifest['resume_error'])
                else:
                    self.assertEqual(manifest['resumed_with'], str(resume))


if __name__ == "__main__":
    unittest.main()
