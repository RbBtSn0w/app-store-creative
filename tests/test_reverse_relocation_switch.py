"""Reverse switching returns active data to occupied original roots."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_reverse_relocation_plan as fixtures
from artifact_lifecycle import Lifecycle


class ReverseRelocationSwitchTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationPlanTests.setUp
    source = fixtures.ReverseRelocationPlanTests.source
    targets = fixtures.ReverseRelocationPlanTests.targets
    prepared = fixtures.ReverseRelocationPlanTests.prepared
    moved = fixtures.ReverseRelocationPlanTests.moved

    def reverse(self):
        artifact, forward, moved = self.moved()
        run = moved.start_run({})
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        return artifact, forward, moved, reverse, run

    def test_reverse_copied_object_inspection_includes_new_media_and_is_read_only(self):
        artifact, forward, moved = self.moved()
        run = moved.start_run({}); attempt = moved.start_attempt(run['id'], 'capture', 'fixture-owner')
        source = moved.work_path(attempt['id']) / 'new-source'; source.write_bytes(b'New reverse fixture media')
        added = moved.register(attempt['id'], source, 'source')
        moved.finish_attempt(attempt['id'], 'failed', reason='Retain disposable fixture')
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'fixture-owner', 'Return fixture')
        moved.switch_reverse_relocation(reverse['id'], 'fixture-owner', 'Return fixture')
        returned = Lifecycle.from_configuration(self.root, moved.config_path)
        returned.start_run({})
        before = {str(path): path.read_bytes() for path in returned.paths.workspace.rglob('*.json')}
        result = returned.relocated_object_status(reverse['id'])
        self.assertEqual(result['status'], 'PASS', result)
        self.assertEqual(result['checked_files'], len([item for item in reverse['files'] if item['root'] == 'objects']))
        returned.verify_artifact(artifact['id']); returned.verify_artifact(added['id'])
        returned.object_path(added['sha256']).write_bytes(b'Changed returned object')
        failed = returned.relocated_object_status(reverse['id'])
        self.assertEqual(failed['status'], 'FAIL')
        self.assertFalse(failed['object_integrity_verified'])
        self.assertEqual(before, {str(path): path.read_bytes() for path in returned.paths.workspace.rglob('*.json')})

    def test_switch_keeps_new_records_and_preserved_original_backup(self):
        artifact, forward, moved, reverse, run = self.reverse()
        result = moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return to original')
        self.assertEqual(result['status'], 'SWITCHED')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        self.assertEqual(returned.paths.binding(), forward['from'])
        returned.verify_artifact(artifact['id'])
        returned._run(run['id'])
        returned.start_run({})
        self.assertTrue(result['preserved_backups'])
        self.assertTrue(all(Path(path).is_dir() for path in result['preserved_backups']))
        with self.assertRaisesRegex(ValueError, 'fenced'):
            moved.start_run({})

    def test_completed_exchange_sync_failure_resumes_without_swapping_back(self):
        artifact, forward, moved, reverse, run = self.reverse()
        import delivery_lifecycle
        original = delivery_lifecycle.apply_directory_change
        triggered = []
        def interrupted(change):
            result = original(change)
            if not triggered:
                triggered.append(True)
                raise OSError('After exchange interrupted')
            return result
        with patch('delivery_lifecycle.apply_directory_change', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'After exchange interrupted'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        with self.assertRaisesRegex(ValueError, 'fenced'):
            moved.start_run({})
        self.assertEqual(moved.relocation_status(reverse['id'])['status'], 'SWITCH_INTERRUPTED')
        moved.resume_reverse_relocation(reverse['id'], 'owner', 'Resume return')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned._run(run['id']); returned.verify_artifact(artifact['id']); returned.start_run({})

    def test_changed_preserved_copy_refuses_switch_before_config_change(self):
        artifact, forward, moved, reverse, run = self.reverse()
        before = moved.config_path.read_bytes()
        (self.store.paths.workspace / 'unknown-file').write_text('Keep this')
        with self.assertRaisesRegex(ValueError, 'preserved source'):
            moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        self.assertEqual(moved.config_path.read_bytes(), before)
        moved.start_run({})

    def test_object_only_return_keeps_shared_workspace_and_new_object(self):
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        forward = self.store.plan_relocation({**self.cfg['storage'], 'objectRoot': 'moved objects'})
        self.store.prepare_relocation(forward['id'], 'owner', 'Move')
        self.store.switch_relocation(forward['id'], 'owner', 'Move')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        run = moved.start_run({}); attempt = moved.start_attempt(run['id'], 'render', 'owner')
        path = moved.work_path(attempt['id']) / 'added'; path.write_bytes(b'New material')
        added = moved.register(attempt['id'], path, 'source')
        moved.finish_attempt(attempt['id'], 'succeeded')
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned.verify_artifact(added['id']); returned.start_run({})
        self.assertEqual(returned.paths.workspace, moved.paths.workspace)
        self.assertEqual(moved.resume_reverse_relocation(reverse['id'], 'owner', 'Already returned')['status'], 'SWITCHED')

    def test_interruption_before_fence_receipt_can_resume(self):
        artifact, forward, moved, reverse, run = self.reverse()
        original = moved._record
        def record(category, data, suffix=None):
            if suffix == 'reverse-fence':
                raise OSError('Fence receipt interrupted')
            return original(category, data, suffix)
        with patch.object(moved, '_record', side_effect=record):
            with self.assertRaisesRegex(OSError, 'Fence receipt interrupted'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.resume_reverse_relocation(reverse['id'], 'owner', 'Resume')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned._run(run['id']); returned.start_run({})

    def test_completed_recovery_is_read_only_after_new_target_run(self):
        artifact, forward, moved, reverse, run = self.reverse()
        receipt = moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned.start_run({})
        before = {str(path): path.read_bytes() for path in returned.paths.workspace.rglob('*.json')}
        self.assertEqual(moved.resume_reverse_relocation(reverse['id'], 'owner', 'Already done'), receipt)
        self.assertEqual({str(path): path.read_bytes() for path in returned.paths.workspace.rglob('*.json')}, before)

    def test_cli_switch_and_explicit_source_recovery(self):
        import subprocess
        import sys
        artifact, forward, moved, reverse, run = self.reverse()
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        base = [sys.executable, str(script), 'storage']
        switched = subprocess.run(base + ['switch-reverse-relocate', '--repo', str(self.root),
            '--id', reverse['id'], '--actor', 'owner', '--reason', 'Return', '--confirm', 'SWITCH'],
            capture_output=True, text=True)
        self.assertEqual(switched.returncode, 0, switched.stderr)
        recovered = subprocess.run(base + ['resume-reverse-relocate', '--repo', str(self.root),
            '--id', reverse['id'], '--source-workspace', str(moved.paths.workspace),
            '--actor', 'owner', '--reason', 'Verify done', '--confirm', 'RESUME'], capture_output=True, text=True)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(json.loads(recovered.stdout), json.loads(switched.stdout))

    def test_configuration_sync_failure_keeps_target_inactive_until_retry(self):
        artifact, forward, moved, reverse, run = self.reverse()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Config sync failed')):
            with self.assertRaisesRegex(OSError, 'Config sync failed'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
            returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
            with self.assertRaisesRegex(ValueError, 'pending|inactive'):
                returned.start_run({})
            with self.assertRaisesRegex(OSError, 'Config sync failed'):
                moved.resume_reverse_relocation(reverse['id'], 'owner', 'Retry sync')
        moved.resume_reverse_relocation(reverse['id'], 'owner', 'Sync recovered')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned._run(run['id']); returned.verify_artifact(artifact['id']); returned.start_run({})

    def test_intent_sync_interruption_before_fencing_can_resume(self):
        import reverse_relocation
        artifact, forward, moved, reverse, run = self.reverse()
        original_sync = reverse_relocation._sync
        def sync(path):
            if path == moved._path('relocations', reverse['id'], 'switch-intent').parent:
                raise OSError('Intent sync interrupted')
            return original_sync(path)
        with patch('reverse_relocation._sync', side_effect=sync):
            with self.assertRaisesRegex(OSError, 'Intent sync interrupted'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.resume_reverse_relocation(reverse['id'], 'owner', 'Recover intent')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned._run(run['id']); returned.start_run({})

    def test_tampered_target_configuration_refused_before_directory_changes(self):
        artifact, forward, moved, reverse, run = self.reverse()
        with patch('reverse_relocation._execute', side_effect=OSError('Before exchange')):
            with self.assertRaisesRegex(OSError, 'Before exchange'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        intent_path = moved._path('relocations', reverse['id'], 'switch-intent')
        intent = json.loads(intent_path.read_text())
        unknown = self.root / 'unapproved target'
        intent['target_config']['storage']['workspaceRoot'] = str(unknown)
        intent_path.write_text(json.dumps(intent))
        before = moved.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'target configuration'):
            moved.resume_reverse_relocation(reverse['id'], 'owner', 'Recover')
        self.assertFalse(unknown.exists())
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_completed_reverse_resume_refuses_changed_target_binding(self):
        import hashlib
        from artifact_lifecycle import canonical
        _, _, moved, reverse, _ = self.reverse()
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        key = hashlib.sha256(canonical(reverse['from'])).hexdigest()
        path = Path(reverse['to']['workspace']) / 'records/storage-bindings' / (key + '.json')
        changed = json.loads(path.read_text()); changed['switch_sha256'] = '0' * 64
        path.write_text(json.dumps(changed)); before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'control|activation'):
            moved.resume_reverse_relocation(reverse['id'], 'owner', 'Recheck completed return')
        self.assertEqual(path.read_bytes(), before)
        import subprocess
        import sys
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'storage', 'resume-reverse-relocate',
            '--repo', str(self.root), '--source-workspace', str(moved.paths.workspace),
            '--id', reverse['id'], '--actor', 'owner', '--reason', 'Recheck completed return',
            '--confirm', 'RESUME'], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('activation verification failed', result.stderr)
        self.assertEqual(path.read_bytes(), before)
