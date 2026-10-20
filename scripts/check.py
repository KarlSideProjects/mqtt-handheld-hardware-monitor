#!/usr/bin/env python3
"""Run only platform-neutral checks; live hardware tests require check_device.py."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / 'browser'
LOCAL_TESTS = (
    'test_install.py',
    'test_trimui_browser.py',
    'test_trimui_power.py',
    'test_monitor.py',
    'test_monitor_events.py',
    'test_pve.py',
    'test_menu.py',
    'test_device_info.py',
    'test_check_runner.py',
)


def run(command, *, env=None, timeout=120):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(command, cwd=BROWSER, env=env, timeout=timeout, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', action='store_true', help='also check both handheld browser viewports')
    args = parser.parse_args()

    for test in LOCAL_TESTS:
        run([sys.executable, test])
    run(['node', 'test_monitor_ui.cjs'])
    for script in sorted(BROWSER.glob('*.sh')):
        run(['bash', '-n', str(script)])
    if args.layout:
        for width, height in ((1024, 768), (1280, 720)):
            env = dict(os.environ, MONITOR_VIEWPORT=f'{{"width":{width},"height":{height}}}')
            run(['node', 'test_monitor_layout.cjs'], env=env)


if __name__ == '__main__':
    main()
