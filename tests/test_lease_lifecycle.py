"""Execution leases fence expired and replaced producers."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest
import test_artifact_lifecycle as fixtures
import artifact_lifecycle


class LeaseTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def attempt(self):
        run = self.store.start_run({})
        return self.store.start_attempt(run['id'], 'render', 'agent-a', lease_seconds=60)

    def test_other_client_requires_matching_lease_token(self):
        attempt = self.attempt()
        other = artifact_lifecycle.Lifecycle(self.root, self.cfg)
        source = self.root / 'sample'; source.write_bytes(b'bytes')
        with self.assertRaisesRegex(ValueError, 'lease'):
            other.register(attempt['id'], source, 'screenshot')
        data = other.register(attempt['id'], source, 'screenshot', lease_token=attempt['lease_token'])
        self.assertEqual(data['attempt_id'], attempt['id'])

    def test_expired_producer_cannot_write_and_recovery_preserves_history(self):
        attempt = self.attempt()
        source = self.root / 'sample'; source.write_bytes(b'bytes')
        with patch('lease_lifecycle.utcnow', return_value=datetime.now(timezone.utc) + timedelta(hours=1)):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.store.register(attempt['id'], source, 'screenshot')
            replacement = self.store.recover_attempt(attempt['id'], owner='agent-b', reason='Producer crashed')
        self.assertNotEqual(replacement['id'], attempt['id'])
        self.assertEqual(replacement['retry_of'], attempt['id'])
        self.assertEqual(self.store._read('attempts', attempt['id'], 'outcome')['status'], 'interrupted')
        with self.assertRaisesRegex(ValueError, 'ended'):
            self.store.finish_attempt(attempt['id'], 'succeeded')

    def test_renewal_rotates_token_and_preserves_prior_lease(self):
        attempt = self.attempt()
        renewed = self.store.renew_attempt(attempt['id'], lease_token=attempt['lease_token'], lease_seconds=120)
        other = artifact_lifecycle.Lifecycle(self.root, self.cfg)
        with self.assertRaisesRegex(ValueError, 'lease'):
            other.finish_attempt(attempt['id'], 'succeeded', lease_token=attempt['lease_token'])
        other.finish_attempt(attempt['id'], 'succeeded', lease_token=renewed['lease_token'])
        self.assertEqual(len(list((self.store.paths.workspace / 'records/attempt-leases' / attempt['id']).glob('*.json'))), 2)

    def test_unexpired_attempt_cannot_be_taken_over(self):
        attempt = self.attempt()
        with self.assertRaisesRegex(ValueError, 'active'):
            self.store.recover_attempt(attempt['id'], owner='agent-b', reason='Takeover')

    def test_invalid_duration_fails_before_attempt_is_recorded(self):
        run = self.store.start_run({})
        for duration in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.store.start_attempt(run['id'], 'render', 'agent', lease_seconds=duration)
        self.assertEqual(list((self.store.paths.workspace / 'records/attempts').glob('*/started.json')), [])

    def test_concurrent_recovery_creates_only_one_replacement(self):
        from concurrent.futures import ThreadPoolExecutor
        attempt = self.attempt()
        clients = [artifact_lifecycle.Lifecycle(self.root, self.cfg) for _ in range(2)]
        def recover(client):
            try:
                return client.recover_attempt(attempt['id'], owner='replacement', reason='Crashed')
            except ValueError as error:
                return error
        with patch('lease_lifecycle.utcnow', return_value=datetime.now(timezone.utc) + timedelta(hours=2)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(recover, clients))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(len(self.store.status(attempt['run_id'])['attempts']), 2)

    def test_lease_is_checked_again_before_artifact_commit(self):
        attempt = self.attempt()
        source = self.root / 'sample'; source.write_bytes(b'bytes')
        current = datetime.now(timezone.utc)
        with patch('lease_lifecycle.utcnow', side_effect=[current, current + timedelta(hours=1)]):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.store.register(attempt['id'], source, 'screenshot')
        self.assertEqual(list((self.store.paths.workspace / 'records/artifacts').glob('*.json')), [])

    def test_production_guard_renews_and_stops_heartbeat(self):
        import threading
        attempt = self.attempt()
        renewed = threading.Event()
        original = self.store.renew_attempt
        def track(*args, **kwargs):
            result = original(*args, **kwargs)
            if result['generation'] >= 3:
                renewed.set()
            return result
        with patch.object(self.store, 'renew_attempt', side_effect=track):
            with self.store.keep_lease(attempt['id'], lease_seconds=1):
                self.assertTrue(renewed.wait(timeout=2))
        self.store.finish_attempt(attempt['id'], 'succeeded')

    def test_cli_renewal_fences_previous_token(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        attempt = self.attempt()
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = [sys.executable, str(cli), 'attempt']
        renewed = subprocess.run(command + ['renew', '--repo', str(self.root), '--id', attempt['id'],
            '--lease-token', attempt['lease_token']], capture_output=True, text=True)
        self.assertEqual(renewed.returncode, 0, renewed.stderr)
        latest = json.loads(renewed.stdout)['lease_token']
        finish = command + ['finish', '--repo', str(self.root), '--id', attempt['id'], '--status', 'succeeded']
        stale = subprocess.run(finish + ['--lease-token', attempt['lease_token']], capture_output=True, text=True)
        self.assertNotEqual(stale.returncode, 0)
        completed = subprocess.run(finish + ['--lease-token', latest], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
