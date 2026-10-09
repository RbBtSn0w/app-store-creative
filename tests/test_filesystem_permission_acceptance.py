"""Exercise actual OS permission denial using only owned temporary storage."""
import stat
import unittest
import test_retention_lifecycle as fixtures


class FilesystemPermissionAcceptanceTests(unittest.TestCase):
    setUp = fixtures.RetentionTests.setUp
    artifact = fixtures.RetentionTests.artifact

    def deny_object_reads(self):
        root = self.store.paths.objects
        mode = stat.S_IMODE(root.stat().st_mode)
        root.chmod(0)
        self.addCleanup(root.chmod, mode)
        try:
            list(root.iterdir())
        except PermissionError:
            return root, mode
        root.chmod(mode)
        self.skipTest('This host bypasses directory permission denial; no OS denial evidence')

    def test_actual_permission_denial_keeps_inventory_unknown_and_blocks_cleanup(self):
        _, artifact = self.artifact()
        records = self.store.paths.workspace / 'records'
        before = {str(path): path.read_bytes() for path in records.rglob('*.json')}
        root, mode = self.deny_object_reads()
        inventory = self.store.inventory()
        self.assertIsNone(inventory['objects']['active_count'])
        self.assertIsNone(inventory['capacity']['active_object_bytes'])
        self.assertTrue(any(error['area'] == 'objects' for error in inventory['observation_errors']))
        with self.assertRaisesRegex(ValueError, 'complete object observation'):
            self.store.plan_cleanup(retention_days=0)
        self.assertEqual(before, {str(path): path.read_bytes() for path in records.rglob('*.json')})
        root.chmod(mode)
        self.store.verify_artifact(artifact['id'])
        self.assertEqual(self.store.inventory()['objects']['active_count'], 1)

    def test_actual_permission_denial_cannot_plan_a_relocation(self):
        _, artifact = self.artifact()
        targets = {'workspaceRoot': 'next/work', 'objectRoot': 'next/media',
                   'releaseRoot': 'next/releases', 'publicationRoot': 'next/publications'}
        baseline = self.store.plan_relocation(targets)
        self.assertEqual(baseline['operation'], 'relocation-plan')
        root, mode = self.deny_object_reads()
        with self.assertRaisesRegex(ValueError, 'complete storage observations'):
            self.store.plan_relocation(targets)
        self.assertFalse((self.root / 'next').exists())
        root.chmod(mode)
        self.store.verify_artifact(artifact['id'])

    def test_actual_staging_write_denial_records_failure_and_recovers_new_batch(self):
        import json
        import tempfile
        from pathlib import Path
        from artifact_lifecycle import Lifecycle
        _, artifact = self.artifact()
        self.store.config_path.write_text(json.dumps(self.cfg))
        parent = self.root / 'destination'; parent.mkdir()
        targets = {'workspaceRoot': 'destination/work', 'objectRoot': 'destination/media',
                   'releaseRoot': 'destination/releases', 'publicationRoot': 'destination/publications'}
        plan = self.store.plan_relocation(targets)
        mode = stat.S_IMODE(parent.stat().st_mode)
        parent.chmod(0o500); self.addCleanup(parent.chmod, mode)
        try:
            with tempfile.TemporaryFile(dir=parent):
                pass
        except PermissionError:
            pass
        else:
            parent.chmod(mode)
            self.skipTest('This host bypasses directory write denial; no OS denial evidence')
        with self.assertRaises(PermissionError):
            self.store.prepare_relocation(plan['id'], 'fixture-owner', 'Permission acceptance')
        outcome = self.store._read('relocations', plan['id'], 'prepare-outcome')
        self.assertEqual(outcome['status'], 'PREPARATION_FAILED')
        original_intent = self.store._path('relocations', plan['id'], 'prepare-intent').read_bytes()
        self.store.verify_artifact(artifact['id'])
        self.assertEqual(json.loads(self.store.config_path.read_text()), self.cfg)
        parent.chmod(mode)
        recovery = self.store.recover_relocation(plan['id'], 'fixture-owner', 'Permission restored')
        self.assertNotEqual(recovery['retry_plan_id'], plan['id'])
        prepared = self.store.prepare_relocation(recovery['retry_plan_id'], 'fixture-owner', 'Retry in new batch')
        self.assertEqual(prepared['status'], 'PREPARED')
        self.store.switch_relocation(recovery['retry_plan_id'], 'fixture-owner', 'Activate verified copy')
        active = Lifecycle.from_configuration(self.root, self.store.config_path)
        active.verify_artifact(artifact['id'])
        self.assertEqual(active.paths.binding(), plan['to'])
        self.assertEqual(self.store._path('relocations', plan['id'], 'prepare-intent').read_bytes(), original_intent)

    def test_actual_configuration_parent_write_denial_requires_new_batch_after_mode_change(self):
        import json
        import tempfile
        from artifact_lifecycle import Lifecycle
        _, artifact = self.artifact()
        self.store.config_path.write_text(json.dumps(self.cfg))
        targets = {'workspaceRoot': 'target/work', 'objectRoot': 'target/media',
                   'releaseRoot': 'target/releases', 'publicationRoot': 'target/publications'}
        plan = self.store.plan_relocation(targets)
        self.store.prepare_relocation(plan['id'], 'fixture-owner', 'Move fixture')
        original = self.store.config_path.read_bytes()
        mode = stat.S_IMODE(self.root.stat().st_mode)
        self.root.chmod(0o500); self.addCleanup(self.root.chmod, mode)
        try:
            with tempfile.TemporaryFile(dir=self.root):
                pass
        except PermissionError:
            pass
        else:
            self.root.chmod(mode)
            self.skipTest('This host bypasses configuration directory write denial')
        with self.assertRaises(PermissionError):
            self.store.switch_relocation(plan['id'], 'fixture-owner', 'Move fixture')
        self.assertEqual(self.store.config_path.read_bytes(), original)
        self.store.verify_artifact(artifact['id'])
        self.assertTrue(self.store.relocation_status(plan['id'])['current_binding_writable'])
        self.assertFalse(self.store._path('relocations', plan['id'], 'switch-intent').exists())
        self.root.chmod(mode)
        with self.assertRaisesRegex(ValueError, 'intent differs or is stale'):
            self.store.switch_relocation(plan['id'], 'fixture-owner', 'Move fixture')
        self.store.cancel_relocation(plan['id'], 'fixture-owner', 'Retire preparation bound to denied mode')
        retry = self.store.plan_relocation(targets)
        self.assertNotEqual(retry['id'], plan['id'])
        self.store.prepare_relocation(retry['id'], 'fixture-owner', 'Retry restored permissions')
        receipt = self.store.switch_relocation(retry['id'], 'fixture-owner', 'Retry restored permissions')
        self.assertEqual(receipt['status'], 'SWITCHED')
        active = Lifecycle.from_configuration(self.root, self.store.config_path)
        active.verify_artifact(artifact['id'])
