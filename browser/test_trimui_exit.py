"""On TrimUI with Hardware Monitor running: test exit and restore the stock menu.

Run: python3 test_trimui_exit.py --expected-brightness <brightness before launch>
This writes gamepad events and closes the running monitor.
"""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-brightness', type=int, required=True)
    args = parser.parse_args()
    with urllib.request.urlopen('http://127.0.0.1:8766/status', timeout=3) as response:
        state = json.load(response)
    assert state['device']['name'] == 'TrimUI', 'Run only on the TrimUI dashboard'
    pattern = '^python3 .*runtime/trimui_browser.py '
    assert subprocess.run(['pgrep', '-f', pattern], capture_output=True).returncode == 0
    event = next(p.name for p in Path('/sys/class/input').glob('event*')
                 if (p / 'device/name').read_text().strip() == 'TRIMUI Player1')
    fd = os.open('/dev/input/' + event, os.O_WRONLY)
    try:
        for code, value in ((314, 1), (315, 1), (315, 0), (314, 0)):
            os.write(fd, struct.pack('@llHHi', 0, 0, 1, code, value)
                     + struct.pack('@llHHi', 0, 0, 0, 0, 0))
    finally:
        os.close(fd)
    started = time.monotonic()
    while time.monotonic() - started < 15:
        mounted = 'hwmonitor/runtime/rootfs/' in Path('/proc/mounts').read_text()
        menu = subprocess.run(['pidof', 'MainUI'], capture_output=True).returncode == 0
        browser = subprocess.run(['pgrep', '-f', pattern], capture_output=True).returncode == 0
        if menu and not mounted and not browser:
            break
        time.sleep(.1)
    else:
        raise AssertionError('Exit did not restore menu and release browser/mounts within 15 seconds')
    lock = Path('/mnt/UDISK/hwmonitor/runtime/rootfs/.mount-lock')
    assert lock.is_file()
    assert subprocess.run(['flock', '-n', str(lock), 'true']).returncode == 0
    assert int(Path('/sys/class/backlight/backlight0/brightness').read_text()) == args.expected_brightness
    assert Path('/sys/class/drm/card0-DSI-1/dpms').read_text().strip() == 'On'
    print(f'PASS: Select+Start, menu/backlight restored, no browser/mounts or held lock ({time.monotonic()-started:.2f}s)')


if __name__ == '__main__':
    main()
