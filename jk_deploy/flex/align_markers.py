#!/usr/bin/env python3
"""Align four checker grids using unordered corner IDs and validate the table."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.interpolate import CloughTocher2DInterpolator, RBFInterpolator
from scipy.spatial import cKDTree

from fit_floor import rotations, transform, undistort

HERE = Path(__file__).resolve().parent
DEFAULT_GEOMETRY = HERE.parent / "calibration/table_corner_markers/v1/generated/marker_geometry.json"


def match_grid(local, reference):
    if local.shape != reference.shape or local.ndim != 2 or local.shape[1] != 2 or len(local) < 4:
        raise ValueError("Need at least four corresponding marker corners")
    if not np.isfinite(local).all() or not np.isfinite(reference).all():
        raise ValueError("Non-finite marker coordinates")
    choices = []
    for r in rotations():
        shift = np.rint(np.mean(reference-local@r.T, axis=0)).astype(int)
        error = np.linalg.norm(local@r.T+shift-reference, axis=1)
        choices.append((float(np.sqrt(np.mean(error**2))), r, shift))
    choices.sort(key=lambda item: item[0])
    score, rotation, shift = choices[0]
    # These extrapolated anchors select integer grid phase, not subpixel geometry.
    if score > .75 or choices[1][0]-score < 1.:
        raise ValueError(f"Ambiguous marker/grid alignment: {score:.3f} cells")
    return rotation, shift, score


def checker_phase(session, model):
    data = np.load(session / "captures" / f"input{model['input']}.floor.npz")
    grid = data["grid"]@np.array(model["rotation"]).T+model["shift"]
    lo, hi = np.ceil(grid.min(0)).astype(int), np.floor(grid.max(0)).astype(int)
    x, y = np.meshgrid(np.arange(lo[0], hi[0]), np.arange(lo[1], hi[1]))
    world = np.c_[x.ravel()+.5, y.ravel()+.5]
    pixels = CloughTocher2DInterpolator(grid, data["points"])(world)
    valid = np.isfinite(pixels).all(1)
    image = cv2.imread(str(session / "captures" / f"input{model['input']}.png"), 0)
    samples = cv2.remap(image, np.nan_to_num(pixels).astype(np.float32).reshape(-1, 1, 2),
                        None, cv2.INTER_LINEAR).ravel()
    parity = ((x+y)%2).ravel()
    medians = []
    for k in (0, 1):
        selected = samples[valid & (parity == k)]
        if len(selected) < 50:
            raise ValueError("Insufficient checker samples for phase verification")
        medians.append(float(np.median(selected)))
    if abs(medians[1]-medians[0]) < 30:
        raise ValueError("Checker phase is not confidently distinguishable")
    return {"median_luma_even_odd": medians, "white_parity": int(np.argmax(medians))}


def validate_marker_views(views, allowed=None):
    if len(views) != 4:
        raise ValueError("Need four marker views")
    if allowed is None:
        visibility = {}
        for i, (_, ids, _) in enumerate(views):
            for n in set(map(int, ids.ravel())) if ids is not None else ():
                visibility.setdefault(n, set()).add(i)
        allowed = sorted(n for n, cameras in visibility.items() if len(cameras) >= 2)
        if len(allowed) != 4:
            raise ValueError(f"Need four corner IDs shared across camera pairs; found {allowed}. "
                             "Check missing markers or specify --marker-ids for unrelated labels.")
    if len(set(allowed)) != 4 or len(allowed) != 4 or any(n not in range(50) for n in allowed):
        raise ValueError("Specify four distinct marker IDs in 0..49")
    selected, ignored = [], []
    for i, (corners, ids, shape) in enumerate(views):
        try:
            selected.append(validate_marker_detections(corners, ids, shape, allowed))
        except ValueError as error:
            raise ValueError(f"Input {i}: {error}") from error
        extras = sorted(set(map(int, ids.ravel()))-set(allowed))
        if extras:
            ignored.append({"input": i, "ids": extras})
    return selected, {"selected_ids": sorted(allowed), "ignored_unshared_ids": ignored}


def validate_marker_detections(corners, ids, image_shape, allowed=None):
    if ids is None:
        raise ValueError("No complete markers decoded; show the full patterns and white borders")
    selected = {}
    height, width = image_shape[:2]
    for points, marker_id in zip(corners, ids.ravel()):
        marker_id = int(marker_id)
        if allowed is not None and marker_id not in allowed:
            continue
        if marker_id in selected:
            raise ValueError(f"Duplicate ID {marker_id} in one view; use four unique labels")
        points = np.asarray(points, float).reshape(4, 2)
        if not np.isfinite(points).all():
            raise ValueError(f"Marker {marker_id}: non-finite corners")
        sides = np.linalg.norm(points-np.roll(points, -1, axis=0), axis=1)
        if sides.min() < 30:
            raise ValueError(f"Marker {marker_id}: only {sides.min():.1f} pixels on shortest edge; move closer")
        if (points < 12).any() or (points > [width-13, height-13]).any():
            raise ValueError(f"Marker {marker_id} too close to image edge; include the white border")
        if not cv2.isContourConvex(points.astype(np.float32)) or abs(cv2.contourArea(points.astype(np.float32))) < 600:
            raise ValueError(f"Marker {marker_id}: degenerate or overly oblique outline")
        selected[marker_id] = points
    if len(selected) != 2:
        raise ValueError(f"Need two complete corner markers per camera; found {sorted(selected)}")
    return selected


def camera_ring(pixels, front=0):
    if len(pixels) != 4 or front not in range(4):
        raise ValueError("Need four camera views and a front input in 0..3")
    visibility = {}
    for i, markers in enumerate(pixels):
        if len(markers) != 2:
            raise ValueError(f"Camera {i+1} must see two distinct corners")
        for marker in markers:
            visibility.setdefault(marker, []).append(i)
    if len(visibility) != 4 or any(len(v) != 2 for v in visibility.values()):
        raise ValueError("Need four unique IDs, each seen by exactly two cameras; check missing/duplicate labels")
    edges = {}
    for marker, cameras in visibility.items():
        edge = frozenset(cameras)
        if edge in edges:
            raise ValueError("Two markers connect the same cameras; the four-view ring is disconnected")
        edges[edge] = marker
    # On this rig the native front image is upside down: its left corner is
    # front-right on the table. This convention is independent of marker IDs.
    front_markers = sorted(pixels[front], key=lambda n: pixels[front][n].mean(0)[0])
    if abs(pixels[front][front_markers[1]].mean(0)[0]-pixels[front][front_markers[0]].mean(0)[0]) < 80:
        raise ValueError("Front corners have insufficient horizontal separation to determine orientation")
    right = next(i for i in visibility[front_markers[0]] if i != front)
    order = [front, right]
    while len(order) < 4:
        current = order[-1]
        neighbors = {j for n in pixels[current] for j in visibility[n] if j != current}
        onward = neighbors-set(order)
        if len(onward) != 1:
            raise ValueError("Shared IDs do not form one unambiguous four-camera ring")
        order.append(onward.pop())
    if frozenset((order[-1], front)) not in edges:
        raise ValueError("Camera ring does not close")
    corner_ids = [edges[frozenset((order[i], order[(i+1)%4]))] for i in range(4)]
    return order, corner_ids, visibility


def align_grids(grids, pixels, front_center, front=0):
    order, corner_ids, visibility = camera_ring(pixels, front)
    front_right, front_left = corner_ids[0], corner_ids[3]
    across = grids[front][front_right].mean(0)-grids[front][front_left].mean(0)
    outward = (grids[front][front_right].mean(0)+grids[front][front_left].mean(0))/2-front_center
    if min(np.linalg.norm(across), np.linalg.norm(outward)) < 1:
        raise ValueError("Cannot determine front orientation from the corner markers")
    orientation = max(rotations(), key=lambda r: (across@r.T)[0]/np.linalg.norm(across)
                      -(outward@r.T)[1]/np.linalg.norm(outward))
    anchors = {}
    models, observations = [None]*4, {n: [] for n in visibility}
    for i in order:
        grid = grids[i]
        if i == front:
            r, shift, score = orientation, np.zeros(2, int), 0.
        else:
            shared = sorted(set(anchors) & set(grid))
            r, shift, score = match_grid(np.concatenate([grid[n] for n in shared]),
                                         np.concatenate([anchors[n] for n in shared]))
        for n, points in grid.items():
            world = points@r.T+shift
            anchors.setdefault(n, world)
            observations[n].append(world)
        models[i] = {"input": i, "rotation": r.tolist(), "shift": shift.tolist(),
                     "marker_rms_cells": score}
    disagreements = {}
    for n, values in observations.items():
        errors = np.linalg.norm(values[0]-values[1], axis=1)
        disagreements[n] = float(np.sqrt(np.mean(errors**2)))
        if disagreements[n] > .75 or errors.max() > 1.25:
            raise ValueError(f"Marker {n}: camera loop does not agree ({disagreements[n]:.2f} cells)")
    return models, observations, order, corner_ids, disagreements


def table_frame(observations, corner_ids, geometry, inset_percent=0.5):
    if not 0 <= inset_percent <= 10:
        raise ValueError("Crop inset must be between 0 and 10 percent")
    label = np.asarray(geometry["marker_corners_canonical_xy"], np.float32)
    if label.shape != (4, 2) or not np.isfinite(label).all() or abs(cv2.contourArea(label)) < 100:
        raise ValueError("Invalid holder geometry")
    table, centers, disagreement = {}, {}, {}
    for n, values in observations.items():
        estimates = []
        for value in values:
            h = cv2.getPerspectiveTransform(label, value.astype(np.float32))
            estimates.append(transform(np.array([[0., 0.]]), h)[0])
        if not np.isfinite(estimates).all():
            raise ValueError(f"Marker {n}: unstable table-corner extrapolation")
        table[n] = np.mean(estimates, axis=0)
        centers[n] = np.mean(values, axis=(0, 1))
        disagreement[n] = float(np.linalg.norm(estimates[0]-estimates[1]))
        if disagreement[n] > 2:
            raise ValueError(f"Marker {n}: table-corner estimates differ by {disagreement[n]:.2f} cells")
    q = np.array([table[n] for n in corner_ids])  # NE, SE, SW, NW, independent of IDs.
    if not cv2.isContourConvex(q.astype(np.float32)):
        raise ValueError("Table corners are crossed/concave; check holder seating and label orientation")
    center = q.mean(0)
    x = (q[0]-q[3]+q[1]-q[2])/2
    y = (q[2]-q[3]+q[1]-q[0])/2
    if min(np.linalg.norm(x), np.linalg.norm(y)) < 10:
        raise ValueError("Table estimate is too small or degenerate")
    u, _, vt = np.linalg.svd(np.column_stack((x/np.linalg.norm(x), y/np.linalg.norm(y))))
    axes = u@vt
    if np.linalg.det(axes) < .99:
        raise ValueError("Table orientation is mirrored; verify camera orientation")
    local = (q-center)@axes
    width = float(np.mean(local[[0, 1], 0])-np.mean(local[[2, 3], 0]))
    height = float(np.mean(local[[1, 2], 1])-np.mean(local[[0, 3], 1]))
    ideal = np.array([[width/2, -height/2], [width/2, height/2],
                      [-width/2, height/2], [-width/2, -height/2]])
    errors = np.linalg.norm(local-ideal, axis=1)
    if errors.max() > .05*min(width, height):
        raise ValueError("Corner layout is not rectangular enough; inspect labels, cloth, and holder seating")
    for n in corner_ids:
        offset, outward = table[n]-centers[n], centers[n]-center
        cosine = float(offset@outward/max(np.linalg.norm(offset)*np.linalg.norm(outward), 1e-9))
        if cosine < .65:
            raise ValueError(f"Marker {n}: label may be rotated on its holder; clipped corner must point outward")
    shrink = 1-2*inset_percent/100
    crop = [-width*shrink/2, -height*shrink/2, width*shrink, height*shrink]
    frame = {"origin_cells": center.tolist(), "axes": axes.tolist()}
    quality = {"rectangle_max_error_cells": float(errors.max()),
               "table_corner_disagreement_cells": disagreement,
               "inset_percent_per_edge": inset_percent}
    return crop, frame, {n: p.tolist() for n, p in table.items()}, quality


def marker_grid_support(grid, points, homography, detected, label):
    """Map marker corners into the measured lattice, limiting extrapolation."""
    rays = undistort(points)
    inverse = np.linalg.inv(homography)
    residual = RBFInterpolator(rays, grid-transform(rays, inverse),
                               neighbors=32, smoothing=1e-5)
    observed, farthest = {}, 0.
    tree = cKDTree(grid)
    for n, p in detected.items():
        q = undistort(p)
        observed[n] = transform(q, inverse)+residual(q)
        if not np.isfinite(observed[n]).all():
            raise ValueError(f"{label}, marker {n}: unstable inverse mapping")
        distance = float(tree.query(observed[n])[0].max())
        farthest = max(farthest, distance)
        if distance > 8:
            raise ValueError(f"{label}, marker {n}: too far from reliable checker coverage "
                             f"({distance:.1f} cells; maximum 8)")
    return observed, farthest


def build_config(session, front=0, allowed=None, geometry=None, inset_percent=.5):
    if allowed is not None and (len(allowed) != 4 or len(set(allowed)) != 4 or any(n not in range(50) for n in allowed)):
        raise ValueError("--marker-ids must specify four distinct IDs in 0..49")
    geometry = geometry or json.loads(DEFAULT_GEOMETRY.read_text())
    fits = json.loads((session / "floor_fits.json").read_text())
    if len(fits) != 4 or [fit["input"] for fit in fits] != list(range(4)):
        raise ValueError("Floor fits must contain inputs 0,1,2,3 in order")
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    views = []
    for i, fit in enumerate(fits):
        image = cv2.imread(str(session / "captures" / f"input{i}.png"))
        if image is None or image.shape[:2] != (1200, 1920):
            raise ValueError(f"Camera {i+1}: need a native 1920x1200 image")
        corners, ids, _ = detector.detectMarkers(image)
        views.append((corners, ids, image.shape))
    pixels, selection = validate_marker_views(views, allowed)
    grids, support = [], []
    for i, fit in enumerate(fits):
        detected = pixels[i]
        data = np.load(session / "captures" / f"input{i}.floor.npz")
        if len(data["grid"]) < 150:
            raise ValueError(f"Camera {i+1}: fewer than 150 checker intersections")
        # The markers border the observed grid. Correct the coarse lens/homography
        # inverse locally before rounding its coordinates to a whole-cell shift.
        observed, farthest = marker_grid_support(data["grid"], data["points"], fit["H"],
                                                  detected, f"Camera {i+1}")
        grids.append(observed)
        support.append({"input": i, "farthest_marker_corner_from_checker_cells": farthest})
    center = transform(undistort(np.array([[960., 600.]])), np.linalg.inv(fits[front]["H"]))[0]
    models, observations, order, corner_ids, disagreements = align_grids(grids, pixels, center, front)
    phases = [checker_phase(session, model) for model in models]
    if len({p["white_parity"] for p in phases}) != 1:
        raise ValueError(f"Checker colors disagree: possible one-cell slip: {phases}")
    crop, frame, table, quality = table_frame(observations, corner_ids, geometry, inset_percent)
    return {
        "schema_version": 2, "description": "Unordered corner-marker checker-plane calibration candidate",
        "capture_order": order, "front_input": front,
        "corner_ids_clockwise_from_front_right": corner_ids,
        "camera_names": [f"input{i} {role}" for i, role in zip(order, ("front", "right", "rear", "left"))],
        "alignment_source": "Unordered ArUco DICT_4X4_50 IDs and integer checker grids",
        "marker_selection": selection,
        "aligned_models": models, "marker_disagreement_cells": disagreements,
        "checker_phase_verification": phases,
        "table_corner_estimates_cells": table, "crop_cells": crop, "view_frame": frame,
        "crop_quality": quality, "checker_support": support, "feather_cells": 1.5,
        "holder_geometry": geometry,
        "notes": "Static flat-plane candidate, not a new intrinsic fit or metric accuracy guarantee. "
                 "Labels must have correct orientation on seated holders. Front camera uses the existing inverted native image convention."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--front-input", type=int, choices=range(4), default=0)
    parser.add_argument("--marker-ids", type=int, nargs=4)
    parser.add_argument("--geometry", type=Path, default=DEFAULT_GEOMETRY)
    parser.add_argument("--inset-percent", type=float, default=.5)
    args = parser.parse_args()
    config = build_config(args.session, args.front_input, args.marker_ids,
                          json.loads(args.geometry.read_text()), args.inset_percent)
    temporary = args.session / "session.json.tmp"
    temporary.write_text(json.dumps(config, indent=2)+"\n")
    temporary.replace(args.session / "session.json")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
