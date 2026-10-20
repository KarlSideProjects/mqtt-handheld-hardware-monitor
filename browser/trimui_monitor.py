#!/usr/bin/env python3
"""TrimUI host using headless Chromium and the handheld's native SDL renderer."""
import os
from pathlib import Path
import signal
import subprocess
import threading
from http.server import ThreadingHTTPServer

import monitor

# Linux Xbox-compatible codes; physical labels must still be checked on the device.
BUTTONS = {305: 'detail', 304: 'back', 308: 'screen', 315: 'toggle',
           310: 'previous', 311: 'next'}


def gamepad(directory=Path('/sys/class/input')):
    for entry in sorted(directory.glob('event*')):
        if monitor.LocalStatus.read(entry / 'device/name') == 'TRIMUI Player1':
            return '/dev/input/' + entry.name
    raise OSError('TRIMUI Player1 not found; check /proc/bus/input/devices')


class Backlight(monitor.Screen):
    """Only backlight blanking is supported here; panel power-off is unverified."""
    def toggle(self):
        self.path.write_text(str(self.dim if self.asleep else 0))
        self.asleep = not self.asleep


class TrimUIStatus(monitor.LocalStatus):
    def __init__(self, **kwargs):
        super().__init__(thermal_types=('cpul_thermal_zone', 'cpub_thermal_zone'), **kwargs)

    def sample(self, now=None):
        return dict(super().sample(now), name='TrimUI', screen_key='Y', exit_keys='Select + Start')


def main():
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    path = gamepad()
    state = monitor.Monitor()
    state.device = TrimUIStatus()
    state.screen = Backlight(brightness=os.environ.get('TRIMUI_MONITOR_BRIGHTNESS', '16'))
    client = browser = None
    try:
        state.screen.enter()
        client = monitor.mqtt_start(state)
        with ThreadingHTTPServer(('127.0.0.1', 8766), monitor.handler(state)) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            threading.Thread(target=monitor.controls,
                             args=(state, server, path, BUTTONS, (314, 315), (16, 17)), daemon=True).start()
            try:
                browser = subprocess.Popen([os.environ['TRIMUI_BROWSER'],
                                            'http://127.0.0.1:8766/'])
                while worker.is_alive():
                    try:
                        result = browser.wait(timeout=.25)
                    except subprocess.TimeoutExpired:
                        continue
                    if result:
                        raise RuntimeError(f'Chromium/SDL exited with status {result}; see launch.log')
                    break
            finally:
                server.shutdown()
    finally:
        if browser is not None and browser.poll() is None:
            browser.terminate()
            try:
                browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser.kill()
                browser.wait()
        try:
            state.screen.restore()
        finally:
            if client:
                client.disconnect()
                client.loop_stop()


if __name__ == '__main__':
    main()
