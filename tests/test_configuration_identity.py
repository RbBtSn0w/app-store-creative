"""Approval content identity excludes local placement but retains recipe inputs."""
import copy
import unittest
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import Lifecycle


class ConfigurationIdentityTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_storage_changes_preserve_content_identity(self):
        first = self.store.start_run({})
        cfg = copy.deepcopy(self.cfg)
        cfg['storage'] = {'workspaceRoot': 'elsewhere', 'releaseRoot': 'archives', 'publicationRoot': 'handoffs'}
        second = Lifecycle(self.root, cfg).start_run({})
        self.assertEqual(first['config_sha256'], second['config_sha256'])
        self.assertNotEqual(first['config_snapshot_sha256'], second['config_snapshot_sha256'])
        self.assertNotEqual(first['storage'], second['storage'])

    def test_recipe_changes_invalidate_content_identity(self):
        first = self.store.start_run({})
        self.store.config['headline'] = 'New product promise'
        second = self.store.start_run({})
        self.assertNotEqual(first['config_sha256'], second['config_sha256'])

    def test_storage_change_still_requires_explicit_relocation(self):
        first = self.store.start_run({})
        changed = copy.deepcopy(self.cfg); changed['storage']['objectRoot'] = 'moved objects'
        with self.assertRaisesRegex(ValueError, 'relocate'):
            Lifecycle(self.root, changed)._run(first['id'])


class ApprovalPlacementTests(unittest.TestCase):
    def test_equivalent_absolute_placement_preserves_approved_seal(self):
        from test_delivery_lifecycle import DeliveryLifecycleTests
        fixture = DeliveryLifecycleTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        validation, approval = fixture.approved()
        cfg = copy.deepcopy(fixture.config)
        binding = fixture.store.paths.binding()
        cfg['storage'] = {key: binding[label] for key, label in [
            ('workspaceRoot', 'workspace'), ('objectRoot', 'objects'),
            ('releaseRoot', 'releases'), ('publicationRoot', 'publications')]}
        relocated = Lifecycle(fixture.root, cfg)
        delivery = relocated.seal(fixture.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(delivery['approval_id'], approval['id'])
