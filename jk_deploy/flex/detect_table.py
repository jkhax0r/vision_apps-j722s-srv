#!/usr/bin/env python3
"""Retry the cloth detector with alternate seed locations, preserving native pixels."""
import argparse
import json
from pathlib import Path
import tempfile

import cv2
import numpy as np

from fit_floor import D, K, square_lattice
from fit_intrinsics import detect


def native_points(points, variant):
    result = points.copy()
    if variant in ("rotate180", "flip_x"):
        result[:, 0] = 1919-result[:, 0]
    if variant in ("rotate180", "flip_y"):
        result[:, 1] = 1199-result[:, 1]
    return result


def detect_retry(path):
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (1200, 1920):
        raise ValueError(f"Need native 1920x1200 image: {path}")
    attempts = []
    for variant, flip in (("native", None), ("rotate180", -1), ("flip_x", 1), ("flip_y", 0)):
        try:
            with tempfile.TemporaryDirectory(prefix="jk-checker-") as tmp:
                candidate = Path(tmp)/"input.png"
                cv2.imwrite(str(candidate), image if flip is None else cv2.flip(image, flip))
                cv2.setRNGSeed(0)
                detect(candidate)
                with np.load(candidate.with_suffix(".corners.npz")) as data:
                    grid, points = data["grid"], native_points(data["points"], variant)
                square, _, metric = square_lattice(grid, points, K, D)
                if len(grid) < 150 or np.ptp(square, axis=0).min() < 10:
                    raise ValueError("Need at least 150 corners spanning ten cells along both axes")
                hull = cv2.convexHull(points.astype(np.float32))
                fraction = cv2.contourArea(hull)/(1920*1200)
                if fraction < .10:
                    raise ValueError("Checker coverage is too small; need at least 10% of the image")
            np.savez(path.with_suffix(".corners.npz"), grid=grid, points=points)
            overlay = image.copy()
            for point in points:
                cv2.circle(overlay, tuple(np.rint(point).astype(int)), 3, (0, 0, 255), -1)
            cv2.imwrite(str(path.with_suffix(".corners.png")), overlay)
            attempts.append({"variant": variant, "status": "accepted", "corners": len(grid),
                             "image_hull_fraction": fraction, "square_metric": float(metric)})
            return attempts
        except (ValueError, RuntimeError, cv2.error, np.linalg.LinAlgError) as error:
            attempts.append({"variant": variant, "status": "rejected", "reason": str(error)})
    raise ValueError(f"Checker detection failed for {path.name}: {json.dumps(attempts)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    attempts = detect_retry(args.image)
    args.image.with_suffix(".detection.json").write_text(json.dumps(attempts, indent=2)+"\n")
    print(json.dumps(attempts), flush=True)


if __name__ == "__main__":
    main()
