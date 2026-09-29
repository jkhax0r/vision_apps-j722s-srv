#!/usr/bin/env python3
"""Check printable solids, actual PDF sizes, and synthetic marker detection."""
import json
import unittest

import cadquery as cq
import cv2
import numpy as np
import pymupdf as pdf

from generate import OUT, IDS, DICTIONARY, MM, read_binary_stl


class DesignTests(unittest.TestCase):
    def detect(self, image, marker_id):
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = cv2.aruco.ArucoDetector(DICTIONARY).detectMarkers(image)
        self.assertIsNotNone(ids, f"Missing ID {marker_id}")
        self.assertEqual(ids.ravel().tolist(), [marker_id])
        return corners[0][0]

    def test_cad_solids_and_print_bounds(self):
        for name, dims in (("table_corner_cap", [133, 133, 18]),
                           ("flat_marker_plate", [130, 130, 2])):
            part = cq.importers.importStep(str(OUT / f"{name}.step")).val()
            self.assertTrue(part.isValid())
            self.assertEqual(len(part.Solids()), 1)
            self.assertGreater(part.Volume(), 20000)
            triangles, _ = read_binary_stl(OUT / f"{name}.stl")
            vertices = triangles.reshape(-1, 3)
            np.testing.assert_allclose(np.ptp(vertices, axis=0), dims, atol=.01)
            self.assertAlmostEqual(vertices[:, 2].min(), 0, places=4)

    def test_closed_meshes(self):
        for name in ("table_corner_cap", "flat_marker_plate"):
            triangles, _ = read_binary_stl(OUT / f"{name}.stl")
            _, index = np.unique(np.round(triangles.reshape(-1, 3), 5), axis=0,
                                 return_inverse=True)
            faces = index.reshape(-1, 3)
            edges = np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]],
                                            faces[:, [2, 0]])), axis=1)
            _, counts = np.unique(edges, axis=0, return_counts=True)
            self.assertTrue(np.all(counts == 2), name)
            self.assertGreater(np.min(np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                                              triangles[:, 2]-triangles[:, 0]), axis=1)), 1e-7)

    def test_four_ids_all_rotations_at_small_sizes(self):
        for marker_id in IDS:
            original = cv2.imread(str(OUT / f"corner_{marker_id}_label.png"), 0)
            for side in (100, 160, 240):
                small = cv2.resize(original, (side, side), interpolation=cv2.INTER_AREA)
                for rotation in range(4):
                    self.detect(np.ascontiguousarray(np.rot90(small, rotation)), marker_id)

    def test_perspective_views(self):
        source = np.float32([[0, 0], [1199, 0], [1199, 1199], [0, 1199]])
        dest = np.float32([[60, 60], [260, 85], [225, 180], [80, 160]])
        h = cv2.getPerspectiveTransform(source, dest)
        for marker_id in IDS:
            image = cv2.imread(str(OUT / f"corner_{marker_id}_label.png"), 0)
            warped = cv2.warpPerspective(image, h, (320, 240), borderValue=255)
            self.detect(cv2.GaussianBlur(warped, (3, 3), .6), marker_id)

    def test_pdf_page_and_marker_dimensions(self):
        for name, size in (("4x6", [101.6, 152.4]), ("letter", [215.9, 279.4]),
                           ("a4", [210, 297])):
            with pdf.open(OUT / f"corner_markers_{name}.pdf") as doc:
                self.assertEqual(len(doc), 4)
                for page, marker_id in zip(doc, IDS):
                    np.testing.assert_allclose([page.rect.width/MM, page.rect.height/MM], size, atol=.001)
                    pix = page.get_pixmap(matrix=pdf.Matrix(2, 2), colorspace=pdf.csRGB)
                    image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
                    corners = self.detect(image, marker_id)
                    lengths = np.linalg.norm(corners-np.roll(corners, -1, axis=0), axis=1)/(MM*2)
                    np.testing.assert_allclose(lengths, 80, atol=.5)
                    if name == "4x6":
                        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                        self.assertLess(gray[0, pix.width//2], 128)
                        self.assertLess(gray[-1, pix.width//2], 128)

    def test_label_matches_manifest(self):
        data = json.loads((OUT / "marker_geometry.json").read_text())
        corners = np.array(data["marker_corners_canonical_xy"])
        np.testing.assert_allclose(corners.mean(0), data["marker_center_xy"])
        np.testing.assert_allclose(np.linalg.norm(corners-np.roll(corners, -1, axis=0), axis=1), 80)
        self.assertEqual(data["marker_plane_z_without_paper"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
