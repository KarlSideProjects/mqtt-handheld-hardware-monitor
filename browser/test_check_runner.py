"""Regressions for local and explicitly selected handheld checks."""
import sys
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

    def test_preflight_rejects_wrong_device_before_test_process(self):
        with patch.object(check_device, 'status', return_value={
            'device': {'name': 'TrimUI'}, 'connection': 'Connected', 'count': 3,
        }), patch.object(check_device.subprocess, 'run') as run:
            with self.assertRaisesRegex(check_device.PreflightError, 'expected R36'):
                check_device.preflight('r36', 'awake')
            run.assert_not_called()

    def test_preflight_reports_offline_before_test_process(self):
        with patch.object(check_device, 'status', return_value={
            'device': {'name': 'R36'}, 'connection': 'Disconnected', 'count': 0,
        }), patch.object(check_device.subprocess, 'run') as run:
            with self.assertRaisesRegex(check_device.PreflightError, 'offline'):
                check_device.preflight('r36', 'awake')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
