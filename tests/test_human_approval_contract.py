"""Design and upload approvals reject invalid authorization metadata before writing."""
import unittest
import test_publication_lifecycle as fixtures


class HumanApprovalContractTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_design_rejects_invalid_authorization_without_writing_approval(self):
        validation = self.store.validate_candidate(self.candidate['id'])
        self.assert_rejections(lambda actor, reference: self.store.approve_design(
            self.candidate['id'], validation['id'], actor, reference))

    def test_upload_rejects_invalid_authorization_without_writing_approval(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        self.assert_rejections(lambda actor, reference: self.store.approve_upload(plan['id'], actor, reference))

    def assert_rejections(self, approve):
        directory = self.store.paths.workspace / 'records/approvals'
        before = {path.name: path.read_bytes() for path in directory.glob('*.json')}
        for invalid in ('  ', '\n\t', True, 7, {'name': 'owner'}, ['human-reference']):
            for actor, reference in ((invalid, 'human:approval'), ('owner', invalid)):
                with self.subTest(actor=actor, reference=reference):
                    with self.assertRaisesRegex(ValueError, 'human actor and authorization'):
                        approve(actor, reference)
                    self.assertEqual({path.name: path.read_bytes() for path in directory.glob('*.json')}, before)

    def test_invalid_upload_records_do_not_authorize_status_or_handoff(self):
        import json
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        approval = self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        path = self.store._path('approvals', approval['id'])
        for change in ({'actor': ' '}, {'authorization_reference': []}, {'target': {**self.target, 'app_id': 'other'}}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**approval, **change}))
                status = self.store.publication_status(plan['id'])
                self.assertEqual(status['upload_approval'], 'pending')
                self.assertFalse(status['remote_verified'])
                self.assertEqual(status['approval_errors'][0]['id'], approval['id'])
                self.assertTrue(status['approval_errors'][0]['errors'])
                self.assertEqual(self.store.export_publication(plan['id'])['upload_approval'], 'pending')
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'commit|binding|integrity'):
                    self.store.export_publication(plan['id'], write=True)
                self.assertEqual(path.read_bytes(), before)

    def test_design_approval_consumer_rechecks_authorization_and_config_binding(self):
        import json
        validation = self.store.validate_candidate(self.candidate['id'])
        approval = self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human:design')
        path = self.store._path('approvals', approval['id'])
        for change in ({'actor': ' '}, {'authorization_reference': True}, {'config_sha256': '0'*64}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**approval, **change}))
                with self.assertRaises(ValueError):
                    self.store.seal(self.candidate['id'], validation['id'], approval['id'])

    def test_run_status_marks_invalid_design_approval_stale(self):
        import json
        validation = self.store.validate_candidate(self.candidate['id'])
        approval = self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human:design')
        path = self.store._path('approvals', approval['id'])
        for change in ({'actor': ' '}, {'authorization_reference': True}, {'validation_id': None}, {'candidate_sha256': None}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**approval, **change}))
                candidate = next(item for item in self.store.status(self.run['id'])['candidates'] if item['id'] == self.candidate['id'])
                result = next(item for item in candidate['design_approvals'] if item['id'] == approval['id'])
                self.assertEqual(result['binding_status'], 'STALE')
                self.assertTrue(result['binding_errors'])

    def test_committed_design_approval_cannot_authorize_another_scope(self):
        from artifact_lifecycle import identifier
        validation = self.store.validate_candidate(self.candidate['id'])
        approval = self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human:design')
        changes = ({'stage': 'upload'}, {'candidate_id': identifier()},
                   {'validation_id': identifier()}, {'candidate_sha256': '0' * 64},
                   {'config_sha256': '0' * 64},
                   {'target': {**approval['target'], 'version': 'other-version'}})
        directory = self.store.paths.workspace / 'records/deliveries'
        before = {p.name: p.read_bytes() for p in directory.glob('*.json')}
        for change in changes:
            with self.subTest(change=change):
                with self.store.transaction():
                    other = self.store._record('approvals', {**approval, **change, 'id': identifier()})
                # Valid commit binding must not bypass the approval scope checks.
                self.assertEqual(self.store._read('approvals', other['id']), other)
                with self.assertRaisesRegex(ValueError, 'bound to candidate'):
                    self.store.seal(self.candidate['id'], validation['id'], other['id'])
                self.assertEqual({p.name: p.read_bytes() for p in directory.glob('*.json')}, before)

    def test_committed_upload_approval_cannot_authorize_another_scope(self):
        from artifact_lifecycle import canonical, identifier
        import hashlib
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        approval = self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
        for change in ({'stage': 'design'}, {'publication_id': identifier()},
                       {'plan_sha256': '0' * 64},
                       {'target': {**plan['target'], 'app_id': 'another-app'}}):
            with self.subTest(change=change):
                with self.store.transaction():
                    other = self.store._record('approvals', {**approval, **change, 'id': identifier()})
                self.assertEqual(self.store._read('approvals', other['id']), other)
                self.assertFalse(self.store._upload_approval_matches(other, plan, plan_hash))
