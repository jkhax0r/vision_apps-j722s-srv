#!/usr/bin/env python3
"""Boot selection and non-interference with calibration regression tests."""
import fcntl
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from boot import run_boot


class BootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)

    def executable(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nexit 0\n')
        path.chmod(0o755)
        return path

    def test_latest_successful_calibration_selected(self):
        launcher = self.executable(self.runtime/'table_latest/run.sh')
        (self.runtime/'active_table_calibration.json').write_text(json.dumps({'launcher': str(launcher)}))
        with patch.object(run_boot, 'validate_candidate') as validate:
            self.assertEqual(run_boot.select_launcher(self.runtime), launcher)
            validate.assert_called_once_with(launcher.parent)

    def test_bad_current_calibration_does_not_silently_load_old(self):
        launcher = self.executable(self.runtime/'table_bad/run.sh')
        (self.runtime/'active_table_calibration.json').write_text(json.dumps({'launcher': str(launcher)}))
        with patch.object(run_boot, 'validate_candidate', side_effect=ValueError('Bad hashes')):
            with self.assertRaisesRegex(ValueError, 'Bad hashes'):
                run_boot.select_launcher(self.runtime)

    def test_outside_launcher_rejected(self):
        (self.runtime/'active_table_calibration.json').write_text('{"launcher":"/root/run.sh"}')
        with self.assertRaisesRegex(ValueError, 'outside'):
            run_boot.select_launcher(self.runtime)

    def test_initial_marker_preset_fallback(self):
        launcher = self.executable(self.runtime/'run_flex_markers.sh')
        cal = self.runtime/'grid_calibration_20260929_markers'
        cal.mkdir()
        for name in ('four_mesh.bin', 'four_blend.bin'):
            (cal/name).write_bytes(b'fixture')
        self.assertEqual(run_boot.select_launcher(self.runtime), launcher)

    def test_in_progress_calibration_is_never_interrupted(self):
        with (self.runtime/'calibration.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('sys.argv', ['run_boot', '--runtime', str(self.runtime)]), \
                    patch.object(run_boot, 'wait_display') as wait, \
                    patch.object(run_boot.subprocess, 'run') as command:
                run_boot.main()
            wait.assert_not_called()
            command.assert_not_called()

    def test_existing_live_renderer_is_not_restarted(self):
        with patch('sys.argv', ['run_boot', '--runtime', str(self.runtime)]), \
                patch.object(run_boot, 'wait_display'), \
                patch.object(run_boot, 'active', return_value=True), \
                patch.object(run_boot.subprocess, 'run') as command:
            run_boot.main()
        command.assert_called_once_with([str(self.runtime/'run_calibration_ui.sh')], check=True, timeout=10)

    def test_missing_initial_preset_and_nonexecutable_launcher_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No saved calibration'):
            run_boot.select_launcher(self.runtime)
        launcher = self.executable(self.runtime/'table_latest/run.sh')
        launcher.chmod(0o644)
        (self.runtime/'active_table_calibration.json').write_text(json.dumps({'launcher': str(launcher)}))
        with patch.object(run_boot, 'validate_candidate'), self.assertRaisesRegex(ValueError, 'executable'):
            run_boot.select_launcher(self.runtime)

    def test_display_wait_retries_temporary_timeout(self):
        result = subprocess.CompletedProcess([], 0, 'on screen:            0(0x0)')
        with patch.object(run_boot.subprocess, 'run', side_effect=[subprocess.TimeoutExpired('display', 3), result]), \
                patch.object(run_boot.time, 'sleep') as sleep:
            run_boot.wait_display()
        sleep.assert_called_once()

    def test_display_wait_has_deadline(self):
        with patch.object(run_boot.time, 'monotonic', side_effect=[0, 61]), \
                self.assertRaisesRegex(TimeoutError, 'systemd will retry'):
            run_boot.wait_display()

    def test_boot_starts_selected_calibration_then_controls(self):
        launcher = self.executable(self.runtime/'table/run.sh')
        with patch('sys.argv', ['run_boot', '--runtime', str(self.runtime)]), \
                patch.object(run_boot, 'wait_display'), \
                patch.object(run_boot, 'select_launcher', return_value=launcher), \
                patch.object(run_boot, 'active', side_effect=[False, True, True]), \
                patch.object(run_boot.subprocess, 'run') as command:
            run_boot.main()
        self.assertEqual(command.call_args_list[0].args[0], [str(launcher)])
        self.assertEqual(command.call_args_list[1].args[0], [str(self.runtime/'run_calibration_ui.sh')])

    def test_failed_boot_health_check_is_not_success(self):
        with patch('sys.argv', ['run_boot', '--runtime', str(self.runtime)]), \
                patch.object(run_boot, 'wait_display'), \
                patch.object(run_boot, 'active', side_effect=[True, False]), \
                patch.object(run_boot.subprocess, 'run'), \
                self.assertRaisesRegex(RuntimeError, 'did not start'):
            run_boot.main()

    def test_stop_orders_ui_cleanup_before_video_stop(self):
        with patch('sys.argv', ['run_boot', '--runtime', str(self.runtime), '--stop']), \
                patch.object(run_boot.subprocess, 'run') as command:
            run_boot.main()
        self.assertEqual(command.call_args_list[0].args[0], ['systemctl', 'stop', 'jk-calibration-ui.service'])
        self.assertEqual(command.call_args_list[1].args[0], [str(self.runtime/'run_flex_stitch.sh'), 'stop'])


if __name__ == '__main__':
    unittest.main()
