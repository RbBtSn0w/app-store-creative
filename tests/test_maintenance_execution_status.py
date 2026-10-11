"""Read-only execution observations verify effects independently of saved outcomes."""
import json
import unittest
import test_retention_lifecycle as fixtures


class MaintenanceExecutionStatusTests(unittest.TestCase):
    setUp = fixtures.RetentionTests.setUp
    artifact = fixtures.RetentionTests.artifact
    quarantined = fixtures.RetentionTests.quarantined

    def test_quarantine_status_checks_bytes_and_preserves_all_records(self):
        data, operation = self.quarantined()
        records = self.store.paths.workspace / 'records'
        before = {str(path): path.read_bytes() for path in records.rglob('*.json')}
        result = self.store.maintenance_status(operation['id'])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['phase'], 'quarantined')
        self.assertTrue(result['execution_verified'])
        self.store._quarantine_path(operation['id'], data['sha256']).write_bytes(b'Changed')
        changed = self.store.maintenance_status(operation['id'])
        self.assertEqual(changed['status'], 'FAIL')
        self.assertFalse(changed['execution_verified'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in records.rglob('*.json')})

    def test_public_inspection_matches_core_after_restart_and_rejects_overrides(self):
        from pathlib import Path
        import subprocess
        import sys
        import urllib.error
        import export_engine
        import test_studio_release
        _, operation = self.quarantined()
        self.store.config_path.write_text(json.dumps(self.cfg))
        expected = self.store.maintenance_status(operation['id'])
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = [sys.executable, str(script), 'history', 'inspect-maintenance', '--repo', str(self.root), '--id', operation['id']]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        request = test_studio_release.StudioReleaseTests.request
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            observed, _ = request(self, ctx, '/api/history/maintenance/' + operation['id'])
            self.assertEqual(observed, expected)
            with self.assertRaises(urllib.error.HTTPError) as failure:
                request(self, ctx, '/api/history/maintenance/' + operation['id'] + '?workspace=/tmp/override')
            self.assertEqual(failure.exception.code, 400); failure.exception.close()

    def test_plan_does_not_claim_execution_and_purge_checks_reappearance(self):
        data, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.assertEqual(self.store.maintenance_status(plan['id'])['status'], 'NOT_EXECUTED')
        self.store.purge_cleanup(plan['id'], 'fixture-owner', 'Disposable fixture')
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'PASS')
        path = self.store._quarantine_path(operation['id'], data['sha256'])
        path.write_bytes(b'Preserve owner data')
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'FAIL')
        self.assertEqual(path.read_bytes(), b'Preserve owner data')
