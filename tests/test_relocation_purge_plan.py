"""Purge plans bind exact redundant copies and preserve current recovery evidence."""
import json
from pathlib import Path
import unittest
import test_relocation_source_dispositions as fixtures


class RelocationPurgePlanTests(unittest.TestCase):
    setUp = fixtures.RelocationSourceDispositionTests.setUp
    source = fixtures.RelocationSourceDispositionTests.source
    targets = fixtures.RelocationSourceDispositionTests.targets
    prepared = fixtures.RelocationSourceDispositionTests.prepared
    moved = fixtures.RelocationSourceDispositionTests.moved
    planned = fixtures.RelocationSourceDispositionTests.planned
    staged = fixtures.RelocationSourceDispositionTests.staged
    committed = fixtures.RelocationSourceDispositionTests.committed

    def test_plan_lists_two_redundant_copies_and_current_recovery(self):
        active, receipt, artifact = self.committed()
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        self.assertEqual(plan['operation'], 'relocation-purge-plan')
        self.assertEqual(len(plan['files']), 2)
        self.assertTrue(all(item['sha256'] == artifact['sha256'] for item in plan['files']))
        self.assertEqual(plan['recovery'][0]['path'], str(active.object_path(artifact['sha256'])))
        self.assertFalse(plan['purge_executed'])
        self.assertTrue(all(Path(item['path']).exists() for item in plan['files']))
        self.assertEqual(active.verify_relocation_purge(plan['id'])['status'], 'READY')

    def test_default_seven_days_requires_expired_quarantine(self):
        active, receipt, artifact = self.committed()
        with self.assertRaisesRegex(ValueError, 'retention'):
            active.plan_relocation_purge(receipt['id'])

    def test_restoration_started_refuses_purge(self):
        active, receipt, artifact = self.committed()
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        with self.assertRaises(ValueError):
            active.plan_relocation_purge(receipt['id'], quarantine_days=0)

    def test_missing_active_recovery_refuses_plan(self):
        active, receipt, artifact = self.committed()
        active.object_path(artifact['sha256']).unlink()
        with self.assertRaises(ValueError):
            active.plan_relocation_purge(receipt['id'], quarantine_days=0)

    def test_open_incident_protects_copies(self):
        active, receipt, artifact = self.committed()
        active.open_incident('owner', 'Media investigation', artifacts=[artifact['id']])
        with self.assertRaisesRegex(ValueError, 'incident'):
            active.plan_relocation_purge(receipt['id'], quarantine_days=0)

    def test_new_reference_makes_existing_plan_stale(self):
        active, receipt, artifact = self.committed()
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0); active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_purge(plan['id'])

    def test_configured_original_source_path_refuses_plan(self):
        active, receipt, artifact = self.committed()
        config = json.loads(active.config_path.read_text()); config['sourcePath'] = str(self.store.object_path(artifact['sha256']))
        active.config_path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'configured'):
            active.plan_relocation_purge(receipt['id'], quarantine_days=0)

    def test_same_bytes_active_recovery_replacement_invalidates_plan(self):
        import shutil
        active, receipt, artifact = self.committed()
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        path = active.object_path(artifact['sha256']); kept = path.with_name('kept')
        path.rename(kept); shutil.copy2(kept, path); kept.unlink()
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_purge(plan['id'])

    def test_purge_plan_path_edit_is_rejected(self):
        active, receipt, artifact = self.committed()
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        path = active._path('maintenance', plan['id']); data = json.loads(path.read_text())
        data['files'][0]['path'] = str(self.root / 'private'); path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_purge(plan['id'])

    def test_policy_requires_nonnegative_integer(self):
        active, receipt, artifact = self.committed()
        for value in (True, -1, 0.5):
            with self.assertRaises(ValueError):
                active.plan_relocation_purge(receipt['id'], quarantine_days=value)

    def test_closing_incident_allows_new_plan(self):
        active, receipt, artifact = self.committed()
        incident = active.open_incident('owner', 'Media investigation', artifacts=[artifact['id']])
        active.close_incident(incident['id'], 'owner', 'Resolved')
        self.assertEqual(active.plan_relocation_purge(receipt['id'], quarantine_days=0)['operation'], 'relocation-purge-plan')

    def test_incident_dependency_protects_original_copy(self):
        active, receipt, artifact = self.committed()
        run = active.start_run({}); attempt = active.start_attempt(run['id'], 'render', 'owner')
        path = active.work_path(attempt['id']) / 'derived'; path.write_bytes(b'derived media')
        derived = active.register(attempt['id'], path, 'source', inputs=[artifact['id']])
        active.finish_attempt(attempt['id'], 'failed', reason='Investigation')
        active.open_incident('owner', 'Investigate derived media', artifacts=[derived['id']])
        with self.assertRaisesRegex(ValueError, 'incident'):
            active.plan_relocation_purge(receipt['id'], quarantine_days=0)

    def test_dangling_purge_intent_prevents_new_plan(self):
        active, receipt, artifact = self.committed()
        active._path('maintenance', receipt['id'], 'purge-intent').symlink_to('missing-intent')
        with self.assertRaisesRegex(ValueError, 'purge has started'):
            active.plan_relocation_purge(receipt['id'], quarantine_days=0)
