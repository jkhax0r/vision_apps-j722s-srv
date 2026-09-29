#!/usr/bin/env python3
"""Checks for the measured Flex floor mapping and its binary GPU contract."""
import json
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from bake_floor import FloorCamera, align, mapping, screen_world
from fit_floor import project, undistort

SESSION = Path(__file__).resolve().parent / "sessions/20260928_four_grid"


class FloorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((SESSION / "session.json").read_text())
        cls.models = align(json.loads((SESSION / "floor_fits.json").read_text()), cls.config)
        cls.cameras = [FloorCamera(SESSION, model) for model in cls.models]

    def test_shared_lens_inverse(self):
        points = np.array([[10., 10.], [960., 600.], [1900., 1180.], [100., 900.]])
        rays = undistort(points)
        np.testing.assert_allclose(project(np.c_[rays, np.ones(len(rays))]), points, atol=1e-5)

    def test_saved_fit_reconstruction_does_not_refit_ransac(self):
        original = self.cameras[0]
        with patch("bake_floor.cv2.findHomography", side_effect=AssertionError("Unexpected refit")):
            reconstructed = FloorCamera(SESSION, copy.deepcopy(original.model), fitted_h=original.h)
        points = np.array([[0., 0.], [10., -10.], [3., 2.]])
        np.testing.assert_allclose(original.map(points)[0], reconstructed.map(points)[0])

    def test_integer_alignment(self):
        self.assertEqual([m["shift"] for m in self.models], [[0, 0], [15, 8], [7, 19], [-3, 7]])
        for model in self.models:
            r = np.array(model["rotation"])
            np.testing.assert_array_equal(r @ r.T, np.eye(2))
            self.assertLess(model["marker_rms_cells"], .4)

    def test_floor_crop_preserves_square_cells(self):
        world, inside = screen_world(np.array([[.5, .5], [.5+1/960, .5], [.5, .5+1/720], [0, 0]]), self.config)
        self.assertAlmostEqual(world[1, 0]-world[0, 0], world[2, 1]-world[0, 1])
        self.assertFalse(inside[-1])
        np.testing.assert_allclose(world[0], [6., 9.5])

    def test_heldout_corners(self):
        for camera in self.cameras:
            report = camera.validation()
            self.assertGreaterEqual(report["points"], 30)
            self.assertLess(report["rms_px"], 2)

    def test_top_axis_uses_camera_one(self):
        uv = np.array([[.5, .1], [.5, .25]])
        p0, a0 = mapping(uv, 0, self.cameras, self.config)
        p1, a1 = mapping(uv, 1, self.cameras, self.config)
        np.testing.assert_allclose(p0[0], p1[1])
        np.testing.assert_allclose(a0[:, 0], 1)
        np.testing.assert_allclose(a1[:, 1], 1)

    def test_gpu_binary_and_orientation(self):
        mesh = np.fromfile(SESSION / "four_mesh.bin", "<i2").reshape(4, 136, 136, 7)
        blend = np.fromfile(SESSION / "four_blend.bin", np.uint8).reshape(4, 136, 136, 2)
        self.assertEqual(mesh[0, 0, 0, 1], -540)
        self.assertEqual(mesh[2, -1, -1, 1], 540)
        self.assertTrue(np.all(mesh[..., 2] == 0))
        for offset, size in ((3, 1200), (4, 1920), (5, 1200), (6, 1920)):
            self.assertTrue(np.all(mesh[..., offset] >= 8))
            self.assertTrue(np.all(mesh[..., offset] <= (size-.5)*16))
        self.assertTrue(np.all((blend.sum(-1) == 0) | (blend.sum(-1) == 255)))


if __name__ == "__main__":
    unittest.main()
