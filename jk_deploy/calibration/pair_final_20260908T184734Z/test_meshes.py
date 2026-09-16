#!/usr/bin/env python3
"""Check the native-resolution GPU mesh contract without cameras or OpenCV."""
from pathlib import Path
import argparse
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parent


class MeshTests(unittest.TestCase):
    def test_full_resolution_coordinates(self):
        for mode in ('lens', 'measured'):
            with self.subTest(mode=mode):
                old = np.fromfile(ROOT/f'{mode}_mesh.bin', dtype='<i2').reshape(4, 136, 136, 7)
                new = np.fromfile(ROOT/f'{mode}_fullres_mesh.bin', dtype='<i2').reshape(4, 136, 136, 7)
                np.testing.assert_array_equal(old[..., :3], new[..., :3])
                self.assertTrue(np.all((new[..., [3, 5]] >= 8) &
                                       (new[..., [3, 5]] <= 19192)))
                self.assertTrue(np.all((new[..., [4, 6]] >= 8) &
                                       (new[..., [4, 6]] <= 30712)))
                for quadrant in (0, 3):
                    np.testing.assert_array_equal(new[quadrant, 0, 0, 3:],
                                                  [19192, 30712, 19192, 30712])
                    np.testing.assert_array_equal(new[quadrant, -1, -1, 3:], [8, 8, 8, 8])
                    self.assertTrue(np.all(np.diff(new[quadrant, :, :, 4], axis=1) < 0))
                    self.assertTrue(np.all(np.diff(new[quadrant, :, :, 3], axis=0) < 0))
                weights = np.fromfile(ROOT/f'{mode}_blend.bin', dtype='u1').reshape(4, 136, 136, 2)
                self.assertTrue(np.isin(weights.astype(int).sum(-1), [0, 255]).all())
                self.assertTrue(np.all(weights[0] == [0, 255]))
                self.assertTrue(np.all(weights[3] == [255, 0]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path, default=ROOT)
    args, remaining = parser.parse_known_args()
    ROOT = args.session.resolve()
    unittest.main(argv=[sys.argv[0], *remaining])
