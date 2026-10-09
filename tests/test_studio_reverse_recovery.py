"""HTTP recovery reuses explicit original authority for interrupted reverse switches."""
import unittest
import urllib.error
import test_reverse_relocation_rollback as fixtures
import test_studio_release
import export_engine
from artifact_lifecycle import Lifecycle


class StudioReverseRecoveryTests(unittest.TestCase):
    setUp = fixtures.ReverseRollbackTests.setUp
    source = fixtures.ReverseRollbackTests.source
    targets = fixtures.ReverseRollbackTests.targets
    prepared = fixtures.ReverseRollbackTests.prepared
    moved = fixtures.ReverseRollbackTests.moved
    reverse = fixtures.ReverseRollbackTests.reverse
    interrupted = fixtures.ReverseRollbackTests.interrupted
    request = test_studio_release.StudioReleaseTests.request

    def recover(self, action):
        artifact, _, moved, reverse, run, before = self.interrupted()
        workspace = str(moved.paths.workspace)
        with export_engine.LocalServerContext(self.root, moved.config_path) as ctx:
            payload = {'id': reverse['id'], 'source_workspace': workspace, 'actor': 'test-owner',
                       'reason': 'Recover interrupted reverse fixture', 'confirm': action.upper()}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/storage/' + action + '-relocate', payload)
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            result, _ = self.request(ctx, '/api/storage/' + action + '-reverse-relocate', payload)
            self.assertEqual(result['status'], 'SWITCHED' if action == 'resume' else 'ROLLED_BACK')
        current = Lifecycle.from_configuration(self.root, moved.config_path)
        current.verify_artifact(artifact['id']); current._run(run['id']); current.start_run({})
        if action == 'rollback':
            self.assertEqual(moved.config_path.read_bytes(), before)

    def test_resume_reverse_after_directory_exchange(self):
        self.recover('resume')

    def test_rollback_reverse_after_directory_exchange(self):
        self.recover('rollback')
