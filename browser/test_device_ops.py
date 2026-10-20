"""Local device-update tests: real files and a controlled browser/status boundary."""
import base64
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from device_ops import (OpsError, ROOTS, UI_FILES, apply_update, last_verification,
                        make_release, preflight, summarize_status)


def status():
    return {'connection': 'Connected', 'count': 1, 'bad_messages': 0,
            'device': {'name': 'TrimUI'}, 'selected': 'pve', 'detail': 'pve',
            'pve_view': 'guest', 'pve_guest_id': 'lab:qemu:100',
            'hosts': [{'host': 'pve', 'history': ['private-history'],
                       'metrics': {'password': 'private-password'},
                       'virtualization': {'status': 'ok', 'guest_count': 7,
                                          'fresh': True, 'age_seconds': 2}}],
            'password': 'private-password', 'token': 'private-token'}


class Clock:
    now = 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Browser:
    def __init__(self, root, stale=False):
        self.root, self.stale, self.revision = root, stale, None

    def reload(self):
        if not self.stale:
            match = re.search(r"deploymentRevision='([a-f0-9]{64})'",
                              (self.root / 'monitor.html').read_text())
            self.revision = match[1] if match else None
            url = re.search(r"deploymentAckUrl='([^']+)'", (self.root / 'monitor.html').read_text())
            if url and url[1].startswith('http://127.0.0.1:'):
                import urllib.request
                urllib.request.urlopen(url[1], timeout=2).close()

    def loaded_revision(self):
        return self.revision


class DeviceOpsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.source, self.target = self.base / 'source', self.base / 'app'
        for root in (self.source, self.target):
            (root / 'assets').mkdir(parents=True)
            for name in UI_FILES:
                (root / name).write_text('new asset' if root == self.source else 'old asset')
            for name in ('monitor.py', 'pve.py', 'trimui_monitor.py'):
                (root / name).write_text('# identical backend\n')
        (self.source / 'monitor.html').write_text("const deploymentRevision='__HWMONITOR_REVISION__';const deploymentAckUrl='__HWMONITOR_ACK_URL__';")
        self.private = self.target / 'mqtt-config.json'
        self.private.write_text('{"password":"never-change"}')
        self.private.chmod(0o600)
        self.release = make_release(self.source, 'trimui')
        self.clock = Clock()

    def update(self, browser=None, reader=status):
        return apply_update(self.target, self.release, browser or Browser(self.target), reader,
                            clock=self.clock, sleep=self.clock.sleep)

    def test_diagnostics_allowlist_excludes_secrets_and_histories(self):
        result = summarize_status(status(), 'trimui')
        serialized = json.dumps(result)
        for hidden in ('private-password', 'private-token', 'private-history', 'metrics', 'history'):
            self.assertNotIn(hidden, serialized)
        self.assertEqual(result['hosts'][0]['guest_count'], 7)
        self.assertEqual(result['view']['pve_guest_id'], 'lab:qemu:100')

    def test_updates_files_loaded_revision_and_live_observations_preserving_config(self):
        before = self.private.stat()
        result = self.update()
        self.assertEqual(result['revision'], self.release['revision'])
        self.assertTrue(result['loaded'])
        self.assertGreaterEqual(self.clock.now, 11)
        self.assertEqual((Path(result['backup']) / 'monitor.html').read_text(), 'old asset')
        after = self.private.stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_mode),
                         (after.st_ino, after.st_mtime_ns, after.st_mode))
        self.assertEqual(last_verification(self.target)['revision'], self.release['revision'])
        (self.target / 'pve.js').write_text('changed after verification')
        self.assertIsNone(last_verification(self.target))

    def test_stale_browser_restores_all_files_and_reports_recovery(self):
        with self.assertRaises(OpsError) as caught:
            self.update(Browser(self.target, stale=True))
        self.assertEqual(caught.exception.code, 'loaded_revision_timeout')
        self.assertTrue(caught.exception.recovery['files_restored'])
        for name in UI_FILES:
            self.assertEqual((self.target / name).read_text(), 'old asset')

    def test_disconnected_mqtt_rolls_back_even_after_new_page_loaded(self):
        with self.assertRaises(OpsError) as caught:
            self.update(reader=lambda: {**status(), 'connection': 'Disconnected'})
        self.assertEqual(caught.exception.code, 'mqtt_not_live')
        self.assertEqual((self.target / 'monitor.html').read_text(), 'old asset')

    def test_offline_sender_fails_after_expiry_window(self):
        def reader():
            return {**status(), 'count': 0 if self.clock.now >= 10 else 1}
        with self.assertRaises(OpsError) as caught:
            self.update(reader=reader)
        self.assertEqual(caught.exception.code, 'mqtt_not_live')

    def test_backend_mismatch_and_unexpected_files_fail_before_replacement(self):
        (self.target / 'monitor.py').write_text('# older backend')
        with self.assertRaises(OpsError) as caught:
            self.update()
        self.assertEqual(caught.exception.code, 'backend_requires_install')
        self.assertEqual((self.target / 'monitor.html').read_text(), 'old asset')
        (self.target / 'monitor.py').write_text('# identical backend\n')
        self.release['files']['../mqtt-config.json'] = base64.b64encode(b'bad').decode()
        with self.assertRaises(OpsError):
            self.update()
        self.assertIn('never-change', self.private.read_text())

    def test_tampered_release_is_rejected(self):
        self.release['files']['pve.js'] = base64.b64encode(b'tampered').decode()
        with self.assertRaises(OpsError):
            self.update()
        self.assertEqual((self.target / 'pve.js').read_text(), 'old asset')

    def test_wrong_device_and_sleeping_screen_fail_preflight(self):
        with patch('device_ops.os.uname', return_value=SimpleNamespace(machine='aarch64')):
            with self.assertRaises(OpsError) as caught:
                preflight('trimui', ROOTS['trimui'], {**status(), 'device': {}})
            self.assertEqual(caught.exception.code, 'wrong_device')
            with self.assertRaises(OpsError) as caught:
                preflight('trimui', ROOTS['trimui'], {**status(), 'screen_off': True})
            self.assertEqual(caught.exception.code, 'wake_monitor_before_update')

    def test_reload_failure_does_not_report_successful_browser_recovery(self):
        browser = Browser(self.target)
        def fail_reload():
            raise OSError('browser unavailable')
        browser.reload = fail_reload
        with self.assertRaises(OpsError) as caught:
            self.update(browser)
        self.assertTrue(caught.exception.recovery['files_restored'])
        self.assertFalse(caught.exception.recovery['page_revision_restored'])


if __name__ == '__main__':
    unittest.main()
