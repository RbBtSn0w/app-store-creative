"""Retention uses the same dependency consistency rules as production and archives."""
import json
import unittest
import test_artifact_lifecycle as fixtures


class RetentionDependencyContractTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_protected_dependency_cycle_refuses_cleanup_plan(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'fixture-owner')
        source_path = self.store.work_path(attempt['id']) / 'source'; source_path.write_bytes(b'fixture')
        source = self.store.register(attempt['id'], source_path, 'source')
        output = self.store.register(attempt['id'], source_path, 'screenshot', inputs=[source['id']])
        self.store.finish_attempt(attempt['id'], 'succeeded')
        self.store.select(run['id'], [output['id']])
        path = self.store._path('artifacts', source['id'])
        path.write_text(json.dumps({**source, 'inputs': [output['id']]}))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.plan_cleanup(retention_days=0)
        self.assertEqual(list((self.store.paths.workspace / 'records/maintenance').rglob('*.json')), [])

    def test_dependency_validator_rejects_cycle_independently_of_record_integrity(self):
        from artifact_lifecycle import dependency_closure
        records = {'source': {'id': 'source', 'inputs': ['output']},
                   'output': {'id': 'output', 'inputs': ['source']}}
        with self.assertRaisesRegex(ValueError, 'cycle'):
            dependency_closure(['output'], records.__getitem__)
