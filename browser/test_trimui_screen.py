"""On TrimUI with the dashboard running: python3 test_trimui_screen.py.

Injects Y three times off/on, checks native DPMS/CRTC and MQTT while off, and
leaves the display awake. Requires live MQTT hosts and firmware DRM debugfs.
This verifies driver state, not optical output or electrical power consumption.
"""
import json
import os
from pathlib import Path
import re
import struct
import time
import urllib.request


def status():
    with urllib.request.urlopen('http://127.0.0.1:8766/status', timeout=3) as response:
        return json.load(response)


def active():
    text = Path('/sys/kernel/debug/dri/0/state').read_text()
    connector = next(block for block in re.split(r'(?m)^connector\[', text)[1:] if 'DSI-1' in block.splitlines()[0])
    name = re.search(r'\n\s*crtc=(.+)', connector)[1].strip()
    crtc = next(block for block in re.split(r'(?m)^crtc\[', text)[1:] if block.splitlines()[0].endswith(': ' + name))
    return int(re.search(r'\n\s*active=(\d+)', crtc)[1])


def key():
    event = next(p.name for p in Path('/sys/class/input').glob('event*')
                 if (p / 'device/name').read_text().strip() == 'TRIMUI Player1')
    fd = os.open('/dev/input/' + event, os.O_WRONLY)
    try:
        for value in (1, 0):
            os.write(fd, struct.pack('@llHHi', 0, 0, 1, 308, value)
                     + struct.pack('@llHHi', 0, 0, 0, 0, 0))
    finally:
        os.close(fd)


def wait_screen(off):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = status()
        dpms = Path('/sys/class/drm/card0-DSI-1/dpms').read_text().strip()
        brightness = int(Path('/sys/class/backlight/backlight0/brightness').read_text())
        if state['screen_off'] == off and dpms == ('Off' if off else 'On') and active() == (0 if off else 1):
            assert (brightness == 0) if off else (brightness > 0)
            return state
        time.sleep(.1)
    raise AssertionError('Y did not change backlight, DPMS and display pipeline within 5 seconds')


def main():
    initial = status()
    assert initial['device']['name'] == 'TrimUI' and initial['connection'] == 'Connected' and initial['count'] > 0
    assert not initial['screen_off'], 'Start with the dashboard awake'
    results = []
    try:
        for cycle, hold in enumerate((12, 2, 2), 1):
            started = time.monotonic()
            key(); wait_screen(True)
            off_ms = round((time.monotonic() - started) * 1000, 1)
            deadline = time.monotonic() + hold
            while time.monotonic() < deadline:
                state = wait_screen(True)
                assert state['connection'] == 'Connected' and state['count'] > 0, 'Live MQTT data stopped while off'
                time.sleep(.5)
            started = time.monotonic()
            key(); state = wait_screen(False)
            results.append(dict(cycle=cycle, hold_seconds=hold, off_ms=off_ms,
                                on_ms=round((time.monotonic() - started) * 1000, 1), online_hosts=state['count']))
        print(json.dumps(dict(result='PASS', cycles=results, scope='evdev Y, DPMS, CRTC, backlight, live MQTT; not optical or electrical')), flush=True)
    finally:
        if status()['screen_off']:
            key()
            wait_screen(False)


if __name__ == '__main__':
    main()
