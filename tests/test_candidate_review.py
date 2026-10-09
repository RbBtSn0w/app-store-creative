"""Read persisted review state after lost responses or process restart."""
import json
import unittest
import test_delivery_lifecycle as fixtures
import export_engine
import test_studio_release
from artifact_lifecycle import Lifecycle


class CandidateReviewTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved
    request = test_studio_release.StudioReleaseTests.request

    def test_restart_recovers_exact_approval_and_delivery_without_writes(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.store.config_path.write_text(json.dumps(self.config))
        before = {str(p): p.read_bytes() for p in self.store.paths.workspace.rglob('*.json')}
        restarted = Lifecycle.from_configuration(self.root)
        review = restarted.candidate_review(self.candidate['id'])
        self.assertEqual(review['validation']['id'], validation['id'])
        self.assertEqual(review['approval_id'], approval['id'])
        self.assertEqual(review['delivery_id'], delivery['id'])
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            result, _ = self.request(ctx, '/api/candidates/' + self.candidate['id'] + '/review')
            self.assertEqual(result, review)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.store.paths.workspace.rglob('*.json')})

    def test_fresh_candidate_has_no_invented_approval(self):
        result = self.store.candidate_review(self.candidate['id'])
        self.assertIsNone(result['validation']); self.assertIsNone(result['approval_id']); self.assertIsNone(result['delivery_id'])
