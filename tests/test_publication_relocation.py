"""Local archive moves retain the original Git commit location."""
import hashlib
from pathlib import Path
import unittest
import test_publication_lifecycle as fixtures
from artifact_lifecycle import Lifecycle, canonical


class PublicationRelocationTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_moved_package_uses_original_git_archive_path(self):
        commit = self.persist(); old = self.store.paths.binding()
        original = self.store._path('deliveries', self.delivery['id']).read_bytes()
        moved = self.root / 'relocated archives'; Path(old['releases']).rename(moved)
        cfg = {**self.config, 'storage': {'releaseRoot': str(moved)}}
        store = Lifecycle(self.root, cfg); new = store.paths.binding()
        switched = store._record('relocations', {'id': 'move', 'status': 'SWITCHED',
            'from': old, 'to': new, 'project_id': self.config['project']['id'],
            'config_path': str(store.config_path)}, 'switched')
        store._record('storage-bindings', {'id': hashlib.sha256(canonical(old)).hexdigest(),
            'from': old, 'to': new, 'relocation_id': 'move',
            'switch_sha256': hashlib.sha256(canonical(switched)).hexdigest()})
        plan = store.plan_publication(self.delivery['id'], commit, self.target)
        self.assertTrue(plan['archive_path'].startswith('creative-releases/'))
        store.approve_upload(plan['id'], 'owner', 'human:approved')
        self.assertTrue(store.publication_status(plan['id'])['archive_verified'])
        self.assertEqual(store._path('deliveries', self.delivery['id']).read_bytes(), original)
