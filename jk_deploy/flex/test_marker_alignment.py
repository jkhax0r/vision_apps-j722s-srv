#!/usr/bin/env python3
import unittest
import json
from pathlib import Path

import numpy as np

from align_markers import checker_phase, match_grid
from fit_floor import rotations


class MarkerAlignmentTests(unittest.TestCase):
    def test_rotated_and_reflected_integer_grids(self):
        points = np.array([[0., 0.], [3., 0.], [3., 3.], [0., 3.]])
        for rotation in rotations():
            shift = np.array([13, -9])
            reference = points@rotation.T+shift
            r, t, error = match_grid(points, reference)
            np.testing.assert_array_equal(r, rotation)
            np.testing.assert_array_equal(t, shift)
            self.assertLess(error, 1e-9)

    def test_bad_correspondences_rejected(self):
        points = np.array([[0., 0.], [3., 0.], [3., 3.], [0., 3.]])
        with self.assertRaises(ValueError):
            match_grid(points, points*3)

    def test_insufficient_points_rejected(self):
        with self.assertRaises(ValueError):
            match_grid(np.zeros((2, 2)), np.zeros((2, 2)))

    def test_captured_checker_phase_agrees(self):
        session = Path(__file__).resolve().parent / "sessions/20260929T155359Z_marker_inspection"
        models = json.loads((session / "session.json").read_text())["aligned_models"]
        self.assertEqual({checker_phase(session, m)["white_parity"] for m in models}, {1})

    def test_one_cell_slip_changes_checker_phase(self):
        session = Path(__file__).resolve().parent / "sessions/20260929T155359Z_marker_inspection"
        model = json.loads((session / "session.json").read_text())["aligned_models"][2]
        original = checker_phase(session, model)["white_parity"]
        model["shift"][1] -= 1
        self.assertNotEqual(checker_phase(session, model)["white_parity"], original)


if __name__ == "__main__":
    unittest.main()
