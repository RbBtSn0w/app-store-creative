"""Copied storage stays inactive until exact switch evidence is present."""
import hashlib
import unittest
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import canonical


class RelocationActivationTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def pending(self):
        self.store.start_run({})
        binding = self.store.paths.binding(); key = hashlib.sha256(canonical(binding)).hexdigest()
        receipt = {'schema_version': 1, 'created_at': '2026-10-03T00:00:00+00:00', 'id': 'move', 'status': 'SWITCHED', 'to': binding,
                   'config_path': str(self.store.config_path), 'project_id': self.cfg['project']['id']}
        self.store._record('storage-activations', {'id': key, 'to': binding, 'relocation_id': 'move',
            'switch_sha256': hashlib.sha256(canonical(receipt)).hexdigest()})
        return receipt

    def test_pending_destination_rejects_production_and_cleanup(self):
        self.pending()
        with self.assertRaisesRegex(ValueError, 'inactive'):
            self.store.start_run({})
        with self.assertRaisesRegex(ValueError, 'inactive'):
            self.store.plan_cleanup()

    def test_matching_receipt_activates_destination(self):
        receipt = self.pending(); self.store._record('relocations', receipt, 'switched')
        self.store.start_run({})

    def test_changed_receipt_cannot_activate_destination(self):
        receipt = self.pending(); receipt['project_id'] = 'other'
        self.store._record('relocations', receipt, 'switched')
        with self.assertRaisesRegex(ValueError, 'inactive'):
            self.store.start_run({})

    def test_retained_workspace_rejects_new_binding_before_activation_install(self):
        from artifact_lifecycle import Lifecycle
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'objectRoot': 'future objects'}}
        target = Lifecycle(self.root, cfg)
        self.store._record('relocations', {'id': 'pending-switch',
            'receipt': {'to': target.paths.binding()}}, 'switch-intent')
        with self.assertRaisesRegex(ValueError, 'inactive'):
            target.start_run({})
        self.assertFalse(target.paths.objects.exists())
