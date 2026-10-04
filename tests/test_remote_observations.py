"""Remote completion derives from separately bound, nonconflicting evidence."""
from datetime import datetime, timezone
import hashlib
import unittest
import test_publication_lifecycle as fixtures
from artifact_lifecycle import canonical


class RemoteObservationTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def plan(self, approved=True):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        if approved:
            self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        return plan

    def observe(self, plan, gate, facts, **extra):
        return self.store.record_observation(plan['id'], {
            'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': self.target,
            'artifact_id': plan['assets'][0]['artifact_id'], 'remote_id': 'remote-media',
            'gate': gate, 'source': 'asc-api' if gate in ('upload', 'processing') else 'media-probe',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'evidence_reference': 'executor:verified-receipt', 'facts': facts, **extra})

    def test_upload_receipt_alone_never_proves_media_completion(self):
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_separate_matching_observations_prove_screenshot_completion(self):
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        self.observe(plan, 'media', {'media_verified': True})
        state = self.store.publication_status(plan['id'])
        self.assertEqual(state['status'], 'PASS')
        self.assertTrue(state['remote_verified'])
        self.assertFalse(state['remote_write'])

    def test_conflicting_observations_require_explicit_supersession(self):
        plan = self.plan()
        first = self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        second = self.observe(plan, 'processing', {'processing_state': 'FAILED'})
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'CONFLICT')
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, supersedes=[first['id'], second['id']])
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'UNKNOWN')

    def test_foreign_plan_and_target_observations_are_rejected(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, plan_sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, target={**self.target, 'app_id': 'foreign'})

    def test_unapproved_remote_facts_cannot_mark_completion(self):
        plan = self.plan(approved=False)
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        self.observe(plan, 'media', {'media_verified': True})
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_sensitive_or_unrecognized_receipt_fields_are_rejected(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'facts'):
            self.observe(plan, 'processing', {'processing_state': 'COMPLETE', 'authorization': 'secret'})

    def test_stale_observations_never_prove_completion(self):
        from datetime import timedelta
        plan = self.plan()
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']}, observed_at=old)
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, observed_at=old)
        self.observe(plan, 'media', {'media_verified': True}, observed_at=old)
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'UNKNOWN')

    def test_different_remote_resources_are_conflicting(self):
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, remote_id='different-resource')
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'CONFLICT')

    def test_preview_requires_decoded_poster_and_playback(self):
        from remote_observations import gate_result, requirements
        preview = {'role': 'preview', 'poster_frame_time_code': '00:00:05:01'}
        self.assertEqual(requirements(preview), ['upload', 'processing', 'playback', 'poster'])
        facts = {'poster_width': 1920, 'poster_height': 1080, 'poster_frame_time_code': '00:00:05:01'}
        self.assertEqual(gate_result(preview, 'poster', facts, 'asc-api'), 'UNKNOWN')
        self.assertEqual(gate_result(preview, 'poster', {**facts, 'poster_verified': True}, 'media-probe'), 'PASS')
        self.assertEqual(gate_result(preview, 'poster', {**facts, 'poster_verified': False}, 'browser'), 'FAIL')

    def test_corrupted_archive_prevents_complete_publication(self):
        from pathlib import Path
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        self.observe(plan, 'media', {'media_verified': True})
        (Path(self.delivery['local_path']) / 'media/en-US/mac_16_10/hero.png').write_bytes(b'corrupt')
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_export_preserves_sanitized_observations_without_overwrite(self):
        import json
        from pathlib import Path
        plan = self.plan()
        observation = self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        exported = self.store.export_publication(plan['id'], write=True)
        path = Path(exported['handoff_path']).parent / 'observations' / (observation['id'] + '.json')
        self.assertEqual(json.loads(path.read_text())['id'], observation['id'])
        self.assertNotIn(str(self.root), path.read_text())
        before = path.read_bytes()
        self.store.export_publication(plan['id'], write=True)
        self.assertEqual(path.read_bytes(), before)

    def test_cli_imports_executor_observation_into_shared_status(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        plan = self.plan()
        observation = {'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': self.target,
            'artifact_id': plan['assets'][0]['artifact_id'], 'remote_id': 'media', 'gate': 'processing',
            'source': 'asc-cli', 'observed_at': datetime.now(timezone.utc).isoformat(),
            'evidence_reference': 'asc:receipt-123', 'facts': {'processing_state': 'COMPLETE'}}
        (self.root / 'receipt.json').write_text(json.dumps(observation))
        (self.root / 'creative.config.json').write_text(json.dumps(self.config))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'observe', '--repo', str(self.root),
            '--id', plan['id'], '--observation', 'receipt.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.store.publication_status(plan['id'])
        self.assertEqual(next(g for g in state['gates'] if g['gate'] == 'processing')['status'], 'PASS')
