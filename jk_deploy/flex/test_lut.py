#!/usr/bin/env python3
"""Numerical/format checks, not a substitute for physical rig calibration."""
import argparse
import unittest

import numpy as np

from make_lut import ROOT, camera_rays, load_lenses, map_view, project_lens


class LensTests(unittest.TestCase):
    def setUp(self):
        self.models, _ = load_lenses()
        self.args = argparse.Namespace(height=760, radius=100, pitch=55,
                                       width=2800, feather=100, hole=120, rotate_180=True)

    def test_center_and_symmetry(self):
        for model in self.models:
            points = project_lens(np.array([[0., 0, 1], [.2, .3, 1], [-.2, -.3, 1]]), model)
            np.testing.assert_allclose(points[0], [959.5, 599.5])
            np.testing.assert_allclose(points[1] + points[2], 2 * points[0])

    def test_shared_projection_is_between_sources(self):
        rays = np.array([[0., 0, 1], [.5, .25, 1], [-.7, -.4, 1]])
        p0, p1 = [project_lens(rays, m) for m in self.models]
        shared = (p0 + p1) / 2
        self.assertTrue(np.all(shared >= np.minimum(p0, p1)))
        self.assertTrue(np.all(shared <= np.maximum(p0, p1)))

    def test_ground_below_ring_is_forward(self):
        for slot in range(4):
            ray = camera_rays(np.array([[0., 0, 0]]), slot, self.args)
            self.assertGreater(ray[0, 2], 0)

    def test_mesh_format_and_weights(self):
        mesh = np.fromfile(ROOT / 'calibration/four_mesh.bin', '<i2').reshape(4, 136, 136, 7)
        weights = np.fromfile(ROOT / 'calibration/four_blend.bin', np.uint8).reshape(4, 136, 136, 2)
        self.assertTrue(np.all(np.abs(mesh[..., :2]) <= 540))
        self.assertTrue(np.all(mesh[..., 2] == 0))
        for offset, limit in ((3, 1200), (4, 1920), (5, 1200), (6, 1920)):
            self.assertTrue(np.all(mesh[..., offset] >= 8))
            self.assertTrue(np.all(mesh[..., offset] <= (limit - .5) * 16))
        sums = weights.sum(axis=-1)
        self.assertTrue(np.all((sums == 0) | (sums == 255)))
        self.assertGreater(np.mean(sums != 0), .9)

    def test_shared_axis_has_same_source(self):
        # At the top-center boundary, q0 uses front as texture1 and q1 as texture2.
        uv = np.array([[.5, .05], [.5, .2]])
        pixels0, weights0 = map_view(uv, 0, self.models, self.args)
        pixels1, weights1 = map_view(uv, 1, self.models, self.args)
        np.testing.assert_allclose(pixels0[0], pixels1[1])
        np.testing.assert_allclose(weights0[:, 0], 1)
        np.testing.assert_allclose(weights1[:, 1], 1)


if __name__ == '__main__':
    unittest.main()
