#!/usr/bin/env python3
"""Bake paired TI GPU meshes for the fixed-lens and measured-cloth comparisons."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from scipy.interpolate import CloughTocher2DInterpolator
from scipy.optimize import least_squares
from scipy.spatial import Delaunay

ROOT = Path(__file__).resolve().parent
LENS_ROOT = ROOT.parent/'lens_20260908'
sys.path.insert(0, str(LENS_ROOT))
from fit_intrinsics import square_lattice

PITCH = 27.25
# Black outer marker corners in printed TL, TR, BR, BL order. BL is the
# checker-grid anchor nearest the yellow circle, as positioned by the user.
MARKER = (
    [[1675, 407], [1731, 461], [1711, 513], [1646, 454]],
    [[282, 289], [348, 236], [377, 276], [304, 335]],
)
OCCLUSIONS = (
    ((1535, 365, 1770, 565), (1420, 545, 1770, 800)),
    ((175, 180, 415, 465), (330, 365, 775, 680)),
)
cv2.setNumThreads(4)


def objects(grid):
    return np.c_[grid*PITCH, np.zeros(len(grid))].reshape(-1, 1, 3)


def project(model, grid, pose=None):
    pose = model['pose'] if pose is None else pose
    xy, _ = cv2.fisheye.projectPoints(objects(grid), pose[:3], pose[3:], model['K'], model['D'])
    return xy.reshape(-1, 2)


def plane_coordinates(model, pixels):
    rays = cv2.fisheye.undistortPoints(pixels.reshape(-1, 1, 2), model['K'], model['D'])
    rotation = cv2.Rodrigues(model['pose'][:3])[0]
    h = np.c_[rotation[:, :2]*PITCH, model['pose'][3:]]
    plane = np.c_[rays.reshape(-1, 2), np.ones(len(pixels))]@np.linalg.inv(h).T
    return plane[:, :2]/plane[:, 2:]


def fit(camera):
    lens = json.loads((LENS_ROOT/f'gmsl{camera}_intrinsics.json').read_text())
    model = {'camera': camera, 'K': np.array(lens['K']), 'D': np.array(lens['D'])}
    data = np.load(ROOT/f'captures/gmsl{camera}.corners.npz')
    grid, basis, _ = square_lattice(data['grid'], data['points'], model['K'], model['D'])
    measured = data['points']
    # Marker paper, yellow cap and tools are not checkerboard corners. Mask
    # them in BOTH comparison methods, including plausible false detections.
    clear = np.ones(len(measured), dtype=bool)
    for x0, y0, x1, y1 in OCCLUSIONS[camera]:
        clear &= ~((measured[:, 0] >= x0) & (measured[:, 0] <= x1) &
                   (measured[:, 1] >= y0) & (measured[:, 1] <= y1))
    grid, measured = grid[clear], measured[clear]
    rays = cv2.fisheye.undistortPoints(measured.reshape(-1, 1, 2), model['K'], model['D'])
    ok, r, t = cv2.solvePnP(objects(grid), rays, np.eye(3), None)
    if not ok:
        raise RuntimeError(f'Cannot initialize camera {camera} pose')
    initial = np.r_[r.ravel(), t.ravel()]
    fit = least_squares(lambda p: (project(model, grid, p)-measured).ravel(), initial,
                        loss='soft_l1', f_scale=2, x_scale='jac', max_nfev=100)
    if not fit.success:
        raise RuntimeError(f'Camera {camera} pose did not converge')
    model['pose'] = fit.x
    residual = np.linalg.norm(project(model, grid)-measured, axis=1)
    keep = residual < 12
    if keep.mean() < .8:
        raise RuntimeError(f'Camera {camera} fit rejected too many grid points')
    model.update(grid=grid[keep], points=measured[keep], lattice_basis=basis,
                 rms_px=float(np.sqrt(np.mean(residual[keep]**2))),
                 p95_px=float(np.percentile(residual[keep], 95)))
    gray = cv2.imread(str(ROOT/f'captures/gmsl{camera}.png'), 0)
    corners = cv2.cornerSubPix(gray, np.array(MARKER[camera], np.float32).reshape(-1, 1, 2),
                              (4, 4), (-1, -1), (3, 30, .01)).reshape(-1, 2)
    model['marker_grid'] = plane_coordinates(model, corners.astype(float))
    print(camera, 'pose RMS', model['rms_px'], 'marker', model['marker_grid'], flush=True)
    return model


def rotations():
    for swap in (False, True):
        for x in (-1, 1):
            for y in (-1, 1):
                rotation = np.diag([x, y])
                yield rotation[:, ::-1] if swap else rotation


def align(models):
    marker = models[0]['marker_grid']
    target = np.array([[1., 0.], [0., 1.]])
    directions = marker[[1, 3]]-marker[0]
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    rotation = min(rotations(), key=lambda r: np.linalg.norm(directions@r.T-target))
    shift = -np.rint(marker[3]@rotation.T)
    models[0].update(rotation=rotation, shift=shift)
    anchor = marker@rotation.T+shift
    options = []
    for rotation in rotations():
        shift = np.rint(np.mean(anchor-models[1]['marker_grid']@rotation.T, axis=0))
        error = np.linalg.norm(anchor-(models[1]['marker_grid']@rotation.T+shift), axis=1).mean()
        options.append((error, rotation, shift))
    error, rotation, shift = min(options, key=lambda o: o[0])
    if error > .5:
        raise RuntimeError(f'Marker correspondence is ambiguous: {error:.2f} cells')
    models[1].update(rotation=rotation, shift=shift)
    for model in models:
        model['global_grid'] = model['grid']@model['rotation'].T+model['shift']
    print('marker mismatch', error, 'cells,', error*PITCH, 'mm', flush=True)
    return error


def bake(models, mode, args):
    hulls = [Delaunay(m['global_grid']) for m in models]
    maps = [CloughTocher2DInterpolator(m['global_grid'], m['points']) for m in models]
    height = args.width/(640/800)

    def corrected(uv):
        world = uv*[args.width, height]+[args.x, args.y]
        sources, valid = [], []
        for model, hull, warp in zip(models, hulls, maps):
            source = (project(model, (world-model['shift'])@model['rotation'])
                      if mode == 'lens' else warp(world))
            inside = (hull.find_simplex(world) >= 0) & np.isfinite(source).all(1)
            inside &= (source[:, 0] >= 0) & (source[:, 0] <= 1919)
            inside &= (source[:, 1] >= 0) & (source[:, 1] <= 1199)
            sources.append(np.nan_to_num(source))
            valid.append(inside)
        alpha = np.clip(.5-world[:, 0]/args.feather, 0, 1)
        alpha = np.where(~valid[1], 1, alpha)
        alpha = np.where(~valid[0], 0, alpha)
        weights = np.c_[alpha, 1-alpha]
        weights[~(valid[0] | valid[1])] = 0
        return sources, weights

    meshes, blends = [], []
    for q in range(4):
        left, top = q in (0, 3), q in (0, 1)
        col, row = np.meshgrid(np.linspace(0, 1, 136), np.linspace(0, 1, 136))
        local = np.c_[col.ravel(), row.ravel()]
        screen = local*.5+[0 if left else .5, 0 if top else .5]
        if left:
            sources = [local*[1919, 1199]]*2
            weights = np.tile([1, 0] if top else [0, 1], (len(local), 1))
        else:
            uv = screen.copy()
            uv[:, 0] = (uv[:, 0]-.5)*2
            sources, weights = corrected(uv)
        entry = np.zeros((len(local), 7), dtype='<i2')
        entry[:, 0] = np.rint(screen[:, 0]*1080-540)
        entry[:, 1] = np.rint(540-screen[:, 1]*1080)
        for offset, source in ((3, sources[1]), (5, sources[0])):
            normalized = source/3+[0, 40]
            entry[:, offset] = np.rint(np.clip(normalized[:, 1], 0, 479)*16)
            entry[:, offset+1] = np.rint(np.clip(normalized[:, 0], 0, 639)*16)
        weight0 = np.rint(weights[:, 1]*255).astype(np.uint8)
        weight1 = np.where(weights.sum(1) > 0, 255-weight0, 0).astype(np.uint8)
        meshes.append(entry)
        blends.append(np.c_[weight0, weight1])
    np.concatenate(meshes).tofile(ROOT/f'{mode}_mesh.bin')
    np.concatenate(blends).tofile(ROOT/f'{mode}_blend.bin')
    xx, yy = np.meshgrid(np.linspace(0, 1, 640), np.linspace(0, 1, 800))
    sources, weights = corrected(np.c_[xx.ravel(), yy.ravel()])
    raw, warped = [], []
    for camera, source in enumerate(sources):
        image = cv2.imread(str(ROOT/f'captures/gmsl{camera}.png'))
        raw.append(cv2.resize(image, (640, 400), interpolation=cv2.INTER_AREA))
        warped.append(cv2.remap(image, source[:, 0].reshape(800, 640).astype('float32'),
                                 source[:, 1].reshape(800, 640).astype('float32'), cv2.INTER_LINEAR))
    stitch = sum(v.astype(float)*weights[:, i].reshape(800, 640, 1) for i, v in enumerate(warped))
    stitch = stitch.clip(0, 255).astype(np.uint8)
    cv2.imwrite(str(ROOT/f'{mode}_stitched.png'), stitch)
    cv2.imwrite(str(ROOT/f'{mode}_preview.png'), np.concatenate([np.concatenate(raw), stitch], axis=1))
    return {'mode': mode, 'x': args.x, 'y': args.y, 'width': args.width, 'height': height,
            'feather_cells': args.feather, 'uncovered_fraction': float(np.mean(weights.sum(1) == 0))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--x', type=float, default=-15)
    parser.add_argument('--y', type=float, default=-12)
    parser.add_argument('--width', type=float, default=30)
    parser.add_argument('--feather', type=float, default=1)
    args = parser.parse_args()
    if args.width <= 0 or args.feather <= 0:
        parser.error('Width and feather must be positive')
    models = [fit(c) for c in (0, 1)]
    error = align(models)
    settings = [bake(models, mode, args) for mode in ('lens', 'measured')]
    serializable = [{k: np.asarray(v).tolist() for k, v in m.items()
                    if k not in ('grid', 'points', 'global_grid')} for m in models]
    result = {'marker_error_cells': error, 'square_mm': PITCH,
              'models': serializable, 'settings': settings}
    (ROOT/'alignment.json').write_text(json.dumps(result, indent=2)+'\n')
    print(settings, flush=True)


if __name__ == '__main__':
    main()
