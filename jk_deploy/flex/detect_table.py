#!/usr/bin/env python3
"""Retry the cloth detector with alternate seed locations, preserving native pixels."""
import argparse
import json
from pathlib import Path
import tempfile

import cv2
import numpy as np

from align_markers import marker_grid_support, validate_marker_detections
from fit_floor import D, K, square_lattice, undistort
from fit_intrinsics import detect


def native_points(points, variant):
    result = points.copy()
    if variant in ("rotate180", "flip_x"):
        result[:, 0] = 1919-result[:, 0]
    if variant in ("rotate180", "flip_y"):
        result[:, 1] = 1199-result[:, 1]
    return result


def check_marker_patch(grid, observed):
    # One isolated checker row can vanish from the intersection of repeated
    # detections. Require a local 2-D patch, not just a nearby single point.
    for marker, corners in observed.items():
        nearby = grid[np.linalg.norm(grid-corners.mean(0), axis=1) < 8]
        area = cv2.contourArea(cv2.convexHull(nearby.astype(np.float32))) if len(nearby) >= 3 else 0.
        if len(nearby) < 20 or area < 8:
            raise ValueError(f"Marker {marker}: checker support is only a sparse or narrow patch "
                             f"({len(nearby)} corners, {area:.1f} square cells)")


def detect_retry(path, marker_ids=None):
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (1200, 1920):
        raise ValueError(f"Need native 1920x1200 image: {path}")
    markers = None
    if marker_ids is not None:
        detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
        corners, ids, _ = detector.detectMarkers(image)
        markers = validate_marker_detections(corners, ids, image.shape, marker_ids)
    candidates = [("native", None, None)]
    if markers is not None:
        for marker, corners in sorted(markers.items(), key=lambda item: item[1].mean(0)[0]):
            center = corners.mean(0)
            window = (int(np.clip(center[0]-300, 0, 1320)), int(np.clip(center[1]-250, 0, 700)))
            candidates.append((f"marker_{marker}", None, [window]))
    candidates += [("rotate180", -1, None), ("flip_x", 1, None), ("flip_y", 0, None)]
    attempts = []
    for variant, flip, windows in candidates:
        try:
            with tempfile.TemporaryDirectory(prefix="jk-checker-") as tmp:
                candidate = Path(tmp)/"input.png"
                cv2.imwrite(str(candidate), image if flip is None else cv2.flip(image, flip))
                cv2.setRNGSeed(0)
                detect(candidate, seed_windows=windows)
                with np.load(candidate.with_suffix(".corners.npz")) as data:
                    grid, points = data["grid"], native_points(data["points"], variant)
                square, _, metric = square_lattice(grid, points, K, D)
                if len(grid) < 150 or np.ptp(square, axis=0).min() < 10:
                    raise ValueError("Need at least 150 corners spanning ten cells along both axes")
                hull = cv2.convexHull(points.astype(np.float32))
                fraction = cv2.contourArea(hull)/(1920*1200)
                if fraction < .10:
                    raise ValueError("Checker coverage is too small; need at least 10% of the image")
                support = {}
                if markers is not None:
                    # A large patch can still omit a table corner across a tripod
                    # leg. Retry the seed before accepting that incomplete patch.
                    rays = undistort(points)
                    homography, mask = cv2.findHomography(square, rays, cv2.RANSAC, .008)
                    if homography is None or mask is None or mask.sum() < 4:
                        raise ValueError("No stable checker homography")
                    keep = mask.ravel().astype(bool)
                    homography, _ = cv2.findHomography(square[keep], rays[keep], 0)
                    if homography is None:
                        raise ValueError("No stable checker homography")
                    observed, distance = marker_grid_support(square, points, homography, markers, path.stem)
                    check_marker_patch(square, observed)
                    support["farthest_marker_corner_from_checker_cells"] = distance
            np.savez(path.with_suffix(".corners.npz"), grid=grid, points=points)
            overlay = image.copy()
            for point in points:
                cv2.circle(overlay, tuple(np.rint(point).astype(int)), 3, (0, 0, 255), -1)
            cv2.imwrite(str(path.with_suffix(".corners.png")), overlay)
            attempts.append({"variant": variant, "status": "accepted", "corners": len(grid),
                             "image_hull_fraction": fraction, "square_metric": float(metric), **support})
            return attempts
        except (ValueError, RuntimeError, cv2.error, np.linalg.LinAlgError) as error:
            attempts.append({"variant": variant, "status": "rejected", "reason": str(error)})
    raise ValueError(f"Checker detection failed for {path.name}: {json.dumps(attempts)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--marker-ids", type=int, nargs=4, help="Selected table IDs; require checker coverage at both visible markers")
    args = parser.parse_args()
    attempts = detect_retry(args.image, args.marker_ids)
    args.image.with_suffix(".detection.json").write_text(json.dumps(attempts, indent=2)+"\n")
    print(json.dumps(attempts), flush=True)


if __name__ == "__main__":
    main()
