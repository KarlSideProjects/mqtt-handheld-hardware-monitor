"""Regressions for local and explicitly selected handheld checks."""
import sys
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import check
import check_device


class CheckRunnerTests(unittest.TestCase):
    def test_local_runner_excludes_live_device_tests(self):
        self.assertFalse(set(check.LOCAL_TESTS) & {
            'test_awake.py', 'test_trimui_screen.py', 'test_trimui_exit.py',
        })

    def test_r36_identity_uses_debian13_input_and_backlight_paths(self):
        exists = lambda path: str(path) in {
            '/dev/input/by-path/platform-odroidgo3-joypad-event-joystick',
            '/sys/class/backlight/backlight/brightness',
        }
        with patch.object(check_device.platform, 'machine', return_value='aarch64'), \
             patch.object(check_device.Path, 'read_text', return_value='ID=debian\nVERSION_ID="13"\n'), \
             patch.object(check_device.Path, 'exists', autospec=True, side_effect=lambda path: exists(path)):
            self.assertTrue(check_device.r36_device())
        with patch.object(check_device.platform, 'machine', return_value='aarch64'), \
             patch.object(check_device.Path, 'read_text', return_value='ID=debian\nVERSION_ID="13"\n'), \
             patch.object(check_device.Path, 'exists', return_value=False):
            self.assertFalse(check_device.r36_device())

    def test_preflight_accepts_r36_local_status_without_device_name(self):
        local_status = {'device': {'cpu': 10}, 'connection': 'Connected', 'count': 3}
        with patch.object(check_device, 'status', return_value=local_status), \
             patch.object(check_device, 'r36_device', return_value=True), \
             patch.object(check_device.platform, 'machine', return_value='aarch64'), \
             patch.object(check_device.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(check_device, 'require'), \
             patch.object(check_device.subprocess, 'run', side_effect=[
                 SimpleNamespace(returncode=0, stdout=''),
                 SimpleNamespace(returncode=0, stdout='HardwareMonitor sleep idle'),
             ]):
            self.assertIs(check_device.preflight('r36', 'awake'), local_status)

    def test_preflight_rejects_wrong_device_before_test_process(self):
        with patch.object(check_device, 'status', return_value={
            'device': {'name': 'TrimUI'}, 'connection': 'Connected', 'count': 3,
        }), patch.object(check_device.subprocess, 'run') as run:
            with self.assertRaisesRegex(check_device.PreflightError, 'expected R36.*TrimUI'):
                check_device.preflight('r36', 'awake')
            run.assert_not_called()

    def test_preflight_reports_offline_before_test_process(self):
        with patch.object(check_device, 'status', return_value={
            'device': {'cpu': 10}, 'connection': 'Disconnected', 'count': 0,
        }), patch.object(check_device, 'r36_device', return_value=True), \
             patch.object(check_device.subprocess, 'run') as run:
            with self.assertRaisesRegex(check_device.PreflightError, 'offline'):
                check_device.preflight('r36', 'awake')
            run.assert_not_called()

    def test_exit_cli_allows_dimmed_backlight_and_passes_original_brightness(self):
        gamepad_name = Path('/sys/class/input/event1/device/name')
        current_brightness, original_brightness = '16', '32'
        pgrep = SimpleNamespace(returncode=0, stdout=(
            '1826 python3 /mnt/UDISK/hwmonitor/runtime/trimui_browser.py '
            '/mnt/UDISK/hwmonitor/browser/monitor.html\n'))
        completed = SimpleNamespace(returncode=0)
        with patch.object(check_device.sys, 'argv', [
                'check_device.py', '--device', 'trimui', '--test', 'exit',
                '--expected-brightness', original_brightness, '--allow-destructive-exit']), \
             patch.object(check_device, 'status', return_value={
                 'device': {'name': 'TrimUI'}, 'connection': 'Connected', 'count': 3}), \
             patch.object(check_device.platform, 'machine', return_value='aarch64'), \
             patch.object(check_device.Path, 'glob', return_value=[gamepad_name]), \
             patch.object(check_device.Path, 'is_file', return_value=True), \
             patch.object(check_device.Path, 'read_text', autospec=True, side_effect=lambda path: (
                 'TRIMUI Player1' if str(path).endswith('/device/name') else current_brightness)), \
             patch.object(check_device, 'require'), \
             patch.object(check_device.subprocess, 'run', side_effect=[pgrep, completed]) as run:
            self.assertEqual(check_device.main(), 0)
            self.assertEqual(run.call_args.args[0][-2:], ['--expected-brightness', original_brightness])

    def test_pgrep_output_with_pid_prefix_identifies_trimui_dashboard(self):
        output = '1826 python3 /mnt/UDISK/hwmonitor/runtime/trimui_browser.py /mnt/UDISK/hwmonitor/browser/monitor.html\n'
        with patch.object(check_device.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=output)):
            self.assertTrue(check_device.trimui_dashboard_running())


if __name__ == '__main__':
    unittest.main()
