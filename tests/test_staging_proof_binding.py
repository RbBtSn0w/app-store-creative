"""Prepared receipts pin creation proofs independently of current directories."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import test_relocation_switch as fixtures
from artifact_lifecycle import canonical


class StagingProofBindingTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def replace(self, plan, published=False):
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        group = 'objects'
        root = Path(plan['to'][group] if published else prepared['staging'][group])
        original = root.with_name(root.name + '-original'); root.rename(original); shutil.copytree(original, root)
        path = self.store._path('relocations', plan['id'], 'staging-root-' + group)
        proof = json.loads(path.read_text()); info = root.stat()
        proof['directory_identity'] = [info.st_dev, info.st_ino]; path.write_bytes(canonical(proof))

    def test_replaced_root_and_rewritten_proof_refuse_initial_switch(self):
        artifact, plan = self.prepared(); self.replace(plan)
        before = self.store.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'proof.*hash'):
            self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.store.start_run({})

    def test_shared_workspace_refuses_rewritten_proof_during_resume(self):
        self.targets = lambda: {**self.cfg['storage'], 'objectRoot': 'new objects'}
        artifact, plan = self.prepared()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Sync interrupted'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.replace(plan, published=True)
        with self.assertRaisesRegex(ValueError, 'proof.*hash'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'switched').exists())

    def test_inventory_refuses_rewritten_identity_proof(self):
        artifact, plan = self.prepared(); self.replace(plan)
        report = self.store.inventory()['relocation_backups']
        self.assertTrue(any(row['relocation_id'] == plan['id'] and 'hash' in row['reason']
                            for row in report['unverified_operations']))
        self.assertFalse(any(row['relocation_id'] == plan['id'] and row['status'] == 'VERIFIED'
                             for row in report['staging']))

    def test_reverse_recovery_refuses_rewritten_proof(self):
        import test_reverse_relocation_switch as reverse_fixtures
        fixture = reverse_fixtures.ReverseRelocationSwitchTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        artifact, forward, moved, reverse, run = fixture.reverse()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Sync interrupted'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        path = moved._path('relocations', reverse['id'], 'staging-root-objects')
        proof = json.loads(path.read_text()); proof['directory_identity'][1] += 1
        path.write_bytes(canonical(proof))
        before = moved.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'proof.*hash'):
            moved.resume_reverse_relocation(reverse['id'], 'owner', 'Resume')
        with self.assertRaisesRegex(ValueError, 'proof.*hash'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
        self.assertEqual(moved.config_path.read_bytes(), before)
