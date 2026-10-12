"""Runs bind their workflow contract and implementation at creation time."""
import json
import unittest
import test_artifact_lifecycle as fixtures


class RunWorkflowSnapshotTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_run_snapshots_workflow_contract_and_implementation(self):
        run = self.store.start_run({'version': '1.5'})
        self.assertEqual(run['workflow'], {'name': 'app-store-creative', 'version': 1,
                                         'implementation': self.store._implementation_identity})
        self.assertEqual(self.store.status(run['id'])['run']['workflow'], run['workflow'])

    def test_missing_or_unknown_workflow_cannot_start_an_attempt(self):
        run = self.store.start_run({})
        path = self.store._path('runs', run['id'])
        for workflow in (None, {'name': 'app-store-creative', 'version': 2},
                         {'name': 'app-store-creative', 'version': True}):
            with self.subTest(workflow=workflow):
                path.write_text(json.dumps({**run, 'workflow': workflow}))
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'workflow'):
                    self.store.start_attempt(run['id'], 'capture', 'fixture-owner')
                self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list((self.store.paths.workspace / 'records/attempts').glob('*/started.json')), [])

    def test_changed_snapshot_target_and_source_bindings_cannot_start_attempt(self):
        run = self.store.start_run({'version': '1.5'})
        path = self.store._path('runs', run['id'])
        for fields in ({'config': {'project': {'id': 'changed'}}},
                       {'target': {'version': '99'}}, {'source_hashes': {'source': '0' * 64}}):
            with self.subTest(fields=fields):
                path.write_text(json.dumps({**run, **fields}))
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'snapshot|commit event'):
                    self.store.start_attempt(run['id'], 'capture', 'fixture-owner')
                self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list((self.store.paths.workspace / 'records/attempts').glob('*/started.json')), [])

    def test_project_identity_is_required_before_any_write(self):
        import tempfile
        from pathlib import Path
        from artifact_lifecycle import Lifecycle
        for project in (None, {}, {'id': ''}, {'id': '   '}, {'id': True}, {'id': 'bad\nidentity'}):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                with self.assertRaisesRegex(ValueError, 'Project identity'):
                    Lifecycle(root, {'project': project}).start_run({})
                self.assertEqual(list(root.iterdir()), [])
