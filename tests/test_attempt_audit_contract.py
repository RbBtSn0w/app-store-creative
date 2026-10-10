import unittest
import test_artifact_lifecycle as fixtures


class AttemptAuditContractTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_invalid_stage_or_owner_creates_no_attempt(self):
        run = self.store.start_run({})
        for stage, owner in [(' ', 'agent'), ('capture', '\t'), (17, 'agent'), ('capture', ['agent'])]:
            with self.subTest(stage=stage, owner=owner):
                with self.assertRaisesRegex(ValueError, 'Stage and owner'):
                    self.store.start_attempt(run['id'], stage, owner)
                self.assertEqual(self.store.status(run['id'])['attempts'], [])

    def test_invalid_failure_reason_does_not_end_attempt(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'agent')
        for reason in [' ', 17, ['failed']]:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, 'require a reason'):
                    self.store.finish_attempt(attempt['id'], 'failed', reason=reason)
                self.assertIsNone(self.store.status(run['id'])['attempts'][0]['outcome'])
