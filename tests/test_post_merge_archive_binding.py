"""Squashed archives require a new publication scope and upload authorization."""
import subprocess
import unittest
import test_publication_lifecycle as fixtures


class PostMergeArchiveBindingTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git

    def test_squash_commit_rebinds_archive_without_reusing_upload_approval(self):
        self.git('init', '--quiet', '--initial-branch=main')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '--quiet', '--allow-empty', '-m', 'test: initial archive repository')
        self.git('checkout', '--quiet', '-b', 'archive-review')
        self.git('add', 'creative-releases')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '--quiet', '-m', 'test: review archive')
        review_commit = self.git('rev-parse', 'HEAD')
        previous = self.store.plan_publication(self.delivery['id'], review_commit, self.target)
        approval = self.store.approve_upload(previous['id'], 'fixture-owner', 'fixture:pre-merge-approval')
        approval_path = self.store._path('approvals', approval['id'])
        approval_bytes = approval_path.read_bytes()
        self.git('checkout', '--quiet', 'main')
        self.git('merge', '--quiet', '--squash', 'archive-review')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '--quiet', '-m', 'test: merge reviewed archive')
        merged_commit = self.git('rev-parse', 'HEAD')
        self.assertNotEqual(review_commit, merged_commit)
        remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--quiet', '--bare', str(remote)], check=True)
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '--quiet', 'origin', 'main')
        with self.assertRaises(ValueError):
            self.store.plan_publication(self.delivery['id'], review_commit, self.target, 'origin')
        merged = self.store.plan_publication(self.delivery['id'], merged_commit, self.target, 'origin')
        self.assertEqual(merged['manifest_sha256'], previous['manifest_sha256'])
        self.assertEqual(merged['archive_commit'], merged_commit)
        self.assertTrue(merged['retrieval_proof']['retrieval_verified'])
        self.assertEqual(self.store.export_publication(merged['id'])['upload_approval'], 'pending')
        self.assertFalse(self.store.publication_status(merged['id'])['remote_verified'])
        self.assertEqual(approval_path.read_bytes(), approval_bytes)
        self.assertEqual(self.store._read('publications', previous['id'], 'plan'), previous)
