"""Two-stage coordinate transfer, missing coverage, and provenance regression tests."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from bake_floor import FloorCamera
from calibrate_table import calibrate
from check_calibration_markers import check
from fit_floor import project, rotations, transform
from refine_clean_table import clean_config, transfer_grid
from stage_table import validate_candidate

HERE = Path(__file__).parent
REFERENCE = HERE/'sessions/20260929_flexible_v2'


class TransferTests(unittest.TestCase):
    def setUp(self):
        x, y = np.meshgrid(np.arange(24), np.arange(24))
        self.world = np.c_[x.ravel(), y.ravel()].astype(float)
        self.points = self.world*[40, 30]+[250, 150]
        self.keep = (self.world[:, 0] > 2) & (self.world[:, 1] > 2)

    def transfer(self, grid=None, points=None):
        return transfer_grid(self.world[self.keep], self.points[self.keep],
                             self.world if grid is None else grid, self.points if points is None else points)

    def test_all_integer_origins_and_orientations_preserve_new_corners(self):
        for rotation in rotations():
            shift = np.array([7, -13])
            local = (self.world-shift)@rotation
            r, s, quality = self.transfer(local)
            np.testing.assert_array_equal(local@r.T+s, self.world)
            self.assertEqual(quality['new_checker_intersections'], int((~self.keep).sum()))
            self.assertGreater(quality['outside_old_checker_hull'], 0)
            self.assertEqual(quality['shared_pixel_rms'], 0)

    def test_small_displacement_warns_without_warping_measurements(self):
        rotation, shift, quality = self.transfer(points=self.points+[1.2, 0])
        np.testing.assert_array_equal(self.world@rotation.T+shift, self.world)
        self.assertTrue(quality['warning'])

    def test_large_displacement_cannot_be_silently_merged(self):
        with self.assertRaisesRegex(ValueError, 'Too few unchanged'):
            self.transfer(points=self.points+[8, 0])

    def test_mixed_cell_phase_is_rejected(self):
        grid = self.world.copy()
        grid[-20:, 0] += 1
        with self.assertRaises(ValueError):
            self.transfer(grid=grid)

    def test_invalid_and_duplicate_measurements_are_rejected(self):
        bad = self.points.copy()
        bad[0, 0] = np.nan
        with self.assertRaises(ValueError):
            self.transfer(points=bad)
        with self.assertRaises(ValueError):
            self.transfer(points=np.tile(self.points[0], (len(self.points), 1)))

    def test_uncovered_corner_gets_real_residual_correction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'captures').mkdir()
            cv2.imwrite(str(root/'captures/input0.png'), np.zeros((1200, 1920, 3), np.uint8))
            h = np.array([[.035, 0, -.4], [0, .035, -.4], [0, 0, 1.]])
            base = project(np.c_[transform(self.world, h), np.ones(len(self.world))])
            correction = np.c_[2+self.world[:, 0]*.08, -2+self.world[:, 1]*.04]
            points = base+correction
            def camera(keep):
                np.savez(root/'captures/input0.floor.npz', grid=self.world[keep], points=points[keep])
                return FloorCamera(root, {'input': 0, 'rotation': [[1, 0], [0, 1]], 'shift': [0, 0]}, h)
            marked = camera(self.keep)
            clear = camera(np.ones(len(points), bool))
            measured = self.world[~self.keep]
            old, _ = marked.map(measured)
            new, _ = clear.map(measured)
            expected = points[~self.keep]+.5
            self.assertGreater(np.linalg.norm(old-expected, axis=1).mean(), 2)
            self.assertLess(np.linalg.norm(new-expected, axis=1).max(), 1e-7)


class CleanConfigTests(unittest.TestCase):
    def test_retained_markers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'still visible'):
            clean_config(REFERENCE, REFERENCE)

    def test_reference_crop_and_identity_survive_grid_reindexing(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            shutil.copytree(REFERENCE/'captures', session/'captures')
            for i in range(4):
                file = session/'captures'/f'input{i}.floor.npz'
                with np.load(file) as data:
                    grid, points = data['grid'], data['points']
                np.savez(file, grid=grid[:, ::-1]+[13, -7], points=points)
            with patch('refine_clean_table.cv2.aruco.ArucoDetector') as detector:
                detector.return_value.detectMarkers.return_value = ([], None, [])
                config = clean_config(session, REFERENCE)
            previous = json.loads((REFERENCE/'session.json').read_text())
            for key in ('crop_cells', 'view_frame', 'table_corner_estimates_cells',
                        'capture_order', 'corner_ids_clockwise_from_front_right'):
                self.assertEqual(config[key], previous[key])
            self.assertTrue(config['clean_refinement']['passed'])
            self.assertTrue(all(c['coordinate_rms_cells'] < .01 for c in config['clean_refinement']['cameras']))

    def test_stage_refuses_missing_refinement_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            for name in ('calibration.json', 'report.json', 'four_mesh.bin', 'four_blend.bin', 'camera_order.txt'):
                shutil.copy2(REFERENCE/name, session/name)
            config = json.loads((session/'calibration.json').read_text())
            config['clean_refinement'] = {'passed': True}
            (session/'calibration.json').write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, 'Two-stage'):
                validate_candidate(session)

    def test_clean_pipeline_bakes_and_validates_native_artifacts(self):
        # Saved marked imagery exercises the fit/build pipeline with decoding
        # suppressed. Actual marker removal still requires a physical capture.
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'candidate'
            with patch('refine_clean_table.cv2.aruco.ArucoDetector') as detector:
                detector.return_value.detectMarkers.return_value = ([], None, [])
                result = calibrate(REFERENCE/'captures', output, reference=REFERENCE,
                                   detected_corners=REFERENCE/'captures')
            self.assertEqual(result['status'], 'passed')
            self.assertTrue(result['clean_refinement']['passed'])
            validate_candidate(output)
            original = json.loads((REFERENCE/'session.json').read_text())
            config = json.loads((output/'calibration.json').read_text())
            self.assertEqual(config['crop_cells'], original['crop_cells'])
            self.assertEqual(config['capture_order'], original['capture_order'])


class MarkerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        manifest = {'schema_version': 1, 'status': 'complete', 'width': 1920, 'height': 1200,
                    'format': 'UYVY', 'frames_per_burst': 12,
                    'passes': [{'directory': f'pass{i:02d}'} for i in range(1, 4)]}
        (self.root/'burst_manifest.json').write_text(json.dumps(manifest))
        self.images = [cv2.imread(str(REFERENCE/'captures'/f'input{i}.png')) for i in range(4)]

    def check(self, marked_check=None):
        with patch('check_calibration_markers.average_raw', side_effect=[(frame, {}) for frame in self.images]):
            return check(self.root, self.root/'result.json', marked_check)

    def test_visible_markers_identified_before_removal_prompt(self):
        result = self.check()
        self.assertTrue(result['passed'])
        self.assertEqual(result['marker_selection']['selected_ids'], [1, 2, 3, 4])

    def test_clear_stage_rejects_remaining_corner_markers(self):
        self.check()
        with self.assertRaisesRegex(ValueError, 'still visible'):
            self.check(self.root/'result.json')

    def test_clear_stage_accepts_no_remaining_markers(self):
        self.check()
        with patch('check_calibration_markers.cv2.aruco.ArucoDetector') as detector:
            detector.return_value.detectMarkers.return_value = ([], None, [])
            self.assertTrue(self.check(self.root/'result.json')['markers_removed'])

    def test_missing_markers_fail_first_stage(self):
        with patch('check_calibration_markers.cv2.aruco.ArucoDetector') as detector:
            detector.return_value.detectMarkers.return_value = ([], None, [])
            with self.assertRaises(ValueError):
                self.check()


if __name__ == '__main__':
    unittest.main()
