"""Publication consumption rechecks target shape and approved delivery platform."""
import json
import unittest
import test_publication_lifecycle as fixtures


class PublicationTargetConsumptionTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def test_invalid_saved_target_cannot_be_approved_or_exported(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        path = self.store._path('publications', plan['id'], 'plan')
        for changes in ({'platform': 'IOS'}, {'app_id': True}, {'version_id': ' '}):
            with self.subTest(changes=changes):
                path.write_text(json.dumps({**plan, 'target': {**plan['target'], **changes}}))
                before = path.read_bytes()
                approval_paths = list((self.store.paths.workspace / 'records/approvals').glob('*.json'))
                with self.assertRaises(ValueError):
                    self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload')
                with self.assertRaises(ValueError):
                    self.store.export_publication(plan['id'], write=True)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(list((self.store.paths.workspace / 'records/approvals').glob('*.json')), approval_paths)
                self.assertFalse((self.store.paths.publications / plan['id'] / 'plan.json').exists())

    def test_changed_saved_assets_cannot_be_approved_or_exported(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        path = self.store._path('publications', plan['id'], 'plan')
        for changes in ({'path': '../outside.png'}, {'sha256': '0' * 64},
                        {'source_checksum': '0' * 32}, {'role': 'preview'},
                        {'artifact_id': 'another-artifact'}):
            with self.subTest(changes=changes):
                body = json.loads(json.dumps(plan))
                body['assets'][0].update(changes)
                path.write_text(json.dumps(body))
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload')
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.export_publication(plan['id'], write=True)
                self.assertFalse((self.store.paths.publications / plan['id'] / 'plan.json').exists())

    def test_legitimately_committed_invalid_assets_still_fail_archive_comparison(self):
        from artifact_lifecycle import identifier
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        for changes in ({'path': '../outside.png'}, {'sha256': '0' * 64},
                        {'source_checksum': '0' * 32}, {'role': 'preview'},
                        {'artifact_id': 'another-artifact'}):
            with self.subTest(changes=changes):
                body = json.loads(json.dumps(plan))
                body['id'] = identifier()
                body['assets'][0].update(changes)
                with self.store.transaction():
                    saved = self.store._record('publications', body, 'plan')
                self.assertEqual(self.store._read('publications', saved['id'], 'plan'), saved)
                with self.assertRaisesRegex(ValueError, 'assets'):
                    self.store.approve_upload(saved['id'], 'owner', 'human:approved')
                with self.assertRaisesRegex(ValueError, 'assets'):
                    self.store.export_publication(saved['id'], write=True)
                self.assertFalse((self.store.paths.publications / saved['id']).exists())
