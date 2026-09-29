"""Validate retry eligibility without reading or allocating full camera frames."""
import json
from pathlib import Path
import tempfile
import unittest

from ui.capture_recovery import saved_capture_source


def saved_job(root):
    job = root/'20260929T210046Z_test'
    job.mkdir()
    (job/'status.json').write_text('{"state":"failed","phase":"Calibration not applied"}')
    (job/'corners_removed.json').write_text('{"action":"corners_removed"}')
    for name in ('marked_check.json', 'clear_check.json'):
        (job/name).write_text('{"passed":true}')
    for stage in ('raw', 'raw_clear'):
        directory = job/stage
        directory.mkdir()
        manifest = dict(schema_version=1, status='complete', frames_per_burst=6,
                        width=1920, height=1200, format='UYVY',
                        passes=[dict(directory=f'pass{i+1:02d}') for i in range(3)])
        (directory/'burst_manifest.json').write_text(json.dumps(manifest))
        for row in manifest['passes']:
            path = directory/row['directory']
            path.mkdir()
            for camera in range(4):
                with (path/f'input{camera}.uyvy').open('wb') as stream:
                    stream.truncate(6*1920*1200*2)
    return job


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.job = saved_job(self.root)

    def test_complete_capture_and_retry_of_retry_resolve_original(self):
        self.assertEqual(saved_capture_source(self.job), self.job)
        retry = self.root/'retry'
        retry.mkdir()
        (retry/'status.json').write_text(json.dumps(dict(capture_source=str(self.job))))
        self.assertEqual(saved_capture_source(retry), self.job)

    def test_missing_confirmation_rejected(self):
        (self.job/'corners_removed.json').unlink()
        with self.assertRaises(OSError):
            saved_capture_source(self.job)

    def test_invalid_checks_rejected(self):
        for content in ('{}', '[]', '{"passed":false}', '{"passed":1}', 'broken'):
            with self.subTest(content=content):
                (self.job/'clear_check.json').write_text(content)
                with self.assertRaises(ValueError):
                    saved_capture_source(self.job)

    def test_manifest_errors_rejected(self):
        path = self.job/'raw_clear/burst_manifest.json'
        original = json.loads(path.read_text())
        for values in (dict(status='failed'), dict(simulated_input=True), dict(frames_per_burst=0),
                       dict(frames_per_burst=True), dict(width=1280), dict(passes=None),
                       dict(passes=[None]), dict(passes=[{}]*3),
                       dict(passes=[dict(directory='../escape')]*3)):
            with self.subTest(values=values):
                path.write_text(json.dumps(dict(original, **values)))
                with self.assertRaises(ValueError):
                    saved_capture_source(self.job)

    def test_truncated_frame_rejected(self):
        (self.job/'raw_clear/pass03/input3.uyvy').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'truncated'):
            saved_capture_source(self.job)

    def test_external_symlink_rejected(self):
        raw = self.job/'raw/pass01/input0.uyvy'
        raw.rename(self.root/'outside.uyvy')
        raw.symlink_to(self.root/'outside.uyvy')
        with self.assertRaises(ValueError):
            saved_capture_source(self.job)

    def test_external_source_rejected(self):
        (self.job/'status.json').write_text('{"capture_source":"/somewhere/else"}')
        with self.assertRaisesRegex(ValueError, 'same jobs'):
            saved_capture_source(self.job)

    def test_invalid_status_rejected(self):
        (self.job/'status.json').write_text('[]')
        with self.assertRaises(ValueError):
            saved_capture_source(self.job)


if __name__ == '__main__':
    unittest.main()
