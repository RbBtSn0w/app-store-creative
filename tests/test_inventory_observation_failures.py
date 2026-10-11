"""Unobserved storage never becomes empty capacity or cleanup authorization."""
import json
from pathlib import Path
import os
import unittest
from unittest.mock import patch
import test_inventory_lifecycle as fixtures


class InventoryObservationFailureTests(unittest.TestCase):
    setUp = fixtures.InventoryTests.setUp
    artifact = fixtures.InventoryTests.artifact

    def denied(self, root):
        original = os.walk
        def walk(path, *args, **kwargs):
            if Path(path) == root:
                error = PermissionError('Injected unreadable directory')
                if kwargs.get('onerror'):
                    kwargs['onerror'](error)
                return iter([])
            return original(path, *args, **kwargs)
        return patch('inventory_lifecycle.os.walk', side_effect=walk)

    def test_unreadable_work_is_unknown_capacity_with_a_scoped_error(self):
        self.artifact()
        work = self.store.paths.workspace / 'work'; work.mkdir(exist_ok=True)
        (work / 'unregistered').write_bytes(b'Keep')
        with self.denied(work):
            report = self.store.inventory()
        self.assertIsNone(report['capacity']['work_file_bytes'])
        self.assertTrue(any(item['area'] == 'work' for item in report['observation_errors']))
        self.assertEqual((work / 'unregistered').read_bytes(), b'Keep')
        self.assertEqual(report['objects']['active_count'], 1)

    def test_unreadable_objects_are_not_reported_as_missing_or_empty(self):
        artifact = self.artifact()
        with self.denied(self.store.paths.objects):
            report = self.store.inventory()
        self.assertIsNone(report['objects']['active_count'])
        self.assertIsNone(report['capacity']['active_object_bytes'])
        self.assertIsNone(report['capacity']['payload_logical_bytes'])
        self.assertEqual(report['objects']['missing'], [])
        self.assertIn(artifact['sha256'], report['objects']['unobserved_registered'])
        self.assertTrue(report['observation_errors'])

    def test_unreadable_reference_tree_blocks_cleanup_plan_and_execution(self):
        artifact = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        records = self.store.paths.workspace / 'records'
        before = sorted((records / 'maintenance').rglob('*.json'))
        with self.denied(records):
            with self.assertRaises((OSError, ValueError)):
                self.store.plan_cleanup(retention_days=0)
            with self.assertRaises((OSError, ValueError)):
                self.store.quarantine_cleanup(plan['id'], 'owner', 'Expired')
        self.assertEqual(sorted((records / 'maintenance').rglob('*.json')), before)
        self.store.verify_artifact(artifact['id'])

    def test_unreadable_publication_root_blocks_relocation_snapshot(self):
        self.artifact()
        self.store.config_path.write_text(json.dumps(self.cfg))
        self.store.paths.publications.mkdir(exist_ok=True)
        with self.denied(self.store.paths.publications):
            with self.assertRaises((OSError, ValueError)):
                self.store.plan_relocation({'workspaceRoot':'next work', 'objectRoot':'next objects',
                    'releaseRoot':'next releases', 'publicationRoot':'next publications'})
        self.assertFalse((self.root / 'next work').exists())

    def test_unreadable_object_tree_blocks_cleanup_before_operation_creation(self):
        artifact = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        records = self.store.paths.workspace / 'records/maintenance'
        before = sorted(records.rglob('*.json'))
        with self.denied(self.store.paths.objects):
            with self.assertRaisesRegex(ValueError, 'complete object observation'):
                self.store.plan_cleanup(retention_days=0)
            with self.assertRaisesRegex(ValueError, 'complete object observation'):
                self.store.quarantine_cleanup(plan['id'], 'owner', 'Expired')
        self.assertEqual(sorted(records.rglob('*.json')), before)
        self.store.verify_artifact(artifact['id'])

    def test_file_stat_failure_cannot_silently_hide_registered_objects(self):
        artifact = self.artifact()
        payload = self.store.object_path(artifact['sha256'])
        original = Path.lstat
        def lstat(path, *args, **kwargs):
            if path == payload:
                raise PermissionError('Injected stat failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', lstat):
            report = self.store.inventory()
        self.assertIsNone(report['capacity']['active_object_bytes'])
        self.assertIsNone(report['objects']['active_count'])
        self.assertTrue(report['observation_errors'])
        self.assertEqual(report['objects']['missing'], [])
        self.store.verify_artifact(artifact['id'])
