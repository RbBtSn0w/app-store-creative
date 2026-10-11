"""Prepared quarantine media has a read-only, evidence-bound inventory."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import test_relocation_quarantine_preparation as fixtures


class RelocationQuarantineInventoryTests(unittest.TestCase):
    setUp = fixtures.RelocationQuarantinePreparationTests.setUp
    source = fixtures.RelocationQuarantinePreparationTests.source
    targets = fixtures.RelocationQuarantinePreparationTests.targets
    prepared = fixtures.RelocationQuarantinePreparationTests.prepared
    moved = fixtures.RelocationQuarantinePreparationTests.moved
    planned = fixtures.RelocationQuarantinePreparationTests.planned
    operation = fixtures.RelocationQuarantinePreparationTests.operation

    def staged(self):
        active, plan, artifact = self.planned()
        result = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        return active, result, artifact

    def row(self, active):
        return active.inventory()['quarantine_preparations']['operations'][0]

    def test_prepared_payload_capacity_and_read_only_inventory(self):
        active, receipt, artifact = self.staged()
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        report = active.inventory()['quarantine_preparations']; row = report['operations'][0]
        self.assertEqual(row['phase'], 'PREPARED'); self.assertEqual(row['status'], 'VERIFIED')
        self.assertEqual(row['observed_logical_bytes'], artifact['size_bytes'])
        self.assertEqual(report['capacity']['observed_logical_bytes'], artifact['size_bytes'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_partial_payload_is_reported_as_partial(self):
        active, plan, artifact = self.planned()
        def copy(source, target):
            target.write(b'part'); target.flush(); raise OSError('Interrupted')
        with patch('relocation_quarantine.shutil.copyfileobj', side_effect=copy):
            with self.assertRaises(OSError):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        row = self.row(active)
        self.assertEqual(row['phase'], 'INTERRUPTED'); self.assertEqual(row['status'], 'PARTIAL')
        self.assertEqual(row['observed_logical_bytes'], 4)

    def test_corrupt_prepared_media_cannot_be_verified(self):
        active, receipt, artifact = self.staged()
        Path(receipt['copies'][0]['quarantine_path']).write_bytes(b'changed')
        self.assertEqual(self.row(active)['status'], 'CHANGED')

    def test_same_byte_payload_replacement_is_identity_conflict(self):
        active, receipt, artifact = self.staged()
        path = Path(receipt['copies'][0]['quarantine_path']); kept = path.parent.parent / 'kept'
        path.rename(kept); shutil.copy2(kept, path)
        self.assertEqual(self.row(active)['status'], 'IDENTITY_CONFLICT')

    def test_unknown_file_is_reported_and_preserved(self):
        active, receipt, artifact = self.staged()
        path = Path(receipt['copies'][0]['quarantine_path']).parent / 'notes'; path.write_text('Keep')
        row = self.row(active)
        self.assertEqual(row['status'], 'CHANGED'); self.assertIn('notes', row['extra_files'])
        self.assertEqual(path.read_text(), 'Keep')

    def test_root_alias_is_not_scanned(self):
        active, receipt, artifact = self.staged()
        root = Path(receipt['copies'][0]['quarantine_path']).parent
        kept = root.with_name('kept'); root.rename(kept); root.symlink_to(kept)
        row = self.row(active)
        self.assertEqual(row['status'], 'UNSAFE'); self.assertIsNone(row['observed_logical_bytes'])

    def test_receipt_path_tampering_is_unverified(self):
        active, receipt, artifact = self.staged()
        path = active._path('maintenance', receipt['id'], 'prepared')
        data = json.loads(path.read_text()); data['copies'][0]['quarantine_path'] = str(self.root / 'foreign')
        path.write_text(json.dumps(data))
        report = active.inventory()['quarantine_preparations']
        self.assertTrue(report['unverified_operations']); self.assertFalse(report['operations'])

    def test_cli_and_studio_match_after_restart(self):
        import subprocess, sys
        import export_engine
        from test_studio_release import StudioReleaseTests
        active, receipt, artifact = self.staged()
        expected = active.inventory()
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'inventory', '--repo', str(self.root)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), expected)
        for _ in range(2):
            with export_engine.LocalServerContext(self.root, active.config_path) as context:
                result, _ = StudioReleaseTests.request(self, context, '/api/inventory')
                self.assertEqual(result, expected)

    def test_unreadable_root_is_reported_as_unverified(self):
        import os
        active, receipt, artifact = self.staged()
        root = Path(receipt['copies'][0]['quarantine_path']).parent
        original = os.walk
        def walk(path, **options):
            if Path(path) == root:
                options['onerror'](PermissionError('Quarantine read denied'))
                return
            yield from original(path, **options)
        with patch('inventory_lifecycle.os.walk', side_effect=walk):
            report = active.inventory()['quarantine_preparations']
        self.assertFalse(report['operations'])
        self.assertIn('read denied', report['unverified_operations'][0]['reason'])

    def test_creation_proof_edit_is_bound_by_prepared_receipt(self):
        active, receipt, artifact = self.staged()
        path = active._path('maintenance', receipt['id'], 'copy-0')
        data = json.loads(path.read_text()); data['file_identity'] = [0, 0]; path.write_text(json.dumps(data))
        report = active.inventory()['quarantine_preparations']
        self.assertFalse(report['operations']); self.assertTrue(report['unverified_operations'])

    def test_missing_root_has_unknown_observed_bytes(self):
        active, receipt, artifact = self.staged()
        root = Path(receipt['copies'][0]['quarantine_path']).parent; root.rename(root.with_name('kept'))
        row = self.row(active)
        self.assertEqual(row['status'], 'MISSING'); self.assertIsNone(row['observed_logical_bytes'])
