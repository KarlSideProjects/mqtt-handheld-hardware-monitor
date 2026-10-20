"""Exercise stock launch handoff and verification against controlled OS boundaries."""
import contextlib
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import device_ops as ops


class Clock:
    now = 0
    def __call__(self): return self.now
    def sleep(self, delay): self.now += delay


class Runtime:
    def __init__(self, root):
        self.root, self.clock, self.rows = root, Clock(), []
        self.queue, self.log = root / 'cmd_to_run.sh', root / 'launch.log'
        self.log.write_text('old pageflip: Could not queue pageflip: -16\n')
        self.rows = [self.row(10, 'runtrimui.sh', ['/bin/sh', '/usr/trimui/bin/runtrimui.sh']),
                     self.row(11, 'MainUI', ['./MainUI'], 10)]
        self.term_ignored = True
        self.bad_frame = False

    def row(self, pid, name, args, ppid=1):
        return {'pid': pid, 'name': name, 'args': args, 'ppid': ppid, 'started': str(pid),
                'exe': '/usr/trimui/bin/MainUI' if name == 'MainUI' else '/usr/bin/python3',
                'cwd': str(self.root)}

    def signal(self, row, sig):
        current = next(p for p in self.rows if p['pid'] == row['pid'])
        if current['name'] == 'MainUI':
            if sig == signal.SIGTERM and self.term_ignored: return
            assert self.queue.read_text() == '#!/bin/sh\nexec /mnt/SDCARD/Apps/HardwareMonitor/launch.sh\n'
            self.rows.remove(current)
            self.rows += [self.row(12, 'python3', ['python3', 'trimui_monitor.py'], 10),
                          self.row(13, 'python3', ['python3', '/mnt/UDISK/hwmonitor/runtime/trimui_browser.py'], 12)]
            if self.bad_frame: self.log.write_text(self.log.read_text() + 'Could not queue pageflip: -16\n')
        elif current['name'] == 'python3':
            self.rows = [p for p in self.rows if p['pid'] not in (12, 13)]
            self.queue.unlink(missing_ok=True)
            self.rows.append(self.row(11, 'MainUI', ['./MainUI'], 10))

    def status(self):
        if not any(p['pid'] == 12 for p in self.rows): raise ops.OpsError('monitor_unavailable')
        return {'connection': 'Connected', 'count': 3, 'hosts': [], 'device': {'name': 'TrimUI'}}


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = Runtime(self.root)

    @contextlib.contextmanager
    def environment(self):
        r = self.runtime
        with patch.object(ops, 'ROOTS', {'trimui': self.root}), \
             patch.object(ops, 'launch_preflight'), \
             patch.object(ops, 'processes', side_effect=lambda: list(r.rows)), \
             patch.object(ops, 'signal_process', side_effect=r.signal), \
             patch.object(ops, 'STOCK_QUEUE', r.queue), \
             patch.object(ops, 'display_log', return_value=r.log):
            yield

    def restart(self):
        r = self.runtime
        return ops.restart_monitor('trimui', self.root, reader=r.status, clock=r.clock, sleep=r.clock.sleep)

    def test_stock_queue_precedes_menu_exit_and_single_display_survives_observation(self):
        with self.environment(): result = self.restart()
        self.assertEqual(result['display']['monitor_count'], 1)
        self.assertEqual(result['display']['mainui_count'], 0)
        self.assertTrue(result['display']['stock_parent'])
        self.assertEqual(result['new_pageflip_errors'], 0)
        self.assertGreaterEqual(self.runtime.clock.now, 12)
        self.assertEqual(self.runtime.queue.stat().st_mode & 0o777, 0o700)

    def test_busy_queue_is_preserved_and_menu_remains_running(self):
        self.runtime.queue.write_text('another application')
        with self.environment(), self.assertRaisesRegex(ops.OpsError, 'launch_queue_busy'):
            self.restart()
        self.assertEqual(self.runtime.queue.read_text(), 'another application')
        self.assertTrue(any(p['name'] == 'MainUI' for p in self.runtime.rows))

    def test_existing_stock_monitor_can_restart_after_queue_cleanup(self):
        self.runtime.queue.write_text('#!/bin/sh\nexec /mnt/SDCARD/Apps/HardwareMonitor/launch.sh\n')
        self.runtime.signal(self.runtime.rows[1], signal.SIGKILL)
        with self.environment(): result = self.restart()
        self.assertEqual(result['display']['monitor_count'], 1)
        self.assertEqual(result['display']['mainui_count'], 0)

    def test_new_pageflip_error_fails_even_when_mqtt_and_http_are_healthy(self):
        self.runtime.bad_frame = True
        with self.environment(), self.assertRaisesRegex(ops.OpsError, 'display_pageflip_error'):
            self.restart()
        self.assertFalse(any(p['pid'] == 12 for p in self.runtime.rows))
        self.assertTrue(any(p['name'] == 'MainUI' for p in self.runtime.rows))

    def test_unrelated_mainui_identity_is_never_signalled(self):
        self.runtime.rows[1]['exe'] = '/tmp/untrusted/MainUI'
        with self.environment(), self.assertRaisesRegex(ops.OpsError, 'unsafe_stock_launcher'):
            self.restart()
        self.assertEqual(len(self.runtime.rows), 2)
        self.assertFalse(self.runtime.queue.exists())

    def test_startup_waits_for_mqtt_before_full_observation_window(self):
        calls = [0]
        def reader():
            calls[0] += 1
            return {**self.runtime.status(), 'count': 0 if calls[0] <= 4 else 3}
        with self.environment():
            result = ops.restart_monitor('trimui', self.root, reader=reader,
                                         clock=self.runtime.clock, sleep=self.runtime.clock.sleep)
        self.assertGreaterEqual(self.runtime.clock.now, 15)
        self.assertEqual(result['status']['online_hosts'], 3)

    def test_monitor_identity_requires_the_application_directory(self):
        wrong = self.runtime.row(20, 'python3', ['python3', 'trimui_monitor.py'])
        wrong['cwd'] = '/tmp/another-application'
        with patch.object(ops, 'ROOTS', {'trimui': self.root}):
            self.assertEqual(ops.monitor_processes('trimui', [wrong]), [])

    def test_r36_stops_menu_before_launch_and_restores_it_on_failure(self):
        r = self.runtime
        r.rows = []
        running = {'menu': True}
        def run(command, **kwargs):
            running['menu'] = command[-2] == 'start'
            return type('Completed', (), {'returncode': 0})()
        def launch(command, **kwargs):
            self.assertFalse(running['menu'])
            raise OSError('fixture launch failure')
        with patch.object(ops, 'ROOTS', {'r36': self.root}), \
             patch.object(ops, 'launch_preflight', return_value=self.root/'Hardware Monitor.sh'), \
             patch.object(ops, 'processes', side_effect=lambda: r.rows), \
             patch.object(ops.subprocess, 'run', side_effect=run), \
             patch.object(ops.subprocess, 'Popen', side_effect=launch):
            with self.assertRaises(OSError):
                ops.restart_monitor('r36', self.root, clock=r.clock, sleep=r.clock.sleep)
        self.assertTrue(running['menu'])

    def test_missing_log_fails_verification(self):
        original = self.runtime.signal
        def signal_and_remove(row, sig):
            original(row, sig)
            if any(p['pid'] == 12 for p in self.runtime.rows):
                self.runtime.log.unlink(missing_ok=True)
        self.runtime.signal = signal_and_remove
        with self.environment(), self.assertRaisesRegex(ops.OpsError, 'display_log_unavailable'):
            self.restart()

    def test_r36_counts_client_shell_once_and_waits_for_failed_renderer_shutdown(self):
        r = self.runtime
        r.rows = []
        stopped_at = [None]
        menu = [True]
        def rows():
            if stopped_at[0] is not None and r.clock.now >= stopped_at[0]: r.rows = []
            return list(r.rows)
        def run(command, **kwargs):
            if command[-2] == 'start': self.assertEqual(rows(), [])
            menu[0] = command[-2] == 'start'
            return type('Completed', (), {'returncode': 0})()
        def launch(*args, **kwargs):
            r.rows = [r.row(20, 'python3', ['python3', 'monitor.py']),
                      r.row(21, 'bash', ['/bin/bash', str(self.root/'client.sh')]),
                      r.row(22, 'xinit', ['xinit', str(self.root/'client.sh')])]
            self.assertEqual(ops.display_health('r36')['renderer_count'], 1)
        def stop(*args): stopped_at[0] = r.clock.now + 1
        def reader(): return {'connection': 'Connected', 'count': 1 if r.clock.now < 1 else 0}
        with patch.object(ops, 'ROOTS', {'r36': self.root}), \
             patch.object(ops, 'launch_preflight', return_value=self.root/'launcher'), \
             patch.object(ops, 'processes', side_effect=rows), \
             patch.object(ops, 'signal_process', side_effect=stop), \
             patch.object(ops.subprocess, 'run', side_effect=run), \
             patch.object(ops.subprocess, 'Popen', side_effect=launch):
            with self.assertRaisesRegex(ops.OpsError, 'mqtt_not_live'):
                ops.restart_monitor('r36', self.root, reader=reader, clock=r.clock, sleep=r.clock.sleep)
        self.assertTrue(menu[0])
        self.assertGreaterEqual(r.clock.now, 2)

    def test_existing_queue_requires_stock_parent_even_with_matching_command(self):
        self.runtime.queue.write_bytes(ops.TRIMUI_COMMAND)
        self.runtime.signal(self.runtime.rows[1], signal.SIGKILL)
        self.runtime.rows[1]['ppid'] = 1
        with self.environment(), self.assertRaisesRegex(ops.OpsError, 'launch_queue_busy'):
            self.restart()
        self.assertTrue(any(p['pid'] == 12 for p in self.runtime.rows))

    @unittest.skipUnless(hasattr(ops.os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Linux pidfd required')
    def test_pidfd_signal_terminates_only_the_observed_child(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            row = next(p for p in ops.processes() if p['pid'] == child.pid)
            ops.signal_process(row, signal.SIGTERM)
            self.assertEqual(child.wait(timeout=3), -signal.SIGTERM)
        finally:
            if child.poll() is None: child.terminate()
            child.wait(timeout=3)

    def test_signal_refuses_reused_pid_before_sending(self):
        row = self.runtime.rows[1]
        with patch.object(ops, 'processes', return_value=[dict(row, started='replacement')]), \
             patch.object(ops.os, 'pidfd_open') as pidfd:
            with self.assertRaisesRegex(ops.OpsError, 'process_changed'):
                ops.signal_process(row, signal.SIGTERM)
            pidfd.assert_not_called()


if __name__ == '__main__':
    unittest.main()
