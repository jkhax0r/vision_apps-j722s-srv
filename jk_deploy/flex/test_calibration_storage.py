import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calibration_storage import cleanup_calibrations


class StorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.jobs = self.root/'jobs'
        self.runtime = self.root/'runtime'
        self.jobs.mkdir()
        self.runtime.mkdir()
        self.names = [f'20260929T12000{i}Z_abcdef' for i in range(5)]
        for name in self.names:
            job = self.jobs/name
            job.mkdir()
            (job/'status.json').write_text('{}')
            (job/'raw').mkdir()
            (job/'raw/frame').write_bytes(b'frame')
            preset = self.runtime/('table_'+name)
            preset.mkdir()
            (preset/'four_mesh.bin').write_bytes(b'mesh')
        self.current = self.runtime/('table_'+self.names[2])
        self.previous = self.runtime/('table_'+self.names[1])
        (self.runtime/'active_table_calibration.json').write_text(json.dumps(dict(
            launcher=str(self.current/'run.sh'), previous_preset=str(self.previous),
            job=str(self.jobs/self.names[2]))))

    def clean(self, protect=()):
        return cleanup_calibrations(self.jobs, self.runtime, self.current, protect)

    def test_new_cal_discards_old_retry_and_captures_keeps_installed_results(self):
        new = self.jobs/self.names[4]
        result = self.clean([new])
        self.assertFalse(result['errors'])
        self.assertFalse((self.jobs/self.names[0]).exists())
        self.assertFalse((self.jobs/self.names[3]).exists())
        for index in (1, 2):
            self.assertTrue((self.jobs/self.names[index]/'status.json').exists())
            self.assertFalse((self.jobs/self.names[index]/'raw').exists())
            self.assertTrue((self.runtime/('table_'+self.names[index])/'four_mesh.bin').exists())
        self.assertTrue((new/'raw/frame').exists())
        self.assertFalse((self.runtime/('table_'+self.names[0])).exists())
        self.clean([new])  # Idempotent.

    def test_explicit_retry_protects_only_requested_capture(self):
        source = self.jobs/self.names[0]
        self.clean([source])
        self.assertTrue((source/'raw/frame').exists())
        self.assertFalse((self.jobs/self.names[3]).exists())

    def test_unknown_and_symlink_paths_are_not_followed(self):
        unknown = self.jobs/'personal'
        unknown.mkdir()
        external = self.root/'external'
        external.mkdir()
        (external/'keep').write_text('keep')
        (self.jobs/'20260929T120009Z_abcdef').symlink_to(external)
        (self.jobs/self.names[0]/'link').symlink_to(external)
        self.clean()
        self.assertTrue((external/'keep').exists())
        self.assertTrue(unknown.exists())

    def test_bad_pointer_fails_before_deletion(self):
        (self.runtime/'active_table_calibration.json').write_text('{}')
        with self.assertRaises(KeyError):
            self.clean()
        self.assertTrue((self.jobs/self.names[0]/'raw/frame').exists())

    def test_external_pointer_fails_before_deletion(self):
        pointer = self.runtime/'active_table_calibration.json'
        value = json.loads(pointer.read_text())
        value['previous_preset'] = str(self.root/'outside')
        pointer.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.clean()
        self.assertTrue((self.jobs/self.names[0]).exists())

    def test_mount_fails_before_any_deletion(self):
        mounted = self.jobs/self.names[3]/'raw'
        with patch.object(Path, 'is_mount', lambda p: p == mounted):
            with self.assertRaises(ValueError):
                self.clean()
        self.assertTrue((self.jobs/self.names[0]).exists())

    def test_delete_error_reported_and_other_jobs_still_cleaned(self):
        import shutil
        original = shutil.rmtree
        bad = self.jobs/self.names[0]
        def remove(path):
            if path == bad:
                raise PermissionError('test')
            original(path)
        with patch('calibration_storage.shutil.rmtree', side_effect=remove):
            result = self.clean()
        self.assertEqual(len(result['errors']), 1)
        self.assertFalse((self.jobs/self.names[3]).exists())
