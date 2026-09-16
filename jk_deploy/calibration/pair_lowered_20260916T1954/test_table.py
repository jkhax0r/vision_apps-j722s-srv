#!/usr/bin/env python3
"""Check full-screen table LUTs, missing-camera masks and launcher selection."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

import make_table

ROOT = Path(__file__).resolve().parent


class TableTests(unittest.TestCase):
    def test_fullscreen_mesh_and_quadrant_boundaries(self):
        for mode in ('lens', 'bowl'):
            mesh = np.fromfile(ROOT/f'{mode}_table_fullres_mesh.bin', '<i2').reshape(4, 136, 136, 7)
            small = np.fromfile(ROOT/f'{mode}_table_mesh.bin', '<i2').reshape(mesh.shape)
            old = np.fromfile(ROOT/f'{mode}_fullres_mesh.bin', '<i2').reshape(mesh.shape)
            weights = np.fromfile(ROOT/f'{mode}_table_blend.bin', 'u1').reshape(4, 136, 136, 2)
            np.testing.assert_array_equal(mesh[..., :3], small[..., :3])
            np.testing.assert_array_equal(mesh[..., :3], old[..., :3])
            self.assertTrue(np.all((mesh[..., [3, 5]] >= 8) & (mesh[..., [3, 5]] <= 19192)))
            self.assertTrue(np.all((mesh[..., [4, 6]] >= 8) & (mesh[..., [4, 6]] <= 30712)))
            self.assertTrue(np.isin(weights.astype(int).sum(-1), [0, 255]).all())
            for q in (0, 3):
                self.assertFalse(np.array_equal(mesh[q], old[q]))
            for data in (mesh, weights):
                np.testing.assert_array_equal(data[0, :, -1], data[1, :, 0])
                np.testing.assert_array_equal(data[3, :, -1], data[2, :, 0])
                np.testing.assert_array_equal(data[0, -1], data[3, 0])
                np.testing.assert_array_equal(data[1, -1], data[2, 0])

    def test_floor_geometry_and_blind_area(self):
        models, bounds, flat, height = make_table.setup()
        self.assertAlmostEqual(bounds['view_cells'][2]/bounds['view_cells'][3], 1.6)
        self.assertAlmostEqual(bounds['side_cells']*make_table.make_bowl.base.PITCH, 1219.2)
        sources, weights, _, z = make_table.mapping(models, bounds, flat, height,
                                                   np.array([[.5, .3], [.5, 1]]), 'lens')
        np.testing.assert_array_equal(z, 0)
        self.assertAlmostEqual(weights[0].sum(), 1)
        self.assertEqual(weights[1].sum(), 0)  # Neither camera sees the near-center area.
        mesh = np.fromfile(ROOT/'lens_table_fullres_mesh.bin', '<i2').reshape(4, 136, 136, 7)
        uv = np.array([[67/135*.5, 67/135*.5]])
        sources, _, _, _ = make_table.mapping(models, bounds, flat, height, uv, 'lens')
        for camera, offset in ((1, 3), (0, 5)):
            native = ([1919, 1199]-np.clip(sources[camera][0], [0, 0], [1919, 1199])+.5)*16
            np.testing.assert_array_equal(mesh[0, 67, 67, offset:offset+2], np.rint(native[::-1]))

    def test_manifest(self):
        manifest = json.loads((ROOT/'table_settings.json').read_text())
        for name, digest in manifest['hashes'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), digest)
        for mode in manifest['modes']:
            limit = .10 if manifest['bounds']['fit'] == 'fill' else .40
            self.assertLess(mode['uncovered_table_fraction'], limit)

    def test_whole_table_margins(self):
        models, bounds, flat, height = make_table.setup()
        side = bounds['side_cells']
        bounds['view_cells'] = [bounds['left_cell']-.3*side, bounds['far_cell'], side*1.6, side]
        for mode in ('lens', 'bowl'):
            _, weights, on_table, z = make_table.mapping(
                models, bounds, flat, height, np.array([[0, 0], [1, 0], [0, 1], [1, 1]]), mode)
            self.assertFalse(on_table.any())
            self.assertTrue(np.isfinite(z).all())
            np.testing.assert_array_equal(weights, 0)

    def test_launcher(self):
        with tempfile.TemporaryDirectory() as work:
            stage = Path(work)
            launcher = stage/'run_gmsl_pair_calibrated.sh'
            shutil.copyfile(ROOT.parents[1]/launcher.name, launcher)
            cal = stage/'calibration/lowered_20260916T1954'
            cal.mkdir(parents=True)
            for source in [*ROOT.glob('*.bin'), *ROOT.glob('*.json')]:
                shutil.copyfile(source, cal/source.name)
            env = dict(os.environ, PAIR_ALIGNMENT='lowered_20260916T1954', PAIR_FULL_RES='1')
            def check(mode='lens', layout='auto'):
                return subprocess.run(['bash', str(launcher), '--check'], capture_output=True,
                                      text=True, env=dict(env, PAIR_WARP_MODE=mode, PAIR_LAYOUT=layout))
            for mode in ('lens', 'bowl'):
                result = check(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('layout=table', result.stdout)
            self.assertIn('layout=split', check(layout='split').stdout)
            self.assertIn('layout=split', check(mode='measured').stdout)
            (cal/'table_bounds.json').write_text('{}')
            result = check()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Stale or damaged table mapping', result.stderr)


if __name__ == '__main__':
    unittest.main()
