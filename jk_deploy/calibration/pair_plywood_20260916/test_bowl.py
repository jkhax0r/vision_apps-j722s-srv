#!/usr/bin/env python3
"""Check that the bowl comparison changes only the corrected source mapping."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

import make_bowl

ROOT = Path(__file__).resolve().parent


class BowlTests(unittest.TestCase):
    def test_invalid_generation_keeps_existing_files(self):
        with tempfile.TemporaryDirectory() as work:
            stage = Path(work)
            (stage/'captures').symlink_to(ROOT/'captures', target_is_directory=True)
            paths = list(ROOT.glob('bowl_*.bin'))+[ROOT/'bowl_settings.json']
            for source in paths+[ROOT/'alignment.json', ROOT/'settings.json']:
                shutil.copyfile(source, stage/source.name)
            (stage/'lens_blend.bin').write_bytes(b'intentionally incompatible blend')
            before = [(stage/p.name).read_bytes() for p in paths]
            result = subprocess.run([sys.executable, str(make_bowl.TOOLS/'make_bowl.py'),
                                     '--session', str(stage), '--height-mm', '50'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Bowl changes source coverage/blending', result.stderr)
            self.assertEqual(before, [(stage/p.name).read_bytes() for p in paths])

    def test_launcher_preflight(self):
        with tempfile.TemporaryDirectory() as work:
            stage = Path(work)
            launcher = stage/'run_gmsl_pair_calibrated.sh'
            shutil.copyfile(ROOT.parents[1]/launcher.name, launcher)
            cal = stage/'calibration/plywood_20260916'
            cal.mkdir(parents=True)
            for source in list(ROOT.glob('bowl_*.bin'))+[ROOT/'bowl_settings.json',
                                                       ROOT/'alignment.json', ROOT/'lens_blend.bin']:
                shutil.copyfile(source, cal/source.name)
            env = dict(os.environ, PAIR_WARP_MODE='bowl', PAIR_ALIGNMENT='plywood_20260916', PAIR_FULL_RES='1')
            def check():
                return subprocess.run(['bash', str(launcher), '--check'], env=env,
                                      capture_output=True, text=True)
            self.assertEqual(check().returncode, 0)
            alignment = cal/'alignment.json'
            alignment.write_bytes(alignment.read_bytes()+b'\n')
            result = check()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Stale or damaged', result.stderr)

    def test_geometry_and_blend(self):
        for suffix in ('mesh.bin', 'fullres_mesh.bin'):
            flat = np.fromfile(ROOT/f'lens_{suffix}', '<i2').reshape(4, 136, 136, 7)
            bowl = np.fromfile(ROOT/f'bowl_{suffix}', '<i2').reshape(flat.shape)
            np.testing.assert_array_equal(bowl[..., :3], flat[..., :3])
            np.testing.assert_array_equal(bowl[[0, 3]], flat[[0, 3]])
            self.assertFalse(np.array_equal(bowl[[1, 2], ..., 3:], flat[[1, 2], ..., 3:]))
            if suffix == 'fullres_mesh.bin':
                self.assertTrue(np.all((bowl[..., [3, 5]] >= 8) & (bowl[..., [3, 5]] <= 19192)))
                self.assertTrue(np.all((bowl[..., [4, 6]] >= 8) & (bowl[..., [4, 6]] <= 30712)))
        self.assertEqual((ROOT/'bowl_blend.bin').read_bytes(), (ROOT/'lens_blend.bin').read_bytes())
        weights = np.fromfile(ROOT/'bowl_blend.bin', 'u1').reshape(-1, 2).astype(int)
        self.assertTrue(np.all(weights.sum(1) == 255))

    def test_metadata_and_surface(self):
        settings = json.loads((ROOT/'bowl_settings.json').read_text())
        expected = dict(settings['artifact_sha256'], **{'alignment.json': settings['alignment_sha256']})
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), digest)
        self.assertEqual(settings['uncovered_fraction'], 0)
        _, models = make_bowl.load_models()  # Also checks both K/D against the separate lens fits.
        self.assertFalse(np.array_equal(models[0]['K'], models[1]['K']))
        xyz, _, surface = make_bowl.generate_surface(models, settings['base_half_cells'])
        saved = np.load(ROOT/'ti_bowl_surface.npz')
        np.testing.assert_array_equal(xyz, saved['xyz'])
        self.assertTrue(np.isfinite(xyz).all())
        self.assertEqual(xyz[..., 2].min(), 0)
        x, y = np.meshgrid(np.linspace(settings['x'], settings['x']+settings['width'], 640),
                           np.linspace(settings['y'], settings['y']+settings['height'], 800))
        height = surface(np.c_[x.ravel(), y.ravel()])*saved['height_scale']
        self.assertAlmostEqual(height.max(), settings['height_max_mm'])
        self.assertGreaterEqual(height.min(), 0)

    def test_zero_height_reproduces_flat(self):
        alignment, models = make_bowl.load_models()
        flat = next(s for s in alignment['settings'] if s['mode'] == 'lens')
        opts = SimpleNamespace(x=flat['x'], y=flat['y'], width=flat['width'],
                               feather=flat['feather_cells'], seam_x=flat['seam_x'])
        with tempfile.TemporaryDirectory() as work:
            stage = Path(work)
            (stage/'captures').symlink_to(ROOT/'captures', target_is_directory=True)
            make_bowl.base.ROOT = stage
            try:
                make_bowl.base.bake(models, 'lens', opts, surface_height=lambda xy: np.zeros(len(xy)))
                for suffix in ('mesh.bin', 'fullres_mesh.bin', 'blend.bin'):
                    self.assertEqual((ROOT/f'lens_{suffix}').read_bytes(),
                                     (stage/f'lens_{suffix}').read_bytes())
            finally:
                make_bowl.base.ROOT = ROOT


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path, default=ROOT)
    args, remaining = parser.parse_known_args()
    ROOT = make_bowl.ROOT = args.session.resolve()
    unittest.main(argv=[sys.argv[0], *remaining])
