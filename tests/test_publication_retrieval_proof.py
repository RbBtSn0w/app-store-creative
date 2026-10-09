"""Publication plans bind actual independent Git retrieval evidence."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_publication_lifecycle as fixtures


class PublicationRetrievalProofTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_plan_records_exact_retrieval_identity(self):
        commit = self.persist(); plan = self.store.plan_publication(self.delivery['id'], commit, self.target)
        proof = plan['retrieval_proof']
        self.assertTrue(proof['retrieval_verified'])
        self.assertEqual(proof['archive_commit'], commit)
        self.assertEqual(proof['archive_path'], plan['archive_path'])
        self.assertEqual(proof['manifest_sha256'], self.delivery['manifest_sha256'])
        self.assertTrue(self.store.publication_status(plan['id'])['retrieval_verified'])

    def test_failed_clone_does_not_create_publication_plan(self):
        commit = self.persist()
        with patch('delivery_lifecycle.verify_git_archive', side_effect=ValueError('Clone failed')):
            with self.assertRaisesRegex(ValueError, 'Clone failed'):
                self.store.plan_publication(self.delivery['id'], commit, self.target)
        self.assertEqual(list((self.store.paths.workspace / 'records/publications').glob('*/plan.json')), [])

    def test_mismatched_proof_fails_publication_archive_gate(self):
        commit = self.persist(); plan = self.store.plan_publication(self.delivery['id'], commit, self.target)
        path = self.store._path('publications', plan['id'], 'plan')
        body = json.loads(path.read_text()); body['retrieval_proof']['archive_commit'] = '0' * 40
        path.write_text(json.dumps(body))
        before = path.read_bytes()
        status = self.store.publication_status(plan['id'])
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(status['delivery_id'])
        self.assertFalse(status['remote_verified'])
        self.assertFalse(status['remote_media_verified'])
        self.assertEqual(status['gates'], [])
        self.assertFalse(status['retrieval_verified'])
        self.assertEqual(status['status'], 'FAIL')

    def test_mismatched_proof_blocks_upload_approval_and_handoff(self):
        commit = self.persist(); plan = self.store.plan_publication(self.delivery['id'], commit, self.target)
        path = self.store._path('publications', plan['id'], 'plan')
        body = json.loads(path.read_text()); body['retrieval_proof']['manifest_sha256'] = '0' * 64
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.approve_upload(plan['id'], 'owner', 'human:approved')
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.export_publication(plan['id'])

    def test_missing_or_failed_provenance_cannot_authorize_publication(self):
        commit = self.persist()
        plan = self.store.plan_publication(self.delivery['id'], commit, self.target)
        path = self.store._path('publications', plan['id'], 'plan')
        for value in (None, False, 1, 'true'):
            with self.subTest(value=value):
                body = json.loads(json.dumps(plan))
                if value is None:
                    body['retrieval_proof'].pop('provenance_verified')
                else:
                    body['retrieval_proof']['provenance_verified'] = value
                path.write_text(json.dumps(body))
                before = path.read_bytes()
                self.assertFalse(self.store.publication_status(plan['id'])['retrieval_verified'])
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.approve_upload(plan['id'], 'owner', 'human:approved')
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.export_publication(plan['id'], write=True)
                self.assertEqual(path.read_bytes(), before)

    def test_legitimately_committed_invalid_proof_is_rejected_by_field_validation(self):
        from artifact_lifecycle import identifier
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        for value in (None, False, 1, 'true'):
            with self.subTest(value=value):
                body = json.loads(json.dumps(plan))
                body['id'] = identifier()
                if value is None:
                    body['retrieval_proof'].pop('provenance_verified')
                else:
                    body['retrieval_proof']['provenance_verified'] = value
                with self.store.transaction():
                    saved = self.store._record('publications', body, 'plan')
                self.assertEqual(self.store._read('publications', saved['id'], 'plan'), saved)
                with self.assertRaisesRegex(ValueError, 'retrieval proof'):
                    self.store.approve_upload(saved['id'], 'owner', 'human:approved')
                with self.assertRaisesRegex(ValueError, 'retrieval proof'):
                    self.store.export_publication(saved['id'], write=True)
                self.assertFalse(self.store.publication_status(saved['id'])['retrieval_verified'])
                self.assertFalse((self.store.paths.publications / saved['id']).exists())
