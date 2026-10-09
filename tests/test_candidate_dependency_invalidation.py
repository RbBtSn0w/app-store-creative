"""Live dependencies invalidate mutable candidate use without rewriting approvals."""
import json
import unittest
import test_delivery_lifecycle as fixtures


class CandidateDependencyInvalidationTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_same_runtime_cannot_seal_after_project_recipe_changes(self):
        validation, approval = self.approved()
        original = self.store._path('approvals', approval['id']).read_bytes()
        self.store.config_path.write_text(json.dumps({**self.config, 'theme': {'background': '#112233'}}))
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(self.store._path('approvals', approval['id']).read_bytes(), original)

    def test_same_runtime_cannot_record_new_approval_after_recipe_changes(self):
        validation = self.store.validate_candidate(self.candidate['id'])
        self.store.config_path.write_text(json.dumps({**self.config, 'theme': {'background': '#112233'}}))
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human:design')
        self.assertEqual(list((self.store.paths.workspace / 'records/approvals').glob('*.json')), [])

    def test_source_change_blocks_new_seal_but_preserves_existing_delivery(self):
        from artifact_lifecycle import digest
        from pathlib import Path
        source = self.root / 'source.png'
        run = self.store.start_run({'platform': 'MAC_OS', 'version': '1.5'}, {'source.png': digest(source)})
        attempt = self.store.start_attempt(run['id'], 'render', 'test-owner')
        captured = self.store.register(attempt['id'], source, 'source', logical_path='source.png')
        rendered = self.store.register(attempt['id'], source, 'screenshot', inputs=[captured['id']],
                                       logical_path='en-US/mac_16_10/hero.png')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        candidate = self.store.select(run['id'], [rendered['id']])
        validation = self.store.validate_candidate(candidate['id'])
        approval = self.store.approve_design(candidate['id'], validation['id'], 'owner', 'human:design')
        delivery = self.store.seal(candidate['id'], validation['id'], approval['id'])
        before = self.store._path('approvals', approval['id']).read_bytes()
        manifest = Path(delivery['local_path']) / 'manifest.json'; archive_before = manifest.read_bytes()
        source.write_bytes(b'new source revision')
        with self.assertRaisesRegex(ValueError, 'source inputs changed'):
            self.store.seal(candidate['id'], validation['id'], approval['id'])
        self.assertEqual(self.store.delivery_status(delivery['id'])['local_status'], 'PASS')
        self.assertEqual(manifest.read_bytes(), archive_before)
        self.assertEqual(self.store._path('approvals', approval['id']).read_bytes(), before)
