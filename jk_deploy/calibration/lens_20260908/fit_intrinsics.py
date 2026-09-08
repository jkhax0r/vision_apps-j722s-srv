#!/usr/bin/env python3
"""Offline first-pass fisheye calibration of the September 8 cloth captures."""
import argparse
import json
from itertools import product
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent
SIZE = (1920, 1200)
SQUARE_MM = 27.25
K0 = np.array([[1010., 0., 959.5], [0., 1010., 599.5], [0., 0., 1.]])
D0 = np.array([-1/24, 1/1920, 0., 0.])
cv2.setNumThreads(4)


def seed_cell(gray, corners, tree):
    # An unbounded repeating cloth can produce a larger-than-one-cell basis.
    # Reject seed quads containing additional detected checker corners.
    for x, y in ((700, 250), (500, 200), (1000, 200), (300, 100), (700, 50),
                 (700, 500), (1100, 500), (100, 450), (500, 450), (1100, 50),
                 (1200, 0), (1000, 0), (0, 50), (1200, 250), (300, 400)):
        found, points, meta = cv2.findChessboardCornersSBWithMeta(
            gray[y:y+500, x:x+600], (5, 5),
            cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_LARGER)
        if not found:
            continue
        points = points.reshape(*meta.shape, 2) + [x, y]
        choices = []
        for row in range(meta.shape[0]-1):
            for col in range(meta.shape[1]-1):
                quad = points[row:row+2, col:col+2].reshape(4, 2)
                distance, indices = tree.query(quad)
                if distance.max() > 3 or len(set(indices)) != 4:
                    continue
                quad = corners[indices]
                edges = quad[[1, 2]] - quad[0]
                # SB may skip several repeated cells. Find the nearest
                # corner along each detected grid direction before growing.
                nearby = np.array(tree.query_ball_point(quad[0], 150))
                vectors = corners[nearby]-quad[0]
                lengths = np.linalg.norm(vectors, axis=1)
                neighbors = []
                for edge in edges:
                    cosine = (vectors@edge)/np.maximum(lengths*np.linalg.norm(edge), 1e-8)
                    candidates = np.flatnonzero((lengths > 8) & (cosine > .985))
                    if not len(candidates):
                        break
                    neighbors.append(nearby[candidates[np.argmin(lengths[candidates])]])
                if len(neighbors) != 2 or neighbors[0] == neighbors[1]:
                    continue
                edges = corners[neighbors]-quad[0]
                distance, diagonal = tree.query(quad[0]+edges.sum(0))
                if distance > .18*np.linalg.norm(edges, axis=1).min():
                    continue
                indices = np.array([indices[0], *neighbors, diagonal])
                if len(set(indices)) != 4:
                    continue
                quad = corners[indices]
                scale = np.linalg.norm(edges, axis=1).min()
                if scale < 9 or scale > 120:
                    continue
                probes = np.array([quad.mean(0), (quad[0]+quad[1])/2,
                                   (quad[0]+quad[2])/2])
                if tree.query(probes)[0].min() < scale*.20:
                    continue
                score = np.linalg.norm(quad.mean(0)-[1000, 500])
                choices.append((score, indices))
        if choices:
            return min(choices, key=lambda c: c[0])[1]
    raise RuntimeError("No unambiguous one-cell seed found")


def detect(path):
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != SIZE[::-1]:
        raise ValueError(f"Invalid full-resolution input: {path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    points = cv2.goodFeaturesToTrack(gray, 12000, .035, 7, blockSize=5)
    if points is None:
        raise RuntimeError(f"No corners in {path}")
    points = cv2.cornerSubPix(gray, points, (4, 4), (-1, -1),
                             (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                              30, .01)).reshape(-1, 2)
    tree = cKDTree(points)
    indices = seed_cell(gray, points, tree)
    grid = dict(zip(((0, 0), (1, 0), (0, 1), (1, 1)), indices))
    used = set(indices)
    for _ in range(120):
        proposals = {}
        for uv, index in list(grid.items()):
            point = points[index]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                dest, prev = (uv[0]+dx, uv[1]+dy), (uv[0]-dx, uv[1]-dy)
                if dest in grid or prev not in grid:
                    continue
                step = point - points[grid[prev]]
                distance, candidate = tree.query(point+step)
                if candidate not in used and distance < min(9, .24*np.linalg.norm(step)):
                    proposals.setdefault(dest, []).append((distance, candidate))
        accepted = 0
        for uv, candidates in sorted(proposals.items(), key=lambda item: min(item[1])[0]):
            indices = {candidate for _, candidate in candidates}
            if len(indices) != 1:
                continue
            index = indices.pop()
            if index in used:
                continue
            grid[uv] = index
            used.add(index)
            accepted += 1
        if not accepted:
            break
    lattice = np.array(list(grid), dtype=np.float64)
    measured = points[list(grid.values())].astype(np.float64)
    ideal = cv2.fisheye.undistortPoints(measured.reshape(-1, 1, 2), K0, D0).reshape(-1, 2)
    _, mask = cv2.findHomography(lattice, ideal, cv2.RANSAC, .015)
    if mask is None or mask.sum() < 100:
        raise RuntimeError(f"Insufficient consistent checker corners: {path}")
    keep = mask.ravel().astype(bool)
    lattice, measured = lattice[keep], measured[keep]
    np.savez(path.with_suffix('.corners.npz'), grid=lattice, points=measured)
    overlay = image.copy()
    for uv, xy in zip(lattice, measured):
        p = tuple(np.rint(xy).astype(int))
        cv2.circle(overlay, p, 3, (0, 0, 255), -1)
        if int(uv[0]) % 5 == 0 and int(uv[1]) % 5 == 0:
            cv2.putText(overlay, f'{int(uv[0])},{int(uv[1])}', p,
                        cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 255, 0), 1)
    cv2.imwrite(str(path.with_suffix('.corners.png')), overlay)
    print(path.parent.name, path.stem, len(measured), 'corners', flush=True)


def square_lattice(grid, points, k=K0, d=D0):
    # Repeating patterns also admit an oblique integer basis (e.g. a
    # diagonal plus a row). Reduce it to the actual square-cell axes.
    normalized = cv2.fisheye.undistortPoints(points.reshape(-1, 1, 2), k, d)
    h, _ = cv2.findHomography(grid, normalized)
    choices = []
    for entries in product(range(-2, 3), repeat=4):
        basis = np.array(entries).reshape(2, 2)
        if round(np.linalg.det(basis)) != 1:
            continue
        a, b = (h[:, :2]@basis).T
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        score = abs(a@b/(na*nb)) + abs(np.log(na/nb))
        score += 1e-7*np.linalg.norm(basis-np.eye(2))
        choices.append((score, basis))
    score, basis = min(choices, key=lambda c: c[0])
    if score > .2:
        raise RuntimeError('Non-square or inconsistent detected lattice')
    return grid@np.linalg.inv(basis).T, basis, score


def load_views(camera):
    views = []
    for path in sorted(ROOT.glob(f'pose_*/gmsl{camera}.corners.npz')):
        data = np.load(path)
        grid, basis, score = square_lattice(data['grid'], data['points'])
        grid = (grid-grid.mean(0))*SQUARE_MM
        objects = np.c_[grid, np.zeros(len(grid))].reshape(-1, 1, 3)
        views.append({'pose': path.parent.name, 'objects': objects,
                      'points': data['points'].reshape(-1, 1, 2),
                      'lattice_basis': basis.tolist(), 'lattice_metric_error': float(score)})
    return views


def calibrate(views, free_center=False):
    constants = cv2.fisheye if hasattr(cv2.fisheye, 'CALIB_FIX_SKEW') else cv2
    flags = (constants.CALIB_USE_INTRINSIC_GUESS |
             constants.CALIB_RECOMPUTE_EXTRINSIC | constants.CALIB_FIX_SKEW |
             constants.CALIB_FIX_K3 | constants.CALIB_FIX_K4)
    if not free_center:
        flags |= constants.CALIB_FIX_PRINCIPAL_POINT
    rms, k, d, rotations, translations = cv2.fisheye.calibrate(
        [v['objects'] for v in views], [v['points'] for v in views], SIZE,
        K0.copy(), D0.copy(), flags=flags,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-8))
    residuals = []
    for view, rotation, translation in zip(views, rotations, translations):
        projected, _ = cv2.fisheye.projectPoints(view['objects'], rotation, translation, k, d)
        residuals.append(np.linalg.norm(projected-view['points'], axis=2).ravel())
    return rms, k, d, residuals


def evaluate_pose(view, k, d):
    normalized = cv2.fisheye.undistortPoints(view['points'], k, d)
    ok, rotation, translation = cv2.solvePnP(view['objects'], normalized, np.eye(3), None)
    if not ok:
        raise RuntimeError(f"Pose fit failed: {view['pose']}")
    projected, _ = cv2.fisheye.projectPoints(view['objects'], rotation, translation, k, d)
    errors = np.linalg.norm(projected-view['points'], axis=2).ravel()
    return {'pose': view['pose'], 'points': len(errors),
            'rms_px': float(np.sqrt(np.mean(errors**2))),
            'median_px': float(np.median(errors)), 'p95_px': float(np.percentile(errors, 95))}


def fit_camera(camera):
    views = load_views(camera)
    if len(views) < 6:
        raise RuntimeError(f"Need at least six detected views; camera {camera} has {len(views)}")
    # First-pass outliers include occluding objects, false grid extensions and
    # local cloth folds. Retain raw detections alongside the filtered results.
    rms, k, d, errors = calibrate(views)
    print('Initial', camera, rms, k.tolist(), d.ravel().tolist(), flush=True)
    def clean(source, residuals):
        result = []
        for view, error in zip(source, residuals):
            keep = error < 10
            if keep.sum() >= 100 and keep.mean() > .65:
                result.append(dict(view, objects=view['objects'][keep], points=view['points'][keep]))
        if len(result) < 6:
            raise RuntimeError('Fit rejected too many views; refusing to report a calibration')
        return result
    cleaned = clean(views, errors)
    rms, k, d, _ = calibrate(cleaned)
    print('Filtered', camera, rms, k.tolist(), d.ravel().tolist(), flush=True)
    # Holdout poses do not participate in fitting or training-point filtering.
    holdout = [v for v in views if v['pose'] in ('pose_008', 'pose_010')]
    training = [v for v in views if v['pose'] not in ('pose_008', 'pose_010')]
    if len(holdout) != 2:
        raise RuntimeError('Missing one of the two holdout poses')
    _, _, _, training_errors = calibrate(training)
    _, train_k, train_d, _ = calibrate(clean(training, training_errors))
    result = {'camera': camera, 'model': 'OpenCV fisheye, k1/k2 only, centered principal point',
              'opencv_version': cv2.__version__, 'numpy_version': np.__version__,
              'size': list(SIZE), 'square_mm': SQUARE_MM, 'K': k.tolist(),
              'D': d.ravel().tolist(), 'training_rms_px': float(rms),
              'per_pose': [evaluate_pose(v, k, d) for v in cleaned],
              'all_detected_per_pose': [evaluate_pose(v, k, d) for v in views],
              'lattice_bases': {v['pose']: v['lattice_basis'] for v in views},
              'holdout': [evaluate_pose(v, train_k, train_d) for v in holdout],
              'holdout_train_K': train_k.tolist(), 'holdout_train_D': train_d.ravel().tolist(),
              'status': 'Experimental; inspect held-out errors and correction before deployment'}
    (ROOT/f'gmsl{camera}_intrinsics.json').write_text(json.dumps(result, indent=2)+'\n')
    # A lens-only view, without ground perspective correction or camera blending.
    new_k = k.copy()
    new_k[0, 0] *= .8
    new_k[1, 1] *= .8
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(k, d, np.eye(3), new_k, SIZE, cv2.CV_32FC1)
    for pose in ('pose_001', 'pose_008', 'pose_010'):
        raw = cv2.imread(str(ROOT/pose/f'gmsl{camera}.png'))
        if raw is None:
            continue
        corrected = cv2.remap(raw, map1, map2, cv2.INTER_LINEAR)
        cv2.imwrite(str(ROOT/pose/f'gmsl{camera}.undistorted.png'), corrected)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['detect', 'fit'])
    parser.add_argument('--camera', type=int, choices=[0, 1])
    parser.add_argument('--force', action='store_true', help='Recompute cached corner detections')
    args = parser.parse_args()
    cameras = (0, 1) if args.camera is None else (args.camera,)
    if args.mode == 'detect':
        failures = []
        for pose in sorted(ROOT.glob('pose_*')):
            for camera in cameras:
                path = pose/f'gmsl{camera}.png'
                if path.with_suffix('.corners.npz').exists() and not args.force:
                    continue
                try:
                    detect(path)
                except RuntimeError as error:
                    path.with_suffix('.corners.npz').unlink(missing_ok=True)
                    failures.append({'image': str(path.relative_to(ROOT)), 'error': str(error)})
                    print('FAILED', path, error, flush=True)
        (ROOT/'detection_failures.json').write_text(json.dumps(failures, indent=2)+'\n')
    else:
        for camera in cameras:
            fit_camera(camera)


if __name__ == '__main__':
    main()
