"""Historical quarantine observations follow receipt-bound relocated copies."""
from pathlib import Path
import json
import unittest
import test_maintenance_relocation_coordination as fixtures
from artifact_lifecycle import Lifecycle


class QuarantineLocationProjectionTests(unittest.TestCase):
    setUp = fixtures.MaintenanceRelocationCoordinationTests.setUp
    source = fixtures.MaintenanceRelocationCoordinationTests.source
    targets = fixtures.MaintenanceRelocationCoordinationTests.targets
    prepared = fixtures.MaintenanceRelocationCoordinationTests.prepared
    moved = fixtures.MaintenanceRelocationCoordinationTests.moved
    planned = fixtures.MaintenanceRelocationCoordinationTests.planned
    staged = fixtures.MaintenanceRelocationCoordinationTests.staged
    next_roots = fixtures.MaintenanceRelocationCoordinationTests.next_roots
    def relocated(self, terminal='CANCELLED'):
        active, receipt, artifact = self.staged()
        if terminal == 'CANCELLED':
            active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Keep copies')
        elif terminal == 'RESTORED':
            active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired')
            active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        elif terminal == 'PURGED':
            active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired')
            purge = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
            active.purge_relocation(purge['id'], 'owner', 'Expired')
        plan = active.plan_relocation(self.next_roots())
        active.prepare_relocation(plan['id'], 'owner', 'Move')
        active.switch_relocation(plan['id'], 'owner', 'Move')
        moved = Lifecycle(self.root, json.loads(active.config_path.read_text()))
        return moved, receipt, artifact, plan

    def row(self, core):
        inventory = core.inventory()['quarantine_preparations']
        self.assertEqual(inventory['unverified_operations'], [])
        self.assertEqual(len(inventory['operations']), 1)
        return inventory['operations'][0]

    def test_cancelled_copy_reports_current_path_without_rewriting_operation(self):
        moved, receipt, artifact, plan = self.relocated()
        row = self.row(moved)
        self.assertEqual(row['phase'], 'CANCELLED'); self.assertEqual(row['status'], 'VERIFIED')
        self.assertEqual(row['path'], str(moved.paths.workspace / 'maintenance/relocation-quarantine' / receipt['id']))
        self.assertNotEqual(row['path'], moved._read('maintenance', receipt['id'])['quarantine_root'])
        moved.verify_artifact(artifact['id'])

    def test_same_bytes_replacement_is_identity_conflict(self):
        moved, receipt, artifact, plan = self.relocated()
        payload = next((moved.paths.workspace / 'maintenance/relocation-quarantine' / receipt['id']).iterdir())
        substitute = payload.with_name('replacement'); substitute.write_bytes(payload.read_bytes()); substitute.replace(payload)
        self.assertEqual(self.row(moved)['status'], 'IDENTITY_CONFLICT')

    def test_unknown_file_is_reported_and_retained(self):
        moved, receipt, artifact, plan = self.relocated('RESTORED')
        note = moved.paths.workspace / 'maintenance/relocation-quarantine' / receipt['id'] / 'owner-note'
        note.write_text('Keep')
        row = self.row(moved)
        self.assertEqual(row['phase'], 'RESTORED'); self.assertEqual(row['status'], 'CHANGED')
        self.assertEqual(row['extra_files'], ['owner-note']); self.assertEqual(note.read_text(), 'Keep')

    def test_purged_copy_reports_empty_current_root_and_original_removal_proof(self):
        moved, receipt, artifact, plan = self.relocated('PURGED')
        row = self.row(moved)
        self.assertEqual(row['phase'], 'PURGED'); self.assertEqual(row['status'], 'PURGED')
        self.assertEqual(row['purge_plan']['quarantine_id'], receipt['id'])
        self.assertEqual(len(row['files']), row['expected_file_count'])
        self.assertEqual(row['observed_logical_bytes'], 0)
        self.assertEqual(len(row['purged_files']), 1)
        self.assertEqual(moved.inventory()['relocation_backups'].get('disposition_errors', []), [])
        moved.verify_artifact(artifact['id'])

    def test_prepared_copy_replacement_refuses_switch(self):
        active, receipt, artifact = self.staged()
        active.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Keep copies')
        plan = active.plan_relocation(self.next_roots())
        prepared = active.prepare_relocation(plan['id'], 'owner', 'Move')
        from quarantine_locations import staged_workspace
        payload = next((staged_workspace(active, plan) / 'maintenance/relocation-quarantine' / receipt['id']).iterdir())
        replacement = payload.with_name('replacement'); replacement.write_bytes(payload.read_bytes()); replacement.replace(payload)
        with self.assertRaisesRegex(ValueError, 'quarantine location proof differs'):
            active.switch_relocation(plan['id'], 'owner', 'Move')
        self.assertFalse((self.root / 'third work').exists())

    def test_successive_forward_migrations_report_latest_copy(self):
        moved, receipt, artifact, plan = self.relocated()
        storage = {key: value.replace('third', 'fourth') for key, value in self.next_roots().items()}
        next_plan = moved.plan_relocation(storage)
        moved.prepare_relocation(next_plan['id'], 'owner', 'Move again')
        moved.switch_relocation(next_plan['id'], 'owner', 'Move again')
        current = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        self.assertEqual(self.row(current)['status'], 'VERIFIED')
        current.verify_artifact(artifact['id'])

    def test_reverse_return_to_original_binding_checks_new_copy_identity(self):
        moved, receipt, artifact, plan = self.relocated()
        reverse = moved.plan_reverse_relocation(plan['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        current = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        self.assertEqual(current.paths.binding(), current._read('maintenance', receipt['id'])['storage'])
        self.assertEqual(self.row(current)['status'], 'VERIFIED')
        current.verify_artifact(artifact['id'])

    def test_purged_view_survives_reverse_return(self):
        moved, receipt, artifact, plan = self.relocated('PURGED')
        reverse = moved.plan_reverse_relocation(plan['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        current = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        self.assertEqual(self.row(current)['status'], 'PURGED')
        current.verify_artifact(artifact['id'])

    def test_edited_location_proof_is_unverified(self):
        moved, receipt, artifact, plan = self.relocated()
        path = moved._path('relocations', plan['id'], 'prepared')
        prepared = json.loads(path.read_text())
        prepared['quarantine_locations'][0]['directory_identity'][1] += 1
        path.write_text(json.dumps(prepared))
        inventory = moved.inventory()['quarantine_preparations']
        self.assertEqual(inventory['operations'], [])
        self.assertTrue(inventory['unverified_operations'])
