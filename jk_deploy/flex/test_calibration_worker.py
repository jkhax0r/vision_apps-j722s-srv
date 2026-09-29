#!/usr/bin/env python3
"""Exercise the on-device job controller without camera or systemd access."""
import json
import hashlib
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import subprocess

from ui import calibration_worker as worker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Target /tmp is a small tmpfs; synthetic fixtures do not need 3 GiB.
        space = patch.object(worker.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3))
        space.start()
        self.addCleanup(space.stop)
        self.tools = self.root/"tools"
        self.tools.mkdir()
        self.runtime = self.root/"runtime"
        self.runtime.mkdir()
        self.previous = self.runtime/"previous"
        self.previous.mkdir()
        self.job = self.root/"job"
        self.capture = self.tools/"capture_table_bursts.py"
        self.capture.write_text("print('pass01: test capture')\n")
        (self.tools/"check_calibration_markers.py").write_text(
            "import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text('{\"passed\":true}')\n")
        self.patch_wait = patch.object(worker, "wait_for_removal")
        self.wait = self.patch_wait.start()
        self.addCleanup(self.patch_wait.stop)
        self.calibrate = self.tools/"calibrate_repeated.py"
        self.success_script = ("import sys\nfrom pathlib import Path\np=Path(sys.argv[2]); p.mkdir()\n"
                               "(p/'report.json').write_text('{\"motion_warnings\":[]}')\n"
                               "print('Comparing calibration passes')\n")
        self.calibrate.write_text(self.success_script)
        self.launcher = self.runtime/"candidate.sh"
        self.launcher.write_text("#!/bin/sh\nexit 0\n")
        self.launcher.chmod(0o755)
        self.restore = self.runtime/"run_flex_stitch.sh"
        self.restore.write_text("#!/bin/sh\nprintf restored > \"$(dirname \"$0\")/restored\"\n")
        self.restore.chmod(0o755)
        self.patch_tools = patch.object(worker, "TOOLS", self.tools)
        self.patch_tools.start()
        self.addCleanup(self.patch_tools.stop)
        self.patch_preset = patch.object(worker, "current_preset", return_value=(self.previous, "0 1 2 3"))
        self.patch_preset.start()
        self.addCleanup(self.patch_preset.stop)
        self.patch_install = patch.object(worker, "install_candidate", return_value=self.launcher)
        self.install = self.patch_install.start()
        self.addCleanup(self.patch_install.stop)

    def run_job(self):
        code = worker.run_job(self.job, self.runtime, self.root/"python")
        return code, json.loads((self.job/"status.json").read_text())

    def test_success_applies_and_records_timings(self):
        code, status = self.run_job()
        self.assertEqual(code, 0)
        self.assertEqual(status["state"], "complete")
        self.assertEqual(set(status["timings_seconds"]), {
            "Capturing marked table", "Checking marked table", "Waiting for corner removal",
            "Capturing clear table", "Checking clear table", "Calculating marked reference",
            "Refining exposed corners", "Applying"})
        self.wait.assert_called_once()
        self.assertIn("--reference", status["commands"][-2])
        active = json.loads((self.runtime/"active_table_calibration.json").read_text())
        self.assertEqual(active["previous_preset"], str(self.previous))
        self.install.assert_called_once()

    def test_rejected_fit_never_installs(self):
        self.calibrate.write_text("import sys\nfrom pathlib import Path\np=Path(sys.argv[2]); p.mkdir()\n"
                                  "(p/'report.json').write_text('{\"reason\":\"Cameras moved\"}')\nraise SystemExit(1)\n")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertEqual(status["reason"], "Cameras moved")
        self.install.assert_not_called()
        self.assertFalse((self.runtime/"active_table_calibration.json").exists())

    def test_scientific_subprocesses_disable_broken_opencl(self):
        self.calibrate.write_text(self.success_script+"import os\nassert os.environ['OPENCV_OPENCL_RUNTIME']=='disabled'\n")
        code, _ = self.run_job()
        self.assertEqual(code, 0)

    def test_success_with_movement_applies_and_reports_warning(self):
        self.calibrate.write_text(self.success_script.replace('"motion_warnings":[]', '"motion_warnings":[{}]'))
        code, status = self.run_job()
        self.assertEqual(code, 0)
        self.assertEqual(status["state"], "complete")
        self.assertIn("Movement", status["warning"])
        self.assertEqual(status["motion_warning_count"], 1)
        self.install.assert_called_once()

    def test_apply_failure_restores_previous(self):
        self.launcher.write_text("#!/bin/sh\nexit 1\n")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertEqual(status["state"], "failed")
        self.assertTrue((self.runtime/"restored").exists())
        self.assertFalse((self.runtime/"active_table_calibration.json").exists())

    def test_capture_restore_failure_retries_previous(self):
        self.capture.write_text("import sys\nfrom pathlib import Path\np=Path(sys.argv[1]); p.mkdir()\n"
                                "(p/'burst_manifest.json').write_text('{\"resume_error\":\"timeout\"}')\nraise SystemExit(1)\n")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertTrue((self.runtime/"restored").exists())
        self.install.assert_not_called()

    def test_failed_restore_is_not_hidden(self):
        self.launcher.write_text("#!/bin/sh\nexit 1\n")
        self.restore.write_text("#!/bin/sh\nexit 1\n")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertIn("Restoring previous calibration failed", status["restore_error"])

    def test_existing_job_is_not_overwritten(self):
        self.job.mkdir()
        with self.assertRaises(FileExistsError):
            self.run_job()
        self.install.assert_not_called()

    def test_cancelling_removal_prompt_keeps_previous_calibration(self):
        self.wait.side_effect = KeyboardInterrupt("Cancelled")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertEqual(status["state"], "cancelled")
        self.assertIsNone(status["waiting_action"])
        self.assertEqual(len(status["commands"]), 2)
        self.install.assert_not_called()

    def test_failed_marker_check_does_not_prompt_or_capture_clear_stage(self):
        (self.tools/"check_calibration_markers.py").write_text(
            "import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text('{\"reason\":\"Missing marker\"}')\nraise SystemExit(1)\n")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertEqual(status["reason"], "Missing marker")
        self.wait.assert_not_called()
        self.install.assert_not_called()

    def test_second_capture_restore_failure_retries_previous(self):
        self.capture.write_text("import sys\nfrom pathlib import Path\np=Path(sys.argv[1])\n"
                                "if p.name=='raw_clear':\n p.mkdir()\n"
                                " (p/'burst_manifest.json').write_text('{\"resume_error\":\"timeout\"}')\n raise SystemExit(1)\n")
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertTrue((self.runtime/"restored").exists())
        self.install.assert_not_called()

    def test_invalid_candidate_cannot_change_runtime(self):
        with patch.object(worker, "validate_candidate", side_effect=ValueError("Bad hashes")):
            self.patch_install.stop()
            with self.assertRaisesRegex(ValueError, "Bad hashes"):
                worker.install_candidate(self.root/"result", self.runtime, "test")
        self.assertFalse((self.runtime/"table_test").exists())

    def test_low_disk_space_leaves_current_calibration_alone(self):
        with patch.object(worker.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024)):
            code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertIn('GiB', status['reason'])
        self.install.assert_not_called()

    def test_install_failure_never_attempts_launch(self):
        self.install.side_effect = OSError('No space left on device')
        code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertNotIn('Applying', status['timings_seconds'])
        self.assertFalse((self.runtime/'restored').exists())

    def test_pointer_write_failure_restores_preview_and_old_boot_selection(self):
        pointer = self.runtime/'active_table_calibration.json'
        previous = b'{"launcher":"previous/run.sh"}\n'
        original = worker.atomic_json
        for after_replace in (False, True):
            with self.subTest(after_replace=after_replace):
                self.job = self.root/f'write_failure_{after_replace}'
                pointer.write_bytes(previous)
                def fail_pointer(path, value, **kwargs):
                    if path == pointer:
                        if after_replace:
                            original(path, value)
                        raise OSError('Injected disk failure')
                    return original(path, value, **kwargs)
                with patch.object(worker, 'atomic_json', side_effect=fail_pointer):
                    code, status = self.run_job()
                self.assertEqual(code, 1)
                self.assertEqual(pointer.read_bytes(), previous)
                self.assertTrue((self.runtime/'restored').exists())
                self.assertNotIn('restore_error', status)

    def test_failed_first_boot_pointer_commit_removes_new_pointer(self):
        pointer = self.runtime/'active_table_calibration.json'
        original = worker.atomic_json
        def fail_pointer(path, value, **kwargs):
            original(path, value, **kwargs)
            if path == pointer:
                raise OSError('Injected post-rename failure')
        with patch.object(worker, 'atomic_json', side_effect=fail_pointer):
            code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertFalse(pointer.exists())
        self.assertTrue((self.runtime/'restored').exists())

    def test_completion_status_failure_does_not_undo_committed_calibration(self):
        original = worker.atomic_json
        def fail_completion(path, value, **kwargs):
            if path.name == 'status.json' and value.get('state') == 'complete':
                raise OSError('Injected status failure')
            return original(path, value, **kwargs)
        with patch.object(worker, 'atomic_json', side_effect=fail_completion):
            code, status = self.run_job()
        self.assertEqual(code, 0)
        self.assertFalse((self.runtime/'restored').exists())
        active = json.loads((self.runtime/'active_table_calibration.json').read_text())
        self.assertEqual(active['job'], str(self.job))

    def test_cancel_during_apply_restores_preview(self):
        original = worker.subprocess.Popen
        def interrupt_apply(args, **kwargs):
            if args == [str(self.launcher)]:
                raise KeyboardInterrupt('Cancelled')
            return original(args, **kwargs)
        with patch.object(worker.subprocess, 'Popen', side_effect=interrupt_apply):
            code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertEqual(status['state'], 'cancelled')
        self.assertTrue((self.runtime/'restored').exists())

    def test_retry_reprocesses_without_capture_or_prompt(self):
        source = self.root/'saved'
        with patch.object(worker, 'saved_capture_source', return_value=source):
            code = worker.run_job(self.job, self.runtime, self.root/'python', reuse=source)
        status = json.loads((self.job/'status.json').read_text())
        self.assertEqual(code, 0)
        self.wait.assert_not_called()
        self.assertEqual(len(status['commands']), 3)
        self.assertIn(str(source/'raw'), status['commands'][0])
        self.assertIn(str(source/'raw_clear'), status['commands'][1])

    def test_invalid_retry_cannot_start_processing(self):
        with patch.object(worker, 'saved_capture_source', side_effect=ValueError('Truncated capture')):
            code = worker.run_job(self.job, self.runtime, self.root/'python', reuse=self.root/'saved')
        status = json.loads((self.job/'status.json').read_text())
        self.assertEqual(code, 1)
        self.assertNotIn('commands', status)
        self.install.assert_not_called()

    def test_timed_out_child_is_terminated_and_does_not_apply(self):
        self.capture.write_text('import time\ntime.sleep(30)\n')
        popen = worker.subprocess.Popen
        children = []
        def track(*args, **kwargs):
            process = popen(*args, **kwargs)
            children.append(process)
            return process
        with patch.object(worker.time, 'monotonic', side_effect=itertools.count(0, 1000)), \
                patch.object(worker.subprocess, 'Popen', side_effect=track):
            code, status = self.run_job()
        self.assertEqual(code, 1)
        self.assertIn('exceeded', status['reason'])
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.install.assert_not_called()


class RemovalWaitTests(unittest.TestCase):
    def test_waits_for_explicit_confirmation_and_clears_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary)
            updates = []
            def acknowledge(_):
                (job/'corners_removed.json').write_text('{"action":"corners_removed"}')
            with patch.object(worker.time, 'sleep', side_effect=acknowledge):
                worker.wait_for_removal(job, lambda *a, **kw: updates.append((a, kw)))
            self.assertEqual(updates[0][1]['waiting_action'], 'remove_corners')
            self.assertIsNone(updates[-1][1]['waiting_action'])

    def test_timeout_and_invalid_acknowledgement_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary)
            with self.assertRaises(TimeoutError):
                worker.wait_for_removal(job, lambda *a, **kw: None, timeout=-1)
            (job/'corners_removed.json').write_text('{"action":"wrong"}')
            with self.assertRaisesRegex(ValueError, 'Invalid'):
                worker.wait_for_removal(job, lambda *a, **kw: None)


class CandidateStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.result = self.root/'result'
        self.result.mkdir()
        self.runtime = self.root/'runtime'
        self.runtime.mkdir()
        hashes = {}
        for name, size in (('four_mesh.bin', 4*136*136*7*2), ('four_blend.bin', 4*136*136*2)):
            data = bytes(size)
            (self.result/name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        (self.result/'calibration.json').write_text(json.dumps(dict(schema_version=2, capture_order=[0, 1, 2, 3], sha256=hashes)))
        (self.result/'report.json').write_text(json.dumps(dict(status='passed', capture_order=[0, 1, 2, 3], artifact_sha256=hashes)))
        (self.result/'camera_order.txt').write_text('0 1 2 3\n')

    def test_install_publishes_valid_snapshot_without_replacing_existing(self):
        launcher = worker.install_candidate(self.result, self.runtime, 'test')
        worker.validate_candidate(launcher.parent)
        self.assertTrue(launcher.stat().st_mode & 0o111)
        self.assertFalse(list(self.runtime.glob('.cal-candidate-*')))
        with self.assertRaises(FileExistsError):
            worker.install_candidate(self.result, self.runtime, 'test')

    def test_partial_copy_and_fsync_failure_never_publish(self):
        for operation in ('copy2', 'fsync'):
            with self.subTest(operation=operation):
                target = worker.shutil if operation == 'copy2' else worker.os
                with patch.object(target, operation, side_effect=OSError('Injected storage fault')):
                    with self.assertRaises(OSError):
                        worker.install_candidate(self.result, self.runtime, 'failed')
                self.assertFalse((self.runtime/'table_failed').exists())
                self.assertFalse(list(self.runtime.glob('.cal-candidate-*')))

    def test_corrupted_copied_artifact_rejected_before_publish(self):
        copy = worker.shutil.copy2
        def corrupt(source, destination):
            result = copy(source, destination)
            if source.name == 'four_mesh.bin':
                destination.write_bytes(b'corrupt')
            return result
        with patch.object(worker.shutil, 'copy2', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'artifact'):
                worker.install_candidate(self.result, self.runtime, 'failed')
        self.assertFalse((self.runtime/'table_failed').exists())
        self.assertFalse(list(self.runtime.glob('.cal-candidate-*')))

    def test_failed_atomic_file_sync_keeps_old_pointer(self):
        pointer = self.runtime/'active.json'
        pointer.write_text('old')
        with patch.object(worker.os, 'fsync', side_effect=OSError('Injected fsync fault')):
            with self.assertRaises(OSError):
                worker.atomic_json(pointer, {'new': True}, durable=True)
        self.assertEqual(pointer.read_text(), 'old')

    def test_current_preset_uses_service_environment_and_checks_order(self):
        response = subprocess.CompletedProcess([], 0, stdout=f'APP_SRV_FOUR_LUT={self.result}/four_mesh.bin')
        with patch.object(worker.subprocess, 'run', return_value=response):
            self.assertEqual(worker.current_preset(self.runtime), (self.result, '0 1 2 3'))
            (self.result/'camera_order.txt').write_text('0 0 2 3')
            with self.assertRaisesRegex(ValueError, 'camera order'):
                worker.current_preset(self.runtime)
            (self.result/'four_mesh.bin').unlink()
            with self.assertRaisesRegex(ValueError, 'working calibration'):
                worker.current_preset(self.runtime)


if __name__ == "__main__":
    unittest.main()
