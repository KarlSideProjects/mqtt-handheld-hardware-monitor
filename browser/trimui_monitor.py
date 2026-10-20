#!/usr/bin/env python3
"""TrimUI host using headless Chromium and the handheld's native SDL renderer."""
import ctypes as C
import fcntl
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


class DRMResources(C.Structure):
    _fields_ = [('count_fbs', C.c_int), ('fbs', C.POINTER(C.c_uint32)),
                ('count_crtcs', C.c_int), ('crtcs', C.POINTER(C.c_uint32)),
                ('count_connectors', C.c_int), ('connectors', C.POINTER(C.c_uint32)),
                ('count_encoders', C.c_int), ('encoders', C.POINTER(C.c_uint32)),
                ('min_width', C.c_uint32), ('max_width', C.c_uint32),
                ('min_height', C.c_uint32), ('max_height', C.c_uint32)]


class DRMConnector(C.Structure):
    _fields_ = [('connector_id', C.c_uint32), ('encoder_id', C.c_uint32),
                ('connector_type', C.c_uint32), ('connector_type_id', C.c_uint32),
                ('connection', C.c_int), ('mmWidth', C.c_uint32), ('mmHeight', C.c_uint32),
                ('subpixel', C.c_int), ('count_modes', C.c_int), ('modes', C.c_void_p),
                ('count_props', C.c_int), ('props', C.POINTER(C.c_uint32)),
                ('prop_values', C.POINTER(C.c_uint64)), ('count_encoders', C.c_int),
                ('encoders', C.POINTER(C.c_uint32))]


class DRMProperty(C.Structure):
    # Only this prefix of drmModePropertyRes is accessed.
    _fields_ = [('prop_id', C.c_uint32), ('flags', C.c_uint32), ('name', C.c_char * 32)]


def display_power(mode):
    # Serialize DPMS with SDL presentation so power-off cannot race an in-flight pageflip.
    with open('/tmp/hwmonitor-display.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _display_power(mode)


def _display_power(mode):
    if mode not in ('on', 'off'):
        raise ValueError('Unsupported display power mode')
    drm = C.CDLL('libdrm.so.2', use_errno=True)
    for name, args, result in (
        ('drmModeGetResources', [C.c_int], C.POINTER(DRMResources)),
        ('drmModeGetConnector', [C.c_int, C.c_uint32], C.POINTER(DRMConnector)),
        ('drmModeGetProperty', [C.c_int, C.c_uint32], C.POINTER(DRMProperty)),
        ('drmModeConnectorSetProperty', [C.c_int, C.c_uint32, C.c_uint32, C.c_uint64], C.c_int),
        ('drmModeFreeResources', [C.POINTER(DRMResources)], None),
        ('drmModeFreeConnector', [C.POINTER(DRMConnector)], None),
        ('drmModeFreeProperty', [C.POINTER(DRMProperty)], None),
    ):
        function = getattr(drm, name)
        function.argtypes, function.restype = args, result
    fd = os.open('/dev/dri/card0', os.O_RDWR | os.O_CLOEXEC)
    resources = None
    try:
        resources = drm.drmModeGetResources(fd)
        if not resources:
            raise OSError('Cannot enumerate DRM connectors')
        targets = []
        for identifier in resources.contents.connectors[:resources.contents.count_connectors]:
            connector = drm.drmModeGetConnector(fd, identifier)
            if not connector:
                raise OSError('Cannot read DRM connector')
            try:
                info = connector.contents
                if info.connector_type != 16 or info.connection != 1:  # DSI, connected
                    continue
                for prop_id in info.props[:info.count_props]:
                    prop = drm.drmModeGetProperty(fd, prop_id)
                    if not prop:
                        raise OSError('Cannot read DRM property')
                    try:
                        if prop.contents.name == b'DPMS':
                            targets.append((info.connector_id, prop.contents.prop_id))
                    finally:
                        drm.drmModeFreeProperty(prop)
            finally:
                drm.drmModeFreeConnector(connector)
        if len(targets) != 1:
            raise OSError('Expected exactly one connected DSI DPMS control')
        connector, prop = targets[0]
        # Legacy connector DPMS is supported by this firmware, without taking SDL's master.
        if drm.drmModeConnectorSetProperty(fd, connector, prop, 0 if mode == 'on' else 3):
            raise OSError(C.get_errno(), 'DRM display power command failed')
        expected = 'On' if mode == 'on' else 'Off'
        if Path('/sys/class/drm/card0-DSI-1/dpms').read_text().strip() != expected:
            raise OSError('DRM display power state did not change')
    finally:
        if resources:
            drm.drmModeFreeResources(resources)
        os.close(fd)


class Backlight(monitor.Screen):
    """Toggle native DRM display power while keeping the MQTT service awake."""
    power = staticmethod(display_power)

    def toggle(self):
        if self.asleep:
            self.power('on')
            self.path.write_text(str(self.dim))
            self.dpms_off = self.asleep = False
        else:
            self.path.write_text('0')
            # An uncertain off result must still be followed by an explicit on when waking/exiting.
            self.dpms_off = self.asleep = True
            self.power('off')


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
