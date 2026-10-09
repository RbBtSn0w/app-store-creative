"""All lifecycle clients share strict versioned record boundaries."""
import json
import unittest
import test_artifact_lifecycle as fixtures


class LifecycleRecordSchemaTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_reads_reject_non_integer_and_unknown_versions(self):
        run = self.store.start_run({})
        path = self.store._path('runs', run['id'])
        for version in (True, 1.0, '1', 2, None):
            with self.subTest(version=version):
                path.write_text(json.dumps({**run, 'schema_version': version}))
                with self.assertRaisesRegex(ValueError, 'schema'):
                    self.store.status(run['id'])

    def test_non_object_records_report_schema_error(self):
        run = self.store.start_run({})
        path = self.store._path('runs', run['id'])
        for data in ([], None, 1, 'record'):
            with self.subTest(data=data):
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, 'schema'):
                    self.store.status(run['id'])

    def test_unknown_writer_version_fails_before_creating_record(self):
        self.store.start_run({})
        for index, version in enumerate((True, 1.0, '1', 2, None)):
            identity = 'invalid-' + str(index)
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, 'schema'):
                    self.store._record('runs', {'id': identity, 'schema_version': version})
                self.assertFalse(self.store._path('runs', identity).exists())

    def test_record_identity_must_match_requested_identity(self):
        run = self.store.start_run({})
        path = self.store._path('runs', run['id'])
        for identity in ('another-run', None, 1):
            with self.subTest(identity=identity):
                path.write_text(json.dumps({**run, 'id': identity}))
                with self.assertRaisesRegex(ValueError, 'identity'):
                    self.store.status(run['id'])

    def test_parent_symlink_cannot_redirect_record_reads_inside_workspace(self):
        run = self.store.start_run({})
        path = self.store._path('runs', run['id'])
        alternate = self.store.paths.workspace / 'alternate-records'
        path.parent.rename(alternate)
        path.parent.symlink_to(alternate, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlinked'):
            self.store.status(run['id'])

    def test_attempt_status_refuses_unknown_versions_and_wrong_identities(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'fixture-owner')
        self.store.finish_attempt(attempt['id'], 'failed', reason='Fixture failure')
        for suffix in ('started', 'outcome'):
            path = self.store._path('attempts', attempt['id'], suffix)
            original = path.read_text()
            for change, message in (({'schema_version': 2}, 'schema'), ({'id': 'another-attempt'}, 'identity')):
                with self.subTest(suffix=suffix, change=change):
                    path.write_text(json.dumps({**json.loads(original), **change}))
                    try:
                        with self.assertRaisesRegex(ValueError, message):
                            self.store.status(run['id'])
                    finally:
                        path.write_text(original)

    def test_dangling_outcome_link_is_rejected_instead_of_reported_as_running(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'fixture-owner')
        outcome = self.store._path('attempts', attempt['id'], 'outcome')
        outcome.symlink_to(self.root / 'missing-outcome')
        with self.assertRaisesRegex(ValueError, 'Symlinked|escapes'):
            self.store.status(run['id'])

    def test_all_business_record_categories_reject_missing_or_unknown_schema(self):
        from operation_history import CATEGORIES
        self.store.start_run({})
        for category in sorted(CATEGORIES):
            identity = 'schema-boundary-' + category
            path = self.store._path(category, identity)
            path.parent.mkdir(parents=True, exist_ok=True)
            for version in ('missing', True, 1.0, '1', 0, 2, None):
                with self.subTest(category=category, version=version):
                    data = {'id': identity}
                    if version != 'missing':
                        data['schema_version'] = version
                    original = json.dumps(data).encode()
                    path.write_bytes(original)
                    with self.assertRaisesRegex(ValueError, 'schema'):
                        self.store._read(category, identity)
                    self.assertEqual(path.read_bytes(), original)
