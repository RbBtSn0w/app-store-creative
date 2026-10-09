import unittest
from pathlib import Path
import test_publication_lifecycle as fixtures
from delivery_lifecycle import verify_git_archive

class RetrievalPolicyBinding(unittest.TestCase):
    archive_policy = {'schema_version': 1, 'mediaMode': 'lfs'}
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_independent_git_retrieval_rejects_declared_lfs_without_pointers(self):
        commit = self.persist()
        relative = Path(self.delivery['local_path']).relative_to(self.root).as_posix()
        with self.assertRaisesRegex(ValueError, 'archive policy'):
            verify_git_archive(self.root, commit, relative, self.delivery['manifest_sha256'])

