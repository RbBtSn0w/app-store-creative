"""Publication reads expose the same conservative gates in CLI and Studio."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import urllib.error
import test_publication_lifecycle as fixtures
import test_studio_release
import export_engine


class StudioPublicationTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist
    request = test_studio_release.StudioReleaseTests.request

    def test_http_and_cli_match_core_without_writes(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        self.store.config_path.write_text(json.dumps(self.config))
        records = self.store.paths.workspace / 'records'
        before = {str(p): p.read_bytes() for p in records.rglob('*.json')}
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            listing, _ = self.request(ctx, '/api/publications?limit=1')
            self.assertEqual(listing, self.store.list_publications(limit=1))
            detail, _ = self.request(ctx, '/api/publications/' + plan['id'])
            self.assertEqual(detail, self.store.publication_status(plan['id']))
            self.assertEqual(detail['status'], 'UNKNOWN')
            self.assertFalse(detail['remote_verified'])
            cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
            result = subprocess.run([sys.executable, str(cli), 'publication', 'list', '--repo', str(self.root), '--limit', '1'],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), listing)
            with self.assertRaises(urllib.error.HTTPError) as bad:
                self.request(ctx, '/api/publications?repo=foreign')
            self.assertEqual(bad.exception.code, 400); bad.exception.close()
        self.assertEqual(before, {str(p): p.read_bytes() for p in records.rglob('*.json')})

    def test_upload_approval_and_handoff_never_claim_remote_write(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        self.store.config_path.write_text(json.dumps(self.config))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            preview, _ = self.request(ctx, '/api/publication-handoff/' + plan['id'])
            self.assertEqual(preview['handoff'], plan)
            self.assertFalse(preview['remote_write'])
            self.assertNotIn('handoff_path', preview)
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/publications/approve-upload', {'publication_id': plan['id'],
                    'actor': 'test-owner', 'authorization_reference': 'human:test-fixture', 'confirm': 'DESIGN'})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            approval, _ = self.request(ctx, '/api/publications/approve-upload', {'publication_id': plan['id'],
                'actor': 'test-owner', 'authorization_reference': 'human:test-fixture', 'confirm': 'UPLOAD'})
            self.assertEqual(approval['stage'], 'upload')
            handoff, _ = self.request(ctx, '/api/publications/export', {'publication_id': plan['id'], 'confirm': 'EXPORT'})
            self.assertEqual(handoff['upload_approval'], 'approved')
            self.assertFalse(handoff['uploaded']); self.assertFalse(handoff['remote_write'])
            self.assertEqual(handoff['executor'], 'official-asc-plugin')
            self.assertTrue(Path(handoff['handoff_path']).is_file())
            status, _ = self.request(ctx, '/api/publications/' + plan['id'])
            self.assertFalse(status['remote_verified'])
