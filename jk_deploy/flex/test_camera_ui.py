"""Qt hit-testing with fake cameras; run on the target or a PySide6 workstation."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HAVE_QT = importlib.util.find_spec('PySide6') is not None
UI = Path(os.environ.get('JK_UI_DIR', Path(__file__).parent/'ui'))
if HAVE_QT:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('QT_QUICK_BACKEND', 'software')
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
    from PySide6.QtCore import QObject, QPoint, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest
    import shiboken6
    sys.path.insert(0, str(UI))
    from calibration_ui import Backend
    from camera_settings import CameraSettings
    from preview import Preview
    from camera_controls import parse_controls
    from test_camera_controls import CONTROL_TEXT
    from test_capture_recovery import saved_job

    class FakeCameras(CameraSettings):
        def __init__(self, calibration):
            super().__init__(Path('/unused'), calibration)
            self.rows = [dict(identity=f'{0x39+i:04x}', entity=f'tevs {i}', video=f'/dev/video{i+2}',
                              label=f'Camera {i+1}', controls=json.loads(json.dumps(parse_controls(CONTROL_TEXT))))
                         for i in range(4)]
            self.commands = []

        def command(self, action, *args):
            self.commands.append((action, args))
            if action == 'set':
                fields = dict(zip(args[::2], args[1::2]))
                for row in self.rows:
                    if fields['--sensor'] in ('all', row['identity']):
                        for name, value in json.loads(fields['--updates']).items():
                            row['controls'][name]['value'] = value
            self.changed.emit()


@unittest.skipUnless(HAVE_QT, 'PySide6 unavailable; execute these tests on Flex')
class CameraUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cal = Backend(SimpleNamespace(runtime=self.root, jobs=self.root/'jobs', support=self.root/'support'))
        self.cameras = FakeCameras(self.cal)
        self.preview = Preview(Path(self.temporary.name)/'preview.state')
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty('calibration', self.cal)
        self.engine.rootContext().setContextProperty('cameraSettings', self.cameras)
        self.engine.rootContext().setContextProperty('preview', self.preview)
        self.engine.load(str(UI/'Calibration.qml'))
        self.assertTrue(self.engine.rootObjects())
        self.window = self.engine.rootObjects()[0]
        QTest.qWait(150)

    def tearDown(self):
        if self.cal.busy:
            self.cal.process.terminate()
            self.cal.process.waitForFinished(3000)
        shiboken6.delete(self.engine)
        self.cal.timer.stop()
        QTest.qWait(50)

    def item(self, name):
        item = self.window.findChild(QObject, name)
        self.assertIsNotNone(item, name)
        return item

    def tap(self, name):
        item = self.item(name)
        center = item.mapToScene(item.boundingRect().center())
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, center.toPoint())
        QTest.qWait(150)

    def open_settings(self):
        self.tap('calButton')
        self.assertTrue(self.window.property('toolsVisible'))
        self.tap('settingsMenu')
        self.assertTrue(self.window.property('settingsVisible'))

    def choose(self, name, index):
        self.tap(name)
        # All Basic-style menu delegates are 40px high on this target.
        item = self.item(name)
        origin = item.mapToScene(item.boundingRect().bottomLeft())
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier,
                         QPoint(int(origin.x()+60), int(origin.y()+20+40*index)))
        QTest.qWait(150)

    def test_recalibration_requires_confirmation(self):
        self.tap('calButton'); self.tap('recalibrateMenu')
        self.assertTrue(self.window.property('confirmationVisible'))
        self.assertFalse(self.cal.busy)
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(961, 448))
        QTest.qWait(100)
        self.assertFalse(self.window.property('confirmationVisible'))

    def test_manual_mode_enables_shutter_and_gain(self):
        self.open_settings()
        self.assertFalse(self.item('exposureSlider').isEnabled())
        self.choose('exposureMode', 2)
        self.assertEqual(self.cameras.controls['exposure_mode']['value'], 0)
        self.assertTrue(self.item('exposureSlider').isEnabled())
        self.assertTrue(self.item('gainSlider').isEnabled())
        self.assertFalse(self.item('ae_exposure_maxSlider').isEnabled())

    def test_camera_selection_and_brightness_slider(self):
        self.open_settings(); self.choose('cameraSelector', 2)
        self.assertEqual(self.cameras.selected, 2)
        slider = self.item('brightnessSlider')
        corner = slider.mapToScene(slider.boundingRect().topLeft())
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier,
                         QPoint(int(corner.x()+slider.width()*.7), int(corner.y()+slider.height()/2)))
        QTest.qWait(150)
        self.assertNotEqual(self.cameras.rows[2]['controls']['brightness']['value'], 4096)
        self.assertEqual([r['controls']['brightness']['value'] for r in self.cameras.rows[:2]], [4096, 4096])

    def test_apply_to_all(self):
        self.open_settings(); self.tap('allCameras'); self.choose('exposureMode', 2)
        self.assertEqual([r['controls']['exposure_mode']['value'] for r in self.cameras.rows], [0]*4)

    def tap_position(self, x, y):
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))
        QTest.qWait(100)

    def test_each_preview_expands_and_returns_to_quad(self):
        for camera, point in enumerate(((240, 180), (720, 180), (240, 540), (720, 540))):
            self.tap_position(*point)
            self.assertEqual(self.preview.selected, camera)
            self.assertEqual(self.preview.path.read_text(), f'{camera}\n')
            self.assertTrue(self.item('previewBorder').isVisible())
            self.tap_position(480, 360)
            self.assertEqual(self.preview.selected, -1)
            self.assertFalse(self.item('previewBorder').isVisible())

    def test_stitched_half_and_menu_do_not_select_preview(self):
        self.tap_position(1400, 200)
        self.assertEqual(self.preview.selected, -1)
        self.tap('calButton')
        self.assertEqual(self.preview.selected, -1)
        self.tap_position(240, 180)
        self.assertEqual(self.preview.selected, -1)

    def test_settings_work_with_expanded_preview(self):
        self.tap_position(720, 540)
        self.open_settings()
        self.assertEqual(self.preview.selected, 3)
        self.tap_position(240, 180)
        self.assertEqual(self.preview.selected, -1)
        self.assertTrue(self.window.property('settingsVisible'))

    def test_selection_failure_does_not_show_expanded_border(self):
        self.preview.path = Path(self.temporary.name)/'missing'/'state'
        self.tap_position(240, 180)
        self.assertEqual(self.preview.selected, -1)
        self.assertTrue(self.preview.error)
        self.assertFalse(self.item('previewBorder').isVisible())

    def begin_removal(self):
        self.cal.timer.stop()
        self.cal.job = Path(self.temporary.name)/'job'
        self.cal.job.mkdir()
        self.cal.process.start(sys.executable, ['-c', 'import time; time.sleep(60)'])
        self.assertTrue(self.cal.process.waitForStarted(3000))
        self.cal.data.update(state='running', phase='Remove the green corners', waiting_action='remove_corners')
        self.cal.changed.emit()
        QTest.qWait(150)
        self.assertTrue(self.window.property('removalVisible'))

    def test_removal_prompt_is_centered_modal_and_requires_continue(self):
        self.begin_removal()
        popup = self.item('cornerRemovalPrompt')
        self.assertEqual(popup.property('x')+popup.property('width')/2, 960)
        self.assertEqual(popup.property('y')+popup.property('height')/2, 360)
        self.assertTrue(popup.property('modal'))
        acknowledgement = self.cal.job/'corners_removed.json'
        self.assertFalse(acknowledgement.exists())
        self.tap_position(100, 100)
        self.assertTrue(self.window.property('removalVisible'))
        self.assertEqual(self.preview.selected, -1)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.assertTrue(self.window.property('removalVisible'))
        if os.environ.get('JK_REMOVAL_SCREENSHOT'):
            self.assertTrue(self.window.grabWindow().save(os.environ['JK_REMOVAL_SCREENSHOT']))
        self.tap('continueCornerRemoval')
        self.assertEqual(json.loads(acknowledgement.read_text()), {'action': 'corners_removed'})
        self.assertFalse(self.window.property('removalVisible'))
        self.assertTrue(self.cal.busy)
        # Polling the old waiting status before the worker advances must not reopen it.
        self.cal.changed.emit()
        self.assertFalse(self.window.property('removalVisible'))

    def test_cancel_removal_does_not_authorize_second_capture(self):
        self.begin_removal()
        self.tap('cancelCornerRemoval')
        self.assertFalse((self.cal.job/'corners_removed.json').exists())
        self.assertFalse(self.window.property('removalVisible'))

    def test_continue_is_ignored_outside_removal_phase(self):
        self.cal.continueCapture()
        self.assertFalse(self.cal.continue_requested)

    def test_failed_ack_write_keeps_removal_prompt_visible(self):
        self.begin_removal()
        self.cal.job = self.cal.job/'missing'
        self.tap('continueCornerRemoval')
        self.assertTrue(self.window.property('removalVisible'))
        self.assertIn('Could not continue', self.cal.detail)

    def prepare_retry(self):
        self.cal.timer.stop()
        self.cal.args.jobs.mkdir()
        self.saved = saved_job(self.cal.args.jobs)
        self.cal.restore_status()
        self.cal.changed.emit()
        QTest.qWait(100)
        self.assertTrue(self.cal.canRetry)

    def test_retry_is_centered_confirmed_and_cancellable(self):
        self.prepare_retry()
        with patch.object(self.cal, 'launch') as launch:
            self.tap('retrySavedButton')
            self.assertTrue(self.window.property('retryVisible'))
            popup = self.item('retryConfirmation')
            self.assertEqual(popup.property('x')+popup.property('width')/2, 960)
            self.assertEqual(popup.property('y')+popup.property('height')/2, 360)
            launch.assert_not_called()
            self.tap('cancelRetry')
            launch.assert_not_called()
            self.tap('retrySavedButton')
            if os.environ.get('JK_RETRY_SCREENSHOT'):
                self.assertTrue(self.window.grabWindow().save(os.environ['JK_RETRY_SCREENSHOT']))
            self.tap('confirmRetry')
            launch.assert_called_once_with(self.saved)
            self.assertFalse(self.window.property('retryVisible'))

    def test_retry_revalidates_deleted_capture(self):
        self.prepare_retry()
        (self.saved/'raw/pass01/input0.uyvy').unlink()
        with patch.object(self.cal, 'launch') as launch:
            self.cal.retry()
            launch.assert_not_called()
        self.assertFalse(self.cal.canRetry)
        self.assertIn('incomplete', self.cal.detail)

    def test_restart_remembers_interrupted_capture_without_removal_popup(self):
        self.prepare_retry()
        (self.saved/'status.json').write_text('{"state":"running","waiting_action":"remove_corners"}')
        self.cal.restore_status()
        self.cal.changed.emit()
        self.assertEqual(self.cal.state, 'failed')
        self.assertFalse(self.cal.waitingForRemoval)
        self.assertFalse(self.window.property('removalVisible'))
        self.assertTrue(self.cal.canRetry)

    def test_committed_pointer_wins_over_stale_job_status(self):
        self.prepare_retry()
        (self.root/'active_table_calibration.json').write_text(json.dumps(dict(job=str(self.saved))))
        self.cal.restore_status()
        self.assertEqual(self.cal.state, 'complete')
        self.assertFalse(self.cal.canRetry)

    def test_malformed_persisted_status_does_not_crash_ui(self):
        self.prepare_retry()
        for value in ('[]', '{invalid'):
            (self.saved/'status.json').write_text(value)
            self.cal.restore_status()
            self.assertEqual(self.cal.state, 'failed')
            self.assertFalse(self.cal.canRetry)

    def test_retry_starts_fresh_job_and_passes_saved_source(self):
        self.prepare_retry()
        with patch.object(self.cal.process, 'start') as start:
            self.cal.retry()
        args = start.call_args.args[1]
        self.assertEqual(args[-2:], ['--reuse', str(self.saved)])
        self.assertNotEqual(self.cal.job, self.saved)
        self.assertFalse(self.cal.canRetry)

    def test_storage_restore_error_is_visible(self):
        self.cal.data.update(state='failed', persistence_restore_error='disk failure')
        self.assertIn('do not power off', self.cal.detail)

    def test_incomplete_job_has_no_retry_button(self):
        self.prepare_retry()
        (self.saved/'clear_check.json').unlink()
        self.cal.restore_status()
        self.cal.changed.emit()
        QTest.qWait(100)
        self.assertFalse(self.item('retrySavedButton').isVisible())

    def test_repeated_cancel_does_not_interrupt_restore_twice(self):
        self.begin_removal()
        with patch.object(self.cal.process, 'terminate') as terminate:
            self.cal.cancel()
            self.cal.cancel()
            terminate.assert_called_once()

    def test_malformed_status_on_worker_exit_does_not_crash(self):
        self.prepare_retry()
        (self.saved/'status.json').write_text('[]')
        self.cal.done(1, None)
        self.assertEqual(self.cal.state, 'failed')
        self.assertFalse(self.cal.canRetry)


if __name__ == '__main__':
    unittest.main()
