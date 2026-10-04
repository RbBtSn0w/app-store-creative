"""Object ownership follows verified bindings without rewriting owner metadata."""
import hashlib
from pathlib import Path
import unittest
import test_relocation_lifecycle as fixtures
from artifact_lifecycle import Lifecycle, canonical


class ObjectOwnershipRelocationTests(unittest.TestCase):
    setUp = fixtures.RelocationTests.setUp
    source = fixtures.RelocationTests.source

    def test_workspace_move_keeps_object_owner_immutable(self):
        self.source(); old = self.store.paths.binding()
        owner = self.store.paths.objects / '_owner.json'; before = owner.read_bytes()
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'workspaceRoot': 'new workspace'}}
        moved = Lifecycle(self.root, cfg); new = moved.paths.binding()
        switched = moved._record('relocations', {'id': 'move', 'status': 'SWITCHED',
            'from': old, 'to': new, 'config_path': str(moved.config_path),
            'project_id': self.cfg['project']['id']}, 'switched')
        moved._record('storage-bindings', {'id': hashlib.sha256(canonical(old)).hexdigest(),
            'from': old, 'to': new, 'relocation_id': 'move',
            'switch_sha256': hashlib.sha256(canonical(switched)).hexdigest()})
        run = moved.start_run({}); attempt = moved.start_attempt(run['id'], 'render', 'agent')
        source = moved.work_path(attempt['id']) / 'source'; source.write_bytes(b'new render')
        artifact = moved.register(attempt['id'], source, 'source')
        moved.verify_artifact(artifact['id'])
        self.assertEqual(owner.read_bytes(), before)

    def test_workspace_change_without_move_evidence_cannot_claim_objects(self):
        self.source()
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'workspaceRoot': 'other workspace'}}
        other = Lifecycle(self.root, cfg)
        with self.assertRaisesRegex(ValueError, 'owned|shared'):
            other._claim_objects()
