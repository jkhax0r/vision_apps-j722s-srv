import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ui import camera_controls as cc


CONTROL_TEXT = """
    exposure_mode 0x009a0901 (menu) : min=0 max=2 default=1 value=1 (Auto Mode)
        0: Manual Mode
        1: Auto Mode
        2: AGC Mode
    exposure 0x00980911 (int) : min=1 max=1000000 step=1 default=10000 value=10000
    gain 0x00980913 (int) : min=1 max=64 step=1 default=1 value=1
    brightness 0x00980900 (int) : min=0 max=8192 step=1 default=4096 value=4096 flags=slider
    power_line_frequency 0x00980918 (menu) : min=0 max=3 default=0 value=0
        0: Disabled
        1: 50 Hz
        2: 60 Hz
        3: Auto
    ae_exposure_upper 0x00982903 (int) : min=1 max=1000000 step=1 default=8333 value=8333
    ae_exposure_max 0x00982904 (int) : min=1 max=1000000 step=1 default=66666 value=66666
    max_fps 0x00982901 (int) : min=1 max=255 step=1 default=30 value=30
"""


def topology():
    def entity(name, node, content):
        return f'- entity 1: {name} (1 pad)\n device node name {node}\n{content}\n'
    text = entity('max96724 4-002e', '/dev/v4l-subdev20',
                  '\n'.join(f'{4-i}/0 -> 0/{i} [ACTIVE]' for i in range(4)))
    text += entity('cdns_csi2rx.30101000.csi-bridge', '/dev/v4l-subdev21',
                   '\n'.join(f'0/{i} -> 1/{i} [ACTIVE]' for i in range(4)))
    text += entity('30102000.ticsi2rx', '/dev/v4l-subdev22',
                   '\n'.join(f'0/{i} -> {i+1}/0 [ACTIVE]' for i in range(4)))
    for i in range(4):
        text += entity(f'tevs {12+i}-{0x39+i:04x}', f'/dev/v4l-subdev{16-i}',
                       f'-> "max96724 4-002e":{4-i} [ENABLED,IMMUTABLE]')
        text += entity(f'30102000.ticsi2rx context {i+1}', f'/dev/video{12+i}', '')
    return text


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.controls = cc.parse_controls(CONTROL_TEXT)
        self.rows = [dict(identity=f'{0x39+i:04x}', entity=f'tevs {i}', device=f'/dev/v4l-subdev{i}',
                          controls=copy.deepcopy(self.controls)) for i in range(4)]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'camera_settings.json'

    def test_driver_ranges_and_menu(self):
        self.assertEqual(self.controls['exposure_mode']['menu'][2], 'AGC Mode')
        self.assertEqual(self.controls['brightness']['max'], 8192)

    def test_graph_follows_actual_renderer_order_and_renumbered_nodes(self):
        rows = cc.discover(topology(), ['/dev/video14', '/dev/video12', '/dev/video15', '/dev/video13'])
        self.assertEqual([c['identity'] for c in rows], ['003b', '0039', '003c', '003a'])
        self.assertEqual(rows[0]['device'], '/dev/v4l-subdev14')
        self.assertIn('top left', rows[0]['label'])

    def test_inactive_route_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Inactive route'):
            cc.discover(topology().replace('4/0 -> 0/0 [ACTIVE]', '4/0 -> 0/0 []'),
                        [f'/dev/video{i+12}' for i in range(4)])

    def test_duplicate_capture_rejected(self):
        with self.assertRaises(ValueError):
            cc.discover(topology(), ['/dev/video12']*4)

    def test_missing_control_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing TEVS'):
            cc.parse_controls(CONTROL_TEXT.replace('ae_exposure_max', 'unknown'))

    def test_unsafe_controls_ranges_and_types_rejected(self):
        for update in ({'bsl_mode': 1}, {'trigger_mode': 1}, {'brightness': -1},
                       {'gain': 65}, {'gain': True}, {'exposure': 1.2}, {'exposure_mode': 9},
                       {'ae_exposure_max': 100}, {}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                cc.validate(update, self.controls)

    def test_menu_holes_readonly_and_steps_rejected(self):
        del self.controls['exposure_mode']['menu'][2]
        self.controls['gain']['readonly'] = True
        self.controls['brightness']['step'] = 2
        for update in ({'exposure_mode': 2}, {'gain': 2}, {'brightness': 3}):
            with self.assertRaises(ValueError):
                cc.validate(update, self.controls)

    def test_long_shutters_cannot_stall_live_capture(self):
        self.assertEqual(cc.live_limit('exposure', self.controls), 33333)
        self.assertEqual(cc.live_limit('ae_exposure_max', self.controls), 66666)
        for update in ({'exposure': 339036}, {'exposure': 33334}, {'ae_exposure_max': 1000000}):
            with self.assertRaisesRegex(ValueError, 'live-view limit'):
                cc.validate(update, self.controls)
        cc.validate({'exposure': 33333, 'ae_exposure_max': 66666}, self.controls)

    def fake_write(self, camera, updates):
        for k, v in updates.items():
            camera['controls'][k]['value'] = v

    def test_save_by_port_not_subdevice_or_screen_position(self):
        with patch.object(cc, 'write', side_effect=self.fake_write):
            cc.apply(self.rows, {'003a': {'brightness': 4500}}, self.path)
        stored = json.loads(self.path.read_text())
        self.assertEqual(list(stored['cameras']), ['003a'])
        self.assertEqual(stored['cameras']['003a']['brightness'], 4500)
        self.assertEqual(stored['cameras']['003a']['exposure_mode'], 1)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_prevalidate_all_before_any_changes(self):
        self.rows[1]['controls']['brightness']['max'] = 4000
        with patch.object(cc, 'write') as write, self.assertRaises(ValueError):
            cc.apply(self.rows, {'0039': {'brightness': 4500}, '003a': {'brightness': 4500}}, self.path)
        write.assert_not_called()

    def test_failed_partial_batch_rolls_back_and_does_not_save(self):
        def write(camera, updates):
            self.fake_write(camera, updates)
            if camera['identity'] == '003a' and updates['brightness'] == 4500:
                raise RuntimeError('I2C failed')
        with patch.object(cc, 'write', side_effect=write), patch.object(cc, 'read', side_effect=lambda c: c['controls']):
            with self.assertRaisesRegex(RuntimeError, 'previous settings restored'):
                cc.apply(self.rows, {'0039': {'brightness': 4500}, '003a': {'brightness': 4500}}, self.path)
        self.assertEqual([r['controls']['brightness']['value'] for r in self.rows], [4096]*4)
        self.assertFalse(self.path.exists())

    def test_save_failure_rolls_back(self):
        with patch.object(cc, 'write', side_effect=self.fake_write), patch.object(cc, 'read', side_effect=lambda c: c['controls']), \
             patch.object(cc, 'save_settings', side_effect=OSError('No space')):
            with self.assertRaisesRegex(RuntimeError, 'No space'):
                cc.apply(self.rows, {'0039': {'brightness': 4500}}, self.path)
        self.assertEqual(self.rows[0]['controls']['brightness']['value'], 4096)

    def test_corrupt_settings_cannot_write_camera(self):
        self.path.write_text('{invalid')
        with patch.object(cc, 'write') as write, self.assertRaises(ValueError):
            cc.apply(self.rows, {'0039': {'brightness': 4500}}, self.path)
        write.assert_not_called()

    def test_restore_does_not_rewrite_file(self):
        with patch.object(cc, 'write', side_effect=self.fake_write), patch.object(cc, 'save_settings') as save:
            cc.apply(self.rows, {'003c': {'brightness': 4500}}, self.path, persist=False)
        save.assert_not_called()

    def test_shutter_write_enters_manual_then_restores_auto(self):
        updated = copy.deepcopy(self.controls); updated['exposure']['value'] = 5000
        with patch.object(cc, 'run') as run, patch.object(cc, 'read', return_value=updated):
            cc.write(self.rows[0], {'exposure': 5000})
        self.assertEqual([c.args[-1] for c in run.call_args_list],
                         ['--set-ctrl=exposure_mode=0', '--set-ctrl=exposure=5000', '--set-ctrl=exposure_mode=1'])

    def test_readback_mismatch_is_error(self):
        with patch.object(cc, 'run'), patch.object(cc, 'read', return_value=self.controls):
            with self.assertRaisesRegex(RuntimeError, 'readback mismatch'):
                cc.write(self.rows[0], {'brightness': 4500})


if __name__ == '__main__':
    unittest.main()
