"""Coverage warnings must not replace final geometric validation."""
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from repeat_consistency import common_checker_support

FIXTURE = Path(__file__).parent/'sessions/20260929_coverage50'


class CheckerCoverageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directories = [Path(temp.name)/f'pass{p:02}' for p in range(1, 4)]
        for directory in self.directories:
            directory.mkdir()

    def write_grid(self, columns=41, scale=1., limited_camera=3, rows=20):
        x, y = np.meshgrid(np.arange(41), np.arange(rows))
        grid = np.c_[x.ravel(), y.ravel()]
        points = (grid*[40., 35.]+[160., 100.])*scale
        for p, directory in enumerate(self.directories):
            for camera in range(4):
                keep = grid[:, 0] < (columns if camera == limited_camera and p == 1 else 41)
                np.savez(directory/f'input{camera}.corners.npz', grid=grid[keep], points=points[keep])

    def assert_untouched(self, original):
        self.assertEqual({p: p.read_bytes() for p in original}, original)
        for directory in self.directories:
            self.assertFalse(list(directory.glob('*.corners.full.npz')))

    def test_real_failed_run_warns_instead_of_rejecting(self):
        for p, directory in enumerate(self.directories, 1):
            for camera in range(4):
                shutil.copy2(FIXTURE/f'pass{p:02}.npz', directory/f'input{camera}.corners.npz')
        results = common_checker_support(self.directories)
        self.assertEqual(results[0]['passes'][0]['common'], 763)
        self.assertAlmostEqual(results[0]['passes'][2]['hull_fraction_retained'], .7996305973)
        self.assertIn('79.96%', results[0]['warning'])

    def test_exactly_half_coverage_passes_with_warning(self):
        self.write_grid(columns=21)
        results = common_checker_support(self.directories)
        self.assertEqual(results[3]['passes'][0]['hull_fraction_retained'], .5)
        self.assertIn('50.00%', results[3]['warning'])
        self.assertEqual(results[0]['warning'], '')

    def test_below_half_rejects_without_modifying_earlier_cameras(self):
        self.write_grid(columns=20)
        original = {p: p.read_bytes() for d in self.directories for p in d.glob('*.npz')}
        with self.assertRaisesRegex(ValueError, 'Camera 4.*47.50%.*minimum 50%'):
            common_checker_support(self.directories)
        self.assert_untouched(original)

    def test_small_absolute_area_still_rejected(self):
        self.write_grid(scale=.4)
        with self.assertRaisesRegex(ValueError, 'minimum 10%'):
            common_checker_support(self.directories)

    def test_fewer_than_300_common_corners_still_rejected(self):
        self.write_grid(columns=10)
        with self.assertRaisesRegex(ValueError, 'fewer than 300'):
            common_checker_support(self.directories)

    def test_higher_camera_with_smaller_but_distributed_grid_passes(self):
        self.write_grid(scale=.6)
        results = common_checker_support(self.directories)
        self.assertTrue(all(not r['warning'] for r in results))

    def test_narrow_grid_still_rejected_despite_many_points(self):
        self.write_grid(rows=8)
        for directory in self.directories:
            for path in directory.glob('*.npz'):
                with np.load(path) as data:
                    grid, points = data['grid'], data['points'].copy()
                points[:, 1] *= .1
                np.savez(path, grid=grid, points=points)
        with self.assertRaisesRegex(ValueError, 'minimum 10%'):
            common_checker_support(self.directories)


if __name__ == '__main__':
    unittest.main()
