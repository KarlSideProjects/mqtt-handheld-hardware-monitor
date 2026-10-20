#!/usr/bin/env python3
"""Check and build a fixed committed source archive; never deploy a container."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from checkout import CheckoutError, inspect_checkout


class ReleaseError(Exception):
    pass


def private_file(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb')


def build_release(repo, image, output, command):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if not command:
        raise ReleaseError('check_command_required')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._/:\-]*', image):
        raise ReleaseError('invalid_image_tag')
    initial = inspect_checkout(repo)
    if initial['dirty']:
        raise ReleaseError('dirty_checkout')
    if output == repo or repo in output.parents:
        raise ReleaseError('output_must_be_outside_checkout')
    try:
        output.mkdir(mode=0o700)
    except FileExistsError:
        raise ReleaseError('output_exists') from None
    revision = initial['head']
    with private_file(output / 'checks.log') as log:
        result = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    if result.returncode:
        raise ReleaseError('checks_failed')
    checked = inspect_checkout(repo)
    if checked['head'] != revision or checked['dirty']:
        raise ReleaseError('source_changed_during_checks')
    with private_file(output / 'source.tar') as archive:
        result = subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', revision],
                                stdout=archive, stderr=subprocess.PIPE, timeout=30)
    if result.returncode:
        raise ReleaseError('archive_failed')
    with (output / 'source.tar').open('rb') as archive, private_file(output / 'build.log') as log:
        result = subprocess.run(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + revision,
                                 '--iidfile', str(output / 'image.id'), '--tag', image, '-'],
                                stdin=archive, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    if result.returncode:
        raise ReleaseError('build_failed')
    image_file = output / 'image.id'
    image_file.chmod(0o600)
    image_id = image_file.read_text().strip()
    if not re.fullmatch('sha256:[a-f0-9]{64}', image_id):
        raise ReleaseError('invalid_image_id')
    result = subprocess.run(['docker', 'image', 'inspect', image_id], capture_output=True, text=True, timeout=30)
    try:
        metadata = json.loads(result.stdout)[0]
        if (result.returncode or metadata['Id'] != image_id or
                metadata['Config']['Labels']['org.opencontainers.image.revision'] != revision):
            raise ValueError()
    except (ValueError, TypeError, KeyError, IndexError):
        raise ReleaseError('image_revision_mismatch') from None
    def sha256(name):
        return hashlib.sha256((output / name).read_bytes()).hexdigest()
    manifest = {'version': 1, 'source_commit': revision, 'built_at': int(time.time()),
                'source_archive': {'file': 'source.tar', 'sha256': sha256('source.tar')},
                'checks': {'command': command, 'source_commit': revision, 'exit_code': 0,
                           'log': 'checks.log', 'sha256': sha256('checks.log')},
                'image': {'tag': image, 'id': image_id, 'source_commit': revision},
                'build_log': {'file': 'build.log', 'sha256': sha256('build.log')}, 'deployed': False}
    with private_file(output / 'manifest.json') as handle:
        handle.write((json.dumps(manifest, indent=2) + '\n').encode())
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True, help='new private output directory outside the checkout')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='check command following -- (never interpreted by a shell)')
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        manifest = build_release(args.repo, args.image, args.output, command)
        print(json.dumps({'ok': True, 'manifest': str(args.output / 'manifest.json'),
                          'source_commit': manifest['source_commit'], 'image_id': manifest['image']['id'],
                          'deployed': False}))
        return 0
    except (ReleaseError, CheckoutError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error) if isinstance(error, ReleaseError) else 'release_failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
