"""Versioned project retention defaults are shared without implicit upgrades."""
import unittest
import test_retention_lifecycle as fixtures
from artifact_lifecycle import Lifecycle


class ArtifactPolicyTests(unittest.TestCase):
    setUp = fixtures.RetentionTests.setUp
    artifact = fixtures.RetentionTests.artifact
    quarantined = fixtures.RetentionTests.quarantined

    def test_project_trial_retention_supplies_cleanup_default(self):
        self.artifact()
        core = Lifecycle(self.root, {**self.cfg, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 0}})
        plan = core.plan_cleanup()
        self.assertEqual(plan['retention_days'], 0)
        self.assertTrue(plan['objects'])

    def test_unknown_policy_version_or_fields_are_rejected(self):
        for policy in ({'schema_version': 2}, {'schema_version': True}, {'schema_version': 1, 'trialRetentionDays': -1}, {'schema_version': 1, 'trialRetentionDays': True}, {'schema_version': 1, 'unknown': 1}):
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):
                    Lifecycle(self.root, {**self.cfg, 'artifactPolicy': policy})

    def test_project_quarantine_retention_supplies_purge_default(self):
        self.cfg = {**self.cfg, 'artifactPolicy': {'schema_version': 1, 'quarantineDays': 0}}
        self.store = Lifecycle(self.root, self.cfg)
        _, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'])
        self.assertEqual(plan['quarantine_days'], 0)

    def test_changed_project_policy_refuses_existing_cleanup_plan(self):
        self.artifact()
        core = Lifecycle(self.root, {**self.cfg, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 0}})
        plan = core.plan_cleanup()
        changed = Lifecycle(self.root, {**self.cfg, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 1}})
        with self.assertRaisesRegex(ValueError, 'policy'):
            changed.quarantine_cleanup(plan['id'], 'fixture-owner', 'Recheck changed policy')

    def test_public_policy_inspection_matches_cli_and_http_without_record_writes(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        import export_engine
        import test_studio_release
        self.cfg = {**self.cfg, 'artifactPolicy': {'schema_version': 1, 'trialRetentionDays': 3, 'quarantineDays': 2}}
        self.store = Lifecycle(self.root, self.cfg)
        self.store.config_path.write_text(json.dumps(self.cfg))
        expected = self.store.inspect_artifact_policy()
        self.assertEqual(expected['policy']['trialRetentionDays'], 3)
        self.assertFalse(expected['writes_performed'])
        records = self.store.paths.workspace / 'records'
        before = {str(path):path.read_bytes() for path in records.rglob('*.json')}
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'storage', 'artifact-policy', '--repo', str(self.root)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            value, _ = test_studio_release.StudioReleaseTests.request(self, ctx, '/api/storage/artifact-policy')
            self.assertEqual(value, expected)
            import urllib.error
            with self.assertRaises(urllib.error.HTTPError) as failure:
                test_studio_release.StudioReleaseTests.request(self, ctx, '/api/storage/artifact-policy?workspace=/tmp/override')
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
        self.assertEqual(before, {str(path):path.read_bytes() for path in records.rglob('*.json')})
