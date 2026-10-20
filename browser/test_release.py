"""A release binds successful checks and a Docker image to committed source."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init')
        git(self.repo, 'config', 'user.name', 'Test')
        git(self.repo, 'config', 'user.email', 'test@example.invalid')
        (self.repo / 'Dockerfile').write_text('FROM scratch\n')
        (self.repo / 'source').write_text('tested source')
        (self.repo / '.gitignore').write_text('.env\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'fixture')
        (self.repo / '.env').write_text('SECRET=private-secret')
        self.output = self.base / 'release'
        bindir = self.base / 'bin'
        bindir.mkdir()
        docker = bindir / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
if args[0]=='build':
 sys.stdin.buffer.read()
 if os.environ.get('FAIL_BUILD'): raise SystemExit(2)
 label=args[args.index('--label')+1].split('=',1)[1]
 Path(os.environ['DOCKER_TEST_REVISION']).write_text(label)
 Path(args[args.index('--iidfile')+1]).write_text('sha256:'+'a'*64)
 print('private build detail')
elif args[:2]==['image','inspect']:
 rev=Path(os.environ['DOCKER_TEST_REVISION']).read_text()
 print(json.dumps([{'Id':'sha256:'+'a'*64,'Config':{'Labels':{'org.opencontainers.image.revision':rev},'Env':['SECRET=private-secret']}}]))
else: raise SystemExit(3)
''')
        docker.chmod(0o755)
        self.env = patch.dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], DOCKER_TEST_REVISION=str(self.base/'revision'))
        self.env.start()
        self.addCleanup(self.env.stop)

    def build(self, command=None):
        return release.build_release(self.repo, 'monitor:test', self.output,
                                     command or [sys.executable, '-c', 'print("checks passed")'])

    def test_manifest_archive_and_image_share_checked_commit_without_env_secrets(self):
        result = self.build()
        revision = git(self.repo, 'rev-parse', 'HEAD')
        self.assertEqual(result['source_commit'], revision)
        self.assertEqual(result['checks']['source_commit'], revision)
        self.assertEqual(result['image']['id'], 'sha256:'+'a'*64)
        self.assertEqual(result['image']['source_commit'], revision)
        self.assertEqual(json.loads((self.output/'manifest.json').read_text()), result)
        with tarfile.open(self.output/'source.tar') as archive:
            self.assertNotIn('.env', archive.getnames())
            self.assertEqual(archive.extractfile('source').read(), b'tested source')
        self.assertNotIn('private-secret', json.dumps(result))
        for path in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)

    def test_dirty_source_is_rejected_before_running_checks(self):
        (self.repo/'source').write_text('uncommitted')
        with self.assertRaisesRegex(release.ReleaseError, 'dirty_checkout'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_failed_or_mutating_checks_never_produce_success_manifest(self):
        with self.assertRaisesRegex(release.ReleaseError, 'checks_failed'):
            self.build([sys.executable, '-c', 'raise SystemExit(1)'])
        self.assertFalse((self.output/'manifest.json').exists())
        self.output = self.base/'mutated'
        with self.assertRaisesRegex(release.ReleaseError, 'source_changed_during_checks'):
            self.build([sys.executable, '-c', 'from pathlib import Path; Path("source").write_text("changed")'])
        self.assertFalse((self.output/'manifest.json').exists())

    def test_failed_build_and_existing_output_cannot_be_labelled_successful(self):
        with patch.dict(os.environ, FAIL_BUILD='1'), self.assertRaisesRegex(release.ReleaseError, 'build_failed'):
            self.build()
        self.assertFalse((self.output/'manifest.json').exists())
        with self.assertRaisesRegex(release.ReleaseError, 'output_exists'):
            self.build()


if __name__ == '__main__':
    unittest.main()
