#!/usr/bin/env python3
"""Full-LCD table projection using the saved physical poses and lens models."""
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'pair_plywood_20260916'))
import make_bowl


def setup():
    make_bowl.ROOT = ROOT
    alignment, models = make_bowl.load_models()
    bounds = json.loads((ROOT/'table_bounds.json').read_text())
    side = bounds['side_mm']/alignment['square_mm']
    if bounds['fit'] == 'fill':
        left, right = bounds.get('side_inset_cells', [0, 0])
        if not (np.isfinite([left, right]).all() and min(left, right) >= 0 and left+right < side):
            raise ValueError('Side insets must be finite, nonnegative and leave a positive width')
        width = side-left-right
        view = [bounds['left_cell']+left, bounds['far_cell'], width, width/1.6]
    elif bounds['fit'] == 'contain':
        view = [bounds['left_cell']-.3*side, bounds['far_cell'], side*1.6, side]
    else:
        raise ValueError('Table fit must be fill or contain')
    bounds['side_cells'] = side
    bounds['view_cells'] = view
    flat = next(s for s in alignment['settings'] if s['mode'] == 'lens')
    bowl = json.loads((ROOT/'bowl_settings.json').read_text())
    _, _, height = make_bowl.generate_surface(models, bowl['base_half_cells'])
    return models, bounds, flat, lambda grid: height(grid)*bowl['native_height_scale']


def mapping(models, bounds, flat, height, uv, mode):
    x, y, w, h = bounds['view_cells']
    world = uv*[w, h]+[x, y]
    on_table = ((world[:, 0] >= bounds['left_cell']) &
                (world[:, 0] <= bounds['left_cell']+bounds['side_cells']) &
                (world[:, 1] >= bounds['far_cell']) &
                (world[:, 1] <= bounds['far_cell']+bounds['side_cells']))
    # Contain-mode side margins are masked and need no bowl extrapolation.
    bounded = np.clip(world, [bounds['left_cell'], bounds['far_cell']],
                      [bounds['left_cell']+bounds['side_cells'], bounds['far_cell']+bounds['side_cells']])
    z = height(bounded) if mode == 'bowl' else np.zeros(len(world))
    sources, valid = [], []
    for m in models:
        grid = (world-m['shift'])@m['rotation']
        source = make_bowl.base.project(m, grid, height_mm=z)
        camera = (make_bowl.base.objects(grid, z).reshape(-1, 3)@
                  cv2.Rodrigues(m['pose'][:3])[0].T+m['pose'][3:])
        # Unlike the tight comparison crop, the table extends past detected
        # corner hulls. Extrapolate the calibrated plane, but never the image.
        inside = on_table & (camera[:, 2] > 0) & np.isfinite(source).all(1)
        inside &= (source[:, 0] >= 0) & (source[:, 0] <= 1919)
        inside &= (source[:, 1] >= 0) & (source[:, 1] <= 1199)
        sources.append(source)
        valid.append(inside)
    alpha = np.clip(.5-(world[:, 0]-flat['seam_x'])/flat['feather_cells'], 0, 1)
    alpha = np.where(~valid[1], 1, alpha)
    alpha = np.where(~valid[0], 0, alpha)
    weights = np.c_[alpha, 1-alpha]
    weights[~(valid[0] | valid[1])] = 0
    return sources, weights, on_table, z


def bake(models, bounds, flat, height, mode):
    meshes, native_meshes, blends = [], [], []
    for q in range(4):
        x, y = np.meshgrid(np.linspace(0, 1, 136), np.linspace(0, 1, 136))
        uv = np.c_[x.ravel(), y.ravel()]*.5+[0 if q in (0, 3) else .5, 0 if q in (0, 1) else .5]
        sources, weights, _, _ = mapping(models, bounds, flat, height, uv, mode)
        mesh = np.zeros((len(uv), 7), dtype='<i2')
        mesh[:, 0] = np.rint(uv[:, 0]*1080-540)
        mesh[:, 1] = np.rint(540-uv[:, 1]*1080)
        native = mesh.copy()
        for offset, source in ((3, sources[1]), (5, sources[0])):
            small = source/3+[0, 40]
            mesh[:, offset] = np.rint(np.clip(small[:, 1], 0, 479)*16)
            mesh[:, offset+1] = np.rint(np.clip(small[:, 0], 0, 639)*16)
            pixel = [1919, 1199]-np.clip(source, [0, 0], [1919, 1199])+.5
            native[:, offset] = np.rint(pixel[:, 1]*16)
            native[:, offset+1] = np.rint(pixel[:, 0]*16)
        weight0 = np.rint(weights[:, 1]*255).astype('u1')
        weight1 = np.where(weights.sum(1) > 0, 255-weight0, 0).astype('u1')
        meshes.append(mesh)
        native_meshes.append(native)
        blends.append(np.c_[weight0, weight1])
    np.concatenate(meshes).tofile(ROOT/f'{mode}_table_mesh.bin')
    np.concatenate(native_meshes).tofile(ROOT/f'{mode}_table_fullres_mesh.bin')
    np.concatenate(blends).tofile(ROOT/f'{mode}_table_blend.bin')
    x, y = np.meshgrid(np.linspace(0, 1, 1280), np.linspace(0, 1, 800))
    uv = np.c_[x.ravel(), y.ravel()]
    sources, weights, on_table, z = mapping(models, bounds, flat, height, uv, mode)
    preview = np.zeros((800, 1280, 3), dtype=float)
    for camera, source in enumerate(sources):
        image = cv2.imread(str(ROOT/f'captures/gmsl{camera}.png'))
        image = cv2.remap(image, source[:, 0].reshape(800, 1280).astype('float32'),
                          source[:, 1].reshape(800, 1280).astype('float32'), cv2.INTER_LINEAR)
        preview += image*weights[:, camera].reshape(800, 1280, 1)
    cv2.imwrite(str(ROOT/f'{mode}_table_preview.png'), preview.clip(0, 255).astype('u1'))
    return dict(mode=mode, uncovered_table_fraction=float(np.mean(weights.sum(1)[on_table] == 0)),
                height_max_mm=float(z[on_table].max()))


def main():
    models, bounds, flat, height = setup()
    results = [bake(models, bounds, flat, height, mode) for mode in ('lens', 'bowl')]
    manifest = dict(bounds=bounds, modes=results, width=1280, height=800,
                    seam_x=flat['seam_x'], feather_cells=flat['feather_cells'],
                    hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            [ROOT/'alignment.json', ROOT/'table_bounds.json', ROOT/'bowl_settings.json',
                             *sorted(ROOT.glob('*_table_*.bin'))]})
    (ROOT/'table_settings.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
