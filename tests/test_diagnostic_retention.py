"""Diagnostic retention remains subordinate to live references and byte identity."""
import unittest
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import Lifecycle


class DiagnosticRetentionTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_diagnostic_policy_expires_only_unreferenced_diagnostics(self):
        config = {**self.store.config, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 30, 'diagnosticRetentionDays': 0}}
        store = Lifecycle(self.root, config)
        run = store.start_run({})
        attempt = store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'diagnostic'; source.write_bytes(b'diagnostic bytes')
        diagnostic = store.register(attempt['id'], source, 'diagnostic')
        source.write_bytes(b'trial bytes')
        trial = store.register(attempt['id'], source, 'screenshot')
        store.finish_attempt(attempt['id'], 'failed', reason='Trial rejected')
        plan = store.plan_cleanup()
        self.assertEqual([item['sha256'] for item in plan['objects']], [diagnostic['sha256']])
        operation = store.quarantine_cleanup(plan['id'], 'owner', 'Expire diagnostics')
        store.verify_artifact(trial['id'])
        store.restore_cleanup(operation['id'], 'owner', 'Recover diagnostics')
        store.verify_artifact(diagnostic['id'])

    def test_diagnostic_alias_of_recent_trial_remains_protected(self):
        store = Lifecycle(self.root, {**self.store.config, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 30, 'diagnosticRetentionDays': 0}})
        run = store.start_run({}); attempt = store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'shared'; source.write_bytes(b'shared bytes')
        store.register(attempt['id'], source, 'diagnostic')
        store.register(attempt['id'], source, 'screenshot')
        store.finish_attempt(attempt['id'], 'failed', reason='Rejected')
        self.assertEqual(store.plan_cleanup()['objects'], [])

    def test_active_diagnostics_never_expire(self):
        store = Lifecycle(self.root, {**self.store.config, 'artifactPolicy': {'schema_version': 1, 'diagnosticRetentionDays': 0}})
        run = store.start_run({}); attempt = store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'active'; source.write_bytes(b'active diagnostic')
        store.register(attempt['id'], source, 'diagnostic')
        self.assertEqual(store.plan_cleanup()['objects'], [])

    def test_selected_output_protects_expired_diagnostic_dependency(self):
        store = Lifecycle(self.root, {**self.store.config, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 0, 'diagnosticRetentionDays': 0}})
        run = store.start_run({}); attempt = store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'diagnostic'; source.write_bytes(b'producer evidence')
        diagnostic = store.register(attempt['id'], source, 'diagnostic')
        source.write_bytes(b'selected output')
        output = store.register(attempt['id'], source, 'screenshot', inputs=[diagnostic['id']])
        store.finish_attempt(attempt['id'], 'succeeded')
        store.select(run['id'], [output['id']])
        self.assertEqual(store.plan_cleanup()['objects'], [])
        store.verify_artifact(diagnostic['id'])

    def test_diagnostic_cutoff_uses_plan_time_and_purge_rechecks_original_policy(self):
        from datetime import datetime, timedelta
        store = Lifecycle(self.root, {**self.store.config, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 30, 'diagnosticRetentionDays': 0, 'quarantineDays': 0}})
        run = store.start_run({}); attempt = store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'diagnostic'; source.write_bytes(b'expired diagnostic')
        diagnostic = store.register(attempt['id'], source, 'diagnostic')
        store.finish_attempt(attempt['id'], 'failed', reason='Rejected')
        plan = store.plan_cleanup()
        cutoff = datetime.fromisoformat(plan['cutoff'])
        # Earlier observation time cannot borrow a later wall clock to expire media.
        _, earlier = store._retention_state(30, cutoff - timedelta(days=1))
        self.assertEqual(earlier, [])
        _, original = store._retention_state(30, cutoff)
        self.assertEqual(original, plan['objects'])
        quarantine = store.quarantine_cleanup(plan['id'], 'owner', 'Expire diagnostics')
        purge = store.plan_purge(quarantine['id'])
        result = store.purge_cleanup(purge['id'], 'owner', 'Retire diagnostic payload')
        self.assertEqual(result['status'], 'purged')
        self.assertFalse(store.object_path(diagnostic['sha256']).exists())
        self.assertTrue(store._path('artifacts', diagnostic['id']).exists())
        self.assertEqual(store.maintenance_status(quarantine['id'])['status'], 'PASS')
