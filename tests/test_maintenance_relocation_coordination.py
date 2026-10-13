"""Storage relocation cannot orphan unfinished maintenance operations."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_quarantine_commit as fixtures


class MaintenanceRelocationCoordinationTests(unittest.TestCase):
    setUp = fixtures.RelocationQuarantineCommitTests.setUp
    source = fixtures.RelocationQuarantineCommitTests.source
    targets = fixtures.RelocationQuarantineCommitTests.targets
    prepared = fixtures.RelocationQuarantineCommitTests.prepared
    moved = fixtures.RelocationQuarantineCommitTests.moved
    planned = fixtures.RelocationQuarantineCommitTests.planned
    staged = fixtures.RelocationQuarantineCommitTests.staged

    def next_roots(self):
        return {'workspaceRoot': 'third work', 'objectRoot': 'third objects',
                'releaseRoot': 'third releases', 'publicationRoot': 'third publications'}

    def test_prepared_quarantine_blocks_forward_and_reverse_plans(self):
        active, receipt, artifact = self.staged()
        before = active.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unfinished maintenance'):
            active.plan_relocation(self.next_roots())
        move_id = active._read('maintenance', receipt['id'])['files'][0]['relocation_id']
        with self.assertRaisesRegex(ValueError, 'unfinished maintenance'):
            active.plan_reverse_relocation(move_id)
        self.assertEqual(active.config_path.read_bytes(), before)
        self.assertFalse((self.root / 'third work').exists())

    def test_new_quarantine_invalidates_existing_relocation_plan_before_copy(self):
        active, move, artifact = self.moved()
        plan = active.plan_relocation(self.next_roots())
        retention = active.plan_relocation_retention(retention_days=0)
        active.prepare_relocation_quarantine(retention['id'], 'owner', 'Prepare')
        with self.assertRaisesRegex(ValueError, 'unfinished maintenance'):
            active.prepare_relocation(plan['id'], 'owner', 'Move')
        self.assertFalse((self.root / 'third work').exists())

    def test_cancelled_preparation_unblocks_relocation_without_deleting_bytes(self):
        active, receipt, artifact = self.staged()
        payload = Path(receipt['copies'][0]['quarantine_path']); before = payload.read_bytes()
        cancelled = active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Keep existing roots')
        self.assertEqual(cancelled['status'], 'CANCELLED'); self.assertEqual(payload.read_bytes(), before)
        self.assertEqual(active.inventory()['quarantine_preparations']['operations'][0]['phase'], 'CANCELLED')
        self.assertEqual(active.plan_relocation(self.next_roots())['operation'], 'relocation-plan')
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            active.commit_relocation_quarantine(receipt['id'], 'owner', 'Commit')
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            active.resume_relocation_quarantine_preparation(receipt['id'], 'owner', 'Resume')

    def test_completed_restore_unblocks_relocation(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired')
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        self.assertEqual(active.plan_relocation(self.next_roots())['operation'], 'relocation-plan')

    def test_started_purge_blocks_relocation(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired')
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'purge-file-0': raise OSError('Interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaises(OSError): active.purge_relocation(plan['id'], 'owner', 'Expired')
        with self.assertRaisesRegex(ValueError, 'unfinished maintenance'):
            active.plan_relocation(self.next_roots())

    def test_completed_purge_unblocks_relocation(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired')
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        active.purge_relocation(plan['id'], 'owner', 'Expired')
        self.assertEqual(active.plan_relocation(self.next_roots())['operation'], 'relocation-plan')

    def test_cancel_cannot_follow_commit_intent(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired')
        with self.assertRaisesRegex(ValueError, 'commit has started'):
            active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Cancel')
        self.assertFalse(active._path('maintenance', receipt['id'], 'preparation-cancelled').exists())

    def test_cancellation_is_idempotent_and_proof_tampering_blocks_relocation(self):
        import json
        active, receipt, artifact = self.staged()
        cancelled = active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Cancel')
        self.assertEqual(active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Retry'), cancelled)
        path = active._path('maintenance', receipt['id'], 'preparation-cancelled')
        data = json.loads(path.read_text()); data['operation_sha256'] = 'c' * 64; path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'cancellation evidence differs'):
            active.plan_relocation(self.next_roots())

    def test_completed_maintenance_proof_survives_successive_relocation_plans(self):
        from artifact_lifecycle import Lifecycle
        import json
        active, receipt, artifact = self.staged()
        active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Cancel')
        plan = active.plan_relocation(self.next_roots())
        active.prepare_relocation(plan['id'], 'owner', 'Move'); active.switch_relocation(plan['id'], 'owner', 'Move')
        moved = Lifecycle(self.root, json.loads(active.config_path.read_text()))
        fourth = {key: value.replace('third', 'fourth') for key, value in self.next_roots().items()}
        self.assertEqual(moved.plan_relocation(fourth)['operation'], 'relocation-plan')
        moved.verify_artifact(artifact['id'])

    def test_interrupted_preparation_can_cancel_while_retaining_partial_and_unknown_bytes(self):
        active, plan, artifact = self.planned()
        def partial(source, target):
            target.write(b'partial'); target.flush()
            raise OSError('Interrupted copy')
        with patch('relocation_quarantine.shutil.copyfileobj', side_effect=partial):
            with self.assertRaises(OSError):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Prepare')
        operation = next(active._read('maintenance', path.stem)
                         for path in (active.paths.workspace / 'records/maintenance').glob('*.json')
                         if active._read('maintenance', path.stem)['operation'] == 'relocation-quarantine')
        root = Path(operation['quarantine_root'])
        payload = next(root.iterdir()); note = root / 'owner-note'; note.write_bytes(b'Keep this note')
        active.cancel_relocation_quarantine_preparation(operation['id'], 'owner', 'Keep partial evidence')
        self.assertEqual(payload.read_bytes(), b'partial'); self.assertEqual(note.read_bytes(), b'Keep this note')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())
        row = active.inventory()['quarantine_preparations']['operations'][0]
        self.assertEqual(row['phase'], 'CANCELLED'); self.assertEqual(row['status'], 'CHANGED')
        self.assertEqual(active.plan_relocation(self.next_roots())['operation'], 'relocation-plan')
