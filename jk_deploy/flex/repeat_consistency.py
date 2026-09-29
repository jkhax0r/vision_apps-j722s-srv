#!/usr/bin/env python3
"""Compare independently fitted table mappings in one checker-coordinate frame."""
import copy
from itertools import combinations
import json

import cv2
import numpy as np
from scipy.spatial import cKDTree

from align_markers import match_grid
from bake_floor import FloorCamera, mapping, screen_world

LIMITS = {"mapping_rms_px": 3., "mapping_p95_px": 4.5, "mapping_p99_px": 12.,
          "table_corner_max_cells": .5}
MIN_RETAINED_HULL = .50
WARN_RETAINED_HULL = .80


def common_checker_support(directories):
    """Retain independently measured correspondences on the same physical support."""
    results, pending = [], []
    for i in range(4):
        files = [directory/f"input{i}.corners.npz" for directory in directories]
        if any(file.with_name(file.name.replace(".corners.npz", ".corners.full.npz")).exists() for file in files):
            raise ValueError("Common checker support was already selected; start a new candidate")
        observations = []
        for file in files:
            with np.load(file) as data:
                observations.append((data["grid"], data["points"]))
        reference = observations[0][1]
        matches = [np.arange(len(reference))]
        keep = np.ones(len(reference), bool)
        for _, points in observations[1:]:
            distance, index = cKDTree(points).query(reference)
            _, reciprocal = cKDTree(reference).query(points[index])
            keep &= (distance < 1.5) & (reciprocal == np.arange(len(reference)))
            matches.append(index)
        if keep.sum() < 300:
            raise ValueError(f"Input {i}: fewer than 300 common checker intersections across passes")
        retained = []
        for pass_number, ((grid, points), index) in enumerate(zip(observations, matches), 1):
            selected = index[keep]
            before = cv2.contourArea(cv2.convexHull(points.astype(np.float32)))
            after = cv2.contourArea(cv2.convexHull(points[selected].astype(np.float32)))
            fraction = after/max(before, 1)
            if after < .1*1920*1200:
                raise ValueError(f"Camera {i+1}, pass {pass_number}: shared checker area covers "
                                 f"{after/(1920*1200):.2%} of the image; minimum 10%")
            if fraction < MIN_RETAINED_HULL:
                raise ValueError(f"Camera {i+1}, pass {pass_number}: shared checker coverage retains "
                                 f"{fraction:.2%} of detected area; minimum {MIN_RETAINED_HULL:.0%}")
            retained.append({"detected": len(points), "common": len(selected),
                             "hull_fraction_retained": fraction})
        for file, (grid, points), index in zip(files, observations, matches):
            pending.append((file, grid[index[keep]], points[index[keep]]))
        fraction = min(item['hull_fraction_retained'] for item in retained)
        warning = (f"Camera {i+1}: shared checker coverage retains {fraction:.2%} of detected area."
                   if fraction < WARN_RETAINED_HULL else '')
        results.append({"input": i, "passes": retained, "warning": warning,
                        "minimum_hull_fraction_retained": MIN_RETAINED_HULL})
    # Validate every camera before replacing any detections, including on rejection.
    for file, grid, points in pending:
        file.rename(file.with_name(file.name.replace(".corners.npz", ".corners.full.npz")))
        np.savez(file, grid=grid, points=points)
    return results


def compare_pair(reference, candidate):
    a_config, a_cameras = reference
    b_config, b_cameras = candidate
    for key in ("capture_order", "front_input", "corner_ids_clockwise_from_front_right", "holder_geometry"):
        if a_config[key] != b_config[key]:
            raise ValueError(f"Repeated captures disagree on {key}")
    front = a_config["front_input"]
    a, b = a_cameras[front], b_cameras[front]
    distance, indices = cKDTree(a.points).query(b.points)
    keep = distance < 2.
    if keep.sum() < 150 or len(set(indices[keep])) < 150:
        raise ValueError("Too few stationary front checker corners to compare the independent fits")
    # Each detector can choose a different integer grid origin/basis. Remove only
    # that coordinate ambiguity, never a free warp that could hide calibration drift.
    rotation, shift, score = match_grid(b.grid[keep], a.grid[indices[keep]])
    if score > .1:
        raise ValueError("Repeated checker grids do not have an exact integer correspondence")
    errors = [[] for _ in range(4)]
    invalid, totals = np.zeros(4, int), np.zeros(4, int)
    ordered = [a_cameras[i] for i in a_config["capture_order"]]
    for q in range(4):
        x, y = np.meshgrid((np.arange(40)+.5)/40, (np.arange(30)+.5)/30)
        uv = np.c_[x.ravel(), y.ravel()]*.5 + [0 if q in (0, 3) else .5, 0 if q < 2 else .5]
        world, _ = screen_world(uv, a_config)
        source, weights = mapping(uv, q, ordered, a_config)
        candidate_world = (world-shift)@rotation
        for j, slot in enumerate((q, (q+3)%4)):
            physical = a_config["capture_order"][slot]
            pixels, valid = b_cameras[physical].map(candidate_world)
            contributing = weights[:, j] > .05
            totals[physical] += int(contributing.sum())
            invalid[physical] += int((contributing & ~valid).sum())
            errors[physical].extend(np.linalg.norm(source[j]-pixels, axis=1)[contributing & valid].tolist())
    measurements, reasons = [], []
    for i, values in enumerate(errors):
        if len(values) < 100:
            raise ValueError(f"Input {i}: insufficient shared rendered coverage for comparison")
        values = np.asarray(values)
        item = {"input": i, "samples": len(values), "mapping_rms_px": float(np.sqrt(np.mean(values**2))),
                "mapping_p95_px": float(np.percentile(values, 95)),
                "mapping_p99_px": float(np.percentile(values, 99)),
                "new_invalid_fraction": float(invalid[i]/max(totals[i], 1))}
        for key in ("mapping_rms_px", "mapping_p95_px", "mapping_p99_px"):
            if item[key] > LIMITS[key]:
                reasons.append(f"Input {i}: {key}={item[key]:.2f} > {LIMITS[key]}")
        if item["new_invalid_fraction"] > .015:
            reasons.append(f"Input {i}: inconsistent source coverage")
        measurements.append(item)
    corners = []
    for n in a_config["corner_ids_clockwise_from_front_right"]:
        a_corner = np.array(a_config["table_corner_estimates_cells"][str(n)])
        b_corner = np.array(b_config["table_corner_estimates_cells"][str(n)])@rotation.T+shift
        corners.append(float(np.linalg.norm(a_corner-b_corner)))
    if max(corners) > LIMITS["table_corner_max_cells"]:
        reasons.append(f"Table crop moved by {max(corners):.2f} checker cells")
    return {"passed": not reasons, "reasons": reasons, "cameras": measurements,
            "table_corner_displacement_cells": corners, "coordinate_rotation": rotation.tolist(),
            "coordinate_shift": shift.tolist(), "matched_front_corners": int(keep.sum())}


def compare_sessions(sessions):
    loaded = []
    for session in sessions:
        config = json.loads((session/"calibration.json").read_text())
        cameras = []
        for model in config["cameras"]:
            # Reconstruct the fit actually baked, not a fresh RANSAC result.
            cameras.append(FloorCamera(session, copy.deepcopy(model), model["H_global_to_undistorted"]))
        loaded.append((config, cameras))
    if len(loaded) < 3:
        raise ValueError("Need at least three independently calibrated passes")
    pairs, scores = [], np.zeros(len(sessions))
    for a, b in combinations(range(len(loaded)), 2):
        try:
            pair = compare_pair(loaded[a], loaded[b])
            score = sum(camera["mapping_rms_px"] for camera in pair["cameras"])/4
        except ValueError as error:
            pair = {"passed": False, "reasons": [str(error)]}
            score = float("inf")
        scores[a] += score
        scores[b] += score
        pairs.append(dict(reference_pass=a+1, candidate_pass=b+1, **pair))
    return {"passed": all(pair["passed"] for pair in pairs), "pairs": pairs, "limits": LIMITS,
            "selected_pass": int(np.argmin(scores))+1,
            "selection": "Medoid: smallest summed mapping disagreement with other independent passes"}
