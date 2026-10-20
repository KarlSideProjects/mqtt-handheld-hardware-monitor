#!/usr/bin/env python3
"""Diagnose or update a running handheld UI over authenticated SSH."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'browser'))
from device_ops import OpsError, make_release


def ssh_command(device, host, user=None, identity=None, password=False):
    user = user or ('ark' if device == 'r36' else 'root')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', host) or not re.fullmatch(r'[A-Za-z0-9_-]+', user):
        raise OpsError('invalid_ssh_destination')
    command = ['ssh', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'NumberOfPasswordPrompts=1', '-o', 'BatchMode=' + ('no' if password else 'yes')]
    if identity:
        command += ['-i', str(Path(identity).expanduser().resolve()), '-o', 'IdentitiesOnly=yes']
    return command + [user + '@' + host]


@contextlib.contextmanager
def ssh_environment():
    env = dict(os.environ)
    if not env.get('HWMONITOR_SSH_PASSWORD'):
        yield env
        return
    with tempfile.TemporaryDirectory(prefix='hwmonitor-ssh.') as directory:
        askpass = Path(directory) / 'askpass'
        askpass.write_text('#!/bin/sh\nprintf "%s\\n" "$HWMONITOR_SSH_PASSWORD"\n')
        askpass.chmod(0o700)
        env.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE='force', DISPLAY=env.get('DISPLAY', 'hwmonitor:0'))
        yield env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('diagnose', 'update'))
    parser.add_argument('--device', choices=('r36', 'trimui'), required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--user')
    parser.add_argument('--identity', help='SSH private-key path; key contents are never read by this tool')
    args = parser.parse_args(argv)
    try:
        request = {'action': args.action, 'device': args.device}
        if args.action == 'update':
            request['release'] = make_release(ROOT / 'browser', args.device)
        with ssh_environment() as env:
            command = ssh_command(args.device, args.host, args.user, args.identity,
                                  bool(env.get('HWMONITOR_SSH_PASSWORD')))
            source = (ROOT / 'browser/device_ops.py').read_text() + '\nremote_main()\n'
            result = subprocess.run(command + ['python3 -c ' + shlex.quote(source)],
                                    input=json.dumps(request), capture_output=True, text=True, env=env, timeout=75)
        try:
            response = json.loads(result.stdout)
        except ValueError:
            raise OpsError('ssh_or_remote_python_failed') from None
        if not isinstance(response, dict) or not isinstance(response.get('ok'), bool):
            raise OpsError('invalid_remote_response')
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if result.returncode == 0 and response['ok'] else 1
    except (OpsError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'ok': False, 'error': error.code if isinstance(error, OpsError) else 'ssh_unavailable_or_timeout'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
