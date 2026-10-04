"""Read-only inventory distinguishes objects, evidence and local capacity."""
import hashlib
import unittest
import test_artifact_lifecycle as fixtures


class InventoryTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def artifact(self):
        run = self.store.start_run({}); attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'sample'; source.write_bytes(b'object bytes')
        first = self.store.register(attempt['id'], source, 'screenshot')
        self.store.register(attempt['id'], source, 'source')
        self.store.finish_attempt(attempt['id'], 'failed', reason='Discarded trial')
        return first

    def test_reference_dedup_does_not_double_count_active_bytes(self):
        artifact = self.artifact()
        report = self.store.inventory()
        self.assertEqual(report['objects']['reference_count'], 2)
        self.assertEqual(report['objects']['active_count'], 1)
        self.assertEqual(report['capacity']['active_object_bytes'], artifact['size_bytes'])
        self.assertFalse(report['cleanup_executed'])

    def test_orphan_objects_are_reported_without_deletion(self):
        self.artifact()
        sha = hashlib.sha256(b'orphan').hexdigest()
        path = self.store.object_path(sha); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'orphan')
        report = self.store.inventory()
        self.assertIn(str(path), report['objects']['orphan_files'])
        self.assertTrue(path.exists())
        self.assertEqual(len(self.store.plan_cleanup(retention_days=0)['objects']), 1)

    def test_missing_and_corrupt_registered_objects_are_distinct(self):
        artifact = self.artifact(); path = self.store.object_path(artifact['sha256'])
        path.write_bytes(b'corrupt')
        self.assertIn(artifact['sha256'], self.store.inventory()['objects']['corrupt'])
        path.unlink()
        self.assertIn(artifact['sha256'], self.store.inventory()['objects']['missing'])

    def test_quarantined_and_shared_inode_capacity_is_not_missing(self):
        artifact = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        operation = self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discarded')
        report = self.store.inventory()
        self.assertNotIn(artifact['sha256'], report['objects']['missing'])
        self.assertIn(artifact['sha256'], report['objects']['quarantined'])
        self.store.restore_cleanup(operation['id'], actor='owner', reason='Recover')
        report = self.store.inventory()
        self.assertEqual(report['capacity']['payload_unique_inodes'], 1)
        self.assertEqual(report['capacity']['payload_logical_bytes'], artifact['size_bytes'] * 2)

    def test_unknown_symlink_is_reported_without_reading_its_target(self):
        self.artifact()
        outside = self.root / 'private.txt'; outside.write_text('private bytes')
        alias = self.store.paths.objects / 'unknown-link'; alias.symlink_to(outside)
        report = self.store.inventory()
        self.assertIn(str(alias), report['objects']['unsafe_links'])
        self.assertTrue(alias.is_symlink())

    def test_empty_inventory_does_not_create_storage(self):
        report = self.store.inventory()
        self.assertEqual(report['objects']['active_count'], 0)
        self.assertFalse(self.store.paths.workspace.exists())
        self.assertFalse(self.store.paths.objects.exists())

    def test_symlinked_work_root_does_not_read_external_files(self):
        outside = self.root / 'private-directory'; outside.mkdir(); (outside / 'secret').write_text('secret')
        self.store.paths.workspace.mkdir()
        work = self.store.paths.workspace / 'work'; work.symlink_to(outside)
        report = self.store.inventory()
        self.assertEqual(report['capacity']['work_file_bytes'], 0)
        self.assertIn(str(work), report['unregistered_files'])
        self.assertIn(str(work), report['other_unsafe_links'])

    def test_purged_identity_is_not_unexpected_missing(self):
        artifact = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        operation = self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discarded')
        purge = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.store.purge_cleanup(purge['id'], actor='owner', reason='Expired')
        report = self.store.inventory()
        self.assertIn(artifact['sha256'], report['objects']['purged'])
        self.assertNotIn(artifact['sha256'], report['objects']['missing'])

    def test_corrupt_quarantine_is_not_reported_as_recoverable(self):
        artifact = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        operation = self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discarded')
        source = self.store._quarantine_path(operation['id'], artifact['sha256']); source.write_bytes(b'broken')
        report = self.store.inventory()
        self.assertIn(str(source), report['objects']['corrupt_quarantine_files'])
        self.assertNotIn(artifact['sha256'], report['objects']['quarantined'])

    def test_cli_inventory_reports_unknown_remote_capacity(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        self.artifact()
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        process = subprocess.run([sys.executable, str(cli), 'inventory', '--repo', str(self.root)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertIsNone(report['capacity']['lfs_remote_bytes'])
        self.assertFalse(report['cleanup_executed'])

    def test_producer_rejects_symlinked_work_root_before_writing_attempt(self):
        run = self.store.start_run({})
        outside = self.root / 'external-work'; outside.mkdir()
        (self.store.paths.workspace / 'work').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'work'):
            self.store.start_attempt(run['id'], 'render', 'agent')
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list((self.store.paths.workspace / 'records/attempts').glob('*/started.json')), [])
