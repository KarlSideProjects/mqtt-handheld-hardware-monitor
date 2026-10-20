"""SSH failures return useful allowlisted codes, never raw remote output."""
import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import device


class DeviceCliTests(unittest.TestCase):
    def test_transport_errors_are_distinct_and_redacted(self):
        cases = [
            (255, 'Permission denied (publickey,password). secret-data', 'ssh_authentication_failed'),
            (255, 'Host key verification failed. secret-data', 'ssh_host_key_failed'),
            (255, 'REMOTE HOST IDENTIFICATION HAS CHANGED! secret-data', 'ssh_host_key_failed'),
            (255, 'connect to host: Connection timed out. secret-data', 'ssh_connection_failed'),
            (127, 'python3: not found secret-data', 'remote_python_failed'),
            (1, 'Traceback: private-config secret-data', 'remote_python_failed'),
            (0, 'secret-data', 'invalid_remote_response'),
        ]
        for code, stderr, expected in cases:
            with self.subTest(expected=expected), patch.object(device.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stdout='not json secret-data', stderr=stderr)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    result = device.main(['diagnose', '--device', 'trimui', '--host', '192.0.2.1'])
                self.assertEqual(result, 1)
                self.assertEqual(json.loads(out.getvalue())['error'], expected)
                self.assertNotIn('secret-data', out.getvalue())


if __name__ == '__main__':
    unittest.main()
