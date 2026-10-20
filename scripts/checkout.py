#!/usr/bin/env python3
"""Report checkout identity and divergence before making capability claims."""
import argparse
import json
from pathlib import Path
import subprocess


class CheckoutError(Exception):
    pass


def inspect_checkout(repo, fetch=False):
    repo = Path(repo).resolve()
    def git(*args, required=True):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, timeout=30)
        if result.returncode and required:
            raise CheckoutError('git_inspection_failed')
        return result.stdout.strip() if result.returncode == 0 else None
    if fetch:
        result = subprocess.run(['git', '-C', str(repo), 'fetch', '--quiet', 'origin'], capture_output=True, timeout=30)
        if result.returncode:
            raise CheckoutError('fetch_failed')
        result = subprocess.run(['git', '-C', str(repo), 'remote', 'set-head', 'origin', '--auto'],
                                capture_output=True, timeout=30)
        if result.returncode:
            raise CheckoutError('default_ref_unknown')
    head = git('rev-parse', 'HEAD')
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD', required=False)
    default_ref = git('symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD', required=False)
    ahead = behind = None
    if default_ref:
        ahead, behind = map(int, git('rev-list', '--left-right', '--count', f'HEAD...{default_ref}').split())
    changes = git('status', '--porcelain=v1', '-z')
    return {'head': head, 'branch': branch, 'default_ref': default_ref,
            'ahead': ahead, 'behind': behind, 'dirty': bool(changes),
            'changed_paths': len([part for part in changes.split('\0') if part]),
            'refs_source': 'fetched' if fetch else 'local_cache'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--fetch', action='store_true', help='refresh origin refs; never checkout, merge or modify work files')
    args = parser.parse_args(argv)
    try:
        print(json.dumps({'ok': True, **inspect_checkout(args.repo, args.fetch)}))
        return 0
    except (CheckoutError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'ok': False, 'error': str(error) if isinstance(error, CheckoutError) else 'git_inspection_failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
