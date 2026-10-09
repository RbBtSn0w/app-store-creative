"""Budget estimates count retained revision payloads without inventing remote costs."""
import unittest
import test_delivery_lifecycle as fixtures
from artifact_lifecycle import Lifecycle


class MediaBudgetTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_candidate_forecast_and_retained_revision_budget(self):
        forecast = self.store.media_budget(self.candidate['id'])
        self.assertEqual(forecast['status'], 'NOT_CONFIGURED')
        self.assertEqual(forecast['candidate_payload_bytes'], self.input['size_bytes'] + self.output['size_bytes'])
        validation, approval = self.approved()
        self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        measured = self.store.media_budget(self.candidate['id'])
        self.assertEqual(measured['current_payload_bytes'], forecast['candidate_payload_bytes'])
        self.assertEqual(measured['forecast_payload_bytes'], 2 * forecast['candidate_payload_bytes'])
        limited = Lifecycle(self.root, {**self.config, 'artifactPolicy': {'schema_version': 1, 'mediaBudgetBytes': 1}})
        self.assertEqual(limited.media_budget()['status'], 'OVER_BUDGET')
        self.assertIsNone(measured['git_history_bytes'])
        self.assertIsNone(measured['remote_storage_bytes'])

    def test_unavailable_archive_keeps_budget_unknown(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        from pathlib import Path
        (Path(delivery['local_path']) / 'media/en-US/mac_16_10/hero.png').write_bytes(b'Changed')
        report = self.store.media_budget()
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertIsNone(report['current_payload_bytes'])
        self.assertTrue(report['unverified_deliveries'])

    def test_public_budget_reads_match_core_and_preserve_records(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        import export_engine
        import test_studio_release
        self.store.config_path.write_text(json.dumps(self.config))
        expected = self.store.media_budget(self.candidate['id'])
        records = self.store.paths.workspace / 'records'
        before = {str(path):path.read_bytes() for path in records.rglob('*.json')}
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'storage', 'media-budget', '--repo', str(self.root), '--candidate-id', self.candidate['id']], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            value, _ = test_studio_release.StudioReleaseTests.request(self, ctx, '/api/storage/media-budget?candidate_id=' + self.candidate['id'])
            self.assertEqual(value, expected)
            from urllib.error import HTTPError
            for query in ['mediaBudgetBytes=0', 'candidate_id=', 'candidate_id=a&candidate_id=b', 'candidate_id=../outside']:
                with self.assertRaises(HTTPError) as failure:
                    test_studio_release.StudioReleaseTests.request(self, ctx, '/api/storage/media-budget?' + query)
                self.assertEqual(failure.exception.code, 400)
        self.assertEqual(before, {str(path):path.read_bytes() for path in records.rglob('*.json')})
