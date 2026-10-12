"""Configured remote retrieval proves uploaded Git commit availability."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_publication_lifecycle as fixtures
from delivery_lifecycle import verify_git_archive


class GitRemoteRetrievalTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def remote(self):
        commit = self.persist()
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        remote = Path(directory.name).resolve() / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '--quiet', str(remote)], check=True)
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '--quiet', 'origin', 'HEAD:refs/heads/main')
        subprocess.run(['git', '-C', str(remote), 'symbolic-ref', 'HEAD', 'refs/heads/main'], check=True)
        return commit

    def verify(self, commit):
        relative = Path(self.delivery['local_path']).relative_to(self.root).as_posix()
        return verify_git_archive(self.root, commit, relative, self.delivery['manifest_sha256'], remote='origin')

    def test_pushed_commit_is_retrievable_from_configured_remote(self):
        result = self.verify(self.remote())
        self.assertTrue(result['retrieval_verified'])
        self.assertEqual(result['source_scope'], 'configured-remote')
        self.assertEqual(result['remote_name'], 'origin')
        self.assertNotIn('remote.git', str(result))

    def test_local_unpushed_commit_is_not_remote_proof(self):
        self.remote()
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '--quiet', '-m', 'test: local only')
        with self.assertRaisesRegex(ValueError, 'retrieval failed'):
            self.verify(self.git('rev-parse', 'HEAD'))

    def test_publication_plan_preserves_remote_retrieval_scope(self):
        commit = self.remote()
        plan = self.store.plan_publication(self.delivery['id'], commit, self.target, archive_remote='origin')
        self.assertEqual(plan['archive_remote'], 'origin')
        self.assertEqual(plan['retrieval_proof']['source_scope'], 'configured-remote')
        self.assertTrue(self.store.publication_status(plan['id'])['retrieval_verified'])
