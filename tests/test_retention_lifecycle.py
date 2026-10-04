"""Retention protects live references and preserves recoverable object bytes."""
import unittest
import test_artifact_lifecycle as fixtures


class RetentionTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp
    def artifact(self, status='failed'):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'sample'; source.write_bytes(b'preserved bytes')
        data = self.store.register(attempt['id'], source, 'screenshot')
        if status:
            self.store.finish_attempt(attempt['id'], status, reason='Rejected example' if status != 'succeeded' else None)
        return run, data

    def test_quarantine_and_restore_preserve_metadata(self):
        _, data = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        self.assertEqual(len(plan['objects']), 1)
        result = self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discard failed trial')
        self.assertFalse(self.store.object_path(data['sha256']).exists())
        self.store.restore_cleanup(result['id'], actor='owner', reason='Recover trial')
        self.assertEqual(self.store.verify_artifact(data['id'])['sha256'], data['sha256'])
        self.assertTrue(self.store._path('artifacts', data['id']).exists())

    def test_active_and_selected_objects_are_protected(self):
        self.artifact(status=None)
        self.assertEqual(self.store.plan_cleanup(retention_days=0)['objects'], [])
        run, data = self.artifact(status='succeeded')
        self.store.select(run['id'], [data['id']])
        self.assertEqual(self.store.plan_cleanup(retention_days=0)['objects'], [])

    def test_stale_plan_cannot_remove_new_candidate(self):
        run, data = self.artifact(status='succeeded')
        plan = self.store.plan_cleanup(retention_days=0)
        self.store.select(run['id'], [data['id']])
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Cleanup')
        self.store.verify_artifact(data['id'])

    def test_corrupt_quarantine_fails_before_restore(self):
        _, data = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        op = self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discard trial')
        self.store._quarantine_path(op['id'], data['sha256']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.restore_cleanup(op['id'], actor='owner', reason='Recover')
        self.assertFalse(self.store.object_path(data['sha256']).exists())

    def test_unknown_files_are_preserved(self):
        self.artifact()
        unknown = self.store.paths.objects / 'user-owned.txt'
        unknown.write_text('keep')
        plan = self.store.plan_cleanup(retention_days=0)
        self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discard trial')
        self.assertEqual(unknown.read_text(), 'keep')

    def test_interrupted_quarantine_can_restore_unmoved_objects(self):
        _, data = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        with self.store.transaction():
            operation = self.store._record('maintenance', {'id': 'interrupted',
                'operation': 'quarantine', 'plan_id': plan['id'], 'objects': plan['objects']})
        self.store.restore_cleanup(operation['id'], actor='owner', reason='Recover interrupted maintenance')
        self.store.verify_artifact(data['id'])

    def test_discarded_candidate_can_expire_without_losing_reason(self):
        run, data = self.artifact(status='succeeded')
        candidate = self.store.select(run['id'], [data['id']])
        disposition = self.store.discard_candidate(candidate['id'], actor='owner', reason='Wrong narrative')
        self.assertEqual(len(self.store.plan_cleanup(retention_days=0)['objects']), 1)
        self.assertEqual(disposition['reason'], 'Wrong narrative')
        with self.assertRaisesRegex(ValueError, 'discarded'):
            self.store.validate_candidate(candidate['id'])

    def test_approval_keeps_discarded_candidate_protected(self):
        run, data = self.artifact(status='succeeded')
        candidate = self.store.select(run['id'], [data['id']])
        with self.store.transaction():
            self.store._record('approvals', {'id': 'approval', 'stage': 'design', 'candidate_id': candidate['id']})
        self.store.discard_candidate(candidate['id'], actor='owner', reason='Prefer another layout')
        self.assertEqual(self.store.plan_cleanup(retention_days=0)['objects'], [])

    def test_discard_requires_reason_and_cannot_rewrite_history(self):
        run, data = self.artifact(status='succeeded')
        candidate = self.store.select(run['id'], [data['id']])
        with self.assertRaises(ValueError):
            self.store.discard_candidate(candidate['id'], actor='owner', reason='')
        self.store.discard_candidate(candidate['id'], actor='owner', reason='Wrong locale')
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            self.store.discard_candidate(candidate['id'], actor='owner', reason='Changed reason')

    def test_default_retention_keeps_recent_discarded_media(self):
        run, data = self.artifact(status='succeeded')
        candidate = self.store.select(run['id'], [data['id']])
        self.store.discard_candidate(candidate['id'], actor='owner', reason='Wrong layout')
        self.assertEqual(self.store.plan_cleanup()['objects'], [])

    def test_shared_bytes_survive_when_another_candidate_is_retained(self):
        run, data = self.artifact(status='succeeded')
        first = self.store.select(run['id'], [data['id']])
        self.store.select(run['id'], [data['id']])
        self.store.discard_candidate(first['id'], actor='owner', reason='Replaced')
        self.assertEqual(self.store.plan_cleanup(retention_days=0)['objects'], [])

    def test_cli_discard_uses_shared_core_and_preserves_reason(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        run, data = self.artifact(status='succeeded')
        candidate = self.store.select(run['id'], [data['id']])
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        process = subprocess.run([sys.executable, str(cli), 'candidate', 'discard',
            '--repo', str(self.root), '--id', candidate['id'], '--actor', 'owner',
            '--reason', 'Incorrect locale', '--confirm', 'DISCARD'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)['reason'], 'Incorrect locale')

    def quarantined(self):
        _, data = self.artifact()
        plan = self.store.plan_cleanup(retention_days=0)
        return data, self.store.quarantine_cleanup(plan['id'], actor='owner', reason='Discard trial')

    def test_purge_requires_expired_quarantine(self):
        _, operation = self.quarantined()
        with self.assertRaisesRegex(ValueError, 'retention'):
            self.store.plan_purge(operation['id'])

    def test_purge_preserves_records_and_unknown_quarantine_files(self):
        data, operation = self.quarantined()
        unknown = self.store._quarantine_path(operation['id'], data['sha256']).parent / 'notes.txt'
        unknown.write_text('keep')
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        result = self.store.purge_cleanup(plan['id'], actor='owner', reason='Retention expired')
        self.assertEqual(result['status'], 'purged')
        self.assertFalse(self.store._quarantine_path(operation['id'], data['sha256']).exists())
        self.assertTrue(self.store._path('artifacts', data['id']).exists())
        self.assertEqual(unknown.read_text(), 'keep')
        with self.assertRaisesRegex(ValueError, 'purge'):
            self.store.restore_cleanup(operation['id'], actor='owner', reason='Too late')
        self.assertEqual(self.store.purge_cleanup(plan['id'], actor='owner', reason='Retry'), result)

    def test_new_reference_invalidates_purge_plan(self):
        _, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.artifact(status=None)
        with self.assertRaisesRegex(ValueError, 'stale|protected'):
            self.store.purge_cleanup(plan['id'], actor='owner', reason='Retention expired')

    def test_restored_quarantine_cannot_be_purged(self):
        _, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.store.restore_cleanup(operation['id'], actor='owner', reason='Recover')
        with self.assertRaisesRegex(ValueError, 'restored'):
            self.store.purge_cleanup(plan['id'], actor='owner', reason='Retention expired')

    def test_corrupt_quarantine_blocks_purge(self):
        data, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.store._quarantine_path(operation['id'], data['sha256']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.purge_cleanup(plan['id'], actor='owner', reason='Retention expired')

    def test_interrupted_purge_retries_original_journal(self):
        from pathlib import Path
        from unittest.mock import patch
        run, _ = self.artifact()
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'second'; source.write_bytes(b'different bytes')
        self.store.register(attempt['id'], source, 'screenshot')
        self.store.finish_attempt(attempt['id'], 'failed', reason='Rejected')
        cleanup = self.store.plan_cleanup(retention_days=0)
        operation = self.store.quarantine_cleanup(cleanup['id'], actor='owner', reason='Discard')
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        original = Path.unlink
        last = self.store._quarantine_path(operation['id'], plan['objects'][-1]['sha256'])
        def interrupted(path, *args, **kwargs):
            if path == last:
                raise OSError('Simulated interrupted purge')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.store.purge_cleanup(plan['id'], actor='owner', reason='Expired')
        self.assertFalse(self.store._quarantine_path(operation['id'], plan['objects'][0]['sha256']).exists())
        self.assertEqual(self.store.purge_cleanup(plan['id'], actor='owner', reason='Retry')['status'], 'purged')

    def test_cli_purge_requires_explicit_confirmation(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        _, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = [sys.executable, str(cli), 'cleanup', 'purge', '--repo', str(self.root),
                   '--id', plan['id'], '--actor', 'owner', '--reason', 'Expired']
        unconfirmed = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(unconfirmed.returncode, 0)
        confirmed = subprocess.run(command + ['--confirm', 'PURGE'], capture_output=True, text=True)
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        self.assertEqual(json.loads(confirmed.stdout)['status'], 'purged')
