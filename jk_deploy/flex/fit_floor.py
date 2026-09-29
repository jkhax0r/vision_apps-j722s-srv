#!/usr/bin/env python3
"""Fit and inspect a stationary four-camera checkerboard floor session."""
import argparse
import json
import os
from itertools import product
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "calibration/lens_20260908"))
from fit_intrinsics import square_lattice
from make_lut import load_lenses, project_lens

cv2.setNumThreads(int(os.environ.get('JK_CAL_THREADS', '4')))
MODELS, _ = load_lenses()
K = np.mean([m["K"] for m in MODELS], axis=0)
D = np.mean([m["D"] for m in MODELS], axis=0)


def project(rays):
    return np.mean([project_lens(rays, m) for m in MODELS], axis=0)


def undistort(points):
    xy = cv2.fisheye.undistortPoints(np.asarray(points, float).reshape(-1, 1, 2), K, D).reshape(-1, 2)
    for _ in range(6):
        p = project(np.c_[xy, np.ones(len(xy))])
        cols = []
        for axis in range(2):
            delta = np.zeros_like(xy)
            delta[:, axis] = 1e-5
            cols.append((project(np.c_[xy + delta, np.ones(len(xy))]) - p) / 1e-5)
        jac = np.stack(cols, axis=2)
        xy -= np.linalg.solve(jac, (p - points)[..., None])[..., 0]
    return xy


def transform(points, matrix):
    p = np.c_[points, np.ones(len(points))] @ matrix.T
    return p[:, :2] / p[:, 2:]


def rotations():
    for swap, sx, sy in product((False, True), (-1, 1), (-1, 1)):
        mat = np.diag([sx, sy])
        yield mat[:, ::-1] if swap else mat


def colors(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    found = {}
    for name, lo, hi in (("yellow", (20, 120, 100), (38, 255, 255)),
                         ("green", (38, 80, 65), (85, 255, 255)),
                         ("blue", (90, 95, 55), (125, 255, 255))):
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        n, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        candidates = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area >= 500 and w >= 20 and h >= 20:
                candidates.append({"pixel": centers[i].tolist(), "area": int(area),
                                   "rect": [int(x), int(y), int(w), int(h)]})
        found[name] = sorted(candidates, key=lambda v: -v["area"])[:8]
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    args = parser.parse_args()
    results = []
    for i in range(4):
        capture = args.session / "captures" / f"input{i}"
        image = cv2.imread(str(capture.with_suffix(".png")))
        data = np.load(capture.with_suffix(".corners.npz"))
        grid, basis, metric = square_lattice(data["grid"], data["points"], K, D)
        pixels = data["points"]
        rays = undistort(pixels)
        h, mask = cv2.findHomography(grid, rays, cv2.RANSAC, .008)
        keep = mask.ravel().astype(bool)
        h, _ = cv2.findHomography(grid[keep], rays[keep], 0)
        predicted = project(np.c_[transform(grid, h), np.ones(len(grid))])
        error = np.linalg.norm(predicted - pixels, axis=1)
        objects = colors(image)
        for candidates in objects.values():
            for obj in candidates:
                g = transform(undistort(np.array([obj["pixel"]])), np.linalg.inv(h))[0]
                obj["grid"] = g.tolist()
        result = {"input": i, "H": h.tolist(), "basis": basis.tolist(),
                  "metric": metric, "rms_px": float(np.sqrt(np.mean(error[keep] ** 2))),
                  "grid_min": grid.min(0).tolist(), "grid_max": grid.max(0).tolist(),
                  "colors": objects}
        np.savez(capture.with_suffix(".floor.npz"), grid=grid, points=pixels, keep=keep)
        for uv, xy in zip(grid, pixels):
            xy = tuple(np.rint(xy).astype(int))
            cv2.circle(image, xy, 3, (0, 0, 255), -1)
            if round(uv[0]) % 5 == 0 and round(uv[1]) % 5 == 0:
                cv2.putText(image, f"{round(uv[0])},{round(uv[1])}", xy,
                            cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 0), 1)
        cv2.imwrite(str(capture.with_suffix(".floor.png")), image)
        results.append(result)
        print(json.dumps(result), flush=True)
    (args.session / "floor_fits.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
