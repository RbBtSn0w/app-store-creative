"""Export refuses altered upload authorization before materializing handoff."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_publication_lifecycle as fixtures


class UploadApprovalCommitIntegrityTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_changed_upload_authorization_cannot_export_handoff(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        approval = self.store.approve_upload(plan['id'], 'fixture-owner', 'human:fixture-upload')
        path = self.store._path('approvals', approval['id'])
        changed = json.loads(path.read_text()); changed['authorization_reference'] = 'human:changed-reference'
        path.write_text(json.dumps(changed)); before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.export_publication(plan['id'], write=True)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.store.paths.publications / plan['id'] / 'plan.json').exists())

    def test_public_status_diagnoses_unreadable_approval_without_mutation(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        approval = self.store.approve_upload(plan['id'], 'fixture-owner', 'human:fixture-upload')
        path = self.store._path('approvals', approval['id'])
        path.write_text('{invalid-json')
        self.store.config_path.write_text(json.dumps(self.config))
        before = {str(p): p.read_bytes() for p in self.store.paths.workspace.rglob('*') if p.is_file()}
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'status', '--id', plan['id'],
                                 '--repo', str(self.root), '--config', str(self.store.config_path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status['upload_approval'], 'pending')
        self.assertFalse(status['remote_verified'])
        self.assertEqual(status['approval_errors'][0]['id'], approval['id'])
        self.assertTrue(status['approval_errors'][0]['errors'])
        with self.assertRaises(ValueError):
            self.store.export_publication(plan['id'], write=True)
        after = {str(p): p.read_bytes() for p in self.store.paths.workspace.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
