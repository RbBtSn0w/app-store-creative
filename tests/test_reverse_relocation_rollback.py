"""Interrupted reverse switches can return to their active source."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_reverse_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class ReverseRollbackTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationSwitchTests.setUp
    source = fixtures.ReverseRelocationSwitchTests.source
    targets = fixtures.ReverseRelocationSwitchTests.targets
    prepared = fixtures.ReverseRelocationSwitchTests.prepared
    moved = fixtures.ReverseRelocationSwitchTests.moved
    reverse = fixtures.ReverseRelocationSwitchTests.reverse

    def interrupted(self):
        import delivery_lifecycle
        artifact, forward, moved, reverse, run = self.reverse()
        before = moved.config_path.read_bytes()
        original = delivery_lifecycle.apply_directory_change
        def interrupted(change):
            original(change)
            self.changed_root = dict(change)
            raise OSError('After root change')
        with patch('delivery_lifecycle.apply_directory_change', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'After root change'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        return artifact, forward, moved, reverse, run, before

    def test_rollback_restores_source_and_preserves_new_staging(self):
        artifact, forward, moved, reverse, run, before = self.interrupted()
        result = moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Keep active source')
        self.assertEqual(result['status'], 'ROLLED_BACK')
        self.assertEqual(moved.config_path.read_bytes(), before)
        moved.verify_artifact(artifact['id']); moved._run(run['id']); moved.start_run({})
        self.assertFalse(self.store._path('runs', run['id']).exists())
        self.assertTrue(all(Path(path).is_dir() for path in result['preserved_staging']))
        self.assertEqual(moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Repeat'), result)
        with self.assertRaisesRegex(ValueError, 'rollback'):
            moved.resume_reverse_relocation(reverse['id'], 'owner', 'Wrong direction')

    def test_activated_reverse_refuses_rollback(self):
        artifact, forward, moved, reverse, run = self.reverse()
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        before = moved.config_path.read_bytes()
        records_before = {str(path): path.read_bytes() for path in moved.paths.workspace.rglob('*.json')}
        with self.assertRaisesRegex(ValueError, 'Activated'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Undo')
        self.assertEqual(moved.config_path.read_bytes(), before)
        self.assertEqual({str(path): path.read_bytes() for path in moved.paths.workspace.rglob('*.json')}, records_before)
        Lifecycle(self.root, json.loads(before)).start_run({})

    def test_config_sync_failure_keeps_source_fenced_until_retry(self):
        artifact, forward, moved, reverse, run, before = self.interrupted()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Rollback sync failed')):
            for retry in range(2):
                with self.assertRaisesRegex(OSError, 'Rollback sync failed'):
                    moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
                with self.assertRaisesRegex(ValueError, 'fenced'):
                    moved.start_run({})
        moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Sync recovered')
        moved.start_run({})

    def test_shared_workspace_rollback_retires_pending_controls(self):
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        forward = self.store.plan_relocation({**self.cfg['storage'], 'objectRoot': 'moved objects'})
        self.store.prepare_relocation(forward['id'], 'owner', 'Move')
        self.store.switch_relocation(forward['id'], 'owner', 'Move')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        before = moved.config_path.read_bytes()
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Before activation')):
            with self.assertRaisesRegex(OSError, 'Before activation'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Keep moved objects')
        self.assertEqual(moved.config_path.read_bytes(), before)
        moved.start_run({}); moved.verify_artifact(artifact['id'])
        retired = moved._path('relocations', reverse['id'], 'rollback-intent').parent / 'retired-controls'
        self.assertEqual(len(list(retired.glob('*.json'))), 3)

    def test_revert_after_sync_interruption_can_continue_without_swapping_again(self):
        import delivery_lifecycle
        artifact, forward, moved, reverse, run, before = self.interrupted()
        original = delivery_lifecycle.revert_directory_change
        def interrupted(change):
            original(change)
            raise OSError('After undo interrupted')
        with patch('delivery_lifecycle.revert_directory_change', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'After undo interrupted'):
                moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Undo')
        moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Continue undo')
        moved.verify_artifact(artifact['id']); moved.start_run({})
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_cli_rollback_uses_explicit_original_active_workspace(self):
        import subprocess
        import sys
        artifact, forward, moved, reverse, run, before = self.interrupted()
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'storage', 'rollback-reverse-relocate',
            '--repo', str(self.root), '--id', reverse['id'], '--source-workspace', str(moved.paths.workspace),
            '--actor', 'owner', '--reason', 'Keep source', '--confirm', 'ROLLBACK'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ROLLED_BACK')
        moved.start_run({})

    def test_forward_rollback_cannot_skip_reverse_directory_restoration(self):
        artifact, forward, moved, reverse, run, before = self.interrupted()
        with self.assertRaisesRegex(ValueError, 'reverse'):
            moved.rollback_relocation(reverse['id'], 'owner', 'Wrong command')
        with self.assertRaisesRegex(ValueError, 'fenced'):
            moved.start_run({})

    def test_modified_preserved_backup_refuses_revert_without_deleting_it(self):
        artifact, forward, moved, reverse, run, before = self.interrupted()
        self.assertEqual(self.changed_root['operation'], 'EXCHANGE')
        backup = Path(self.changed_root['staging'])
        note = backup / 'keep-note'; note.write_text('Keep modified backup')
        with self.assertRaisesRegex(ValueError, 'backup'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Undo')
        self.assertEqual(note.read_text(), 'Keep modified backup')
        self.assertEqual(moved.config_path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'fenced'):
            moved.start_run({})

    def test_user_config_edit_refuses_rollback_before_directory_change(self):
        artifact, forward, moved, reverse, run, before = self.interrupted()
        edited = json.loads(before); edited['description'] = 'User edited configuration'
        moved.config_path.write_text(json.dumps(edited))
        current = moved.config_path.read_bytes()
        root_inode = self.store.paths.workspace.stat().st_ino
        with self.assertRaisesRegex(ValueError, 'edited'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Undo')
        self.assertEqual(moved.config_path.read_bytes(), current)
        self.assertEqual(self.store.paths.workspace.stat().st_ino, root_inode)

    def test_foreign_fence_scope_refused_before_directory_restoration(self):
        import hashlib
        from artifact_lifecycle import canonical
        artifact, forward, moved, reverse, run, before = self.interrupted()
        key = hashlib.sha256(canonical(reverse['from'])).hexdigest()
        fence_path = moved._path('storage-fences', key, reverse['id'])
        fence = json.loads(fence_path.read_text()); fence['project_id'] = 'foreign-project'
        fence_path.write_text(json.dumps(fence))
        proof_path = moved._path('relocations', reverse['id'], 'reverse-fence')
        proof = json.loads(proof_path.read_text())
        proof['fence_sha256'] = hashlib.sha256(canonical(fence)).hexdigest()
        proof_path.write_text(json.dumps(proof))
        root_inode = self.store.paths.workspace.stat().st_ino
        with self.assertRaisesRegex(ValueError, 'fence scope'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Undo')
        self.assertEqual(self.store.paths.workspace.stat().st_ino, root_inode)
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_new_reverse_after_rollback_can_return_to_same_original_roots(self):
        artifact, forward, moved, reverse, run, before = self.interrupted()
        moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Keep source')
        added_run = moved.start_run({})
        retry = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(retry['id'], 'owner', 'Retry return')
        moved.switch_reverse_relocation(retry['id'], 'owner', 'Retry return')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        returned.verify_artifact(artifact['id']); returned._run(added_run['id']); returned.start_run({})
        self.assertTrue(moved._path('relocations', reverse['id'], 'rollback').is_file())
