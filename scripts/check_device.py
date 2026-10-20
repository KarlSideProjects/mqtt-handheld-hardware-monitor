#!/usr/bin/env python3
"""Explicitly run a bounded hardware test after a read-only device preflight."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / 'browser'
TESTS = {
    ('r36', 'awake'): ('test_awake.py',),
    ('trimui', 'screen'): ('test_trimui_screen.py',),
    ('trimui', 'exit'): ('test_trimui_exit.py',),
}


class PreflightError(RuntimeError):
    pass


def status():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8766/status', timeout=3) as response:
            return json.load(response)
    except (OSError, ValueError) as error:
        raise PreflightError(f'monitor status unavailable at 127.0.0.1:8766 ({error})') from error


def r36_device():
    if platform.machine() != 'aarch64':
        return False
    try:
        release = {}
        for line in Path('/etc/os-release').read_text().splitlines():
            key, separator, value = line.partition('=')
            if separator:
                release[key] = value.strip().strip('"').strip("'")
    except OSError:
        return False
    return (release.get('VERSION_ID') == '13'
            and (release.get('ID') == 'debian' or 'debian' in release.get('ID_LIKE', '').split())
            and Path('/dev/input/by-path/platform-odroidgo3-joypad-event-joystick').exists()
            and Path('/sys/class/backlight/backlight/brightness').exists())


def trimui_dashboard_running():
    result = subprocess.run(['pgrep', '-af', 'trimui_browser.py'], capture_output=True, text=True, check=False)
    return result.returncode == 0 and any(re.search(
        r'^\d+\s+(?:\S*/)?python3\s+.*runtime/trimui_browser\.py(?:\s|$)', line
    ) for line in result.stdout.splitlines())


def require(path, description, *, writable=False):
    path = Path(path)
    if not path.exists() or (writable and not os.access(path, os.W_OK)):
        raise PreflightError(f'missing {description}: {path}')


def preflight(device, test):
    expected_name = {'r36': 'R36', 'trimui': 'TrimUI'}[device]
    state = status()
    local = state.get('device')
    actual_name = local.get('name') if isinstance(local, dict) else None
    if device == 'trimui' and actual_name != 'TrimUI':
        raise PreflightError(f"wrong device: expected TrimUI, monitor reports {actual_name or 'unknown'}")
    if device == 'r36':
        if actual_name not in (None, '', 'R36'):
            raise PreflightError(f'wrong device: expected R36, monitor reports {actual_name}')
        if not r36_device():
            raise PreflightError('expected R36 handheld: requires aarch64 Debian 13, the Odroid gamepad path, and R36 backlight')
    if state.get('connection') != 'Connected' or state.get('count', 0) < 1:
        raise PreflightError(f'{expected_name} monitor is offline or has no online hosts')
    if device == 'trimui' and platform.machine() != 'aarch64':
        raise PreflightError(f'TrimUI hardware tests require aarch64, got {platform.machine()}')

    if test == 'awake':
        for command in ('xset', 'systemd-inhibit'):
            if not shutil.which(command):
                raise PreflightError(f'missing prerequisite command: {command}')
        require('/sys/class/backlight/backlight/brightness', 'R36 backlight brightness')
        if subprocess.run(['xset', '-display', ':0', 'q'], capture_output=True, timeout=4, check=False).returncode:
            raise PreflightError('R36 X display :0 is unavailable')
        inhibitors = subprocess.run(['systemd-inhibit', '--list', '--no-pager'], capture_output=True, text=True, timeout=4, check=False)
        if inhibitors.returncode or 'HardwareMonitor' not in inhibitors.stdout:
            raise PreflightError('HardwareMonitor sleep/idle inhibitor is missing')
    if test in ('screen', 'exit'):
        events = list(Path('/sys/class/input').glob('event*/device/name'))
        gamepad = next((path for path in events if path.is_file() and path.read_text().strip() == 'TRIMUI Player1'), None)
        if gamepad is None:
            raise PreflightError('TRIMUI Player1 input device not found')
        require(Path('/dev/input') / gamepad.parents[1].name, 'TRIMUI input device', writable=True)
        if test == 'screen':
            if state.get('screen_off'):
                raise PreflightError('TrimUI dashboard must start with the screen awake')
            require('/sys/kernel/debug/dri/0/state', 'DRM state (debugfs must be mounted)')
            require('/sys/class/drm/card0-DSI-1/dpms', 'DSI DPMS state')
            require('/sys/class/backlight/backlight0/brightness', 'TrimUI backlight brightness')
        else:
            if not trimui_dashboard_running():
                raise PreflightError('TrimUI dashboard process is not running')
            require('/sys/class/backlight/backlight0/brightness', 'TrimUI backlight brightness')

    print(f'Preflight passed: {expected_name}, {platform.system()} {platform.release()}, '
          f'{platform.machine()}, {test}', flush=True)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=('r36', 'trimui'), required=True)
    parser.add_argument('--test', choices=('awake', 'screen', 'exit'), required=True)
    parser.add_argument('--expected-brightness', type=int)
    parser.add_argument('--allow-destructive-exit', action='store_true',
                        help='required because exit closes the running monitor and restores the stock menu')
    args = parser.parse_args()
    if (args.device, args.test) not in TESTS:
        parser.error(f'{args.test} is not supported on {args.device}')
    if args.test == 'exit' and not args.allow_destructive_exit:
        parser.error('exit closes the running monitor; pass --allow-destructive-exit explicitly')
    if args.test == 'exit' and (args.expected_brightness is None or args.expected_brightness < 0):
        parser.error('--expected-brightness must be a non-negative integer for exit')

    try:
        preflight(args.device, args.test)
        command = [sys.executable, *TESTS[(args.device, args.test)]]
        if args.test == 'exit':
            command.extend(('--expected-brightness', str(args.expected_brightness)))
        subprocess.run(command, cwd=BROWSER, timeout=60, check=True)
    except (PreflightError, subprocess.SubprocessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
