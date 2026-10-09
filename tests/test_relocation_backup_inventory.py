"""Retained relocation copies are reported from verified operation evidence."""
import json
from pathlib import Path
import shutil
import unittest
import test_reverse_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle, canonical


class RelocationBackupInventoryTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationSwitchTests.setUp
    source = fixtures.ReverseRelocationSwitchTests.source
    targets = fixtures.ReverseRelocationSwitchTests.targets
    prepared = fixtures.ReverseRelocationSwitchTests.prepared
    moved = fixtures.ReverseRelocationSwitchTests.moved
    reverse = fixtures.ReverseRelocationSwitchTests.reverse

    def backup(self):
        artifact, forward, moved, reverse, run = self.reverse()
        receipt = moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        active = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        return active, reverse, Path(receipt['preserved_backups'][0])

    def test_verified_backups_have_capacity_and_inventory_is_read_only(self):
        active, reverse, backup = self.backup()
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        report = active.inventory()['relocation_backups']
        copies = [item for item in report['copies'] if item['relocation_id'] == reverse['id']]
        self.assertTrue(copies)
        self.assertTrue(all(item['status'] == 'VERIFIED' for item in copies))
        self.assertGreater(report['capacity']['observed_logical_bytes'], 0)
        self.assertFalse(report['cleanup_executed'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_unknown_backup_file_is_reported_and_preserved(self):
        active, reverse, backup = self.backup()
        unknown = backup / 'owner-notes.txt'; unknown.write_text('Keep this')
        report = active.inventory()['relocation_backups']
        item = next(item for item in report['copies'] if item['path'] == str(backup))
        self.assertEqual(item['status'], 'CHANGED')
        self.assertIn('owner-notes.txt', item['extra_files'])
        self.assertTrue(unknown.is_file())

    def test_same_bytes_replacement_is_identity_conflict(self):
        active, reverse, backup = self.backup()
        preserved = backup.with_name(backup.name + '-preserved'); backup.rename(preserved)
        shutil.copytree(preserved, backup)
        item = next(item for item in active.inventory()['relocation_backups']['copies'] if item['path'] == str(backup))
        self.assertEqual(item['status'], 'IDENTITY_CONFLICT')
        self.assertIsNone(item['observed_logical_bytes'])
        self.assertTrue(preserved.is_dir())

    def test_alias_is_not_followed(self):
        active, reverse, backup = self.backup()
        preserved = backup.with_name(backup.name + '-preserved'); backup.rename(preserved)
        external = self.root / 'external'; external.mkdir()
        canary = external / 'canary'; canary.write_bytes(b'Keep external bytes')
        backup.symlink_to(external)
        item = next(item for item in active.inventory()['relocation_backups']['copies'] if item['path'] == str(backup))
        self.assertEqual(item['status'], 'UNSAFE')
        self.assertIsNone(item['observed_logical_bytes'])
        self.assertEqual(canary.read_bytes(), b'Keep external bytes')

    def test_missing_copy_is_not_counted_as_zero_observed_bytes(self):
        active, reverse, backup = self.backup()
        backup.rename(backup.with_name(backup.name + '-preserved'))
        item = next(item for item in active.inventory()['relocation_backups']['copies'] if item['path'] == str(backup))
        self.assertEqual(item['status'], 'MISSING')
        self.assertIsNone(item['observed_logical_bytes'])

    def test_redirected_intent_is_reported_without_inspecting_foreign_directory(self):
        active, reverse, backup = self.backup()
        path = active._path('relocations', reverse['id'], 'switch-intent')
        intent = json.loads(path.read_text()); intent['roots'][0]['staging'] = str(self.root / 'foreign')
        path.write_bytes(canonical(intent))
        report = active.inventory()['relocation_backups']
        self.assertTrue(report['unverified_operations'])
        self.assertFalse(any(item['relocation_id'] == reverse['id'] for item in report['copies']))

    def test_cli_and_studio_inventory_match_core_after_restart(self):
        import subprocess, sys, urllib.error
        import export_engine
        from test_studio_release import StudioReleaseTests
        active, reverse, backup = self.backup()
        expected = active.inventory()
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'inventory', '--repo', str(self.root)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), expected)
        for _ in range(2):
            with export_engine.LocalServerContext(self.root, active.config_path) as context:
                result, _ = StudioReleaseTests.request(self, context, '/api/inventory')
                self.assertEqual(result, expected)
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    StudioReleaseTests.request(self, context, '/api/inventory?path=/foreign')
                self.assertEqual(failure.exception.code, 400)
                failure.exception.close()

    def test_directory_scan_failure_is_reported_as_unverified(self):
        import os
        from unittest.mock import patch
        active, reverse, backup = self.backup()
        original = os.walk
        def walk(root, **options):
            if Path(root) == backup:
                error = PermissionError('Backup scan denied')
                if options.get('onerror') is not None:
                    options['onerror'](error)
                return
            yield from original(root, **options)
        with patch('inventory_lifecycle.os.walk', side_effect=walk):
            report = active.inventory()['relocation_backups']
        self.assertTrue(any(item['relocation_id'] == reverse['id']
                            and 'scan denied' in item['reason'] for item in report['unverified_operations']))
        self.assertFalse(any(item['path'] == str(backup) and item['status'] == 'VERIFIED' for item in report['copies']))
