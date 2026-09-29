#!/usr/bin/env python3
"""Flexible marker order, crop geometry, and fail-safe candidate regression tests."""
import copy
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from align_markers import (DEFAULT_GEOMETRY, build_config, camera_ring, table_frame,
                           validate_marker_detections, validate_marker_views)
from bake_floor import coverage, mapping, screen_world
from calibrate_table import calibrate
from detect_table import native_points
from stage_table import digest, validate_candidate

HERE = Path(__file__).resolve().parent
SESSION = HERE/"sessions/20260929T155359Z_marker_inspection"


class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geometry = json.loads(DEFAULT_GEOMETRY.read_text())
        cls.raw = []
        cls.pixels = []
        detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
        for i in range(4):
            image = cv2.imread(str(SESSION/"captures"/f"input{i}.png"))
            corners, ids, rejected = detector.detectMarkers(image)
            cls.raw.append((corners, ids, rejected))
            cls.pixels.append(validate_marker_detections(corners, ids, image.shape))

    def test_all_24_label_orders(self):
        for labels in itertools.permutations((7, 12, 23, 45)):
            remap = dict(zip((1, 2, 3, 4), labels))
            pixels = [{remap[n]: p for n, p in view.items()} for view in self.pixels]
            order, corners, _ = camera_ring(pixels)
            self.assertEqual(order, [0, 1, 2, 3])
            self.assertEqual(corners, list(labels))

    def test_all_24_camera_connections(self):
        for connections in itertools.permutations(range(4)):
            pixels = [self.pixels[i] for i in connections]
            order, corners, _ = camera_ring(pixels, connections.index(0))
            self.assertEqual([connections[i] for i in order], [0, 1, 2, 3])
            self.assertEqual(corners, [1, 2, 3, 4])

    def test_real_fit_independent_of_numeric_ids(self):
        original = build_config(SESSION)
        remap = {1: 45, 2: 7, 3: 23, 4: 12}
        raw = [(c, np.array([[remap[int(n)]] for n in ids.ravel()]), r) for c, ids, r in self.raw]
        with patch("align_markers.cv2.aruco.ArucoDetector") as detector:
            detector.return_value.detectMarkers.side_effect = raw
            result = build_config(SESSION)
        self.assertEqual(original["aligned_models"], result["aligned_models"])
        np.testing.assert_allclose(original["crop_cells"], result["crop_cells"])
        np.testing.assert_allclose(original["view_frame"]["axes"], result["view_frame"]["axes"])

    def test_missing_marker(self):
        pixels = copy.deepcopy(self.pixels)
        pixels[0].pop(1)
        with self.assertRaisesRegex(ValueError, "two distinct"):
            camera_ring(pixels)

    def test_duplicate_ids_rejected_before_dictionary(self):
        corners, _, _ = self.raw[0]
        with self.assertRaisesRegex(ValueError, "Duplicate ID"):
            validate_marker_detections(corners, np.array([[1], [1]]), (1200, 1920))

    def test_disconnected_ring(self):
        points = next(iter(self.pixels[0].values()))
        with self.assertRaisesRegex(ValueError, "disconnected"):
            camera_ring([{1: points, 2: points}, {1: points, 2: points},
                         {3: points, 4: points}, {3: points, 4: points}])

    def test_small_or_clipped_markers(self):
        square = np.array([[100., 100.], [180., 100.], [180., 180.], [100., 180.]])
        for bad in (square*.1, square-[99, 0]):
            with self.assertRaises(ValueError):
                validate_marker_detections([bad, square+300], np.array([[1], [2]]), (1200, 1920))

    def test_unshared_false_marker_does_not_reject_real_ring(self):
        views = [(list(c), ids.copy(), (1200, 1920)) for c, ids, _ in self.raw]
        tiny = np.array([[[500., 200.], [518., 200.], [518., 218.], [500., 218.]]])
        c, ids, shape = views[1]
        views[1] = (c+[tiny], np.concatenate([ids, [[37]]]), shape)
        pixels, selection = validate_marker_views(views)
        self.assertEqual(selection["selected_ids"], [1, 2, 3, 4])
        self.assertEqual(selection["ignored_unshared_ids"], [{"input": 1, "ids": [37]}])
        self.assertEqual(camera_ring(pixels)[0], [0, 1, 2, 3])

    def test_too_small_shared_marker_is_still_rejected(self):
        views = [(list(c), ids.copy(), (1200, 1920)) for c, ids, _ in self.raw]
        c, ids, shape = views[0]
        c[0] = c[0].mean(axis=1, keepdims=True)+(c[0]-c[0].mean(axis=1, keepdims=True))*.1
        with self.assertRaisesRegex(ValueError, "shortest edge"):
            validate_marker_views(views)

    def test_ambiguous_extra_shared_marker_is_not_silently_chosen(self):
        views = [(list(c), ids.copy(), (1200, 1920)) for c, ids, _ in self.raw]
        for i in (0, 1):
            c, ids, shape = views[i]
            views[i] = (c+[c[0]+[100, 0]], np.concatenate([ids, [[37]]]), shape)
        with self.assertRaisesRegex(ValueError, "four corner IDs"):
            validate_marker_views(views)

    def rectangle_observations(self, angle=0):
        radians = np.deg2rad(angle)
        axes = np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])
        corners = np.array([[20., -25.], [20., 25.], [-20., 25.], [-20., -25.]])
        label = np.array(self.geometry["marker_corners_canonical_xy"])/27.25
        observations = {}
        for i, point in enumerate(corners):
            value = (point+label*(-np.sign(point)))@axes.T+[8., -3.]
            observations[i+1] = [value, value.copy()]
        return observations, axes

    def test_rotated_rectangular_table_crop(self):
        for angle in (-35, 0, 25, 70):
            observations, axes = self.rectangle_observations(angle)
            crop, frame, _, quality = table_frame(observations, [1, 2, 3, 4], self.geometry, 0)
            np.testing.assert_allclose(crop, [-20, -25, 40, 50], atol=1e-4)
            np.testing.assert_allclose(frame["axes"], axes, atol=1e-6)
            np.testing.assert_allclose(frame["origin_cells"], [8, -3], atol=1e-5)
            self.assertLess(quality["rectangle_max_error_cells"], 1e-4)

    def test_crossed_corners_rejected(self):
        observations, _ = self.rectangle_observations()
        with self.assertRaisesRegex(ValueError, "crossed/concave"):
            table_frame(observations, [1, 3, 2, 4], self.geometry)

    def test_rotated_label_on_holder_rejected(self):
        observations, _ = self.rectangle_observations()
        observations[1] = [np.roll(v, 2, axis=0) for v in observations[1]]
        with self.assertRaises(ValueError):
            table_frame(observations, [1, 2, 3, 4], self.geometry)

    def test_nonrectangular_table_rejected(self):
        observations, _ = self.rectangle_observations()
        observations[1] = [v+[8, 0] for v in observations[1]]
        with self.assertRaisesRegex(ValueError, "rectangular"):
            table_frame(observations, [1, 2, 3, 4], self.geometry)

    def test_rotated_screen_preserves_scale(self):
        observations, _ = self.rectangle_observations(25)
        crop, frame, _, _ = table_frame(observations, [1, 2, 3, 4], self.geometry)
        config = {"crop_cells": crop, "view_frame": frame, "feather_cells": 1.5}
        points = np.array([[.5, .5], [.5+1/960, .5], [.5, .5+1/720]])
        world, _ = screen_world(points, config)
        np.testing.assert_allclose(world[0], [8, -3], atol=1e-5)
        self.assertAlmostEqual(np.linalg.norm(world[1]-world[0]), np.linalg.norm(world[2]-world[0]))
        class Camera:
            def map(self, world):
                return world, np.ones(len(world), bool)
        _, weights = mapping(np.array([[.5, .2]]), 0, [Camera()]*4, config)
        np.testing.assert_allclose(weights, [[1, 0]])

    def test_missing_camera_coverage_rejected(self):
        class Camera:
            def map(self, world):
                return world, np.zeros(len(world), bool)
        with self.assertRaisesRegex(ValueError, "camera coverage"):
            coverage([Camera()]*4, {"crop_cells": [-20, -20, 40, 40], "feather_cells": 1.5})

    def test_retry_pixel_transforms_are_reversible(self):
        points = np.array([[0., 0.], [600., 800.], [1919., 1199.]])
        for variant in ("native", "rotate180", "flip_x", "flip_y"):
            np.testing.assert_allclose(native_points(native_points(points, variant), variant), points)

    def test_existing_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/"session.json").write_text("preserved")
            with self.assertRaises(FileExistsError):
                calibrate(path/"missing", path)
            self.assertEqual((path/"session.json").read_text(), "preserved")
            self.assertFalse((path/"report.json").exists())

    def test_failed_candidate_has_report_not_deployable_binaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"candidate"
            with self.assertRaisesRegex(ValueError, "Missing input0"):
                calibrate(Path(tmp)/"missing", output)
            self.assertEqual(json.loads((output/"report.json").read_text())["status"], "rejected")
            self.assertFalse((output/"four_mesh.bin").exists())

    def make_candidate(self, path):
        hashes = {}
        for name in ("four_mesh.bin", "four_blend.bin"):
            shutil.copy2(SESSION/name, path/name)
            hashes[name] = digest(path/name)
        (path/"camera_order.txt").write_text("0 1 2 3\n")
        (path/"calibration.json").write_text(json.dumps({"schema_version": 2,
            "capture_order": [0, 1, 2, 3], "sha256": hashes}))
        (path/"report.json").write_text(json.dumps({"status": "passed",
            "capture_order": [0, 1, 2, 3], "artifact_sha256": hashes}))

    def test_staging_refuses_changed_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.make_candidate(path)
            validate_candidate(path)
            with (path/"four_mesh.bin").open("r+b") as stream:
                stream.write(b"broken")
            with self.assertRaisesRegex(ValueError, "artifact"):
                validate_candidate(path)

    def test_staging_refuses_failed_report_and_changed_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.make_candidate(path)
            (path/"camera_order.txt").write_text("1 0 2 3\n")
            with self.assertRaisesRegex(ValueError, "Camera order"):
                validate_candidate(path)
            (path/"report.json").write_text('{"status":"rejected"}')
            with self.assertRaisesRegex(ValueError, "passed"):
                validate_candidate(path)

    def test_grid_launcher_reads_order_and_allows_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            shutil.copy2(HERE/"run_flex_grid.sh", path/"run_flex_grid.sh")
            stub = path/"run_flex_stitch.sh"
            stub.write_text('#!/bin/bash\nprintf "%s" "$CAMERA_ORDER"\n')
            stub.chmod(0o755)
            env = dict(os.environ, FLEX_CALIBRATION_DIR=str(path))
            env.pop("CAMERA_ORDER", None)
            def run():
                return subprocess.check_output(["bash", str(path/"run_flex_grid.sh")], env=env, text=True)
            self.assertEqual(run(), "0 1 2 3")
            (path/"camera_order.txt").write_text("2 0 3 1\n")
            self.assertEqual(run(), "2 0 3 1")
            env["CAMERA_ORDER"] = "3 2 1 0"
            self.assertEqual(run(), "3 2 1 0")

    def test_candidate_launcher_uses_its_own_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root/"candidate"
            candidate.mkdir()
            shutil.copy2(HERE/"run_table_candidate.sh", candidate/"run.sh")
            (candidate/"camera_order.txt").write_text("2 0 3 1\n")
            stub = root/"run_flex_stitch.sh"
            stub.write_text('#!/bin/bash\nprintf "%s\\n%s\\n%s" "$CAMERA_ORDER" "$FLEX_CALIBRATION_DIR" "$FLEX_COMPARE"\n')
            stub.chmod(0o755)
            output = subprocess.check_output(["bash", str(candidate/"run.sh")], text=True)
            self.assertEqual(output.splitlines(), ["2 0 3 1", str(candidate), "1"])


if __name__ == "__main__":
    unittest.main()
