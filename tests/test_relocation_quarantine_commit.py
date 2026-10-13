"""Quarantine commits preserve original identities and support interrupted recovery."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_quarantine_preparation as fixtures


class RelocationQuarantineCommitTests(unittest.TestCase):
    setUp = fixtures.RelocationQuarantinePreparationTests.setUp
    source = fixtures.RelocationQuarantinePreparationTests.source
    targets = fixtures.RelocationQuarantinePreparationTests.targets
    prepared = fixtures.RelocationQuarantinePreparationTests.prepared
    moved = fixtures.RelocationQuarantinePreparationTests.moved
    planned = fixtures.RelocationQuarantinePreparationTests.planned

    def staged(self):
        active, plan, artifact = self.planned()
        receipt = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Prepare')
        return active, receipt, artifact

    def test_commit_and_restore_keep_original_identity(self):
        active, receipt, artifact = self.staged()
        source = self.store.object_path(artifact['sha256']); inode = source.stat().st_ino
        result = active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        self.assertEqual(result['status'], 'QUARANTINED'); self.assertFalse(source.exists())
        active.verify_artifact(artifact['id'])
        restored = active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertEqual(restored['status'], 'RESTORED'); self.assertEqual(source.stat().st_ino, inode)
        self.assertEqual(active.restore_relocation_quarantine(receipt['id'], 'owner', 'Retry'), restored)

    def test_stale_references_refuse_before_source_removal(self):
        active, receipt, artifact = self.staged(); active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_after_move_interruption_can_resume(self):
        active, receipt, artifact = self.staged()
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'quarantined':
                raise OSError('Receipt interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaisesRegex(OSError, 'Receipt interrupted'):
                active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        self.assertFalse(self.store.object_path(artifact['sha256']).exists())
        result = active.commit_relocation_quarantine(receipt['id'], 'owner', 'Resume')
        self.assertEqual(result['status'], 'QUARANTINED')
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_restore_never_overwrites_foreign_source(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        source = self.store.object_path(artifact['sha256']); source.write_bytes(b'Owner data')
        with self.assertRaises(ValueError):
            active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertEqual(source.read_bytes(), b'Owner data')

    def test_restore_allows_new_references_after_commit(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies'); active.start_run({})
        self.assertEqual(active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')['status'], 'RESTORED')

    def test_inventory_reports_commit_and_restore_phases(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        row = active.inventory()['quarantine_preparations']['operations'][0]
        self.assertEqual(row['phase'], 'QUARANTINED'); self.assertTrue(row['source_removal_executed'])
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        row = active.inventory()['quarantine_preparations']['operations'][0]
        self.assertEqual(row['phase'], 'RESTORED'); self.assertFalse(row['source_removal_executed'])

    def test_restore_after_receipt_interruption_resumes(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'restored': raise OSError('Restore receipt interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaisesRegex(OSError, 'Restore receipt interrupted'):
                active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())
        self.assertEqual(active.restore_relocation_quarantine(receipt['id'], 'owner', 'Resume')['status'], 'RESTORED')

    def test_completed_commit_retries_after_new_run_without_mutation(self):
        active, receipt, artifact = self.staged()
        result = active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        active.start_run({})
        self.assertEqual(active.commit_relocation_quarantine(receipt['id'], 'owner', 'Retry'), result)

    def test_commit_intent_tampering_refuses_restore(self):
        import json
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        path = active._path('maintenance', receipt['id'], 'commit-intent')
        data = json.loads(path.read_text()); data['actor'] = 'Edited'; path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'evidence differs'):
            active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertFalse(self.store.object_path(artifact['sha256']).exists())

    def test_commit_reserved_path_collision_keeps_source(self):
        active, receipt, artifact = self.staged()
        source = self.store.object_path(artifact['sha256'])
        reserved = source.with_name(f".creative-quarantine-{receipt['id']}-0"); reserved.write_bytes(b'Keep')
        with self.assertRaises(ValueError):
            active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        self.assertTrue(source.exists()); self.assertEqual(reserved.read_bytes(), b'Keep')

    def test_partial_multi_file_commit_restores_after_reference_change(self):
        def sources():
            for content in (b'first snapshot', b'second snapshot'):
                run = self.store.start_run({}); attempt = self.store.start_attempt(run['id'], 'render', 'owner')
                path = self.store.work_path(attempt['id']) / 'source'; path.write_bytes(content)
                artifact = self.store.register(attempt['id'], path, 'source')
                self.store.finish_attempt(attempt['id'], 'failed', reason='Unused')
            return artifact
        self.source = sources
        active, receipt, artifact = self.staged()
        import quarantine_commit
        original = quarantine_commit._move; moved = False
        def move(*arguments):
            nonlocal moved
            original(*arguments)
            if not moved:
                moved = True; raise OSError('First move interrupted')
        with patch('quarantine_commit._move', side_effect=move):
            with self.assertRaisesRegex(OSError, 'First move interrupted'):
                active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        intent = active._read('maintenance', receipt['id'], 'commit-intent')
        self.assertEqual(sum(Path(item['source']['path']).exists() for item in intent['files']), 1)
        active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.commit_relocation_quarantine(receipt['id'], 'owner', 'Resume')
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertTrue(all(Path(item['source']['path']).exists() for item in intent['files']))
        self.assertTrue(all(not Path(item['retained_path']).exists() for item in intent['files']))

    def test_restore_reenables_reverse_relocation(self):
        active, receipt, artifact = self.staged()
        operation = active._read('maintenance', receipt['id'])
        move_id = operation['files'][0]['relocation_id']
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        with self.assertRaises(ValueError):
            active.plan_reverse_relocation(move_id)
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        reverse = active.plan_reverse_relocation(move_id)
        self.assertEqual(reverse['forward_id'], move_id)
