"""Git archive recovery is proven through an independent clone."""
from pathlib import Path
import shutil
import unittest
import test_publication_lifecycle as fixtures


class GitArchiveRetrievalTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_clean_clone_retrieves_package_even_when_worktree_copy_is_missing(self):
        from delivery_lifecycle import verify_git_archive
        commit = self.persist(); relative = Path(self.delivery['local_path']).relative_to(self.root).as_posix()
        shutil.rmtree(self.delivery['local_path'])
        result = verify_git_archive(self.root, commit, relative, self.delivery['manifest_sha256'])
        self.assertTrue(result['retrieval_verified'])
        self.assertEqual(result['archive_commit'], commit)
        self.assertFalse(Path(self.delivery['local_path']).exists())

    def test_uncommitted_archive_cannot_pass_retrieval(self):
        from delivery_lifecycle import verify_git_archive
        self.persist()
        with self.assertRaises(ValueError):
            verify_git_archive(self.root, self.git('rev-parse', 'HEAD'), 'untracked/archive', self.delivery['manifest_sha256'])
