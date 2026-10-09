"""Retained-source inventory recognizes only fully verified quarantine dispositions."""
from pathlib import Path
import json
import unittest
import test_relocation_quarantine_commit as fixtures


class RelocationSourceDispositionTests(unittest.TestCase):
    setUp = fixtures.RelocationQuarantineCommitTests.setUp
    source = fixtures.RelocationQuarantineCommitTests.source
    targets = fixtures.RelocationQuarantineCommitTests.targets
    prepared = fixtures.RelocationQuarantineCommitTests.prepared
    moved = fixtures.RelocationQuarantineCommitTests.moved
    planned = fixtures.RelocationQuarantineCommitTests.planned
    staged = fixtures.RelocationQuarantineCommitTests.staged

    def committed(self):
        active, receipt, artifact = self.staged()
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        return active, receipt, artifact

    def source_row(self, active):
        return next(item for item in active.inventory()['relocation_backups']['copies']
                    if item['path'] == str(self.store.paths.objects))

    def test_quarantined_file_is_managed_without_missing_or_unknown_entries(self):
        active, receipt, artifact = self.committed()
        row = self.source_row(active)
        self.assertEqual(row['status'], 'QUARANTINED')
        self.assertFalse(row['extra_files']); self.assertFalse(row['missing_files'])
        self.assertEqual(row['quarantined_files'][0]['operation_id'], receipt['id'])
        self.assertEqual(row['quarantined_files'][0]['sha256'], artifact['sha256'])

    def test_restored_source_returns_to_verified(self):
        active, receipt, artifact = self.committed()
        active.restore_relocation_quarantine(receipt['id'], 'owner', 'Recover')
        row = self.source_row(active)
        self.assertEqual(row['status'], 'VERIFIED'); self.assertNotIn('quarantined_files', row)

    def test_unknown_note_is_not_hidden_by_disposition(self):
        active, receipt, artifact = self.committed()
        note = self.store.paths.objects / 'owner-note'; note.write_text('Keep')
        row = self.source_row(active)
        self.assertEqual(row['status'], 'CHANGED'); self.assertIn('owner-note', row['extra_files'])
        self.assertEqual(note.read_text(), 'Keep')

    def test_corrupt_retained_media_is_not_accepted(self):
        active, receipt, artifact = self.committed()
        intent = active._read('maintenance', receipt['id'], 'commit-intent')
        Path(intent['files'][0]['retained_path']).write_bytes(b'corrupt')
        report = active.inventory()['relocation_backups']; row = self.source_row(active)
        self.assertEqual(row['status'], 'CHANGED'); self.assertTrue(report['disposition_errors'])

    def test_receipt_tampering_cannot_hide_displacement(self):
        active, receipt, artifact = self.committed()
        path = active._path('maintenance', receipt['id'], 'quarantined')
        data = json.loads(path.read_text()); data['commit_intent_sha256'] = 'a' * 64; path.write_text(json.dumps(data))
        row = self.source_row(active)
        self.assertEqual(row['status'], 'CHANGED'); self.assertNotIn('quarantined_files', row)

    def test_quarantined_sources_not_selected_for_second_cleanup(self):
        active, receipt, artifact = self.committed()
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertFalse(any(item['decision'] == 'eligible' for item in plan['files']))
        self.assertTrue(any(item['status'] == 'QUARANTINED' for item in plan['excluded_roots']))

    def test_partial_commit_is_visible_without_hiding_missing_bytes(self):
        from unittest.mock import patch
        active, receipt, artifact = self.staged()
        original = active._record
        def record(category, data, suffix=None):
            if suffix == 'quarantined': raise OSError('Receipt interrupted')
            return original(category, data, suffix)
        with patch.object(active, '_record', side_effect=record):
            with self.assertRaises(OSError):
                active.commit_relocation_quarantine(receipt['id'], 'owner', 'Expired copies')
        self.assertEqual(self.source_row(active)['status'], 'QUARANTINED')
        self.assertEqual(active.inventory()['quarantine_preparations']['operations'][0]['phase'], 'COMMIT_STARTED')
        active.commit_relocation_quarantine(receipt['id'], 'owner', 'Resume')

    def test_cli_and_studio_share_disposition_view(self):
        import subprocess, sys
        import export_engine
        from test_studio_release import StudioReleaseTests
        active, receipt, artifact = self.committed(); expected = active.inventory()
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'inventory', '--repo', str(self.root)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout), expected)
        with export_engine.LocalServerContext(self.root, active.config_path) as context:
            result, _ = StudioReleaseTests.request(self, context, '/api/inventory')
            self.assertEqual(result, expected)

    def test_reverse_backup_disposition_is_verified(self):
        from artifact_lifecycle import Lifecycle
        active, forward, artifact = self.moved()
        original_move = forward['id']
        reverse = active.plan_reverse_relocation(original_move)
        active.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        active.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(active.config_path.read_text()))
        plan = returned.plan_relocation_retention(retention_days=0)
        staged = returned.prepare_relocation_quarantine(plan['id'], 'owner', 'Prepare backup')
        returned.commit_relocation_quarantine(staged['id'], 'owner', 'Expired backup')
        report = returned.inventory()['relocation_backups']
        rows = [row for row in report['copies'] if row['relocation_id'] == reverse['id']]
        self.assertTrue(any(row['status'] == 'QUARANTINED' for row in rows))
        returned.restore_relocation_quarantine(staged['id'], 'owner', 'Recover')
        rows = [row for row in returned.inventory()['relocation_backups']['copies'] if row['relocation_id'] == reverse['id']]
        self.assertTrue(all(row['status'] == 'VERIFIED' for row in rows))
