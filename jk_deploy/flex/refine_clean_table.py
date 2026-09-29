"""Transfer checker coordinates from a marked capture to an unobstructed capture."""
import copy
import json

import cv2
import numpy as np
from scipy.spatial import cKDTree

from align_markers import checker_phase, match_grid
from stage_table import digest, validate_candidate


def transfer_grid(reference_grid, reference_points, grid, points):
    """Resolve only integer checker origin/orientation, never warp away movement."""
    arrays = [np.asarray(a, float) for a in (reference_grid, reference_points, grid, points)]
    reference_grid, reference_points, grid, points = arrays
    if (any(a.ndim != 2 or a.shape[1] != 2 or not np.isfinite(a).all() for a in arrays) or
            reference_grid.shape != reference_points.shape or grid.shape != points.shape or
            min(len(grid), len(reference_grid)) < 150):
        raise ValueError('Need at least 150 finite checker intersections in both stages')
    distance, index = cKDTree(reference_points).query(points)
    _, reciprocal = cKDTree(points).query(reference_points[index])
    # Keep the search below a fraction of the local checker spacing, to avoid
    # matching the next black/white cell after a camera or cloth displacement.
    spacing = cKDTree(reference_points).query(reference_points, k=2)[0][:, 1]
    keep = (distance < np.minimum(3., spacing[index]*.2)) & (reciprocal == np.arange(len(points)))
    if keep.sum() < 150:
        raise ValueError('Too few unchanged checker intersections between stages; check camera/cloth movement')
    before = cv2.contourArea(cv2.convexHull(reference_points.astype(np.float32)))
    shared = cv2.contourArea(cv2.convexHull(reference_points[index[keep]].astype(np.float32)))
    if before <= 0 or shared/before < .65:
        raise ValueError('Shared checker intersections do not cover enough of the original table')
    rotation, shift, score = match_grid(grid[keep], reference_grid[index[keep]])
    phase_error = np.linalg.norm(grid[keep]@rotation.T+shift-reference_grid[index[keep]], axis=1)
    if score > .1 or phase_error.max() > .1:
        raise ValueError('Checker coordinates changed between stages; refusing a cell-offset merge')
    world = grid@rotation.T+shift
    new_cells = cKDTree(reference_grid).query(world)[0] > .1
    hull = cv2.convexHull(reference_grid.astype(np.float32))
    expanded = sum(cv2.pointPolygonTest(hull, tuple(map(float, p)), False) < 0 for p in world)
    rms = float(np.sqrt(np.mean(distance[keep]**2)))
    return rotation, shift, {
        'shared_intersections': int(keep.sum()), 'shared_hull_fraction': float(shared/before),
        'shared_pixel_rms': rms, 'shared_pixel_p95': float(np.percentile(distance[keep], 95)),
        'new_checker_intersections': int(new_cells.sum()), 'outside_old_checker_hull': int(expanded),
        'coordinate_rms_cells': score,
        'warning': 'Small checker displacement between stages; inspect alignment.' if rms > 1. else '',
    }


def clean_config(session, reference):
    validate_candidate(reference)
    config = copy.deepcopy(json.loads((reference/'session.json').read_text()))
    config.setdefault('marker_selection', {
        'selected_ids': sorted(config['corner_ids_clockwise_from_front_right']), 'ignored_unshared_ids': []})
    models, measurements = [], []
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    marker_ids = set(config['marker_selection']['selected_ids'])
    for i in range(4):
        image = cv2.imread(str(session/'captures'/f'input{i}.png'))
        _, ids, _ = detector.detectMarkers(image)
        remaining = marker_ids & (set(map(int, ids.ravel())) if ids is not None else set())
        if remaining:
            raise ValueError(f'Camera {i+1}: green corner marker IDs {sorted(remaining)} are still visible')
        with np.load(reference/'captures'/f'input{i}.floor.npz') as data:
            model = config['aligned_models'][i]
            reference_grid = data['grid']@np.asarray(model['rotation']).T+model['shift']
            reference_points = data['points']
        with np.load(session/'captures'/f'input{i}.floor.npz') as data:
            rotation, shift, quality = transfer_grid(reference_grid, reference_points, data['grid'], data['points'])
        models.append(dict(input=i, rotation=rotation.tolist(), shift=shift.tolist(),
                           marker_rms_cells=model['marker_rms_cells']))
        measurements.append(dict(input=i, **quality))
    phases = [checker_phase(session, model) for model in models]
    expected = config['checker_phase_verification']
    if any(a['white_parity'] != b['white_parity'] for a, b in zip(phases, expected)):
        raise ValueError('Checker color phase changed between marked and clear captures')
    config.update(aligned_models=models, checker_phase_verification=phases,
                  description='Two-stage table fit: marked identity/crop, unobstructed checker refinement',
                  clean_refinement={'passed': True, 'reference': str(reference.resolve()),
                                    'reference_report_sha256': digest(reference/'report.json'),
                                    'reference_session_sha256': digest(reference/'session.json'),
                                    'cameras': measurements, 'crop_preserved': True})
    return config
