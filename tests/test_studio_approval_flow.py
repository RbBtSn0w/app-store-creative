"""Explicit Studio actions share candidate, approval and sealing contracts."""
import json
import unittest
import urllib.error
import test_delivery_lifecycle as fixtures
import export_engine
import test_studio_release


class StudioApprovalFlowTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    request = test_studio_release.StudioReleaseTests.request

    def test_explicit_validate_approve_seal_chain(self):
        self.store.config_path.write_text(json.dumps(self.config))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            validation, _ = self.request(ctx, '/api/candidates/validate', {'candidate_id': self.candidate['id']})
            self.assertEqual(validation['status'], 'PASS')
            approval, _ = self.request(ctx, '/api/approvals/design', {
                'candidate_id': self.candidate['id'], 'validation_id': validation['id'],
                'actor': 'human-owner', 'authorization_reference': 'human:studio-review', 'confirm': 'APPROVE'})
            delivery, _ = self.request(ctx, '/api/deliveries/seal', {
                'candidate_id': self.candidate['id'], 'validation_id': validation['id'],
                'approval_id': approval['id'], 'confirm': 'SEAL'})
            self.assertEqual(self.store.delivery_status(delivery['id'])['local_status'], 'PASS')
            self.assertEqual(self.store.verify_history()['status'], 'PASS')

    def test_missing_confirmation_cannot_create_approval(self):
        self.store.config_path.write_text(json.dumps(self.config))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/approvals/design', {'candidate_id': self.candidate['id'],
                    'validation_id': 'a'*32, 'actor': 'human', 'authorization_reference': 'human:review'})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
        self.assertEqual(list((self.store.paths.workspace / 'records/approvals').glob('*.json')), [])
