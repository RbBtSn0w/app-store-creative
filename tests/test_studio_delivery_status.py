"""Studio delivery reads reuse the same core verification across restarts."""
import json
from pathlib import Path
import unittest
import urllib.error
import test_delivery_status as fixtures
import test_studio_release
import export_engine


class StudioDeliveryStatusTests(unittest.TestCase):
    setUp = fixtures.DeliveryStatusTests.setUp
    approved = fixtures.DeliveryStatusTests.approved
    sealed = fixtures.DeliveryStatusTests.sealed
    request = test_studio_release.StudioReleaseTests.request

    def test_http_status_matches_core_and_survives_restart_without_writes(self):
        delivery = self.sealed(); cfg = self.store.config_path
        cfg.write_text(json.dumps(self.config))
        records = self.store.paths.workspace / 'records'
        before = {str(path): path.read_bytes() for path in records.rglob('*.json')}
        for _ in range(2):
            with export_engine.LocalServerContext(self.root, cfg) as ctx:
                result, _ = self.request(ctx, '/api/deliveries/' + delivery['id'])
                self.assertEqual(result, self.store.delivery_status(delivery['id']))
                self.assertEqual(result['remote_status'], 'UNKNOWN')
                listing, _ = self.request(ctx, '/api/deliveries?limit=1')
                self.assertEqual(listing, self.store.list_deliveries(limit=1))
                import subprocess, sys
                cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
                command = subprocess.run([sys.executable, str(cli), 'delivery', 'list', '--repo', str(self.root), '--limit', '1'], check=True, capture_output=True, text=True)
                self.assertEqual(listing, json.loads(command.stdout))
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    self.request(ctx, '/api/deliveries?limit=0')
                self.assertEqual(invalid.exception.code, 400)
                invalid.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/deliveries/' + 'a'*32)
                self.assertEqual(failure.exception.code, 404)
                failure.exception.close()
        self.assertEqual({str(path): path.read_bytes() for path in records.rglob('*.json')}, before)

    def test_corrupt_package_is_reported_as_local_failure(self):
        delivery = self.sealed(); cfg = self.store.config_path; cfg.write_text(json.dumps(self.config))
        next((Path(delivery['local_path']) / 'media').rglob('*.png')).write_bytes(b'corrupt')
        with export_engine.LocalServerContext(self.root, cfg) as ctx:
            result, _ = self.request(ctx, '/api/deliveries/' + delivery['id'])
            self.assertEqual(result['local_status'], 'FAIL')
            self.assertTrue(result['errors'])
            self.assertFalse(result['remote_write'])
