"""Permanent removal is journaled, scoped and resumable only by the original plan."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_purge_plan as fixtures


class RelocationPurgeExecutionTests(unittest.TestCase):
    setUp = fixtures.RelocationPurgePlanTests.setUp
    source = fixtures.RelocationPurgePlanTests.source
    targets = fixtures.RelocationPurgePlanTests.targets
    prepared = fixtures.RelocationPurgePlanTests.prepared
    moved = fixtures.RelocationPurgePlanTests.moved
    planned = fixtures.RelocationPurgePlanTests.planned
    staged = fixtures.RelocationPurgePlanTests.staged
    committed = fixtures.RelocationPurgePlanTests.committed

    def purge_plan(self):
        active, receipt, artifact = self.committed()
        return active, receipt, artifact, active.plan_relocation_purge(receipt['id'], quarantine_days=0)

    def test_purge_removes_only_planned_copies_and_preserves_metadata(self):
        active, receipt, artifact, plan = self.purge_plan()
        record = active._path('maintenance', receipt['id']); before = record.read_bytes()
        result = active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        self.assertEqual(result['status'], 'PURGED')
        self.assertTrue(all(not Path(item['path']).exists() for item in plan['files']))
        self.assertEqual(record.read_bytes(), before); active.verify_artifact(artifact['id'])
        self.assertEqual(active.purge_relocation(plan['id'], 'owner', 'Retry'), result)
        with self.assertRaisesRegex(ValueError, 'purge has started'):
            active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')

    def test_new_reference_refuses_before_purge_intent(self):
        active, receipt, artifact, plan = self.purge_plan(); active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        self.assertFalse(active._path('maintenance', receipt['id'], 'purge-intent').exists())
        self.assertTrue(all(Path(item['path']).exists() for item in plan['files']))

    def test_partial_purge_resumes_original_plan(self):
        active, receipt, artifact, plan = self.purge_plan()
        import purge_execution
        original = purge_execution._delete; first = True
        def deleting(*args):
            nonlocal first
            original(*args)
            if first:
                first = False; raise OSError('Deletion interrupted')
        with patch('purge_execution._delete', side_effect=deleting):
            with self.assertRaisesRegex(OSError, 'Deletion interrupted'):
                active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        self.assertEqual(sum(Path(item['path']).exists() for item in plan['files']), 1)
        self.assertEqual(active.purge_relocation(plan['id'], 'owner', 'Resume')['status'], 'PURGED')

    def test_changed_references_after_partial_purge_stop_remaining_deletes(self):
        active, receipt, artifact, plan = self.purge_plan()
        import purge_execution
        original = purge_execution._delete
        def deleting(*args):
            original(*args); raise OSError('Deletion interrupted')
        with patch('purge_execution._delete', side_effect=deleting):
            with self.assertRaises(OSError): active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.purge_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(sum(Path(item['path']).exists() for item in plan['files']), 1)

    def test_unknown_file_added_after_plan_preserved(self):
        active, receipt, artifact, plan = self.purge_plan()
        note = Path(plan['files'][1]['path']).parent / 'owner-note'; note.write_text('Keep')
        with self.assertRaises(ValueError): active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        self.assertEqual(note.read_text(), 'Keep')
        self.assertTrue(all(Path(item['path']).exists() for item in plan['files']))

    def test_inventory_reports_completed_purge_without_missing_objects(self):
        active, receipt, artifact, plan = self.purge_plan()
        active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        report = active.inventory()
        row = report['quarantine_preparations']['operations'][0]
        self.assertEqual(row['phase'], 'PURGED'); self.assertEqual(row['observed_logical_bytes'], 0)
        source = next(row for row in report['relocation_backups']['copies'] if row['path'] == str(self.store.paths.objects))
        self.assertEqual(source['status'], 'PURGED'); self.assertFalse(source['missing_files'])
        self.assertEqual(source['purged_files'][0]['sha256'], artifact['sha256'])
        self.assertFalse(report['relocation_backups'].get('disposition_errors'))

    def test_missing_copy_without_file_checkpoint_is_not_completed_purge(self):
        active, receipt, artifact, plan = self.purge_plan()
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'purge-file-0': raise OSError('Checkpoint interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaises(OSError): active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        Path(plan['files'][0]['path']).unlink()
        with self.assertRaisesRegex(ValueError, 'files changed'):
            active.purge_relocation(plan['id'], 'owner', 'Resume')
        report = active.inventory()
        self.assertTrue(report['quarantine_preparations']['unverified_operations'])
        self.assertTrue(Path(plan['files'][1]['path']).exists())

    def test_completed_receipt_interruption_can_resume(self):
        active, receipt, artifact, plan = self.purge_plan()
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'purged': raise OSError('Completion interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaises(OSError): active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        self.assertTrue(all(not Path(item['path']).exists() for item in plan['files']))
        self.assertEqual(active.inventory()['quarantine_preparations']['operations'][0]['phase'], 'PURGING')
        self.assertEqual(active.purge_relocation(plan['id'], 'owner', 'Resume')['status'], 'PURGED')

    def test_other_plan_cannot_take_over_started_purge(self):
        active, receipt, artifact, plan = self.purge_plan()
        other = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'purge-file-0': raise OSError('Checkpoint interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaises(OSError): active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        with self.assertRaisesRegex(ValueError, 'owns this operation'):
            active.purge_relocation(other['id'], 'owner', 'Take over')
        self.assertEqual(active.purge_relocation(plan['id'], 'owner', 'Resume')['status'], 'PURGED')

    def test_deleted_media_reappearing_is_preserved(self):
        active, receipt, artifact, plan = self.purge_plan()
        active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        path = Path(plan['files'][0]['path']); path.write_bytes(b'Owner data')
        with self.assertRaisesRegex(ValueError, 'reappeared'):
            active.purge_relocation(plan['id'], 'owner', 'Retry')
        self.assertEqual(path.read_bytes(), b'Owner data')
        self.assertTrue(active.inventory()['quarantine_preparations']['unverified_operations'])

    def test_reference_change_during_execution_stops_next_file(self):
        import json
        import purge_execution
        active, receipt, artifact, plan = self.purge_plan()
        original = purge_execution._delete; changed = False
        def deleting(*args):
            nonlocal changed
            original(*args)
            if not changed:
                changed = True
                config = json.loads(active.config_path.read_text()); config['note'] = 'Changed during purge'
                active.config_path.write_text(json.dumps(config))
        with patch('purge_execution._delete', side_effect=deleting):
            with self.assertRaisesRegex(ValueError, 'stale'):
                active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        self.assertEqual(sum(Path(item['path']).exists() for item in plan['files']), 1)


    def test_observation_rejects_changed_completion_byte_count(self):
        import json
        import purge_observations
        active, receipt, artifact, plan = self.purge_plan()
        active.purge_relocation(plan['id'], 'owner', 'Retention expired')
        path = active._path('maintenance', receipt['id'], 'purged')
        result = json.loads(path.read_text())
        result['logical_bytes_removed'] += 1
        path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'receipt differs'):
            purge_observations.context(active, receipt['id'])
        self.assertTrue(active.inventory()['quarantine_preparations']['unverified_operations'])
