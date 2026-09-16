#!/usr/bin/env python3
"""TI-generated bowl versus flat board, with frozen per-camera lens/pose fits."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import cv2
import numpy as np
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'pair_final_20260908T184734Z'))
import make_pair as base


def load_models():
    alignment = json.loads((ROOT/'alignment.json').read_text())
    settings = json.loads((ROOT/'settings.json').read_text())
    base.ROOT, base.PITCH = ROOT, alignment['square_mm']
    models = []
    for camera, saved in enumerate(alignment['models']):
        model = {k: np.asarray(v) if isinstance(v, list) else v for k, v in saved.items()}
        lens = json.loads((base.LENS_ROOT/f'gmsl{camera}_intrinsics.json').read_text())
        for field in ('K', 'D'):
            np.testing.assert_array_equal(model[field], lens[field])
        if not np.isclose(np.linalg.det(model['rotation']), 1):
            raise ValueError('This bowl adapter requires a right-handed board frame')
        data = np.load(ROOT/f'captures/gmsl{camera}.corners.npz')
        grid = data['grid']@np.linalg.inv(model['lattice_basis']).T
        points = data['points']
        keep = np.linalg.norm(base.project(model, grid)-points, axis=1) < 12
        for x0, y0, x1, y1 in settings['occlusions'][camera]:
            keep &= ~((points[:, 0] >= x0) & (points[:, 0] <= x1) &
                      (points[:, 1] >= y0) & (points[:, 1] <= y1))
        model.update(grid=grid[keep], points=points[keep],
                     global_grid=grid[keep]@model['rotation'].T+model['shift'])
        models.append(model)
    return alignment, models


def generate_surface(models, half_base):
    centers = []
    for model in models:
        pose = model['pose']
        center = -cv2.Rodrigues(pose[:3])[0].T@pose[3:]
        center[:2] = center[:2]@model['rotation'].T+model['shift']*base.PITCH
        # TI's bowl coordinates use Y up; the checkerboard frame uses Y down.
        centers.append([center[0], -center[1], 0])
    centers = np.array(centers, dtype=np.float32)
    xyz = np.full((270, 270, 3), np.nan, dtype=np.float32)
    lib = ctypes.CDLL(str(ROOT/'ti_bowl_helper.so'))
    ptr = ctypes.POINTER(ctypes.c_float)
    lib.jk_generate_bowl.argtypes = [ptr, ctypes.c_int, ptr]
    lib.jk_generate_bowl.restype = ctypes.c_int
    status = lib.jk_generate_bowl(centers.ctypes.data_as(ptr), half_base, xyz.ctypes.data_as(ptr))
    if status or not np.isfinite(xyz).all():
        raise RuntimeError('TI bowl generator failed or left invalid vertices')
    xs, ys = xyz[0, :, 0], -xyz[:, 0, 1]
    if not (np.all(np.diff(xs) > 0) and np.all(np.diff(ys) > 0)):
        raise RuntimeError('Unexpected TI bowl axes')
    interp = RegularGridInterpolator((ys, xs), xyz[:, :, 2], bounds_error=True)
    return xyz, centers, lambda grid: interp((grid*base.PITCH)[:, ::-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--height-mm', type=float, default=50)
    parser.add_argument('--base-half-cells', type=int, default=80)
    args = parser.parse_args()
    if not 0 < args.height_mm <= 150 or not 4 <= args.base_half_cells <= 400:
        parser.error('Height must be in (0,150] mm and base half size in [4,400]')
    alignment, models = load_models()
    flat = next(s for s in alignment['settings'] if s['mode'] == 'lens')
    opts = SimpleNamespace(x=flat['x'], y=flat['y'], width=flat['width'],
                           feather=flat['feather_cells'], seam_x=flat['seam_x'])
    xyz, centers, native_surface = generate_surface(models, args.base_half_cells)
    xx, yy = np.meshgrid(np.linspace(flat['x'], flat['x']+flat['width'], 640),
                         np.linspace(flat['y'], flat['y']+flat['height'], 800))
    grid = np.c_[xx.ravel(), yy.ravel()]
    native_height = native_surface(grid)
    if native_height.max() <= 0:
        raise ValueError('Chosen crop does not intersect the raised bowl')
    scale = args.height_mm/float(native_height.max())
    surface = lambda points: native_surface(points)*scale
    with tempfile.TemporaryDirectory(prefix='.bowl-', dir=ROOT) as work:
        stage = Path(work)
        (stage/'captures').symlink_to(ROOT/'captures', target_is_directory=True)
        base.ROOT = stage
        try:
            result = base.bake(models, 'bowl', opts, surface_height=surface)
            finish(stage, result, surface, grid, xyz, centers, scale, args)
        finally:
            base.ROOT = ROOT


def finish(stage, result, surface, grid, xyz, centers, scale, args):
    if result['uncovered_fraction'] > .01:
        raise RuntimeError('Bowl creates uncovered output: lower the requested height')
    same_blend = (stage/'bowl_blend.bin').read_bytes() == (ROOT/'lens_blend.bin').read_bytes()
    if not same_blend:
        raise RuntimeError('Bowl changes source coverage/blending; lower height for a fair A/B')
    source = ROOT.parents[2]/'kernels/srv/c66/core_generate_3dbowl.c'
    result.update(generator='TI svGenerate_3D_Bowl, unmodified C via host adapter',
                  generator_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  base_half_cells=args.base_half_cells,
                  base_half_mm=float(np.linalg.norm(centers[0]-centers[1])/100*args.base_half_cells),
                  height_max_mm=args.height_mm, height_min_mm=float(surface(grid).min()),
                  native_height_scale=scale, bowl_centers_ti_xy_mm=centers[:, :2].tolist(),
                  uses_same_blend_as_flat=same_blend,
                  lens_files=[str((base.LENS_ROOT/f'gmsl{c}_intrinsics.json').relative_to(ROOT.parent))
                              for c in (0, 1)],
                  artifact_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in stage.glob('bowl_*.bin')},
                  alignment_sha256=hashlib.sha256((ROOT/'alignment.json').read_bytes()).hexdigest())
    np.savez_compressed(stage/'ti_bowl_surface.npz', xyz=xyz, height_scale=scale)
    height_map = surface(grid).reshape(800, 640)
    cv2.imwrite(str(stage/'bowl_height.png'), cv2.applyColorMap(
        np.rint(height_map/args.height_mm*255).astype(np.uint8), cv2.COLORMAP_VIRIDIS))
    panels = []
    for mode, title in (('lens', 'FLAT'), ('bowl', 'TI BOWL')):
        panel = cv2.imread(str((ROOT if mode == 'lens' else stage)/f'{mode}_stitched.png'))
        if panel is None:
            raise RuntimeError(f'Missing {mode} preview; run rebuild.sh first')
        panel = cv2.copyMakeBorder(panel, 34, 0, 0, 0, cv2.BORDER_CONSTANT)
        cv2.putText(panel, title, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 1)
        panels.append(panel)
    cv2.imwrite(str(stage/'flat_vs_bowl.png'), np.concatenate(panels, axis=1))
    # Publish only validated artifacts; metadata is last so a partial update
    # cannot pass the launcher's hash check.
    for path in stage.iterdir():
        if path.is_file():
            path.replace(ROOT/path.name)
    (ROOT/'bowl_settings.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
