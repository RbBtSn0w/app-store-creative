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

    def test_completed_purge_rejects_reappeared_files_without_deleting_them(self):
        data, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.store.purge_cleanup(plan['id'], actor='owner', reason='Disposable fixture')
        path = self.store._quarantine_path(operation['id'], data['sha256'])
        path.write_bytes(b'Preserve new owner data')
        with self.assertRaisesRegex(ValueError, 'reappeared'):
            self.store.purge_cleanup(plan['id'], actor='owner', reason='Recheck')
        self.assertEqual(path.read_bytes(), b'Preserve new owner data')

    def test_completed_purge_rejects_changed_receipt_plan_and_intent(self):
        import json
        _, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        result = self.store.purge_cleanup(plan['id'], actor='owner', reason='Disposable fixture')
        changes = [
            (self.store._path('maintenance', operation['id'], 'purged'), 'bytes_removed', result['bytes_removed'] + 1),
            (self.store._path('maintenance', operation['id'], 'purged'), 'status', 'quarantined'),
            (self.store._path('maintenance', plan['id']), 'quarantine_days', 1),
            (self.store._path('maintenance', operation['id'], 'purge-intent'), 'reason', 'Changed intent'),
        ]
        for path, key, value in changes:
            with self.subTest(record=path.name, field=key):
                before = path.read_bytes()
                data = json.loads(before); data[key] = value
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, 'binding differs'):
                    self.store.purge_cleanup(plan['id'], actor='owner', reason='Recheck')
                self.assertEqual(json.loads(path.read_text())[key], value)
                path.write_bytes(before)
        self.assertEqual(self.store.purge_cleanup(plan['id'], actor='owner', reason='Recheck'), result)

    def test_missing_object_without_file_checkpoint_cannot_complete_purge(self):
        from unittest.mock import patch
        data, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        original = self.store._record
        def interrupted(category, body, suffix=None):
            result = original(category, body, suffix)
            if suffix == 'purge-intent':
                raise OSError('Intent persisted before file checkpoint')
            return result
        with patch.object(self.store, '_record', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.store.purge_cleanup(plan['id'], 'owner', 'Disposable fixture')
        self.store._quarantine_path(operation['id'], data['sha256']).unlink()
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            self.store.purge_cleanup(plan['id'], 'owner', 'Recheck missing object')
        self.assertFalse(self.store._path('maintenance', operation['id'], 'purged').exists())

    def test_same_byte_replacement_after_checkpoint_is_preserved(self):
        from unittest.mock import patch
        data, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        original = self.store._record
        def interrupted(category, body, suffix=None):
            result = original(category, body, suffix)
            if suffix == 'purge-file-0':
                raise OSError('Checkpoint persisted before unlink')
            return result
        with patch.object(self.store, '_record', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.store.purge_cleanup(plan['id'], 'owner', 'Disposable fixture')
        path = self.store._quarantine_path(operation['id'], data['sha256'])
        substitute = path.with_name('replacement'); substitute.write_bytes(path.read_bytes()); substitute.replace(path)
        inode = path.stat().st_ino
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            self.store.purge_cleanup(plan['id'], 'owner', 'Preserve replaced object')
        self.assertEqual(path.stat().st_ino, inode)
        self.assertFalse(self.store._path('maintenance', operation['id'], 'purged').exists())

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
