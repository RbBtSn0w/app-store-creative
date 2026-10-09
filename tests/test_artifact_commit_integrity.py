"""Artifact consumption refuses metadata rewritten after its commit."""
import json
import unittest
import test_delivery_lifecycle as fixtures


class ArtifactCommitIntegrityTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp

    def test_metadata_changes_cannot_relabel_or_drop_source_dependencies(self):
        path = self.store._path('artifacts', self.output['id'])
        original = path.read_bytes()
        for field, value in [('role', 'poster'), ('inputs', []),
                             ('logical_path', 'en-US/mac_16_10/relabel.png'),
                             ('partial', True), ('media_type', 'video/mp4')]:
            with self.subTest(field=field):
                record = json.loads(original)
                record[field] = value
                changed = json.dumps(record).encode()
                path.write_bytes(changed)
                try:
                    with self.assertRaisesRegex(ValueError, 'Artifact.*commit'):
                        self.store.verify_artifact(self.output['id'])
                    self.assertEqual(path.read_bytes(), changed)
                finally:
                    path.write_bytes(original)

    def test_missing_commit_event_does_not_accept_existing_object(self):
        event = self.store._path('events', self.output['_commit_event_id'])
        before = event.read_bytes()
        event.unlink()
        try:
            with self.assertRaisesRegex(ValueError, 'Artifact.*commit'):
                self.store.verify_artifact(self.output['id'])
        finally:
            event.write_bytes(before)

    def test_candidate_selection_rejects_rewritten_output_and_dependency(self):
        candidates = self.store.paths.workspace / 'records/candidates'
        original_candidates = {path.name: path.read_bytes() for path in candidates.glob('*.json')}
        for artifact, field, value in [(self.output, 'inputs', []),
                                       (self.input, 'role', 'poster')]:
            with self.subTest(artifact=artifact['id']):
                path = self.store._path('artifacts', artifact['id'])
                original = path.read_bytes()
                changed = json.loads(original)
                changed[field] = value
                changed_bytes = json.dumps(changed).encode()
                path.write_bytes(changed_bytes)
                try:
                    with self.assertRaisesRegex(ValueError, 'Artifact.*commit'):
                        self.store.select(self.run['id'], [self.output['id']])
                    self.assertEqual(path.read_bytes(), changed_bytes)
                    self.assertEqual({path.name: path.read_bytes()
                                      for path in candidates.glob('*.json')}, original_candidates)
                finally:
                    path.write_bytes(original)

    def test_failed_outcome_cannot_be_rewritten_as_success(self):
        attempt = self.store.start_attempt(self.run['id'], 'render', 'fixture-agent')
        output = self.store.register(attempt['id'], self.root / 'source.png', 'screenshot',
                                     inputs=[self.input['id']], logical_path='en-US/mac_16_10/failed.png')
        self.store.finish_attempt(attempt['id'], 'failed', reason='Fixture failure')
        path = self.store._path('attempts', attempt['id'], 'outcome')
        data = json.loads(path.read_bytes())
        data['status'] = 'succeeded'
        data['reason'] = None
        changed = json.dumps(data).encode()
        path.write_bytes(changed)
        before = list((self.store.paths.workspace / 'records/candidates').glob('*.json'))
        with self.assertRaisesRegex(ValueError, 'Attempt.*commit'):
            self.store.select(self.run['id'], [output['id']])
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(list((self.store.paths.workspace / 'records/candidates').glob('*.json')), before)

    def test_rewritten_attempt_owner_cannot_renew_lease(self):
        attempt = self.store.start_attempt(self.run['id'], 'capture', 'fixture-agent')
        path = self.store._path('attempts', attempt['id'], 'started')
        data = json.loads(path.read_bytes())
        data['owner'] = 'different-owner'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Attempt.*commit'):
            self.store.renew_attempt(attempt['id'], attempt['lease_token'])
