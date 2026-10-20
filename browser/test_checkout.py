"""Checkout facts come from real Git repositories, including fetched divergence."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import checkout


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.origin, self.writer, self.clone = (self.root / n for n in ('origin', 'writer', 'clone'))
        subprocess.run(['git', 'init', '--bare', '--initial-branch=master', str(self.origin)], check=True, capture_output=True)
        subprocess.run(['git', 'clone', str(self.origin), str(self.writer)], check=True, capture_output=True)
        git(self.writer, 'config', 'user.email', 'tests@example.invalid')
        git(self.writer, 'config', 'user.name', 'Test')
        self.commit('one')
        git(self.writer, 'push', 'origin', 'master')
        subprocess.run(['git', 'clone', str(self.origin), str(self.clone)], check=True, capture_output=True)

    def commit(self, value):
        (self.writer / 'source').write_text(value)
        git(self.writer, 'add', 'source')
        git(self.writer, 'commit', '-m', value)

    def test_fetch_reports_actual_default_branch_and_stale_checkout(self):
        self.commit('two')
        git(self.writer, 'push', 'origin', 'master')
        cached = checkout.inspect_checkout(self.clone)
        self.assertEqual(cached['refs_source'], 'local_cache')
        self.assertEqual(cached['behind'], 0)
        result = checkout.inspect_checkout(self.clone, fetch=True)
        self.assertEqual(result['default_ref'], 'origin/master')
        self.assertEqual((result['ahead'], result['behind']), (0, 1))
        self.assertEqual(result['refs_source'], 'fetched')
        self.assertEqual(git(self.clone, 'rev-parse', 'HEAD'), cached['head'])

    def test_fetch_refreshes_a_changed_remote_default_branch(self):
        git(self.writer, 'branch', 'main')
        git(self.writer, 'push', 'origin', 'main')
        git(self.origin, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        result = checkout.inspect_checkout(self.clone, fetch=True)
        self.assertEqual(result['default_ref'], 'origin/main')

    def test_dirty_and_detached_are_reported_without_changing_files(self):
        git(self.clone, 'checkout', '--detach')
        (self.clone / 'untracked-private').write_text('secret')
        result = checkout.inspect_checkout(self.clone)
        self.assertIsNone(result['branch'])
        self.assertTrue(result['dirty'])
        self.assertEqual(result['changed_paths'], 1)
        self.assertNotIn('secret', str(result))
        self.assertNotIn('untracked-private', str(result))
        self.assertEqual((self.clone / 'untracked-private').read_text(), 'secret')

    def test_unknown_default_and_failed_fetch_do_not_invent_current_status(self):
        git(self.clone, 'symbolic-ref', '--delete', 'refs/remotes/origin/HEAD')
        result = checkout.inspect_checkout(self.clone)
        self.assertIsNone(result['default_ref'])
        self.assertIsNone(result['behind'])
        git(self.clone, 'remote', 'set-url', 'origin', str(self.root / 'missing'))
        with self.assertRaisesRegex(checkout.CheckoutError, 'fetch_failed'):
            checkout.inspect_checkout(self.clone, fetch=True)


if __name__ == '__main__':
    unittest.main()
