"""Execution gates revalidate retention scope without modifying retained media."""
import json
from pathlib import Path
import shutil
import unittest
import test_relocation_retention_plan as fixtures


class RelocationRetentionVerificationTests(unittest.TestCase):
    setUp = fixtures.RelocationRetentionPlanTests.setUp
    source = fixtures.RelocationRetentionPlanTests.source
    targets = fixtures.RelocationRetentionPlanTests.targets
    prepared = fixtures.RelocationRetentionPlanTests.prepared
    moved = fixtures.RelocationRetentionPlanTests.moved

    def planned(self):
        active, move, artifact = self.moved()
        return active, active.plan_relocation_retention(retention_days=0), artifact

    def test_unchanged_plan_revalidates_without_creating_records(self):
        active, plan, artifact = self.planned()
        before = sorted(str(path) for path in active.paths.workspace.rglob('*'))
        result = active.verify_relocation_retention(plan['id'])
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['eligible_file_count'], 1)
        self.assertEqual(sorted(str(path) for path in active.paths.workspace.rglob('*')), before)
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_source_byte_change_refuses_plan(self):
        active, plan, artifact = self.planned()
        self.store.object_path(artifact['sha256']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])

    def test_same_byte_source_file_replacement_refuses_plan(self):
        active, plan, artifact = self.planned()
        source = self.store.object_path(artifact['sha256'])
        retained = source.with_name('kept'); source.rename(retained)
        shutil.copy2(retained, source); retained.unlink()
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])

    def test_same_byte_recovery_replacement_refuses_plan(self):
        active, plan, artifact = self.planned()
        recovery = active.object_path(artifact['sha256'])
        retained = recovery.with_name('kept'); recovery.rename(retained)
        shutil.copy2(retained, recovery); retained.unlink()
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])

    def test_new_configuration_reference_refuses_plan(self):
        active, plan, artifact = self.planned()
        cfg = json.loads(active.config_path.read_text())
        cfg['sourcePath'] = str(self.store.object_path(artifact['sha256']))
        active.config_path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])

    def test_new_run_invalidates_reference_snapshot(self):
        active, plan, artifact = self.planned()
        active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])

    def test_plan_cannot_redirect_file_scope(self):
        active, plan, artifact = self.planned()
        path = active._path('maintenance', plan['id'])
        data = json.loads(path.read_text())
        next(item for item in data['files'] if item['decision'] == 'eligible')['path'] = str(self.root / 'private')
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])

    def test_root_alias_after_planning_refuses_verification(self):
        active, plan, artifact = self.planned()
        source = self.store.paths.objects
        moved = source.with_name('retained-root'); source.rename(moved)
        source.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.verify_relocation_retention(plan['id'])
        self.assertTrue((moved / artifact['sha256'][:2] / artifact['sha256']).exists())

    def test_object_cleanup_plan_is_not_a_copy_retention_plan(self):
        active, plan, artifact = self.planned()
        ordinary = active.plan_cleanup(retention_days=0)
        with self.assertRaisesRegex(ValueError, 'Invalid relocation retention plan'):
            active.verify_relocation_retention(ordinary['id'])

    def test_other_maintenance_plans_do_not_invalidate_reference_snapshot(self):
        active, plan, artifact = self.planned()
        active.plan_relocation_retention(retention_days=0)
        self.assertEqual(active.verify_relocation_retention(plan['id'])['status'], 'READY')
