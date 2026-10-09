"""Public ASC normalization preserves managed records and observation bindings."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import canonical


class AscObservationCliTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def exercise(self, foreign=False):
        # This record fixture tests the CLI contract, not video production.
        target = {'app_id': 'app', 'version_id': 'version', 'platform': 'MAC_OS'}
        with self.store.transaction():
            plan = self.store._record('publications', {'id': 'a' * 32, 'target': target,
                'assets': [{'artifact_id': 'b' * 32, 'role': 'preview',
                            'source_checksum': 'c' * 32, 'poster_frame_time_code': '00:00:05:01'}]}, 'plan')
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        response = {'versionLocalizationId': 'localization', 'sets': [{'previews': [
            {'type': 'appPreviews', 'id': 'remote', 'attributes': {
                'sourceFileChecksum': 'c' * 32, 'assetDeliveryState': {'state': 'COMPLETE'},
                'previewFrameTimeCode': '00:00:05:01', 'previewImage': {'width': 0, 'height': 0}}}]}]}
        from datetime import datetime, timezone
        scope = {'target': {'app_id': 'foreign'} if foreign else target,
                 'artifact_id': 'b' * 32, 'localization_id': 'localization', 'remote_id': 'remote',
                 'observed_at': datetime.now(timezone.utc).isoformat(), 'evidence_reference': 'asc:read:fixture'}
        for name, value in [('response', response), ('scope', scope)]:
            (self.root / (name + '.json')).write_text(json.dumps(value))
        def snapshot():
            return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'normalize-asc-preview',
            '--repo', str(self.root), '--id', plan['id'], '--response', 'response.json', '--scope', 'scope.json'],
            capture_output=True, text=True)
        self.assertEqual(snapshot(), before)
        return result, plan

    def test_cli_output_is_accepted_by_existing_observation_contract(self):
        result, plan = self.exercise()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['remote_write'])
        for observation in output['observations']:
            self.assertEqual(observation['evidence_sha256'], hashlib.sha256((self.root / 'response.json').read_bytes()).hexdigest())
            self.assertEqual(observation['plan_sha256'], hashlib.sha256(canonical(plan)).hexdigest())
            saved = self.store.record_observation(plan['id'], observation, (self.root / 'response.json').read_bytes())
            self.assertEqual(saved['verdict'], 'FAIL' if observation['gate'] == 'poster' else 'PASS')
        self.assertEqual(self.store.verify_history()['status'], 'PASS')

    def test_foreign_executor_scope_is_rejected_without_record_writes(self):
        result, _ = self.exercise(True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('scope', result.stderr + result.stdout)

    def test_observation_cli_refuses_fifo_evidence_without_hanging(self):
        import os
        if not hasattr(os, 'mkfifo'):
            self.skipTest('Requires POSIX named pipes')
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        (self.root / 'observation.json').write_text('{}')
        evidence = self.root / 'evidence.json'
        os.mkfifo(evidence)
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        try:
            result = subprocess.run([sys.executable, str(cli), 'publication', 'observe',
                '--repo', str(self.root), '--id', 'a' * 32,
                '--observation', 'observation.json', '--evidence', 'evidence.json'],
                capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            self.fail('Observation CLI blocked on FIFO evidence')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular file', result.stderr + result.stdout)
        self.assertFalse(self.store.paths.workspace.exists())

    def test_normalization_refuses_fifo_before_opening_transaction(self):
        import os
        if not hasattr(os, 'mkfifo'):
            self.skipTest('Requires POSIX named pipes')
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        (self.root / 'scope.json').write_text('{}')
        os.mkfifo(self.root / 'response.json')
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'normalize-asc-preview',
            '--repo', str(self.root), '--id', 'a' * 32,
            '--response', 'response.json', '--scope', 'scope.json'],
            capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular file', result.stderr + result.stdout)
        self.assertFalse(self.store.paths.workspace.exists())
