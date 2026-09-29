#!/usr/bin/env python3
"""Regression for a large checker patch missing a corner across tripod legs."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from align_markers import marker_grid_support
from detect_table import check_marker_patch, detect_retry

FIXTURE = Path(__file__).resolve().parent/'sessions/20260929_checker_retry/input0.png'


class CheckerRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name)/'input0.png'
        shutil.copy2(FIXTURE, self.image)

    def test_real_occluded_grid_retries_before_accepting(self):
        attempts = detect_retry(self.image, [1, 2, 3, 4])
        self.assertEqual(attempts[0]['variant'], 'native')
        self.assertEqual(attempts[0]['status'], 'rejected')
        self.assertIn('Marker 3: checker support', attempts[0]['reason'])
        self.assertEqual(attempts[-1]['variant'], 'marker_3')
        self.assertEqual(attempts[-1]['status'], 'accepted')
        self.assertLess(attempts[-1]['farthest_marker_corner_from_checker_cells'], 5)
        with np.load(self.image.with_suffix('.corners.npz')) as data:
            # The native lower-left marker has measured grid nearby now.
            points = data['points']
            self.assertGreater(((points[:, 0] < 450) & (points[:, 1] > 650)).sum(), 20)

    def test_clear_detection_does_not_require_markers(self):
        with patch('detect_table.marker_grid_support') as support:
            attempts = detect_retry(self.image)
        support.assert_not_called()
        self.assertEqual(attempts[0]['variant'], 'native')
        self.assertEqual(attempts[0]['status'], 'accepted')

    def test_all_unsupported_variants_fail_without_publishing(self):
        with patch('detect_table.marker_grid_support', side_effect=ValueError('insufficient marker support')) as support:
            with self.assertRaisesRegex(ValueError, 'Checker detection failed'):
                detect_retry(self.image, [1, 2, 3, 4])
        self.assertEqual(support.call_count, 6)
        self.assertFalse(self.image.with_suffix('.corners.npz').exists())

    def test_single_row_is_not_reliable_corner_support(self):
        grid = np.c_[np.arange(30), np.zeros(30)]
        marker = {3: np.array([[10., 2.], [12., 2.], [12., 4.], [10., 4.]])}
        with self.assertRaisesRegex(ValueError, 'sparse or narrow'):
            check_marker_patch(grid, marker)

    def test_extrapolation_limit_is_not_relaxed(self):
        x, y = np.meshgrid(np.arange(20), np.arange(20))
        grid = np.c_[x.ravel(), y.ravel()].astype(float)
        near = {3: np.array([[20., 2.], [22., 2.], [22., 4.], [20., 4.]])}
        with patch('align_markers.undistort', side_effect=lambda p: p):
            _, distance = marker_grid_support(grid, grid, np.eye(3), near, 'Camera 1')
            self.assertAlmostEqual(distance, 3.)
            with self.assertRaisesRegex(ValueError, 'maximum 8'):
                marker_grid_support(grid, grid, np.eye(3), {3: near[3]+[10., 0.]}, 'Camera 1')


if __name__ == '__main__':
    unittest.main()
